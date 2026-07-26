"""Scrollback preservation for the bottom bar — Windows Terminal only.

Windows Terminal DISCARDS lines that scroll off the top of a restricted
DECSTBM region instead of pushing them into the scrollback buffer
(iTerm2/kitty special-case top-anchored regions and preserve history;
WT does not). With the persistent bottom bar's region pinned, every
transcript line that scrolled past row 1 was destroyed — scrollback
appeared frozen at whatever predated the app launch.

Fix — on Windows ONLY (POSIX escape output stays byte-identical):
:class:`BottomBar` wraps ``sys.stdout``/``sys.stderr`` in
:class:`StreamGuard` proxies while the bar is active. Every transcript
write is simulated against a virtual cursor (:func:`feed`); writes that
cannot scroll the region pass through untouched (the hot path). Writes
that WOULD scroll take the dance:

    1. ``?2026h``          begin synchronized update (no flicker)
    2. erase bar rows      bar paint must never leak into scrollback
    3. ``ESC[r``           margins off -> full-screen scrolling
    4. CUP + text          native scrolling at row H pushes REAL history
    5. CUP(H,1) + LF*k     re-park the transcript bottom at the region top
    6. ``ESC[1;top r``     margins back
    7. repaint bar         reserved rows return, pixel-identical
    8. ``?2026l``          end synchronized update

Cursor-simulation notes:

* ``\\n`` is modelled as CR+LF: Python text-mode streams translate
  ``\\n`` -> ``\\r\\n`` on Windows before the console sees it.
* Deferred autowrap (the xterm "last column flag") is modelled with a
  ``pending`` bool. A dance ends with CUP, which clears the terminal's
  real flag — ``_sim_real_flag`` tracks that divergence and the next
  write commits the wrap explicitly (``\\r\\n`` prepend) when needed.
* Chunks may end mid-escape-sequence (streaming SGR splits). The
  incomplete tail is withheld (``_carry``) and prepended to the next
  write so dance escapes are never injected inside a caller's sequence.
"""

from __future__ import annotations

import platform
import sys
from typing import List, Optional, TextIO, Tuple

from rich.cells import get_character_cell_size

from .bar_rendering import CLEAR_LINE as _CLEAR_LINE

#: DECSET 2026 — synchronized update (atomic frame; ignored if unsupported).
SYNC_ON = "\x1b[?2026h"
SYNC_OFF = "\x1b[?2026l"

#: CSI final bytes that move the cursor (and clear a pending wrap).
_CSI_MOVERS = frozenset("ABCDEFGad`HfST")

#: (row, col, pending_wrap) — row/col are 1-based screen coordinates.
SimState = Tuple[int, int, bool]


def _param(params: str, index: int, default: int) -> int:
    """Extract the ``index``-th semicolon CSI parameter (>=1, defaulted)."""
    parts = params.lstrip("?>=").split(";")
    try:
        value = int(parts[index]) if parts[index] else default
    except (IndexError, ValueError):
        value = default
    return max(1, value)


def _apply_csi(
    final: str, params: str, state: SimState, cols: int, bottom: int
) -> Tuple[SimState, int]:
    """Apply one CSI sequence to the cursor state; return (state, scrolls)."""
    row, col, pending = state
    scrolls = 0
    if final in _CSI_MOVERS:
        pending = False
        n = _param(params, 0, 1)
        if final == "A":
            row = max(1, row - n)
        elif final in ("B", "e"):
            row = min(bottom, row + n)
        elif final in ("C", "a"):
            col = min(cols, col + n)
        elif final == "D":
            col = max(1, col - n)
        elif final == "E":
            row, col = min(bottom, row + n), 1
        elif final == "F":
            row, col = max(1, row - n), 1
        elif final in ("G", "`"):
            col = min(cols, n)
        elif final == "d":
            row = min(bottom, n)
        elif final in ("H", "f"):
            row = min(bottom, _param(params, 0, 1))
            col = min(cols, _param(params, 1, 1))
        elif final in ("S", "T"):
            # SU/SD shift region content: lossy while margins are up, so
            # count as scrolls to force the dance. Cursor doesn't move.
            scrolls = n
    # 'm' (SGR) and every other final: no movement, pending survives.
    return (row, col, pending), scrolls


