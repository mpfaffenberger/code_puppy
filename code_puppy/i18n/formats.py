"""Locale-aware formatting for numbers and dates (stdlib-only, best-effort).

This is the *foundation* seam, not the final implementation. Full CLDR-grade
formatting (grouping separators per locale, currency, compact "1.2K"
notation, RTL digit shaping) lands with Babel in a later workstream. For now
we provide a stable API with sensible en-US-ish defaults and per-locale digit
grouping/decimal separators for the handful of locales we know we'll hit
first, so call sites can migrate today without waiting on Babel.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Union

from .translate import get_locale

# language subtag -> (thousands_sep, decimal_point). Fallback is en-style.
_SEPARATORS = {
    "en": (",", "."),
    "de": (".", ","),
    "fr": ("\u202f", ","),  # narrow no-break space
    "es": (".", ","),
    "it": (".", ","),
    "pt": (".", ","),
    "ru": ("\u00a0", ","),
    "zh": (",", "."),
    "ja": (",", "."),
    "ko": (",", "."),
}

_DEFAULT_SEPARATORS = (",", ".")


def _separators(locale: str) -> tuple[str, str]:
    return _SEPARATORS.get(locale.split("-", 1)[0].lower(), _DEFAULT_SEPARATORS)


def format_number(
    value: Union[int, float],
    *,
    decimals: Optional[int] = None,
    locale: Optional[str] = None,
) -> str:
    """Format a number with locale-appropriate grouping/decimal separators.

    Args:
        value: The number to format.
        decimals: Fixed number of fraction digits, or ``None`` to keep the
            value's natural precision (integers render with no fraction).
        locale: Override the active locale for this call.
    """
    loc = locale or get_locale()
    thousands, decimal_point = _separators(loc)

    if decimals is not None:
        rendered = f"{value:,.{decimals}f}"
    elif isinstance(value, int):
        rendered = f"{value:,d}"
    else:
        rendered = f"{value:,}"

    # Python always emits ","/".": swap to locale glyphs via placeholders to
    # avoid clobbering a separator that happens to equal the other glyph.
    return (
        rendered.replace(",", "\0").replace(".", decimal_point).replace("\0", thousands)
    )


def format_datetime(
    value: Union[datetime, date],
    *,
    date_only: bool = False,
    locale: Optional[str] = None,
) -> str:
    """Format a datetime/date. Placeholder ISO-ish output for the foundation.

    Deliberately conservative: ISO-8601 is unambiguous across locales, so we
    lean on it until Babel provides real CLDR date skeletons. The ``locale``
    arg is accepted now so call sites don't need to change when the richer
    implementation lands.
    """
    _ = locale or get_locale()  # reserved for the Babel-backed upgrade
    if date_only or (isinstance(value, date) and not isinstance(value, datetime)):
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M")
