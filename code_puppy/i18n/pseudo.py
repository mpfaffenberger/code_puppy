"""Pseudolocalization: catch unexternalized strings and layout bugs early.

Pseudolocalization transforms real translations into an obviously-fake but
still-readable form. It does two jobs at once:

1. **Coverage:** any string that shows up *without* pseudo treatment is a
   hardcoded literal that skipped the catalog. A pseudolocale CI run makes
   those pop visually (and lets a test assert on them).
2. **Layout/expansion:** padding text ~+40% surfaces truncation and
   fixed-width layout bugs before a real translator ever files one.

Activate by setting the active locale to ``en-XA`` (or any locale whose
language subtag is ``xa``). Interpolation placeholders (``{name}``) are left
untouched so formatting still works.
"""

from __future__ import annotations

import re

# The pseudolocale tag. ``en-XA`` mirrors the de-facto industry convention.
PSEUDO_LOCALE = "en-XA"

# Per-character accent map. ASCII letters only; everything else passes through.
_ACCENTS = {
    "a": "\u00e0",
    "b": "\u0180",
    "c": "\u00e7",
    "d": "\u0111",
    "e": "\u00e9",
    "f": "\u0192",
    "g": "\u011f",
    "h": "\u0125",
    "i": "\u00ee",
    "j": "\u0135",
    "k": "\u0137",
    "l": "\u013a",
    "m": "\u1e3f",
    "n": "\u00f1",
    "o": "\u00f6",
    "p": "\u00fe",
    "q": "\u0071",
    "r": "\u0155",
    "s": "\u0161",
    "t": "\u0163",
    "u": "\u00fc",
    "v": "\u1e7d",
    "w": "\u0175",
    "x": "\u1e8b",
    "y": "\u00fd",
    "z": "\u017e",
    "A": "\u00c5",
    "B": "\u0181",
    "C": "\u00c7",
    "D": "\u010e",
    "E": "\u00c9",
    "F": "\u0191",
    "G": "\u011e",
    "H": "\u0124",
    "I": "\u00ce",
    "J": "\u0134",
    "K": "\u0136",
    "L": "\u0139",
    "M": "\u1e3e",
    "N": "\u00d1",
    "O": "\u00d6",
    "P": "\u00de",
    "Q": "\u0051",
    "R": "\u0154",
    "S": "\u0160",
    "T": "\u0162",
    "U": "\u00dc",
    "V": "\u1e7c",
    "W": "\u0174",
    "X": "\u1e8a",
    "Y": "\u00dd",
    "Z": "\u017d",
}

# Split on {{ / }} escapes and {identifier} fields so we never accent
# interpolation tokens. Mirrors the grammar in translate._FIELD_RE.
_PLACEHOLDER_RE = re.compile(r"(\{\{|\}\}|\{\w+\})")


def is_pseudo_locale(locale: str) -> bool:
    """True if ``locale``'s language subtag marks it as the pseudolocale."""
    return locale.split("-", 1)[0].lower() == "xa" or locale == PSEUDO_LOCALE


def _accent(segment: str) -> str:
    return "".join(_ACCENTS.get(ch, ch) for ch in segment)


def pseudolocalize(text: str, expand: float = 0.4) -> str:
    """Return the pseudolocalized form of ``text``.

    Accents letters, wraps the whole thing in brackets, and pads with filler
    to simulate translation expansion. ``{placeholders}`` are preserved
    verbatim so :meth:`str.format_map` still works downstream.
    """
    parts = _PLACEHOLDER_RE.split(text)
    accented = "".join(
        part if _PLACEHOLDER_RE.fullmatch(part) else _accent(part) for part in parts
    )

    pad_len = int(len(re.sub(_PLACEHOLDER_RE, "", text)) * max(0.0, expand))
    padding = ("\u2003" * pad_len) if pad_len else ""
    return f"\u27e6{accented}{padding}\u27e7"
