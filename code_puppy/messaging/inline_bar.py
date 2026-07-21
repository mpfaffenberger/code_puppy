"""Inline prompt surface for terminals that mishandle DECSTBM.

Unlike :class:`bottom_bar.BottomBar`, this surface never establishes scroll
margins or paints at absolute screen rows.  It keeps the live UI at the normal
terminal cursor, erases it before transcript output, then redraws it below the
new output.  The public API intentionally matches ``BottomBar`` so the editor
and status/panel plugins do not need terminal-specific branches.

Coordination contract
---------------------

With no scroll region there is nothing confining transcript output: EVERY
write to the terminal must coordinate with the painted bar or the block's
cursor-relative bookkeeping desyncs and stale bar copies strand in
scrollback (the JediTerm corruption bug).  Renderer messages already
coordinate via :meth:`output_transaction`, but streaming output (termflow
markdown, the smooth typewriter writers, ``\\r`` token counters) writes
straight to stdout.  So while active this surface wraps ``sys.stdout`` /
``sys.stderr`` in :class:`~.transcript_guard.StreamGuard` proxies:

* a foreign write first ERASES the painted bar (cursor-relative, still in
  sync because nothing else touched the terminal), then passes through;
* newline-complete writes repaint immediately; unfinished lines wait for
  a short quiescence window (``_REPAINT_QUIET_S``) before the bar moves
  below the partial line and repaints;
* bar-state updates (`set_status`, spinner ticks, panel lines) while the
  bar is hidden only update the cache -- painting mid-stream at an
  arbitrary cursor position is exactly the corruption we're avoiding;
* cursor-hide is reasserted after foreign writes because JediTerm does
  not reliably preserve the one-time DECTCEM state set at startup.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional, TextIO

from .bar_rendering import (
    CLEAR_LINE,
    CURSOR_HIDE,
    CURSOR_SHOW,
    WRAP_OFF,
    WRAP_ON,
    clip_cells,
    render_prompt_block,
    sanitize,
)
from .bottom_bar import POPUP_MAX_ROWS, BottomBar
from .transcript_guard import StreamGuard

#: Quiet time (no foreign writes) before the hidden bar repaints.
_REPAINT_QUIET_S = 0.2

#: Escape sequences that occupy no cells -- ignored when deciding whether
#: the transcript cursor rests at column 1 (CSI, OSC, other ESC-prefixed).
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?<=> ]*[@-~]"  # CSI (SGR, cursor moves, ...)
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC (hyperlinks, titles)
    r"|\x1b[@-Z\\-_]"  # other C1-style ESC sequences
)


class InlineBottomBar(BottomBar):
    """A DECSTBM-free prompt surface for embedded terminal emulators."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._displayed_rows = 0
        self._output_depth = 0
        # Foreign-write coordination (see module docstring).
        self._foreign_guards: list = []
        self._at_line_start = True
        self._last_foreign_write = 0.0
        self._repaint_timer: Optional[threading.Timer] = None

    def start(self) -> None:
        if not self._is_tty():
            return
        with self._lock:
            if self._active:
                return
            self._active = True
            self._cols, self._rows = self._safe_size()
            self._write(CURSOR_HIDE)
            self._paint_inline()
        self._install_foreign_write_guard()
        self._install_sigwinch()
        self._register_atexit()

    def stop(self) -> None:
        with self._lock:
            self._cancel_repaint_timer()
            if not self._active:
                return
            self._erase_inline()
            self._write(CURSOR_SHOW)
            self._active = False
            self._displayed_rows = 0
        self._uninstall_foreign_write_guard()

    def _sync_reserved(self, _painter) -> None:
        """Repaint cached state without creating a terminal scroll region."""
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return
        if not self._displayed_rows:
            # Hidden: transcript output owns the cursor. Painting HERE
            # would land mid-stream at an arbitrary position -- the
            # JediTerm corruption bug. Cache only; the quiescence timer
            # repaints once output settles.
            self._schedule_repaint(_REPAINT_QUIET_S)
            return
        self._ensure_inline_geometry()
        self._erase_inline()
        self._paint_inline()

    def notify_transcript_output(self) -> None:
        """Retain popup-slack semantics; erasing is owned by the transaction."""
        with self._lock:
            if self._popup_slack:
                self._popup_slack -= 1

    @contextmanager
    def output_transaction(self) -> Iterator[None]:
        """Atomically remove the live UI, allow output, then redraw it."""
        with self._lock:
            outermost = self._output_depth == 0
            self._output_depth += 1
            if outermost and self._active and self._suspend_depth == 0:
                self.notify_transcript_output()
                self._erase_inline()
            try:
                yield
            finally:
                self._output_depth -= 1
                if outermost and self._active and self._suspend_depth == 0:
                    self._ensure_inline_geometry()
                    self._commit_partial_line()
                    self._paint_inline()

    @contextmanager
    def suspended(self) -> Iterator[None]:
        if not self._is_tty():
            yield
            return
        with self._lock:
            self._suspend_depth += 1
            if self._suspend_depth == 1 and self._active:
                self._erase_inline()
                # Full-screen TUIs and interactive shells need a real cursor.
                self._write(CURSOR_SHOW)
        try:
            yield
        finally:
            with self._lock:
                self._suspend_depth -= 1
                if self._suspend_depth == 0 and self._active:
                    self._write(CURSOR_HIDE)
                    self._commit_partial_line()
                    self._paint_inline()

    def set_panel_lines(self, lines) -> None:
        from rich.text import Text

        cleaned = [
            line.copy() if isinstance(line, Text) else sanitize(str(line))
            for line in (lines or [])
        ]
        with self._lock:
            self._panel_lines = cleaned
            self._sync_reserved(None)

    def set_popup_lines(self, lines, selected: int = -1) -> None:
        cleaned = [sanitize(str(line)) for line in (lines or [])][:POPUP_MAX_ROWS]
        with self._lock:
            self._popup_lines = cleaned
            self._popup_selected = selected
            self._popup_slack = 0
            self._sync_reserved(None)

    def _ensure_inline_geometry(self) -> None:
        cols, rows = self._safe_size()
        self._cols, self._rows = cols, rows

    def _inline_lines(self) -> list[str]:
        # Clip every row to one cell LESS than the terminal width.  The
        # pinned bar can trust DECAWM-off to stop overlong rows from
        # wrapping, but the whole reason this surface exists is that
        # JediTerm fumbles exactly this kind of VT state (double-width
        # emoji at the margin still wrap).  A wrapped row makes the block
        # one row taller than ``_displayed_rows`` believes, the cursor-up
        # count goes off by one, and every 5fps spinner tick strands a
        # stale copy in scrollback -- the keystroke bug reborn as a
        # spinner bug.  Hard-clipping is the only defence JediTerm can't
        # sabotage.
        max_cells = max(1, self._cols - 1)
        lines: list[str] = []
        # Height-relative clamp (shared with the DECSTBM path via
        # BarPainterMixin): the block must never exceed the viewport, or
        # the cursor-up repaint count in ``_paint_inline`` goes off and
        # strands stale copies in scrollback every spinner tick.
        panel = self._visible_panel_lines()
        for line in panel:
            plain = sanitize(line.plain if hasattr(line, "plain") else str(line))
            lines.append(clip_cells(plain, max_cells))

        prompt_rows, _ = render_prompt_block(
            self._prompt_prefix,
            self._prompt_buffer,
            self._prompt_cursor,
            max_cells,
            5,
            prefix_sgrs=self._prompt_prefix_sgrs,
        )
        lines.extend(prompt_rows)

        for index, line in enumerate(self._popup_lines):
            marker = "› " if index == self._popup_selected else "  "
            lines.append(clip_cells(f"{marker}{line}", max_cells))

        status = f"{self._status_prefix}{self._status}{self._status_suffix}"
        if status:
            lines.append(clip_cells(sanitize(status), max_cells))
        return lines or [""]

    def _paint_inline(self) -> None:
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return
        lines = self._inline_lines()
        parts = [WRAP_OFF]
        for index, line in enumerate(lines):
            if index:
                parts.append("\r\n")
            parts.append(f"{CLEAR_LINE}{line}")
        if len(lines) > 1:
            parts.append(f"\x1b[{len(lines) - 1}A")
        parts.extend(["\r", WRAP_ON])
        self._write("".join(parts))
        self._displayed_rows = len(lines)

    def _erase_inline(self) -> None:
        if not self._displayed_rows:
            return
        parts = [WRAP_OFF, "\r"]
        for index in range(self._displayed_rows):
            if index:
                parts.append("\x1b[1B\r")
            parts.append(CLEAR_LINE)
        if self._displayed_rows > 1:
            parts.append(f"\x1b[{self._displayed_rows - 1}A")
        parts.extend(["\r", WRAP_ON])
        self._write("".join(parts))
        self._displayed_rows = 0

    # =========================================================================
    # Foreign-write coordination (streaming output, prints, logging)
    # =========================================================================

    def guarded_write(self, text: str, target: Optional[TextIO] = None) -> int:
        """Route one transcript write around the painted bar.

        Called by the :class:`StreamGuard` proxies wrapping stdout and
        stderr. Erases the bar first (cursor-relative bookkeeping stays
        in sync because the bar's own paints are the only other writer
        under this lock), passes the text through, then arms the
        quiescence repaint.
        """
        length = len(text)
        if not text:
            return length
        with self._lock:
            stream = target if target is not None else self._resolve_stream()
            if stream is None:
                return length
            if self._displayed_rows:
                self._erase_inline()
            try:
                stream.write(text)
                # Keep terminal ordering deterministic: bar paints go to
                # ``sys.__stdout__`` with an immediate flush, so foreign
                # text must never linger in this stream's buffer.
                stream.flush()
            except Exception:
                pass
            self._track_line_state(text)
            self._last_foreign_write = time.monotonic()
            if self._active and self._suspend_depth == 0:
                # JediTerm occasionally forgets DECTCEM across unrelated
                # output. Reassert it so the real cursor never blinks at
                # the transcript position; the prompt paints a pseudo-cursor.
                self._write(CURSOR_HIDE)
                if self._output_depth == 0 and self._at_line_start:
                    # Safe boundary: CLEAR_LINE cannot destroy transcript
                    # content here, so keep the prompt continuously visible
                    # instead of waiting out the debounce after every line.
                    self._cancel_repaint_timer()
                    self._ensure_inline_geometry()
                    self._paint_inline()
                else:
                    self._schedule_repaint(_REPAINT_QUIET_S)
        return length

    def _track_line_state(self, text: str) -> None:
        """Track whether the transcript cursor rests at column 1."""
        stripped = _ANSI_RE.sub("", text)
        if stripped:
            self._at_line_start = stripped.endswith(("\n", "\r"))

    def _commit_partial_line(self) -> None:
        """Move below an unfinished transcript line before painting.

        Painting starts with ``CLEAR_LINE`` on the current row -- doing
        that on a half-written streaming line would destroy it.
        """
        if not self._at_line_start:
            self._write("\r\n")
            self._at_line_start = True

    def _schedule_repaint(self, delay: float) -> None:
        """Arm (once) the debounced repaint timer. Caller holds the lock."""
        if self._repaint_timer is not None:
            return
        timer = threading.Timer(delay, self._repaint_after_quiet)
        timer.daemon = True
        self._repaint_timer = timer
        timer.start()

    def _cancel_repaint_timer(self) -> None:
        """Drop any pending repaint timer. Caller holds the lock."""
        if self._repaint_timer is not None:
            self._repaint_timer.cancel()
            self._repaint_timer = None

    def _repaint_after_quiet(self) -> None:
        """Timer body: repaint the hidden bar once output has settled."""
        try:
            with self._lock:
                self._repaint_timer = None
                if (
                    not self._active
                    or self._suspend_depth > 0
                    or self._output_depth > 0
                ):
                    return  # the lifecycle exit paths repaint themselves
                if self._displayed_rows:
                    return  # already visible
                remaining = _REPAINT_QUIET_S - (
                    time.monotonic() - self._last_foreign_write
                )
                if remaining > 0.01:
                    self._schedule_repaint(remaining)
                    return
                self._ensure_inline_geometry()
                self._commit_partial_line()
                self._paint_inline()
        except Exception:
            pass  # a repaint hiccup must never kill the timer thread

    def _install_foreign_write_guard(self) -> None:
        """Wrap ``sys.stdout``/``sys.stderr`` so ALL writes coordinate.

        Never installs for constructor-injected streams (tests) or
        redirected std streams -- mirrors the Windows transcript guard's
        install rules.
        """
        if self._stream is not None or self._foreign_guards:
            return
        for name in ("stdout", "stderr"):
            current = getattr(sys, name, None)
            if current is None or isinstance(current, StreamGuard):
                continue
            try:
                if not current.isatty():
                    continue
            except Exception:
                continue
            guard = StreamGuard(self, current)
            setattr(sys, name, guard)
            self._foreign_guards.append((name, guard, current))

    def _uninstall_foreign_write_guard(self) -> None:
        """Restore the original std streams (only if still ours)."""
        for name, guard, original in self._foreign_guards:
            if getattr(sys, name, None) is guard:
                setattr(sys, name, original)
        self._foreign_guards.clear()

    def _emergency_restore(self) -> None:
        try:
            with self._lock:
                self._cancel_repaint_timer()
                if self._active:
                    self._erase_inline()
                self._write(CURSOR_SHOW)
                self._active = False
            self._uninstall_foreign_write_guard()
        except Exception:
            pass
