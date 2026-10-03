"""Operators, edits, INSERT entry/exit, and motion resolution.

Everything here mutates an :class:`Editor` / :class:`VimState` in place and
returns the engine's "consume" boolean (via the helpers). The dispatch
controller in :mod:`engine` decides *which* of these to call.
"""

from __future__ import annotations

from . import motions, textobjects
from .helpers import (
    clamp_normal,
    done,
    invalid,
    push_undo,
    record_keys,
    set_register,
    wait,
)
from .motions import Motion, line_end_offset, line_start_offset
from .state import INSERT, NORMAL, Editor, VimState

_FIND_CMDS = "fFtT"


# --------------------------------------------------------------------------
# Operators: d/c/y + motion / text-object / doubled
# --------------------------------------------------------------------------
def dispatch_operator(state: VimState, ed: Editor, cmd: str) -> bool:
    op = cmd[0]
    rest = cmd[1:]
    if rest == "":
        return wait(state, cmd)

    # Doubled operator -> linewise current line (cc keeps the line).
    if rest == op:
        return _operator_line(state, ed, op, cmd)

    # Text object: {op}i{obj} / {op}a{obj}.
    if rest[0] in "ia":
        if len(rest) == 1:
            return wait(state, cmd)
        span = textobjects.resolve(ed.text, ed.cursor, rest[1], around=(rest[0] == "a"))
        if span is None:
            return invalid(state)
        do_operator(state, ed, op, span[0], span[1], linewise=False, cmd=cmd)
        return True

    # Find motion: {op}f{char} etc.
    if rest[0] in _FIND_CMDS:
        if len(rest) == 1:
            return wait(state, cmd)
        forward = rest[0] in "ft"
        till = rest[0] in "tT"
        m = motions.find_char(ed.text, ed.cursor, rest[1], forward, till)
        state.last_find = (rest[0], rest[1])
        if not m.valid:
            return invalid(state)
        start, end = range_from_motion(ed.text, ed.cursor, m)
        do_operator(state, ed, op, start, end, m.linewise, cmd)
        return True

    # gg motion: dgg.
    if rest[0] == "g":
        if rest == "g":
            return wait(state, cmd)
        if rest == "gg":
            m = motions.buffer_start(ed.text, ed.cursor)
            start, end = range_from_motion(ed.text, ed.cursor, m)
            do_operator(state, ed, op, start, end, m.linewise, cmd)
            return True
        return invalid(state)

    # Regular single-char motion.
    motion = motion_for(state, ed, rest)
    if motion is None or not motion.valid:
        return invalid(state)
    start, end = range_from_motion(ed.text, ed.cursor, motion)
    do_operator(state, ed, op, start, end, motion.linewise, cmd)
    return True


def range_from_motion(text: str, cur: int, m: Motion) -> tuple[int, int]:
    if m.linewise:
        lo, hi = min(cur, m.pos), max(cur, m.pos)
        start = line_start_offset(text, lo)
        end = line_end_offset(text, hi)
        if end < len(text):
            end += 1  # include trailing newline
        elif start > 0:
            start -= 1  # last line: eat the leading newline
        return start, end
    if m.pos >= cur:
        return cur, m.pos + (1 if m.inclusive else 0)
    return m.pos, cur


def _operator_line(state: VimState, ed: Editor, op: str, cmd: str) -> bool:
    count = state.count_value()
    ls = line_start_offset(ed.text, ed.cursor)
    le = ed.cursor
    for _ in range(count - 1):
        le = line_end_offset(ed.text, le)
        if le < len(ed.text):
            le += 1
    le = line_end_offset(ed.text, le)

    if op == "c":  # cc: clear line content, stay on the (now empty) line
        push_undo(state, ed)
        set_register(state, ed.text[ls:le], linewise=True)
        ed.text = ed.text[:ls] + ed.text[le:]
        ed.cursor = ls
        enter_insert(state, ed, list(state.count) + list(cmd))
        return True

    start, end = ls, le
    if end < len(ed.text):
        end += 1
    elif start > 0:
        start -= 1
    do_operator(state, ed, op, start, end, linewise=True, cmd=cmd)
    return True


def do_operator(
    state: VimState, ed: Editor, op: str, start: int, end: int, linewise: bool, cmd: str
) -> None:
    start = max(0, min(start, len(ed.text)))
    end = max(0, min(end, len(ed.text)))
    if start > end:
        start, end = end, start
    removed = ed.text[start:end]

    if op == "y":
        set_register(state, removed, linewise)
        if not linewise:
            ed.cursor = start
        state.reset_pending()
        return

    push_undo(state, ed)
    set_register(state, removed, linewise)
    ed.text = ed.text[:start] + ed.text[end:]
    ed.cursor = start

    if op == "c":
        if linewise:
            ed.text = ed.text[:start] + "\n" + ed.text[start:]
        enter_insert(state, ed, list(state.count) + list(cmd))
    else:
        ed.cursor = clamp_normal(ed.text, ed.cursor)
        record_keys(state, cmd)
        state.reset_pending()


