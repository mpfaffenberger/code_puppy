"""Low-level helpers shared by the engine and operations modules.

These are the leaf utilities -- register/undo bookkeeping, cursor clamping,
and the trio of pending-state terminators (``_wait`` / ``_invalid`` /
``_done``). Kept separate so both the dispatch controller and the operation
implementations can depend on them without import cycles.
"""

from __future__ import annotations

from .motions import line_end_offset, line_start_offset
from .state import Editor, VimState


def set_register(state: VimState, text: str, linewise: bool) -> None:
    if linewise:
        text = text.strip("\n")
    state.register = text
    state.register_linewise = linewise


def push_undo(state: VimState, ed: Editor) -> None:
    state.undo_stack.append((ed.text, ed.cursor))
    if len(state.undo_stack) > 200:
        state.undo_stack.pop(0)


def record_keys(state: VimState, cmd: str) -> None:
    if not state.replaying:
        state.last_change = ("keys", list(state.count) + list(cmd))


def clamp_normal(text: str, cur: int) -> int:
    start = line_start_offset(text, cur)
    end = line_end_offset(text, cur)
    last = end - 1 if end > start else start
    return max(start, min(cur, last))


def wait(state: VimState, cmd: str) -> bool:
    state.pending = cmd
    return True


def invalid(state: VimState) -> bool:
    state.reset_pending()
    return True


def done(state: VimState) -> bool:
    state.reset_pending()
    return True
