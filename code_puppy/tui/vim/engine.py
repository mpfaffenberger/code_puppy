"""The vim key-dispatch controller.

``feed(state, ed, key)`` consumes exactly one key and mutates ``ed`` / ``state``
in place. It returns ``True`` if the key was consumed (the caller should
prevent the default widget behaviour) or ``False`` if the key should fall
through (printable typing in INSERT, Enter, Ctrl-combos, arrows...).

``key`` is either a single printable character or a special name like
``"escape"``. The engine never sees Ctrl-combinations or Enter as consumed
keys -- the adapter passes those through untouched, per the spec.

This module only *routes* keys; the actual editing lives in
:mod:`operations` and :mod:`helpers` to respect the 600-line cap.
"""

from __future__ import annotations

from . import motions, operations as ops, textobjects
from .helpers import clamp_normal, done, invalid, push_undo, set_register, wait
from .state import INSERT, NORMAL, VISUAL, Editor, VimState

_OPERATORS = "dcy"
_FIND_CMDS = "fFtT"


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def feed(state: VimState, ed: Editor, key: str) -> bool:
    if state.mode == INSERT:
        if key == "escape":
            ops.leave_insert(state, ed)
            return True
        return False  # let the TextArea handle typing

    if key == "escape":
        if state.mode == VISUAL:
            state.mode = NORMAL
            ed.anchor = None
        state.reset_pending()
        return True

    if len(key) != 1:
        return False  # special keys (enter, arrows, ctrl+*, backspace) pass through

    if _accumulate_count(state, key):
        return True

    cmd = state.pending + key
    if state.mode == VISUAL:
        return _dispatch_visual(state, ed, cmd)
    return _dispatch_normal(state, ed, cmd)


def _accumulate_count(state: VimState, key: str) -> bool:
    if key.isdigit():
        if key == "0" and not state.count:
            return False  # bare 0 is the line-start motion
        state.count += key
        return True
    return False


# --------------------------------------------------------------------------
# NORMAL mode dispatch
# --------------------------------------------------------------------------
def _dispatch_normal(state: VimState, ed: Editor, cmd: str) -> bool:
    c0 = cmd[0]

    if c0 in _OPERATORS:
        return ops.dispatch_operator(state, ed, cmd)

    # Multi-key prefixes that need an argument.
    if c0 == "g":
        if cmd == "g":
            return wait(state, cmd)
        if cmd == "gg":
            return ops.move(state, ed, motions.buffer_start(ed.text, ed.cursor))
        return invalid(state)
    if c0 in _FIND_CMDS:
        return ops.do_find(state, ed, cmd)
    if c0 == "r":
        if cmd == "r":
            return wait(state, cmd)
        return ops.replace_char(state, ed, cmd[1])
    if c0 == ">":
        if cmd == ">":
            return wait(state, cmd)
        return ops.indent(state, ed, 1) if cmd == ">>" else invalid(state)
    if c0 == "<":
        if cmd == "<":
            return wait(state, cmd)
        return ops.indent(state, ed, -1) if cmd == "<<" else invalid(state)

    # Find-repeat.
    if c0 == ";":
        return ops.do_find_repeat(state, ed, same=True)
    if c0 == ",":
        return ops.do_find_repeat(state, ed, same=False)

    # Enter INSERT mode.
    if c0 in "iIaAoO":
        return ops.enter_insert_cmd(state, ed, cmd)

    # Visual mode.
    if c0 == "v":
        state.mode = VISUAL
        ed.anchor = ed.cursor
        state.reset_pending()
        return True

    # Simple mutating edits.
    if c0 == "x":
        return ops.delete_char(state, ed, cmd)
    if c0 == "D":
        return ops.delete_to_line_end(state, ed, cmd, change=False)
    if c0 == "C":
        return ops.delete_to_line_end(state, ed, cmd, change=True)
    if c0 == "J":
        return ops.join_lines(state, ed, cmd)
    if c0 == "~":
        return ops.toggle_case(state, ed, cmd)
    if c0 == "p":
        return ops.paste(state, ed, cmd, after=True)
    if c0 == "P":
        return ops.paste(state, ed, cmd, after=False)
    if c0 == "Y":
        return ops.yank_line(state, ed)
    if c0 == "u":
        return _undo(state, ed)
    if c0 == ".":
        return _dot_repeat(state, ed)

    # Plain motions.
    motion = ops.motion_for(state, ed, c0)
    if motion is not None:
        return ops.move(state, ed, motion)

    return invalid(state)


