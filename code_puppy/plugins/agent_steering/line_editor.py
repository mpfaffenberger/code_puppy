"""Flicker-free incremental renderer for a single editable line.

Renders ``(line, cursor)`` snapshots to a terminal using the *minimum*
number of writes. This matters on legacy Windows consoles (conhost /
classic PowerShell), which ignore DEC 2026 synchronized output — any
wipe-and-repaint per keystroke flickers visibly there, and big clears
(``\\x1b[J`` over a deep scrollback buffer) are slow.

Design rules:

* Nothing changed → write nothing.
* Cursor-only move → relative row moves + one absolute-column escape.
* Text edit → jump to the first differing index, rewrite only the tail,
  spot-clear any shrink leftovers, reposition.
* Full wipe-and-redraw happens ONLY on the first render or a terminal
  resize (wrapped rows reflow unpredictably — a clean slate is the only
  sane answer), wrapped in DEC 2026 for terminals that support it.

Pending-wrap note: terminals park the cursor on the last column after a
line exactly fills a row, wrapping lazily on the *next* write — but
explicit cursor positioning silently clears that pending flag, after
which a write OVERWRITES the last cell instead of wrapping. We therefore
never write at an exact wrap boundary by trusting the flag: we park on
the previous row and emit ``\\r\\n`` to enter (or scroll-create) the next
row explicitly.
"""

from __future__ import annotations

import shutil
import sys
from typing import Optional, TextIO

_MIN_WIDTH = 1
_FALLBACK_WIDTH = 80

# DEC private mode 2026 — "synchronized output". Used only for the rare
# full-redraw path; supporting terminals commit the frame atomically,
# everything else ignores it. See steering_prompt.py history for why.
_SYNC_BEGIN = "\x1b[?2026h"
_SYNC_END = "\x1b[?2026l"


def terminal_width() -> int:
    """Best-effort terminal width, clamped to ``_MIN_WIDTH``."""
    try:
        cols = shutil.get_terminal_size(fallback=(_FALLBACK_WIDTH, 24)).columns
    except Exception:
        cols = _FALLBACK_WIDTH
    return max(_MIN_WIDTH, cols)


def make_render_state() -> dict:
    """Mutable bookkeeping for one prompt session.

    ``width`` starts as ``None`` so the very first render takes the safe
    full-redraw path. ``cursor_row`` is the cursor's physical row relative
    to the prompt's first row — the anchor for all relative vertical moves.
    """
    return {"line": "", "cursor": 0, "cursor_row": 0, "width": None}


def _end_row(length: int, width: int) -> int:
    """Physical row of the cursor sitting after the last of ``length`` chars.

    Matches terminal pending-wrap behavior: an exact-fill line keeps the
    cursor on the row of the last printed character.
    """
    if length <= 0:
        return 0
    return (length - 1) // max(_MIN_WIDTH, width)


def _visual_pos(index: int, length: int, width: int) -> tuple[int, int]:
    """Display ``(row, col0)`` for cursor ``index`` in a ``length``-char line.

    The end-of-line exact-fill case is clamped to the last cell of the last
    occupied row — the row below doesn't exist on screen yet, so positioning
    there is not an option.
    """
    width = max(_MIN_WIDTH, width)
    if index > 0 and index % width == 0 and index >= length:
        return (index - 1) // width, width - 1
    return index // width, index % width


def _move_to(out: TextIO, from_row: int, to_row: int, col0: int) -> None:
    """Move the cursor with relative row hops + absolute column (CHA)."""
    if to_row < from_row:
        out.write(f"\x1b[{from_row - to_row}A")
    elif to_row > from_row:
        out.write(f"\x1b[{to_row - from_row}B")
    out.write(f"\x1b[{col0 + 1}G")


def _full_redraw(line: str, cursor: int, state: dict, width: int, out: TextIO) -> None:
    """Wipe from the prompt's first row and repaint everything."""
    prev_row = state.get("cursor_row", 0)
    out.write(_SYNC_BEGIN)
    if prev_row > 0:
        out.write(f"\x1b[{prev_row}A")
    out.write("\r\x1b[J")
    out.write(line)
    row = _end_row(len(line), width)
    if cursor < len(line):
        row, col = _visual_pos(cursor, len(line), width)
        _move_to(out, _end_row(len(line), width), row, col)
    out.write(_SYNC_END)
    state["cursor_row"] = row


