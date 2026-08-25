"""Byte-faithful line-ending reconciliation for text edits.

The filesystem layer reads/writes with ``newline=""`` so untouched bytes are
never normalized. Models, however, emit ``\\n`` regardless of a target file's
terminators. Matching therefore happens against an LF-normalized *view* while
every returned match maps back to exact offsets in the original text -- so
ambiguity checks (including overlaps and cross-style duplicates) operate on
the same logical matches that the mutation itself will use.
"""

from __future__ import annotations

from dataclasses import dataclass

CRLF = "\r\n"
LF = "\n"
CR = "\r"


@dataclass(frozen=True)
class PatternMatch:
    """One logical match, mapped to exact offsets in the original text."""

    start: int
    end: int
    style: str


def detect_dominant(text: str) -> str:
    """Return the most common terminator, defaulting to LF for no-newline text."""
    crlf = text.count(CRLF)
    cr_only = text.count(CR) - crlf
    lf_only = text.count(LF) - crlf

    if crlf and crlf >= lf_only and crlf >= cr_only:
        return CRLF
    if cr_only and cr_only > lf_only:
        return CR
    return LF


def to_lf(text: str) -> str:
    """Normalize every terminator style in ``text`` to LF."""
    return text.replace(CRLF, LF).replace(CR, LF)


def to_style(text: str, style: str) -> str:
    """Rewrite every terminator in ``text`` to ``style``."""
    normalized = to_lf(text)
    return normalized if style == LF else normalized.replace(LF, style)


def _normalized_view(text: str) -> tuple[str, list[int]]:
    """Return an LF-normalized view plus a normalized->original offset map."""
    normalized: list[str] = []
    boundaries = [0]
    index = 0
    while index < len(text):
        if text.startswith(CRLF, index):
            normalized.append(LF)
            index += 2
        elif text[index] == CR:
            normalized.append(LF)
            index += 1
        else:
            normalized.append(text[index])
            index += 1
        boundaries.append(index)
    return "".join(normalized), boundaries


def _local_style(text: str, start: int, end: int) -> str:
    """Style for a matched span: its own terminators, else its line's."""
    matched = text[start:end]
    if CR in matched or LF in matched:
        return detect_dominant(matched)

    index = end
    while index < len(text):
        if text.startswith(CRLF, index):
            return CRLF
        if text[index] == CR:
            return CR
        if text[index] == LF:
            return LF
        index += 1

    index = start - 1
    while index >= 0:
        if text[index] == LF:
            return CRLF if index > 0 and text[index - 1] == CR else LF
        if text[index] == CR:
            return CR
        index -= 1
    return LF


def find_logical_matches(haystack: str, pattern: str) -> tuple[PatternMatch, ...]:
    """Find every logical match, including overlaps and mixed-EOL equivalents.

    Both strings are compared through LF-normalized views, so an ``old_str``
    written with plain ``\\n`` matches a CRLF span, and two occurrences that
    only differ by terminator style are both counted -- neither can be
    silently treated as the unique target. The search advances one character
    at a time so overlapping occurrences (e.g. ``"ana"`` in ``"banana"``) are
    never undercounted by non-overlapping primitives like ``str.count``.
    """
    if not pattern:
        return ()

    normalized_haystack, boundaries = _normalized_view(haystack)
    normalized_pattern = to_lf(pattern)
    if not normalized_pattern:
        return ()

    matches: list[PatternMatch] = []
    cursor = 0
    while True:
        start = normalized_haystack.find(normalized_pattern, cursor)
        if start < 0:
            break
        normalized_end = start + len(normalized_pattern)
        original_start = boundaries[start]
        original_end = boundaries[normalized_end]
        matches.append(
            PatternMatch(
                start=original_start,
                end=original_end,
                style=_local_style(haystack, original_start, original_end),
            )
        )
        cursor = start + 1
    return tuple(matches)