# --------------------------------------------------------------------------
# VISUAL mode dispatch
# --------------------------------------------------------------------------
def _dispatch_visual(state: VimState, ed: Editor, cmd: str) -> bool:
    c0 = cmd[0]

    if c0 == "v":  # toggle off
        state.mode = NORMAL
        ed.anchor = None
        state.reset_pending()
        return True

    if c0 == "g":
        if cmd == "g":
            return wait(state, cmd)
        if cmd == "gg":
            ed.cursor = 0
            state.reset_pending()
            return True
        return invalid(state)

    if c0 in _FIND_CMDS:
        if len(cmd) == 1:
            return wait(state, cmd)
        return _visual_find(state, ed, cmd)

    if c0 == ";":
        return ops.do_find_repeat(state, ed, same=True)
    if c0 == ",":
        return ops.do_find_repeat(state, ed, same=False)

    if c0 in "ia":  # text-object selection
        if len(cmd) == 1:
            return wait(state, cmd)
        span = textobjects.resolve(ed.text, ed.cursor, cmd[1], around=(c0 == "a"))
        if span is None:
            return invalid(state)
        ed.anchor, ed.cursor = span[0], max(span[0], span[1] - 1)
        state.reset_pending()
        return True

    # Operators on the selection.
    if c0 in "dxyc":
        return _visual_operator(state, ed, c0)

    # Motions extend the selection.
    motion = ops.motion_for(state, ed, c0)
    if motion is not None and motion.valid:
        ed.cursor = max(0, min(motion.pos, len(ed.text) - 1)) if ed.text else 0
        state.reset_pending()
        return True

    return invalid(state)


def _visual_operator(state: VimState, ed: Editor, c0: str) -> bool:
    lo, hi = _visual_range(ed)
    selected = ed.text[lo : hi + 1]
    if c0 == "y":
        set_register(state, selected, linewise=False)
        ed.cursor, ed.anchor, state.mode = lo, None, NORMAL
    else:  # d, x, c
        push_undo(state, ed)
        set_register(state, selected, linewise=False)
        ed.text = ed.text[:lo] + ed.text[hi + 1 :]
        ed.cursor, ed.anchor = lo, None
        if c0 == "c":
            ops.enter_insert(state, ed, list("c"))
        else:
            ed.cursor = clamp_normal(ed.text, ed.cursor)
            state.mode = NORMAL
    state.reset_pending()
    return True


def _visual_find(state: VimState, ed: Editor, cmd: str) -> bool:
    forward = cmd[0] in "ft"
    till = cmd[0] in "tT"
    m = motions.find_char(ed.text, ed.cursor, cmd[1], forward, till)
    state.last_find = (cmd[0], cmd[1])
    if m.valid:
        ed.cursor = m.pos
    state.reset_pending()
    return True


def _visual_range(ed: Editor) -> tuple[int, int]:
    a = ed.anchor if ed.anchor is not None else ed.cursor
    return (a, ed.cursor) if a <= ed.cursor else (ed.cursor, a)


# --------------------------------------------------------------------------
# Undo & dot-repeat (call back into feed, so they live with the controller)
# --------------------------------------------------------------------------
def _undo(state: VimState, ed: Editor) -> bool:
    if state.undo_stack:
        text, cursor = state.undo_stack.pop()
        ed.text = text
        ed.cursor = clamp_normal(text, cursor)
    return done(state)


def _dot_repeat(state: VimState, ed: Editor) -> bool:
    rec = state.last_change
    if rec is None:
        return done(state)
    state.replaying = True
    try:
        if rec[0] == "keys":
            for k in rec[1]:
                feed(state, ed, k)
        elif rec[0] == "insert":
            _, entry_keys, inserted = rec
            for k in entry_keys:
                feed(state, ed, k)
            if state.mode == INSERT:
                ed.text = ed.text[: ed.cursor] + inserted + ed.text[ed.cursor :]
                ed.cursor += len(inserted)
                feed(state, ed, "escape")
    finally:
        state.replaying = False
    state.reset_pending()
    return True
