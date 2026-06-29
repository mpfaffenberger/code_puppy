"""Pure text-fragment helpers for the /plugins menu detail pane.

Extracted from ``plugins_menu.py`` to keep that file under the 600-line cap and
because these helpers are pure (no class state, no I/O) and independently
unit-testable. They all operate on prompt_toolkit's ``(style, text)`` fragment
tuples or raw strings.
"""

from __future__ import annotations

from typing import List, Tuple

from prompt_toolkit.utils import get_cwidth

Fragments = List[Tuple[str, str]]


def count_lines(fragments: Fragments) -> int:
    """Number of logical (newline-delimited) lines in *fragments*."""
    return sum(text.count("\n") for _, text in fragments)


def drop_leading_lines(fragments: Fragments, n: int) -> Fragments:
    """Return *fragments* with the first *n* logical lines removed."""
    if n <= 0:
        return list(fragments)
    out: Fragments = []
    seen = 0
    for style, text in fragments:
        if seen >= n:
            out.append((style, text))
            continue
        pos = 0
        while seen < n:
            nl = text.find("\n", pos)
            if nl == -1:
                pos = len(text)
                break
            seen += 1
            pos = nl + 1
        remainder = text[pos:]
        if seen >= n and remainder:
            out.append((style, remainder))
    return out


# prompt_toolkit's ``get_cwidth`` uses older Unicode East Asian Width data, so
# it reports 1 for emoji codepoints (e.g. U+1F6E0 hammer-and-wrench) that modern
# terminals actually render at 2 cells. Without compensating for this, padded
# lines end up 1 cell short per emoji and the overflow bleeds into the divider
# column on the next render. The ranges below cover the main emoji blocks where
# this happens — anything in them is forced to width 2.
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x2600, 0x27BF),  # Misc Symbols + Dingbats
    (
        0x1F000,
        0x1FFFF,
    ),  # Emoji blocks (Misc Symbols & Pictographs through Symbols & Pictographs Ext-A)
)


def _is_emoji(cp: int) -> bool:
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


# Codepoints stripped along with emojis: variation selectors (VS1-VS16) and
# the zero-width joiner. These are meaningless without the emoji they modify.
_EMOJI_MODIFIERS = frozenset(range(0xFE00, 0xFE10)) | {0x200D}


def strip_emojis(text: str) -> str:
    """Remove emoji codepoints (and their variation selectors / ZWJ) from *text*.

    Emojis are a known headache in prompt_toolkit TUIs: ``get_cwidth`` under-
    reports many of them, terminal renderers disagree about cell width, and
    variation selectors complicate cell math. Rather than play whack-a-mole
    with each new glyph, display content goes through this strip so the menu
    renders plain text only — the emoji-range override in ``cell_width`` stays
    in place as a defensive backstop for any stragglers.
    """
    return "".join(
        ch for ch in text if not _is_emoji(ord(ch)) and ord(ch) not in _EMOJI_MODIFIERS
    )


def strip_emojis_from_fragments(fragments: Fragments) -> Fragments:
    """Apply :func:`strip_emojis` to every fragment's text payload."""
    return [(style, strip_emojis(text)) for style, text in fragments]


def cell_width(text: str) -> int:
    """Sum of terminal cell widths for *text* (emojis count as 2, ASCII as 1).

    Overrides ``get_cwidth`` for emoji codepoints it under-reports as width 1.
    Variation selectors (VS16 U+FE0F, etc.) and zero-width joiners stay at 0.
    """
    total = 0
    for ch in text:
        w = get_cwidth(ch)
        if w == 1 and _is_emoji(ord(ch)):
            w = 2
        total += w
    return total


def pad_lines_to_cells(fragments: Fragments, width: int) -> Fragments:
    """Pad each logical line in *fragments* to *width* terminal cells.

    Prompt_toolkit's cell-diff renderer mishandles wide characters (emojis):
    a line containing an emoji occupies one more cell than its Python length,
    and when content shifts the diff can leave the emoji's "second half" cell
    frozen with stale glyphs. By measuring width in real terminal cells and
    explicitly writing trailing spaces to every column, we sidestep the
    renderer's wide-char tracking entirely.
    """
    if width <= 0:
        return list(fragments)
    out: Fragments = []
    cells = 0
    for style, text in fragments:
        i = 0
        while True:
            nl = text.find("\n", i)
            if nl == -1:
                segment = text[i:]
                if segment:
                    out.append((style, segment))
                    cells += cell_width(segment)
                break
            segment = text[i:nl]
            if segment:
                out.append((style, segment))
                cells += cell_width(segment)
            if cells < width:
                out.append(("", " " * (width - cells)))
            out.append(("", "\n"))
            cells = 0
            i = nl + 1
    if 0 < cells < width:
        out.append(("", " " * (width - cells)))
    return out


def wrap_text(body: str, width: int) -> List[str]:
    """Wrap a single string to ``width`` columns without dropping characters.

    Mirrors inspect_history's ``_wrap_one_line``: prefer breaking after the
    last space in each window so words stay whole, hard-break when there is no
    usable space (long paths, etc.). ``"".join(result) == body`` always holds.
    """
    if width <= 0 or len(body) <= width:
        return [body]
    pieces: List[str] = []
    remaining = body
    while len(remaining) > width:
        window = remaining[:width]
        cut = window.rfind(" ")
        if cut <= 0:
            cut = width
        else:
            cut += 1
        pieces.append(remaining[:cut])
        remaining = remaining[cut:]
    pieces.append(remaining)
    return pieces


__all__ = [
    "Fragments",
    "cell_width",
    "count_lines",
    "drop_leading_lines",
    "pad_lines_to_cells",
    "strip_emojis",
    "strip_emojis_from_fragments",
    "wrap_text",
]