# --------------------------------------------------------------------------
# Motions
# --------------------------------------------------------------------------
def motion_for(state: VimState, ed: Editor, key: str) -> Motion | None:
    simple = {
        "h": motions.left,
        "l": motions.right,
        "j": motions.down,
        "k": motions.up,
        "w": motions.word_forward,
        "e": motions.word_end,
        "b": motions.word_back,
        "0": motions.line_start,
        "$": motions.line_end,
        "^": motions.first_non_blank,
    }
    if key == "G":
        if state.count:
            from .state import rowcol_to_offset

            row = state.count_value() - 1
            return Motion(rowcol_to_offset(ed.text, row, 0), linewise=True)
        return motions.buffer_end(ed.text, ed.cursor)

    func = simple.get(key)
    if func is None:
        return None

    count = state.count_value()
    pos = ed.cursor
    last: Motion | None = None
    for _ in range(count):
        last = func(ed.text, pos)
        if not last.valid:
            break
        pos = last.pos
    if last is None:
        return None
    return Motion(pos, last.inclusive, last.linewise, last.valid)


def move(state: VimState, ed: Editor, motion: Motion) -> bool:
    if motion.valid:
        ed.cursor = clamp_normal(ed.text, motion.pos)
    state.reset_pending()
    return True


def do_find(state: VimState, ed: Editor, cmd: str) -> bool:
    if len(cmd) == 1:
        return wait(state, cmd)
    forward = cmd[0] in "ft"
    till = cmd[0] in "tT"
    m = motions.find_char(ed.text, ed.cursor, cmd[1], forward, till)
    state.last_find = (cmd[0], cmd[1])
    return move(state, ed, m)


def do_find_repeat(state: VimState, ed: Editor, same: bool) -> bool:
    if state.last_find is None:
        return invalid(state)
    fcmd, char = state.last_find
    forward = fcmd in "ft"
    till = fcmd in "tT"
    if not same:
        forward = not forward
    m = motions.find_char(ed.text, ed.cursor, char, forward, till)
    return move(state, ed, m)


# --------------------------------------------------------------------------
# Mutating edits
# --------------------------------------------------------------------------
def delete_char(state: VimState, ed: Editor, cmd: str) -> bool:
    if not ed.text:
        return done(state)
    count = state.count_value()
    end = min(ed.cursor + count, line_end_offset(ed.text, ed.cursor))
    if end <= ed.cursor:
        return done(state)
    push_undo(state, ed)
    set_register(state, ed.text[ed.cursor : end], linewise=False)
    ed.text = ed.text[: ed.cursor] + ed.text[end:]
    ed.cursor = clamp_normal(ed.text, ed.cursor)
    record_keys(state, cmd)
    return done(state)


def delete_to_line_end(state: VimState, ed: Editor, cmd: str, change: bool) -> bool:
    end = line_end_offset(ed.text, ed.cursor)
    push_undo(state, ed)
    set_register(state, ed.text[ed.cursor : end], linewise=False)
    ed.text = ed.text[: ed.cursor] + ed.text[end:]
    if change:
        enter_insert(state, ed, list(cmd))
        return True
    ed.cursor = clamp_normal(ed.text, ed.cursor)
    record_keys(state, cmd)
    return done(state)


def join_lines(state: VimState, ed: Editor, cmd: str) -> bool:
    le = line_end_offset(ed.text, ed.cursor)
    if le >= len(ed.text):
        return done(state)  # no next line
    push_undo(state, ed)
    j = le + 1
    while j < len(ed.text) and ed.text[j] in " \t":
        j += 1
    ed.text = ed.text[:le] + " " + ed.text[j:]
    ed.cursor = le
    record_keys(state, cmd)
    return done(state)


def toggle_case(state: VimState, ed: Editor, cmd: str) -> bool:
    if not ed.text or ed.cursor >= len(ed.text) or ed.text[ed.cursor] == "\n":
        return done(state)
    push_undo(state, ed)
    ch = ed.text[ed.cursor]
    swapped = ch.lower() if ch.isupper() else ch.upper()
    ed.text = ed.text[: ed.cursor] + swapped + ed.text[ed.cursor + 1 :]
    ed.cursor = min(ed.cursor + 1, line_end_offset(ed.text, ed.cursor) - 1)
    ed.cursor = clamp_normal(ed.text, ed.cursor)
    record_keys(state, cmd)
    return done(state)


