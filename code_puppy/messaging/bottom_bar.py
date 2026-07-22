"""Persistent bottom prompt bar via a terminal scroll region (DECSTBM).

Reserves the bottom rows of the terminal (3 base rows plus one row for
every active sub-agent panel entry):

    rows H-2-n..H-3  sub-agent panel (n = number of panel rows, via set_panel_lines)
    row  H-2         status line (token/context info, via set_status)
    row  H-1         prompt line  (the always-available input line)
    row  H           blank margin

The scrollable region is rows ``1 .. H-3-n``, so
all existing streaming output — termflow markdown, thinking stream, tool
token-count lines — keeps working unmodified: it simply scrolls *inside*
the region while the reserved rows stay put.

Design rules:

* **NOT Rich Live.** All escape writes go directly to ``sys.__stdout__``
  with an immediate flush; Rich never sees them.
* **TTY-only.** If stdout is not a TTY (pipes, CI, ``-p`` headless mode),
  every method is a silent no-op.
* **Thread-safe.** A single reentrant lock guards all state + writes; the
  SIGWINCH handler runs on the main thread and re-enters safely.
* **Cursor stays inside the region.** After establishing the region the
  cursor is parked at the bottom of the scrollable area so subsequent
  console prints scroll correctly instead of stomping the reserved rows.
  The prompt line therefore renders its own *pseudo* cursor (a
  reverse-video cell) rather than parking the real cursor outside the
  region.
* **Resize.** One unified path: every repaint lazily re-polls the
  terminal size (``_ensure_geometry``) and re-establishes on change.
  POSIX additionally gets a chained SIGWINCH handler that merely
  invalidates the cached geometry so the next repaint picks it up — the
  handler itself never paints (signal-safe by construction).

Suspension mirrors the refcount pattern in
``code_puppy.agents._key_listeners.suspended_key_listener``: wrap any code
that needs the full screen (prompt_toolkit menus, ``ask_user_question``
TUI, shell commands) in :meth:`BottomBar.suspended`.
"""

from __future__ import annotations

import atexit
import logging
import signal
import sys
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional, TextIO, Tuple

from .bar_rendering import (
    CLEAR_LINE as _CLEAR_LINE,
)
from .bar_rendering import (
    CURSOR_HIDE as _CURSOR_HIDE,
)
from .bar_rendering import (
    CURSOR_SHOW as _CURSOR_SHOW,
)
from .bar_rendering import (
    MODKEYS_OFF as _MODKEYS_OFF,
)
from .bar_rendering import (
    MODKEYS_ON as _MODKEYS_ON,
)
from .bar_rendering import (
    PASTE_OFF as _PASTE_OFF,
)
from .bar_rendering import (
    PASTE_ON as _PASTE_ON,
)
from .bar_rendering import (
    RESET_REGION as _RESET_REGION,
)
from .bar_rendering import (
    RESTORE_CURSOR as _RESTORE_CURSOR,
)
from .bar_rendering import (
    SAVE_CURSOR as _SAVE_CURSOR,
)
from .bar_rendering import (
    default_get_size as _default_get_size,
)
from .bar_rendering import (
    sanitize as _sanitize,
)

from .bar_painters import PROMPT_MAX_ROWS, BarPainterMixin  # noqa: E402
from .transcript_guard import TranscriptGuardMixin  # noqa: E402

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

#: Minimum rows reserved at the bottom of the screen (top margin +
#: prompt). The status row (below the prompt) adds one more, but only
#: while it has content — an empty status row isn't reserved at all.
RESERVED_ROWS = 2

#: Maximum rows for the completion popup (directly BELOW the prompt).
POPUP_MAX_ROWS = 6

SizeProvider = Callable[[], Tuple[int, int]]


def _configured_panel_max_rows() -> int:
    """Load the panel ceiling without making config import this UI module."""
    try:
        from code_puppy.config import get_subagent_panel_max_rows

        return get_subagent_panel_max_rows()
    except Exception:
        return 0