def feed(
    state: SimState, text: str, cols: int, bottom: int
) -> Tuple[SimState, int, int, bool]:
    """Advance the virtual cursor through ``text``.

    ``bottom`` is the effective scroll boundary: the region bottom for
    the "would this scroll?" trial, the physical screen height for the
    dance's end-state computation.

    Returns ``(state, scrolls, tail_start, moved)``:

    * ``scrolls`` — LF/wrap events at ``bottom`` (lines that would
      scroll off);
    * ``tail_start`` — index where a trailing INCOMPLETE escape
      sequence begins (``len(text)`` when none) — the state returned
      corresponds to ``text[:tail_start]``;
    * ``moved`` — True when any ground-state character was processed
      (used to re-validate the terminal's real wrap flag).
    """
    row, col, pending = state
    scrolls = 0
    moved = False
    i, n = 0, len(text)
    tail_start = n

    def _line_feed() -> None:
        nonlocal row, scrolls
        if row >= bottom:
            row = bottom
            scrolls += 1
        else:
            row += 1

    while i < n:
        ch = text[i]
        if ch == "\x1b":
            seq_start = i
            i += 1
            if i >= n:
                tail_start = seq_start
                break
            kind = text[i]
            if kind == "[":  # CSI
                i += 1
                params_start = i
                while i < n and not ("\x40" <= text[i] <= "\x7e"):
                    i += 1
                if i >= n:
                    tail_start = seq_start
                    break
                (row, col, pending), extra = _apply_csi(
                    text[i], text[params_start:i], (row, col, pending), cols, bottom
                )
                scrolls += extra
                i += 1
            elif kind == "]":  # OSC — skip to BEL or ST (ESC \)
                j = i + 1
                term = -1
                while j < n:
                    if text[j] == "\x07":
                        term = j + 1
                        break
                    if text[j] == "\x1b":
                        if j + 1 < n and text[j + 1] == "\\":
                            term = j + 2
                        break
                    j += 1
                if term < 0:
                    tail_start = seq_start
                    break
                i = term
            elif kind in "()*+":  # charset designation: ESC ( B
                if i + 1 >= n:
                    tail_start = seq_start
                    break
                i += 2
            else:  # ESC + single byte (DECSC, RI, ...) — treated as inert
                i += 1
            continue
        if ch == "\n":
            # Python text streams translate \n -> \r\n on Windows.
            moved, pending, col = True, False, 1
            _line_feed()
        elif ch == "\r":
            moved, pending, col = True, False, 1
        elif ch == "\b":
            moved, pending, col = True, False, max(1, col - 1)
        elif ch == "\t":
            moved, pending = True, False
            col = min(cols, ((col - 1) // 8 + 1) * 8 + 1)
        elif ch < " " or ch == "\x7f":
            pass  # BEL & friends: zero-width, no movement
        else:
            width = get_character_cell_size(ch)
            if width > 0:
                moved = True
                if pending or col + width - 1 > cols:
                    pending, col = False, 1
                    _line_feed()
                col += width
                if col > cols:
                    col, pending = cols, True
        i += 1
    return (row, col, pending), scrolls, tail_start, moved


def first_effective_is_printable(text: str) -> bool:
    """True when the first non-escape-sequence char would print a glyph.

    Decides whether a dance-cleared deferred wrap must be committed with
    an explicit ``\\r\\n`` (printable would otherwise overwrite the last
    cell) or resolves naturally (leading CR/LF behaves identically with
    or without the terminal's wrap flag).
    """
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\x1b":
            i += 1
            if i >= n:
                return False
            kind = text[i]
            if kind == "[":
                i += 1
                while i < n and not ("\x40" <= text[i] <= "\x7e"):
                    i += 1
                i += 1
            elif kind == "]":
                while i < n and text[i] != "\x07":
                    if text[i] == "\x1b" and i + 1 < n and text[i + 1] == "\\":
                        i += 1
                        break
                    i += 1
                i += 1
            else:
                i += 2 if kind in "()*+" else 1
            continue
        if ch < " " or ch == "\x7f":
            return False
        return True
    return False


class StreamGuard:
    """Duck-typed text-stream proxy routing writes through the bar.

    Everything except ``write``/``writelines``/``flush`` delegates to
    the wrapped stream, so ``isatty``/``encoding``/``buffer``/``fileno``
    behave exactly like the original ``sys.stdout``.
    """

    def __init__(self, bar, wrapped: TextIO) -> None:
        self._bar = bar
        self._wrapped = wrapped

    def write(self, s) -> int:
        try:
            return self._bar.guarded_write(str(s), self._wrapped)
        except Exception:
            try:
                return self._wrapped.write(s)
            except Exception:
                return 0

    def writelines(self, lines) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        try:
            self._wrapped.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._wrapped, name)


class TranscriptGuardMixin:
    """Scrollback-preserving write routing, mixed into :class:`BottomBar`.

    The mixin relies on the bar's ``_lock``, geometry fields, region
    bookkeeping and painters. All hooks are cheap no-ops unless a guard
    was installed — which only ever happens on Windows — so POSIX
    behavior (and escape output) is unchanged.
    """

    def _init_transcript_guard_state(self) -> None:
        self._guards: List[Tuple[str, StreamGuard, TextIO]] = []
        self._guard_scroll_fix = False  # history-safe grow-scroll variant
        self._carry = ""  # withheld incomplete escape tail
        self._sim_row = 0  # 0 = simulator not synced (row/col are 1-based)
        self._sim_col = 1
        self._sim_pending = False
        self._sim_real_flag = True  # terminal's real wrap flag matches sim

    # ------------------------------------------------------------------
    # Resync hooks (called by BottomBar under its lock)
    # ------------------------------------------------------------------

    def _guard_on_establish(self, top: int) -> None:
        """Region just (re)established with the cursor parked at (top, 1)."""
        self._sim_row, self._sim_col = top, 1
        self._sim_pending, self._sim_real_flag = False, True

    def _guard_on_teardown(self) -> None:
        """Region coming down — flush the withheld tail, drop sim sync."""
        if self._carry:
            self._write(self._carry)
            self._carry = ""
        self._sim_row = 0

    def _guard_on_resize_scroll(self, delta_up: int) -> None:
        """Reserved area grew: content scrolled up, cursor followed."""
        if self._sim_row:
            self._sim_row = max(1, self._sim_row - delta_up)

    # ------------------------------------------------------------------
    # Write routing
    # ------------------------------------------------------------------

    def guarded_write(self, text: str, target: Optional[TextIO] = None) -> int:
        """Route one transcript write; returns ``len(text)`` (stream API)."""
        length = len(text)
        if not text:
            return length
        with self._lock:
            stream = target if target is not None else self._resolve_stream()
            if stream is None:
                return length
            if self._region_up:
                self._ensure_geometry()  # may re-establish or go dormant
            if not (self._region_up and self._sim_row > 0):
                payload = self._carry + text
                self._carry = ""
                try:
                    stream.write(payload)
                except Exception:
                    pass
                return length
            self._route_guarded(text, stream)
        return length

    def _route_guarded(self, text: str, stream: TextIO) -> None:
        """Fast-path passthrough or dance. Caller holds the lock."""
        cols, rows = self._cols, self._rows
        top = rows - self._reserved
        text = self._carry + text
        self._carry = ""
        did_prepend = False
        if (
            self._sim_pending
            and not self._sim_real_flag
            and first_effective_is_printable(text)
        ):
            # A dance's CUP cleared the terminal's deferred-wrap flag;
            # commit the wrap it would have performed.
            text = "\r\n" + text
            did_prepend = True
        state: SimState = (self._sim_row, self._sim_col, self._sim_pending)
        new_state, scrolls, tail_start, moved = feed(state, text, cols, top)
        emit, self._carry = text[:tail_start], text[tail_start:]
        if scrolls == 0:
            if emit:
                try:
                    stream.write(emit)
                except Exception:
                    pass
            row, col, pending = new_state
            self._sim_row, self._sim_col, self._sim_pending = row, col, pending
            if moved or did_prepend or not pending:
                self._sim_real_flag = True
            return
        end_state, _, _, _ = feed(state, emit, cols, rows)
        self._dance(emit, state, end_state, top, rows, stream)

    def _dance(
        self,
        emit: str,
        start: SimState,
        end: SimState,
        top: int,
        rows: int,
        stream: TextIO,
    ) -> None:
        """History-preserving scroll: full-screen write + re-reserve."""
        end_row, end_col, end_pending = end
        overflow = max(0, end_row - top)
        final_row = end_row - overflow
        parts = [SYNC_ON]
        # Bar paint must never scroll into history: blank the reserved rows.
        for row in range(top + 1, rows + 1):
            parts.append(f"\x1b[{row};1H{_CLEAR_LINE}")
        parts.append("\x1b[r")  # margins off (homes the cursor)
        parts.append(f"\x1b[{start[0]};{start[1]}H")
        parts.append(emit)  # full-screen scrolling -> real scrollback
        if overflow:
            # Re-park the transcript bottom at the region top; each LF at
            # the physical bottom row pans one more line into history.
            parts.append(f"\x1b[{rows};1H" + "\n" * overflow)
        parts.append(f"\x1b[1;{top}r")  # margins back (homes the cursor)
        parts.append(f"\x1b[{final_row};{end_col}H")
        parts.append(self._reserved_rows_seq())  # painters save/restore cursor
        parts.append(SYNC_OFF)
        try:
            stream.write("".join(parts))
            stream.flush()
        except Exception:
            pass
        self._sim_row, self._sim_col = final_row, end_col
        self._sim_pending = end_pending
        # The final CUP cleared the terminal's real wrap flag.
        self._sim_real_flag = not end_pending

    # ------------------------------------------------------------------
    # Install / uninstall (Windows only)
    # ------------------------------------------------------------------

    def _install_transcript_guard(self) -> None:
        """Wrap ``sys.stdout``/``sys.stderr`` — Windows real-TTY runs only.

        Never installs for constructor-injected streams (tests) or when
        the std streams are redirected, and never on POSIX: terminals
        that special-case top-anchored regions keep native behavior.
        """
        if platform.system() != "Windows":
            return
        if self._stream is not None or self._guards or not self._is_tty():
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
            self._guards.append((name, guard, current))
        if self._guards:
            self._guard_scroll_fix = True

    def _uninstall_transcript_guard(self) -> None:
        """Restore the original std streams (only if still ours)."""
        for name, guard, original in self._guards:
            if getattr(sys, name, None) is guard:
                setattr(sys, name, original)
        self._guards.clear()
        self._guard_scroll_fix = False


__all__ = [
    "SYNC_OFF",
    "SYNC_ON",
    "StreamGuard",
    "TranscriptGuardMixin",
    "feed",
    "first_effective_is_printable",
]
