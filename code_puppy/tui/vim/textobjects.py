"""Text objects: inner/around word, quotes, and bracket pairs.

Each function returns an exclusive ``(start, end)`` span of offsets, or
``None`` when the object cannot be resolved at the cursor (operator aborts).
"""

from __future__ import annotations

from .motions import _class, _SPACE, line_end_offset, line_start_offset

_PAIRS = {
    "(": ("(", ")"),
    ")": ("(", ")"),
    "[": ("[", "]"),
    "]": ("[", "]"),
    "{": ("{", "}"),
    "}": ("{", "}"),
    "b": ("(", ")"),
    "B": ("{", "}"),
}
_QUOTES = {'"', "'", "`"}


def word_span(text: str, cur: int, around: bool) -> tuple[int, int] | None:
    n = len(text)
    if n == 0:
        return None
    cur = min(cur, n - 1)
    cls = _class(text[cur])
    start = cur
    while start - 1 >= 0 and _class(text[start - 1]) == cls:
        start -= 1
    end = cur
    while end + 1 < n and _class(text[end + 1]) == cls:
        end += 1
    end += 1  # exclusive
    if not around:
        return start, end
    # "around": swallow trailing whitespace, else leading whitespace.
    new_end = end
    while new_end < n and _class(text[new_end]) == _SPACE and text[new_end] != "\n":
        new_end += 1
    if new_end != end:
        return start, new_end
    new_start = start
    while new_start - 1 >= 0 and _class(text[new_start - 1]) == _SPACE:
        new_start -= 1
    return new_start, end


def quote_span(text: str, cur: int, quote: str, around: bool) -> tuple[int, int] | None:
    ls = line_start_offset(text, cur)
    le = line_end_offset(text, cur)
    positions = [i for i in range(ls, le) if text[i] == quote]
    if len(positions) < 2:
        return None
    # Pair them up (0,1), (2,3)... and find the pair enclosing/after cursor.
    for j in range(0, len(positions) - 1, 2):
        open_i, close_i = positions[j], positions[j + 1]
        if open_i <= cur <= close_i or cur < open_i:
            if around:
                return open_i, close_i + 1
            return open_i + 1, close_i
    return None


def pair_span(text: str, cur: int, key: str, around: bool) -> tuple[int, int] | None:
    open_ch, close_ch = _PAIRS[key]
    # Walk left to find the enclosing opener, tracking nesting.
    depth = 0
    open_i = -1
    i = cur
    # If cursor sits on the opener, start there.
    if cur < len(text) and text[cur] == open_ch:
        open_i = cur
    else:
        i = cur - 1
        while i >= 0:
            if text[i] == close_ch:
                depth += 1
            elif text[i] == open_ch:
                if depth == 0:
                    open_i = i
                    break
                depth -= 1
            i -= 1
    if open_i == -1:
        return None
    # Walk right from the opener to its matching closer.
    depth = 0
    close_i = -1
    j = open_i + 1
    while j < len(text):
        if text[j] == open_ch:
            depth += 1
        elif text[j] == close_ch:
            if depth == 0:
                close_i = j
                break
            depth -= 1
        j += 1
    if close_i == -1:
        return None
    if around:
        return open_i, close_i + 1
    return open_i + 1, close_i


def resolve(text: str, cur: int, obj: str, around: bool) -> tuple[int, int] | None:
    """Dispatch an object character to the right span function."""
    if obj == "w":
        return word_span(text, cur, around)
    if obj in _QUOTES:
        return quote_span(text, cur, obj, around)
    if obj in _PAIRS:
        return pair_span(text, cur, obj, around)
    return None
