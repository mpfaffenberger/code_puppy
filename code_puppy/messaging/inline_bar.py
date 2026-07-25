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
* newline-complete writes repaint immediately; unfinished lines repaint
  BELOW the partial line, hopping the cursor back into it with relative
  moves (see "streaming visibility" below) -- so the prompt stays
  visible while a paragraph streams. When the partial line's rendered
  width can't be trusted (tabs, cursor-moving escapes, wrap-margin
  ambiguity) this falls back to hiding the bar until a short quiescence
  window (``_REPAINT_QUIET_S``) elapses;
* bar-state updates (`set_status`, spinner ticks, panel lines) while the
  bar is hidden only update the cache -- painting mid-stream at an
  arbitrary cursor position is exactly the corruption we're avoiding;
* cursor-hide is reasserted after foreign writes because JediTerm does
  not reliably preserve the one-time DECTCEM state set at startup.

Streaming visibility
--------------------

Mid-line repaints work because only RELATIVE cursor motion is used: the
bar paints one row below the partial line, then the cursor hops back via
``up 1, CR, right N`` where ``N`` is the tracked cell width of the
partial line (modulo terminal width for wrapped lines -- see
:mod:`.inline_partial`). Painting may scroll the screen, but the partial
line scrolls with everything else, so the relative hop stays correct.
Erasing a below-partial bar never scrolls, so it can use DECSC/DECRC to
give the cursor back exactly. SGR state is tracked and replayed after
the hop so styled runs don't lose their colors mid-line. Anything the
width tracker can't model fails closed to the hidden+debounce path --
never to corruption.
"""

from __future__ import annotations

import sys
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional, TextIO

from .bar_rendering import (
    CLEAR_LINE,
    CURSOR_HIDE,
    CURSOR_SHOW,
    RESTORE_CURSOR,
    SAVE_CURSOR,
    SYNC_OFF,
    SYNC_ON,
    WRAP_OFF,
    WRAP_ON,
    clip_cells,
    render_prompt_block,
    sanitize,
)
from .bottom_bar import POPUP_MAX_ROWS, BottomBar
from .inline_partial import ANSI_RE as _ANSI_RE
from .inline_partial import PartialLineTracker
from .transcript_guard import StreamGuard

#: Quiet time (no foreign writes) before the hidden bar repaints.
_REPAINT_QUIET_S = 0.2


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
        # DEC 2026 bracket depth: erase→repaint cycles are wrapped in
        # synchronized-output markers so the terminal applies them as one
        # frame instead of rendering the "bar missing" in-between state
        # (the flicker). Refcounted — nested cycles (a guarded write
        # inside an output transaction) must not end the outer bracket.
        self._sync_depth = 0
        # Streaming-visibility state (see module docstring): the bar is
        # painted below an uncommitted partial line, with the cursor
        # restored INTO that line (one row above the bar top).
        self._bar_below_partial = False
        self._partial = PartialLineTracker()

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
            # Unconditional ESU: a stray open bracket must never outlive
            # the surface (auto-timeout would save us, but be explicit).
            self._write(CURSOR_SHOW + SYNC_OFF)
            self._sync_depth = 0
            self._active = False
            self._displayed_rows = 0
        self._uninstall_foreign_write_guard()

    def _begin_sync(self) -> None:
        """Open the DEC 2026 bracket (outermost only). Caller holds the lock."""
        self._sync_depth += 1
        if self._sync_depth == 1:
            self._write(SYNC_ON)

    def _end_sync(self) -> None:
        """Close the DEC 2026 bracket (outermost only). Caller holds the lock."""
        self._sync_depth = max(0, self._sync_depth - 1)
        if self._sync_depth == 0:
            self._write(SYNC_OFF)

    @contextmanager
    def _synchronized(self) -> Iterator[None]:
        """One atomic frame: erase + repaint render together, no flicker."""
        with self._lock:
            self._begin_sync()
        try:
            yield
        finally:
            with self._lock:
                self._end_sync()

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
        with self._synchronized():  # spinner ticks: erase+paint = one frame
            self._ensure_inline_geometry()
            below = self._bar_below_partial
            erase = self._erase_seq()
            if below:
                # The cursor was restored INTO the partial line — painting
                # here would CLEAR_LINE right through it. Re-paint below
                # (or fall back to hidden+debounce if the hop went stale).
                repaint = self._paint_below_seq()
                if repaint is None:
                    self._write(erase)
                    self._schedule_repaint(_REPAINT_QUIET_S)
                else:
                    self._write(erase + repaint)  # ONE write: no gap
            else:
                self._write(erase + self._paint_seq())  # ONE write: no gap

    def notify_transcript_output(self) -> None:
        """Retain popup-slack semantics; erasing is owned by the transaction."""
        with self._lock:
            if self._popup_slack:
                self._popup_slack -= 1

    @contextmanager
    def output_transaction(self) -> Iterator[None]:
        """Atomically remove the live UI, allow output, then redraw it.

        The whole erase → output → repaint span sits inside one DEC 2026
        bracket: short renders land as a single frame with the prompt
        never visibly vanishing; long ones hit the terminal's sync
        timeout and degrade to the old behavior.
        """
        with self._lock:
            outermost = self._output_depth == 0
            self._output_depth += 1
            coordinating = outermost and self._active and self._suspend_depth == 0
            if coordinating:
                self._begin_sync()
                self.notify_transcript_output()
                self._erase_inline()
            try:
                yield
            finally:
                self._output_depth -= 1
                if coordinating:
                    try:
                        if self._active and self._suspend_depth == 0:
                            self._ensure_inline_geometry()
                            self._commit_partial_line()
                            self._paint_inline()
                    finally:
                        self._end_sync()

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

    def _paint_seq(self) -> str:
        """Build the paint escape sequence + update ``_displayed_rows``.

        Sequence builders (not direct writes) let repaint cycles
        coalesce erase+paint into ONE ``write()`` — no render window
        between the bar vanishing and reappearing, flicker-proof even
        on terminals without DEC 2026.
        """
        lines = self._inline_lines()
        parts = [WRAP_OFF]
        for index, line in enumerate(lines):
            if index:
                parts.append("\r\n")
            parts.append(f"{CLEAR_LINE}{line}")
        if len(lines) > 1:
            parts.append(f"\x1b[{len(lines) - 1}A")
        parts.extend(["\r", WRAP_ON])
        self._displayed_rows = len(lines)
        return "".join(parts)

    def _paint_inline(self) -> None:
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return
        self._write(self._paint_seq())

    def _erase_seq(self) -> str:
        """Build the erase sequence, leaving the cursor where transcript
        output should continue. Updates the display bookkeeping.

        Normal case: the cursor rests on the bar's top row and stays
        there (column 1). Below-partial case: the cursor is INSIDE the
        partial line one row above the bar — DECSC/DECRC give it back
        exactly (erasing never scrolls, so the absolute save is safe).
        """
        below = self._bar_below_partial
        self._bar_below_partial = False
        if not self._displayed_rows:
            return ""
        parts = [WRAP_OFF]
        if below:
            parts.append(SAVE_CURSOR)
            parts.append("\x1b[1B\r")  # down to the bar's top row
        else:
            parts.append("\r")
        for index in range(self._displayed_rows):
            if index:
                parts.append("\x1b[1B\r")
            parts.append(CLEAR_LINE)
        if below:
            parts.append(RESTORE_CURSOR)  # back into the partial line
            parts.append(WRAP_ON)
        else:
            if self._displayed_rows > 1:
                parts.append(f"\x1b[{self._displayed_rows - 1}A")
            parts.extend(["\r", WRAP_ON])
        self._displayed_rows = 0
        return "".join(parts)

    def _erase_inline(self) -> None:
        self._write(self._erase_seq())  # _write no-ops on empty

    def _paint_below_seq(self) -> Optional[str]:
        """Build the paint-below-partial sequence, or ``None`` on bail.

        Relative moves only — painting may scroll, but the partial line
        scrolls with everything else, so ``up 1`` still lands on it.
        """
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return None  # painting would no-op and strand the cursor
        col = self._partial.restore_col(self._cols)
        if col is None:
            return None
        back = "\x1b[1A\r"
        if col:
            back += f"\x1b[{col}C"
        # Replay the stream's styling so its next chunk keeps its colors.
        back += self._partial.sgr_replay
        self._bar_below_partial = True
        # Leading SGR reset: the bar must not inherit mid-line styling.
        return "\r\n\x1b[0m" + self._paint_seq() + back

    def _paint_below_partial(self) -> bool:
        """Paint the block one row below the partial line, hop back into it.

        Returns False when the restore column is untrustworthy; the
        caller falls back to the hidden+debounce path.
        """
        seq = self._paint_below_seq()
        if seq is None:
            return False
        self._write(seq)
        return True

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
            extended = self._extend_in_place_or_none(text)
            if extended is not None:
                # STREAMING FAST PATH: the cursor already sits inside the
                # partial line (hop-back) and this chunk stays on the same
                # row — the bar below doesn't move, so write the text
                # straight through. No erase, no repaint, no escapes:
                # nothing to flicker, DEC 2026 or not.
                try:
                    stream.write(text)
                    stream.flush()
                except Exception:
                    pass
                self._partial = extended
                self._last_foreign_write = time.monotonic()
                return length
            self._begin_sync()  # erase + text + repaint = one frame
            try:
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
                    elif self._output_depth == 0 and self._try_paint_below():
                        # Mid-line stream: the bar painted below the
                        # partial line and the cursor hopped back — the
                        # prompt stays visible while the paragraph flows.
                        self._cancel_repaint_timer()
                    else:
                        self._schedule_repaint(_REPAINT_QUIET_S)
            finally:
                self._end_sync()
        return length

    def _extend_in_place_or_none(self, text: str):
        """Admission test for the streaming fast path (caller holds lock).

        Returns the prospectively-fed tracker when the bar is painted
        below the partial line and ``text`` extends that line without
        changing rows; ``None`` sends the write down the slow path.
        A SIGWINCH invalidates ``_cols`` (set to -1), which fails the
        tracker's ``cols`` check — resizes always take the slow path
        and re-poll geometry.
        """
        if not (self._bar_below_partial and self._displayed_rows):
            return None
        if not self._active or self._suspend_depth > 0 or self._output_depth > 0:
            return None
        return self._partial.extended(text, self._cols)

    def _try_paint_below(self) -> bool:
        """Geometry-refreshing wrapper for :meth:`_paint_below_partial`."""
        self._ensure_inline_geometry()
        return self._paint_below_partial()

    def _track_line_state(self, text: str) -> None:
        """Track cursor-at-column-1 state and feed the partial tracker."""
        self._partial.feed(text)
        stripped = _ANSI_RE.sub("", text)
        if stripped:
            self._at_line_start = stripped.endswith(("\n", "\r"))

    def _commit_partial_line(self) -> None:
        """Move below an unfinished transcript line before painting.

        Painting starts with ``CLEAR_LINE`` on the current row -- doing
        that on a half-written streaming line would destroy it. Also
        resets partial-line tracking: the cursor is on a fresh row now,
        so stale width state must not poison the next hop calculation.
        """
        if not self._at_line_start:
            self._write("\r\n")
            self._at_line_start = True
        self._partial.reset_line()

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
                self._begin_sync()
                try:
                    self._ensure_inline_geometry()
                    self._commit_partial_line()
                    self._paint_inline()
                finally:
                    self._end_sync()
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
                # SYNC_OFF unconditionally: a bracket left open by a
                # crash must not blank-hold the terminal until timeout.
                self._write(CURSOR_SHOW + SYNC_OFF)
                self._sync_depth = 0
                self._active = False
            self._uninstall_foreign_write_guard()
        except Exception:
            pass
