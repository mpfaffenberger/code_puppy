"""Minimal CLDR-style plural category selection.

This is deliberately a *small* subset of CLDR plural rules — enough to be
correct for the languages we're most likely to ship first, with a sane
``other``-only fallback for everything else. The full CLDR ruleset is a
later-workstream concern (likely delegated to Babel); wiring the whole thing
in on day one would be YAGNI.

Reference: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
"""

from __future__ import annotations

from typing import Callable, Dict

from .locale import language_of

# CLDR plural categories, in canonical order.
CATEGORIES = ("zero", "one", "two", "few", "many", "other")


def _english(n: int) -> str:
    # en, de, es, it, nl, sv, ... : one when n == 1.
    return "one" if n == 1 else "other"


def _french(n: int) -> str:
    # fr, pt: 0 and 1 are "one" (CLDR gives pt the same one/other split as fr).
    return "one" if n in (0, 1) else "other"


def _no_plural(_n: int) -> str:
    # zh, ja, ko, vi, th: no grammatical plural distinction.
    return "other"


def _russian(n: int) -> str:
    # ru, uk: a genuinely tricky family, included as a representative example.
    mod10, mod100 = n % 10, n % 100
    if mod10 == 1 and mod100 != 11:
        return "one"
    if mod10 in (2, 3, 4) and mod100 not in (12, 13, 14):
        return "few"
    return "many"


# language subtag -> selector. Missing languages fall back to the English rule
# (one/other), which is the most common shape and a safe default.
_RULES: Dict[str, Callable[[int], str]] = {
    "en": _english,
    "de": _english,
    "es": _english,
    "it": _english,
    "nl": _english,
    "pt": _french,
    "sv": _english,
    "fr": _french,
    "zh": _no_plural,
    "ja": _no_plural,
    "ko": _no_plural,
    "vi": _no_plural,
    "th": _no_plural,
    "ru": _russian,
    "uk": _russian,
}


def plural_category(locale: str, n: int) -> str:
    """Return the CLDR plural category for ``n`` in ``locale``."""
    rule = _RULES.get(language_of(locale), _english)
    return rule(abs(int(n)))