def _first_diff(a: str, b: str) -> int:
    """Index of the first differing character (or the shorter length)."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))


def _clear_shrink_leftovers(
    out: TextIO, row_now: int, wrote: bool, new_len: int, old_len: int, width: int
) -> int:
    """Erase stale cells left behind when the line got shorter.

    Returns the cursor's physical row afterwards. Clears at most the old
    text's footprint — never the whole screen — so nothing visibly blinks.
    """
    # Wipe the rest of the cursor's row — unless we just wrote an exact-fill
    # row (nothing stale there, and EL from a pending-wrap cursor can eat
    # the last character on some terminals).
    if not (wrote and new_len > 0 and new_len % width == 0):
        out.write("\x1b[K")
    last_old_row = _end_row(old_len, width)
    if last_old_row > row_now:
        # Rows below hold only stale text — drop down one and wipe the rest.
        out.write("\x1b[B\r\x1b[J")
        return row_now + 1
    return row_now


def _incremental_edit(
    line: str, cursor: int, state: dict, width: int, out: TextIO
) -> None:
    """Rewrite only what changed, then put the cursor where it belongs."""
    prev_line: str = state["line"]
    edit = _first_diff(prev_line, line)
    boundary = edit > 0 and edit % width == 0

    # Fast path: appending with the cursor already parked at the end (plain
    # typing). One write, zero escapes. Exact wrap boundaries fall through —
    # they need the explicit ``\r\n`` dance below.
    if (
        edit == len(prev_line)
        and state["cursor"] == len(prev_line)
        and cursor == len(line)
        and not boundary
    ):
        out.write(line[edit:])
        state["cursor_row"] = _end_row(len(line), width)
        return

    # Position the write head at the edit point.
    row_now = state["cursor_row"]
    if boundary and edit == len(prev_line):
        # Appending onto a row that doesn't exist yet: park at the end of
        # the last occupied row, then explicitly enter the next one.
        prev_end = (edit - 1) // width
        _move_to(out, row_now, prev_end, width - 1)
        out.write("\r\n")
        row_now = prev_end + 1
    else:
        row_now, col = edit // width, edit % width
        _move_to(out, state["cursor_row"], row_now, col)

    tail = line[edit:]
    if tail:
        out.write(tail)
        row_now = _end_row(len(line), width)

    cleared_below = False
    if len(line) < len(prev_line):
        new_row = _clear_shrink_leftovers(
            out, row_now, bool(tail), len(line), len(prev_line), width
        )
        cleared_below = new_row != row_now
        row_now = new_row

    if tail and cursor == len(line) and not cleared_below:
        # Cursor is already exactly where the write left it — and if that
        # write ended on an exact-fill row, repositioning would clear the
        # terminal's pending-wrap flag for no reason.
        state["cursor_row"] = row_now
        return
    target_row, target_col = _visual_pos(cursor, len(line), width)
    _move_to(out, row_now, target_row, target_col)
    state["cursor_row"] = target_row


def render_line(
    line: str, cursor: int, state: dict, out: Optional[TextIO] = None
) -> None:
    """Render ``line`` with the cursor at ``cursor`` (index into ``line``).

    ``state`` must come from :func:`make_render_state` and be reused across
    calls within one prompt session.
    """
    out = out if out is not None else sys.stdout
    cursor = max(0, min(cursor, len(line)))
    width = terminal_width()

    if state["width"] != width:
        _full_redraw(line, cursor, state, width, out)
    elif line == state["line"]:
        if cursor != state["cursor"]:
            row, col = _visual_pos(cursor, len(line), width)
            _move_to(out, state["cursor_row"], row, col)
            state["cursor_row"] = row
        else:
            return  # nothing changed — touching the terminal invites flicker
    else:
        _incremental_edit(line, cursor, state, width, out)

    state["line"] = line
    state["cursor"] = cursor
    state["width"] = width
    out.flush()


__all__ = ["make_render_state", "render_line", "terminal_width"]