# =============================================================================
# BottomBar
# =============================================================================


class BottomBar(TranscriptGuardMixin, BarPainterMixin):
    """Scroll-region manager for the persistent bottom prompt.

    Use the module-level singleton via :func:`get_bottom_bar` in app code;
    direct construction is for tests (inject ``stream`` / ``get_size``).
    """

    def __init__(
        self,
        stream: Optional[TextIO] = None,
        get_size: Optional[SizeProvider] = None,
    ) -> None:
        self._lock = threading.RLock()
        self._stream = stream
        self._get_size = get_size or _default_get_size
        self._active = False  # user-facing started state
        self._region_up = False  # is DECSTBM currently in effect?
        self._suspend_depth = 0
        self._rows = 0
        self._cols = 0
        self._status = ""
        self._status_prefix = ""  # animated spinner slot (puppy_spinner)
        self._status_suffix = ""  # trailing slot (steer_queue's '(N queued)')
        self._panel_lines: list[str] = []
        # 0 = automatic (terminal-height budget only). Keep the resolved value
        # in memory: panel animation repaints several times per second, so the
        # painter must not re-read puppy.cfg on every frame.
        self._panel_max_rows = _configured_panel_max_rows()
        self._popup_lines: list[str] = []  # completion popup (over panel)
        self._popup_selected = -1
        # Blank rows held below the prompt after the popup shrinks/closes
        # (high-water residue). The prompt does NOT slide back down when
        # the menu closes; the slack is reclaimed lazily by
        # ``notify_transcript_output`` so the prompt falls back into
        # place while output is scrolling anyway.
        self._popup_slack = 0
        self._reserved = 0  # reserved-row count while the region is up
        self._paste_armed = False  # bracketed paste (ESC[?2004h) state
        self._modkeys_armed = False  # xterm modifyOtherKeys level 1
        self._prompt_prefix = ""
        self._prompt_prefix_sgrs: list[str] = []  # per-char prefix colors
        self._prompt_buffer = ""
        self._prompt_cursor = 0
        self._sigwinch_installed = False
        self._atexit_registered = False
        # DECTCEM state: the hardware cursor is hidden while the region
        # is up (the prompt row paints a reverse-video pseudo-cursor;
        # without hiding, a second "rogue" cursor blinks wherever
        # streaming output last wrote inside the region).
        self._cursor_hidden = False
        # Windows scrollback guard (no-op state on POSIX) — see
        # transcript_guard.TranscriptGuardMixin.
        self._init_transcript_guard_state()

    # =========================================================================
    # Public API
    # =========================================================================

    def start(self) -> None:
        """Establish the scroll region and paint the reserved rows.

        Idempotent; silent no-op when stdout isn't a TTY.
        """
        if not self._is_tty():
            return
        with self._lock:
            if self._active:
                return
            self._active = True
            if self._suspend_depth == 0:
                self._establish()
        self._install_transcript_guard()  # Windows-only; no-op elsewhere
        self._install_sigwinch()
        self._register_atexit()

    def stop(self) -> None:
        """Reset the scroll region and clear the reserved rows.

        Fully restores normal terminal state (``ESC[r`` + cleared rows).
        Idempotent; silent no-op when inactive or not a TTY.
        """
        with self._lock:
            if not self._active:
                return
            self._active = False
            if self._region_up:
                self._teardown()
        self._uninstall_transcript_guard()

    def is_active(self) -> bool:
        """True between :meth:`start` and :meth:`stop`."""
        with self._lock:
            return self._active

    def set_status(self, text: str) -> None:
        """Update the status line (bottom row, BELOW the prompt).

        Text is control-character-stripped and truncated to the terminal
        width. Cached even while inactive/suspended so the next repaint
        shows the latest value. Setting the first non-empty value
        materializes the row (the region shrinks by one); clearing both
        slots collapses it again.
        """
        with self._lock:
            self._status = text or ""
            self._sync_reserved(self._status_seq)

    def get_status(self) -> str:
        """Current status-line text (the cached :meth:`set_status` value)."""
        with self._lock:
            return self._status

    def set_status_prefix(self, text: str) -> None:
        """Update the spinner slot painted BEFORE the status text.

        Separate from :meth:`set_status` so an animation (the puppy
        spinner plugin) and the token-context writer never stomp each
        other — each owns its own slot on the shared status row.
        """
        with self._lock:
            self._status_prefix = text or ""
            self._sync_reserved(self._status_seq)

    def set_status_suffix(self, text: str) -> None:
        """Update the trailing slot painted AFTER the status text.

        Third slot on the shared row (prefix=spinner, status=tokens,
        suffix=queue count) — same no-stomping contract as the others.
        """
        with self._lock:
            self._status_suffix = text or ""
            self._sync_reserved(self._status_seq)

    def set_panel_max_rows(self, max_rows: int) -> None:
        """Set the live panel ceiling; ``0`` keeps automatic sizing.

        The terminal-height budget still wins when it is smaller. Updating the
        value repaints immediately without dropping any raw panel state.
        """
        normalized = max(0, int(max_rows))
        with self._lock:
            if normalized == self._panel_max_rows:
                return
            self._panel_max_rows = normalized
            self._sync_reserved(self._panel_seq)

    def set_panel_lines(self, lines: Optional[list]) -> None:
        """Set the sub-agent panel rows (above the status row).

        Accepts every supplied row, each either a plain string (sanitized
        here, painted dim) or a ``rich.text.Text`` (kept styled; content
        sanitized per-segment at paint time -- see
        ``bar_rendering.render_styled_line``).
        An empty list collapses the panel rows and returns them to the
        scroll region. Growing/shrinking re-establishes the region with
        the appropriate row clears so scrollback isn't corrupted.
        While the completion popup is open it takes the panel's place;
        the panel restores automatically when the popup closes.
        """
        from rich.text import Text

        cleaned = [
            line.copy() if isinstance(line, Text) else _sanitize(str(line))
            for line in (lines or [])
        ]
        with self._lock:
            self._panel_lines = cleaned
            self._sync_reserved(self._panel_seq)

    def set_popup_lines(self, lines: Optional[list], selected: int = -1) -> None:
        """Set the completion-popup rows (directly BELOW the prompt block
        — the prompt slides up to make room, IDE-dropdown style).

        Up to ``POPUP_MAX_ROWS`` rows; the ``selected`` index renders in
        the brand accent. While non-empty the popup takes precedence
        over the sub-agent panel (cached and restored on close).

        Shrinking/closing does NOT slide the prompt back down: the
        vacated rows are kept as blank ``_popup_slack`` so the prompt
        stays put, then :meth:`notify_transcript_output` walks them
        back one row at a time as transcript output scrolls in.
        """
        cleaned = [_sanitize(str(line)) for line in (lines or [])][:POPUP_MAX_ROWS]
        with self._lock:
            old_block = len(self._popup_lines) + self._popup_slack
            self._popup_lines = cleaned
            self._popup_selected = selected
            self._popup_slack = max(0, old_block - len(cleaned))
            self._sync_reserved(self._popup_seq)

    @contextmanager
    def output_transaction(self) -> Iterator[None]:
        """Coordinate one transcript render with the live prompt surface."""
        self.notify_transcript_output()
        yield

    def notify_transcript_output(self) -> None:
        """Release ONE row of popup slack — called per rendered message.

        The renderers poke this right before they print. Releasing the
        whole slack at once would teleport the prompt down on the very
        first message after the menu closed (e.g. the submit echo — the
        exact jump we're avoiding), so instead the prompt steps down a
        single row per message: amid the scrolling output each step is
        imperceptible, and a normal burst of turn output walks it back
        to the bottom almost immediately. Cheap no-op (one lock + int
        check) when there is no slack.
        """
        with self._lock:
            if self._popup_slack == 0:
                return
            self._popup_slack -= 1
            self._sync_reserved(self._popup_seq)

    def get_panel_lines(self) -> list:
        """Return a copy of the current sub-agent panel lines."""
        with self._lock:
            return list(self._panel_lines)

    def set_prompt_text(
        self, prefix: str, buffer: str, cursor_pos: int, prefix_sgrs=None
    ) -> None:
        """Repaint the prompt row (row ``H-1``) with a visible cursor.

        The *real* terminal cursor must stay inside the scroll region so
        streaming output keeps scrolling correctly, so the cursor is
        rendered as a reverse-video cell at ``cursor_pos`` instead.
        ``prefix_sgrs``: per-char SGR codes for the prefix (out-of-band
        — in-band escapes would be sanitized away).
        """
        with self._lock:
            self._prompt_prefix = prefix or ""
            self._prompt_prefix_sgrs = list(prefix_sgrs or [])
            self._prompt_buffer = buffer or ""
            self._prompt_cursor = max(0, cursor_pos)
            self._sync_reserved(self._prompt_seq)

    def _sync_reserved(self, painter) -> None:
        """Repaint (or resize the reserved area) after a state change.

        Caller holds the lock. ``self._reserved`` is the authoritative
        on-screen count: if the desired total differs, grow/shrink the
        region; otherwise ``painter`` paints just the changed block. A
        geometry change re-establishes everything and needs neither.
        """
        if not self._region_up:
            # Dormant (terminal was too small)? A grown terminal is only
            # noticed here — try to wake. Never while inactive/suspended.
            if not self._active or self._suspend_depth > 0:
                return
            self._ensure_geometry()
            if not self._region_up:
                return
            self._write(painter())
            return
        self._ensure_geometry()  # re-establishes fully on size change
        if not self._region_up:
            return
        if self._reserved != self._total_reserved():
            self._resize_reserved(self._reserved)
        else:
            self._write(painter())

    @contextmanager
    def suspended(self) -> Iterator[None]:
        """Reentrant context manager releasing the full screen.

        Resets the region and clears the reserved rows on the outermost
        enter, then re-establishes the region + repaints on the outermost
        exit. Needed around prompt_toolkit menus, the ``ask_user_question``
        TUI, and interactive shell commands.
        """
        if not self._is_tty():
            yield
            return
        with self._lock:
            self._suspend_depth += 1
            if self._suspend_depth == 1 and self._region_up:
                self._teardown()
        try:
            yield
        finally:
            with self._lock:
                self._suspend_depth -= 1
                if self._suspend_depth == 0 and self._active:
                    self._establish()

    # =========================================================================
    # Geometry / resize
    # =========================================================================

    def _ensure_geometry(self) -> None:
        """Re-establish the region if the terminal size changed.

        Called lazily on every repaint — this is the whole resize story on
        Windows (no SIGWINCH there).
        """
        cols, rows = self._safe_size()
        if (cols, rows) != (self._cols, self._rows):
            self._establish()

    def _on_resize(self) -> None:
        """SIGWINCH handler body: invalidate cached geometry ONLY.

        The actual re-establish happens on the next repaint via the lazy
        ``_ensure_geometry`` poll — unifying the POSIX and Windows resize
        paths. The handler deliberately does NOT paint: an RLock is
        reentrant on its own thread, so a handler firing mid-``_establish``
        on the main thread could otherwise re-enter it and interleave
        escape writes.
        """
        # Single int store — atomic enough for a poll hint; no lock needed
        # (and taking the RLock here would defeat the point).
        self._cols = -1

    def _install_sigwinch(self) -> None:
        """Chain a SIGWINCH handler — main thread + POSIX only.

        ``signal.signal`` raises ``ValueError`` off the main thread, so
        guard explicitly; resize still works via the lazy repaint poll.
        """
        with self._lock:
            if self._sigwinch_installed:
                return
            if not hasattr(signal, "SIGWINCH"):
                return
            if threading.current_thread() is not threading.main_thread():
                return
            try:
                previous = signal.getsignal(signal.SIGWINCH)

                def _handler(signum, frame):  # pragma: no cover - signal glue
                    try:
                        self._on_resize()
                    except Exception:
                        pass
                    if callable(previous) and previous not in (
                        signal.SIG_DFL,
                        signal.SIG_IGN,
                    ):
                        try:
                            previous(signum, frame)
                        except Exception:
                            pass

                signal.signal(signal.SIGWINCH, _handler)
                self._sigwinch_installed = True
            except Exception:
                # Resize still works via the lazy repaint poll.
                logger.debug("SIGWINCH handler install failed", exc_info=True)

    # =========================================================================
    # Region establish / teardown
    # =========================================================================

    def _establish(self) -> None:
        """Set the scroll region, park the cursor inside it, paint rows."""
        cols, rows = self._safe_size()
        old_rows = self._rows
        old_reserved = self._reserved if self._region_up else 0
        self._cols, self._rows = cols, rows
        # Full rebuild = fresh geometry: leftover popup slack (the
        # lazy-reclaim gap below the prompt) is meaningless here.
        self._popup_slack = 0
        reserved = self._total_reserved()
        if rows < reserved + 1:
            # Terminal too small for a region + reserved rows; if one was
            # in effect, put the terminal back to normal and go dormant
            # (hardware cursor comes back too — no region, no pseudo-cursor).
            if self._region_up:
                parts = [_RESET_REGION]
                if self._cursor_hidden:
                    parts.append(_CURSOR_SHOW)
                    self._cursor_hidden = False
                if self._paste_armed:
                    parts.append(_PASTE_OFF)
                    self._paste_armed = False
                if self._modkeys_armed:
                    parts.append(_MODKEYS_OFF)
                    self._modkeys_armed = False
                self._write("".join(parts))
            self._guard_on_teardown()
            self._region_up = False
            return
        top = rows - reserved
        parts = []
        if old_reserved and old_rows > 0:
            # Re-establish after a resize: the old bar rows were painted
            # at the PREVIOUS geometry and nothing repaints over them —
            # without an explicit erase they linger as ghost duplicates
            # ("multiples of UI elements") at their old positions while
            # the fresh bar paints at the new bottom. Reset the region
            # first so the erases can reach rows outside the incoming
            # one, then blank the old reserved band (clamped to the new
            # screen height).
            parts.append(_RESET_REGION)
            for row in range(
                max(1, old_rows - old_reserved + 1), min(old_rows, rows) + 1
            ):
                parts.append(f"\x1b[{row};1H{_CLEAR_LINE}")
        parts += [
            # Push existing content up so the reserved rows start blank.
            "\n" * reserved,
            # DECSTBM: scrollable region = rows 1..H-reserved. Homes cursor.
            f"\x1b[1;{top}r",
            # CRITICAL: park the cursor INSIDE the scrollable area so
            # subsequent console prints scroll rather than overwriting
            # the reserved rows.
            f"\x1b[{top};1H",
        ]
        if not self._cursor_hidden:
            # DECTCEM hide: the prompt row renders a pseudo-cursor; the
            # hardware cursor must not blink inside the scroll region.
            parts.insert(0, _CURSOR_HIDE)
            self._cursor_hidden = True
        if not self._paste_armed:
            # Bracketed paste while the bar owns input (Phase B).
            parts.insert(0, _PASTE_ON)
            self._paste_armed = True
        if not self._modkeys_armed:
            # modifyOtherKeys level 1: makes Shift+Enter encodable.
            parts.insert(0, _MODKEYS_ON)
            self._modkeys_armed = True
        self._region_up = True
        self._reserved = reserved
        parts.append(self._reserved_rows_seq())
        self._write("".join(parts))
        self._guard_on_establish(top)  # cursor parked at (top, 1)

    def _resize_reserved(self, old_reserved: int) -> None:
        """Grow/shrink the reserved area while the region is up.

        Caller holds the lock and guarantees the terminal size hasn't
        changed (``_ensure_geometry`` ran first). Scrollback-safe:

        * Growing (region shrinks): scroll the region content up by the
          delta first (``CSI S``), so the newly-reserved rows are blank
          instead of eating visible output.
        * Shrinking (region grows): clear the vacated reserved rows so no
          stale panel paint lingers inside the scrollable area.

        CURSOR CONTRACT: the transcript cursor is restored to wherever
        the streaming writer left it (adjusted for the grow-scroll), NOT
        parked at ``top;1``. Parking used to stomp half-typed streaming
        lines: growing scrolls the in-progress line up onto the new
        region bottom, so a blind park landed the cursor at column 1 ON
        that line and the typewriter's next chunk overwrote its head
        (the mangled-response artifact).
        """
        rows = self._rows
        new_reserved = self._total_reserved()
        if rows < new_reserved + 1:
            # Not enough room for the bigger panel — full re-establish
            # handles the dormant transition.
            self._establish()
            return
        parts = [_SAVE_CURSOR]
        delta_up = 0
        if new_reserved > old_reserved:
            # Blank the soon-to-be-reserved rows by scrolling content up.
            delta_up = new_reserved - old_reserved
            if self._guard_scroll_fix:
                # Windows: CSI S inside a restricted region DESTROYS the
                # scrolled lines (they never reach scrollback). Reset the
                # margins and feed LFs at the physical bottom row instead
                # — visually identical, but the lines pan into history.
                parts.append("\x1b[r")
                parts.append(f"\x1b[{rows};1H" + "\n" * delta_up)
            else:
                parts.append(f"\x1b[{delta_up}S")
        else:
            # Clear rows being returned to the scroll region.
            for row in range(rows - old_reserved + 1, rows - new_reserved + 1):
                parts.append(f"\x1b[{row};1H{_CLEAR_LINE}")
        top = rows - new_reserved
        parts.append(f"\x1b[1;{top}r")  # DECSTBM homes the cursor
        # Restore the transcript cursor (DECSTBM homed it). After a grow
        # the content scrolled up by ``delta_up``, so the cursor must
        # follow its line up (CUU clamps at the region top — safe).
        parts.append(_RESTORE_CURSOR)
        if delta_up:
            parts.append(f"\x1b[{delta_up}A")
        self._reserved = new_reserved
        parts.append(self._reserved_rows_seq())
        self._write("".join(parts))
        if delta_up:
            self._guard_on_resize_scroll(delta_up)

    def _teardown(self) -> None:
        """Reset to a full-screen region and clear the reserved rows.

        Re-polls the terminal size: the cached geometry can be stale if
        the terminal was resized while suspended (or right before stop),
        and clearing rows computed from stale height either misses the
        real reserved rows or clears mid-screen content.
        """
        self._guard_on_teardown()  # flush withheld tail BEFORE our escapes
        rows = self._safe_size()[1]
        reserved = self._reserved or self._total_reserved()
        parts = [_RESET_REGION]
        for row in range(max(1, rows - reserved + 1), rows + 1):
            parts.append(f"\x1b[{row};1H{_CLEAR_LINE}")
        parts.append(f"\x1b[{max(1, rows - reserved + 1)};1H")
        if self._cursor_hidden:
            # Give the hardware cursor back — every exit path (stop,
            # suspend-enter, dormant, emergency) funnels through here.
            parts.append(_CURSOR_SHOW)
            self._cursor_hidden = False
        if self._paste_armed:
            parts.append(_PASTE_OFF)
            self._paste_armed = False
        if self._modkeys_armed:
            parts.append(_MODKEYS_OFF)
            self._modkeys_armed = False
        self._write("".join(parts))
        self._region_up = False
        self._reserved = 0

    # =========================================================================
    # Emergency restore (abnormal exit)
    # =========================================================================

    def _register_atexit(self) -> None:
        """Register the last-resort restore hook once, on first start().

        Mirrors the precedent in ``plugins/theme/osc_palette.py`` — the
        user's terminal must never stay bricked with a stale scroll
        region because Code Puppy died without a clean ``stop()``.
        """
        with self._lock:
            if self._atexit_registered:
                return
            try:
                atexit.register(self._emergency_restore)
                self._atexit_registered = True
            except Exception:
                logger.debug("atexit registration failed", exc_info=True)

    def _emergency_restore(self) -> None:
        """Reset the region + re-show the cursor on abnormal exit.

        Region reset only fires if bookkeeping says it's still up, but
        the cursor-show is UNCONDITIONAL (TTY permitting): a visible
        cursor is always the safe failure mode, even if ``_region_up``
        tracking is somehow off. Never raises — this runs during
        interpreter shutdown.
        """
        try:
            with self._lock:
                if self._region_up:
                    self._teardown()  # includes cursor-show + paste-off
                elif self._is_tty():
                    self._write(_CURSOR_SHOW + _PASTE_OFF + _MODKEYS_OFF)
                    self._cursor_hidden = False
                    self._paste_armed = False
                    self._modkeys_armed = False
            self._uninstall_transcript_guard()
        except Exception:
            pass  # interpreter is dying; nothing sane left to do

    # =========================================================================
    # Low-level plumbing
    # =========================================================================

    def _resolve_stream(self) -> Optional[TextIO]:
        if self._stream is not None:
            return self._stream
        return getattr(sys, "__stdout__", None)

    def _is_tty(self) -> bool:
        stream = self._resolve_stream()
        if stream is None:
            return False
        try:
            return bool(stream.isatty())
        except Exception:
            return False

    def _safe_size(self) -> Tuple[int, int]:
        try:
            cols, rows = self._get_size()
            return max(1, int(cols)), max(1, int(rows))
        except Exception:
            return 80, 24

    def _write(self, seq: str) -> None:
        """Write escapes straight to the stream with a flush; never raise."""
        if not seq:
            return
        stream = self._resolve_stream()
        if stream is None:
            return
        try:
            stream.write(seq)
            stream.flush()
        except Exception:
            pass


