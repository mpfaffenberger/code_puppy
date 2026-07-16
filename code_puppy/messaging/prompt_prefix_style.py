"""Convert prompt_toolkit prompt fragments to per-char SGR codes.

The persistent bottom-bar prompt (``bottom_bar`` / ``bar_rendering``)
paints raw text with cell-accurate window math, and ``sanitize()``
strips any escape bytes smuggled in-band — so color has to travel
OUT-OF-BAND: a plain prefix string plus a parallel list with one SGR
parameter string (e.g. ``"1;35"``) per character. ``bar_rendering``
re-applies the codes AFTER chopping rows, so widths never count SGR
bytes as cells.

Only ANSI palette colors are emitted (30-37 / 90-97): the /theme
plugin recolors the terminal by remapping ANSI palette slots via OSC 4,
so palette codes restyle automatically with the chosen theme.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from .bar_rendering import sanitize

#: prompt_toolkit ANSI color name -> SGR foreground code.
_ANSI_FG: Dict[str, int] = {
    "ansiblack": 30,
    "ansired": 31,
    "ansigreen": 32,
    "ansiyellow": 33,
    "ansiblue": 34,
    "ansimagenta": 35,
    "ansicyan": 36,
    "ansiwhite": 37,
    "ansigray": 90,  # prompt_toolkit alias for bright black
    "ansibrightblack": 90,
    "ansibrightred": 91,
    "ansibrightgreen": 92,
    "ansibrightyellow": 93,
    "ansibrightblue": 94,
    "ansibrightmagenta": 95,
    "ansibrightcyan": 96,
    "ansibrightwhite": 97,
}

#: prompt_toolkit attribute token -> SGR parameter.
_ATTRS: Dict[str, str] = {
    "bold": "1",
    "dim": "2",
    "italic": "3",
    "underline": "4",
}


def style_to_sgr(style: str, class_styles: Dict[str, str]) -> str:
    """Resolve a prompt_toolkit style string to SGR parameters.

    ``class:name`` tokens are expanded via ``class_styles`` (e.g. the
    ``PROMPT_STYLES`` dict exported by ``prompt_toolkit_completion``);
    unknown tokens are ignored so the worst case is plain text.

    Returns a parameter string like ``"1;35"`` — empty for unstyled.
    """
    params: List[str] = []
    for token in (style or "").split():
        if token.startswith("class:"):
            resolved = class_styles.get(token[len("class:") :], "")
            expanded = style_to_sgr(resolved, class_styles)
            if expanded:
                params.append(expanded)
        elif token in _ATTRS:
            params.append(_ATTRS[token])
        elif token in _ANSI_FG:
            params.append(str(_ANSI_FG[token]))
    return ";".join(params)


def flatten_prompt_fragments(
    fragments: Sequence[Tuple[str, str]],
    class_styles: Dict[str, str],
) -> Tuple[str, List[str]]:
    """Flatten ``(style, text)`` fragments to ``(plain, per_char_sgrs)``.

    Each fragment's text is passed through the SAME ``sanitize()`` the
    bar renderer applies, so the SGR list stays index-aligned with the
    prefix chars the renderer actually paints.

    Hard newlines are the ONE control character kept: they mark chrome
    line breaks (the prompt_newline plugin appends one so input starts
    on a fresh row) and ``bar_rendering._prompt_visual_rows`` honors
    them. Each kept ``\\n`` still occupies an SGR slot so the per-char
    alignment survives the split.
    """
    plain_parts: List[str] = []
    sgrs: List[str] = []
    for style, text in fragments:
        clean = "\n".join(sanitize(part) for part in text.split("\n"))
        if not clean:
            continue
        sgr = style_to_sgr(style, class_styles)
        plain_parts.append(clean)
        sgrs.extend([sgr] * len(clean))
    return "".join(plain_parts), sgrs


__all__ = ["flatten_prompt_fragments", "style_to_sgr"]
