"""Pure cursor motions over a text buffer (string + offset).

Each public motion returns a :class:`Motion`:

* ``pos``       -- the resulting cursor offset
* ``inclusive`` -- whether an operator range should include ``pos``
* ``linewise``  -- whether the motion operates on whole lines
* ``valid``     -- False if the motion could not be performed (e.g. f{char}
                   when {char} isn't on the line) -- operators abort on this.

Word semantics use a simplified three-class model (word chars, punctuation,
whitespace), which matches vim closely enough for a prompt box.
"""

from __future__ import annotations

from dataclasses import dataclass

_WORD = "word"
_PUNCT = "punct"
_SPACE = "space"


@dataclass
class Motion:
    pos: int
    inclusive: bool = False
    linewise: bool = False
    valid: bool = True


def _class(ch: str) -> str:
    if ch.isspace():
        return _SPACE
    if ch.isalnum() or ch == "_":
        return _WORD
    return _PUNCT


# --- line geometry --------------------------------------------------------
def line_start_offset(text: str, cur: int) -> int:
    return text.rfind("\n", 0, cur) + 1


def line_end_offset(text: str, cur: int) -> int:
    """Offset of the trailing newline (or len) -- one past the last char."""
    nl = text.find("\n", cur)
    return len(text) if nl == -1 else nl


def last_col_offset(text: str, cur: int) -> int:
    """Offset of the last *character* on the line (NORMAL-mode cursor cap)."""
    start = line_start_offset(text, cur)
    end = line_end_offset(text, cur)
    return end - 1 if end > start else start


# --- single-char / arrow motions -----------------------------------------
def left(text: str, cur: int) -> Motion:
    start = line_start_offset(text, cur)
    return Motion(max(start, cur - 1))


def right(text: str, cur: int) -> Motion:
    end = last_col_offset(text, cur)
    return Motion(min(end, cur + 1))


def _vertical(text: str, cur: int, delta: int) -> Motion:
    lines = text.split("\n")
    row = text.count("\n", 0, cur)
    col = cur - line_start_offset(text, cur)
    new_row = max(0, min(row + delta, len(lines) - 1))
    if new_row == row:
        return Motion(cur, linewise=True, valid=False)
    offset = sum(len(s) + 1 for s in lines[:new_row])
    return Motion(offset + min(col, len(lines[new_row])), linewise=True)


def down(text: str, cur: int) -> Motion:
    return _vertical(text, cur, 1)


def up(text: str, cur: int) -> Motion:
    return _vertical(text, cur, -1)


# --- intra-line landmarks -------------------------------------------------
def line_start(text: str, cur: int) -> Motion:
    return Motion(line_start_offset(text, cur))


def line_end(text: str, cur: int) -> Motion:
    return Motion(line_end_offset(text, cur), inclusive=True)


def first_non_blank(text: str, cur: int) -> Motion:
    start = line_start_offset(text, cur)
    end = line_end_offset(text, cur)
    i = start
    while i < end and text[i] in " \t":
        i += 1
    return Motion(i)


# --- buffer landmarks -----------------------------------------------------
def buffer_start(text: str, cur: int) -> Motion:
    return Motion(0, linewise=True)


def buffer_end(text: str, cur: int) -> Motion:
    return Motion(line_start_offset(text, len(text)), linewise=True)


# --- word motions ---------------------------------------------------------
def word_forward(text: str, cur: int) -> Motion:
    n = len(text)
    if cur >= n:
        return Motion(cur)
    i = cur
    cls = _class(text[i])
    if cls != _SPACE:
        while i < n and _class(text[i]) == cls:
            i += 1
    while i < n and _class(text[i]) == _SPACE:
        i += 1
    return Motion(min(i, n))


def word_end(text: str, cur: int) -> Motion:
    n = len(text)
    i = cur + 1
    while i < n and _class(text[i]) == _SPACE:
        i += 1
    if i >= n:
        return Motion(max(cur, n - 1), inclusive=True)
    cls = _class(text[i])
    while i + 1 < n and _class(text[i + 1]) == cls:
        i += 1
    return Motion(i, inclusive=True)


def word_back(text: str, cur: int) -> Motion:
    i = cur - 1
    while i >= 0 and _class(text[i]) == _SPACE:
        i -= 1
    if i < 0:
        return Motion(0)
    cls = _class(text[i])
    while i - 1 >= 0 and _class(text[i - 1]) == cls:
        i -= 1
    return Motion(max(0, i))


# --- find char (f F t T) --------------------------------------------------
def find_char(text: str, cur: int, char: str, forward: bool, till: bool) -> Motion:
    start = line_start_offset(text, cur)
    end = line_end_offset(text, cur)
    if forward:
        idx = text.find(char, min(cur + 1, end), end)
        if idx == -1:
            return Motion(cur, valid=False)
        return Motion(idx - 1 if till else idx, inclusive=True)
    else:
        idx = text.rfind(char, start, cur)
        if idx == -1:
            return Motion(cur, valid=False)
        return Motion(idx + 1 if till else idx)