# =============================================================================
# Module-level singleton
# =============================================================================

_bottom_bar: Optional[BottomBar] = None
_bottom_bar_lock = threading.Lock()


def _use_inline_surface() -> bool:
    """Use the DECSTBM-free surface for known-incompatible terminals."""
    import os

    mode = os.environ.get("CODE_PUPPY_PROMPT_MODE", "auto").strip().lower()
    if mode in {"inline", "flow"}:
        return True
    if mode in {"pinned", "scroll-region"}:
        return False
    emulator = os.environ.get("TERMINAL_EMULATOR", "").strip().lower()
    return emulator == "jetbrains-jediterm"


def get_bottom_bar() -> BottomBar:
    """Get or lazily create the terminal-appropriate prompt surface."""
    global _bottom_bar
    with _bottom_bar_lock:
        if _bottom_bar is None:
            if _use_inline_surface():
                from .inline_bar import InlineBottomBar

                _bottom_bar = InlineBottomBar()
            else:
                _bottom_bar = BottomBar()
        return _bottom_bar


def reset_bottom_bar() -> None:
    """Reset the global BottomBar (for testing)."""
    global _bottom_bar
    with _bottom_bar_lock:
        if _bottom_bar is not None:
            try:
                _bottom_bar.stop()
            except Exception:
                pass
        _bottom_bar = None


__all__ = [
    "POPUP_MAX_ROWS",
    "PROMPT_MAX_ROWS",
    "RESERVED_ROWS",
    "BottomBar",
    "get_bottom_bar",
    "reset_bottom_bar",
]