def replace_char(state: VimState, ed: Editor, char: str) -> bool:
    if not ed.text or ed.cursor >= len(ed.text) or ed.text[ed.cursor] == "\n":
        return invalid(state)
    push_undo(state, ed)
    ed.text = ed.text[: ed.cursor] + char + ed.text[ed.cursor + 1 :]
    record_keys(state, "r" + char)
    return done(state)


def indent(state: VimState, ed: Editor, direction: int) -> bool:
    count = state.count_value()
    push_undo(state, ed)
    pos = ed.cursor
    for _ in range(count):
        ls = line_start_offset(ed.text, pos)
        if direction > 0:
            ed.text = ed.text[:ls] + "  " + ed.text[ls:]
        else:
            removed = 0
            while removed < 2 and ls < len(ed.text) and ed.text[ls] == " ":
                ed.text = ed.text[:ls] + ed.text[ls + 1 :]
                removed += 1
        pos = line_end_offset(ed.text, ls)
        if pos < len(ed.text):
            pos += 1
    ed.cursor = clamp_normal(ed.text, motions.first_non_blank(ed.text, ed.cursor).pos)
    record_keys(state, ">>" if direction > 0 else "<<")
    return done(state)


def paste(state: VimState, ed: Editor, cmd: str, after: bool) -> bool:
    if not state.register:
        return done(state)
    push_undo(state, ed)
    if state.register_linewise:
        if after:
            pos = line_end_offset(ed.text, ed.cursor)
            ed.text = ed.text[:pos] + "\n" + state.register + ed.text[pos:]
            ed.cursor = pos + 1
        else:
            pos = line_start_offset(ed.text, ed.cursor)
            ed.text = ed.text[:pos] + state.register + "\n" + ed.text[pos:]
            ed.cursor = pos
        ed.cursor = motions.first_non_blank(ed.text, ed.cursor).pos
    else:
        pos = ed.cursor + 1 if (after and ed.text) else ed.cursor
        pos = min(pos, len(ed.text))
        ed.text = ed.text[:pos] + state.register + ed.text[pos:]
        ed.cursor = pos + len(state.register) - 1
    ed.cursor = clamp_normal(ed.text, ed.cursor)
    record_keys(state, cmd)
    return done(state)


def yank_line(state: VimState, ed: Editor) -> bool:
    ls = line_start_offset(ed.text, ed.cursor)
    le = line_end_offset(ed.text, ed.cursor)
    set_register(state, ed.text[ls:le], linewise=True)
    return done(state)


# --------------------------------------------------------------------------
# INSERT entry / exit
# --------------------------------------------------------------------------
def enter_insert_cmd(state: VimState, ed: Editor, cmd: str) -> bool:
    c = cmd[0]
    if c == "i":
        pass
    elif c == "I":
        ed.cursor = motions.first_non_blank(ed.text, ed.cursor).pos
    elif c == "a":
        if ed.text and ed.text[ed.cursor : ed.cursor + 1] not in ("", "\n"):
            ed.cursor += 1
    elif c == "A":
        ed.cursor = line_end_offset(ed.text, ed.cursor)
    elif c == "o":
        push_undo(state, ed)
        pos = line_end_offset(ed.text, ed.cursor)
        ed.text = ed.text[:pos] + "\n" + ed.text[pos:]
        ed.cursor = pos + 1
    elif c == "O":
        push_undo(state, ed)
        pos = line_start_offset(ed.text, ed.cursor)
        ed.text = ed.text[:pos] + "\n" + ed.text[pos:]
        ed.cursor = pos
    enter_insert(state, ed, list(cmd))
    return True


def enter_insert(state: VimState, ed: Editor, entry_keys: list[str]) -> None:
    state.mode = INSERT
    ed.anchor = None
    state.insert_start = ed.cursor
    state.insert_entry_keys = entry_keys
    state.reset_pending()


def leave_insert(state: VimState, ed: Editor) -> None:
    if state.insert_start is not None:
        if ed.cursor >= state.insert_start:
            inserted = ed.text[state.insert_start : ed.cursor]
        else:
            inserted = ""
        if not state.replaying:
            state.last_change = ("insert", list(state.insert_entry_keys), inserted)
    state.insert_start = None
    state.insert_entry_keys = []
    state.mode = NORMAL
    ed.cursor = motions.left(ed.text, ed.cursor).pos
    ed.cursor = clamp_normal(ed.text, ed.cursor)
