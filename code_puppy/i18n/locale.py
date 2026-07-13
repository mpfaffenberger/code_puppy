"""Locale detection, normalization, and the resolution chain.

The active locale is resolved with the following precedence (highest first):

1. ``CODE_PUPPY_LOCALE`` environment variable (explicit override)
2. POSIX locale env vars: ``LC_ALL`` > ``LC_MESSAGES`` > ``LANG`` > ``LANGUAGE``
3. The persisted ``locale`` config key (``puppy.cfg``)
4. The default locale (``en-US``)

Everything here is intentionally stdlib-only. Babel/CLDR-backed niceties
(full plural rules, currency formatting) arrive in later i18n workstreams;
the foundation must not drag in a dependency just to boot.
"""

from __future__ import annotations

import os
import re
from typing import Optional

DEFAULT_LOCALE = "en-US"

# Env vars checked, in POSIX precedence order, after the explicit override.
_POSIX_LOCALE_VARS = ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")

# Matches things like "en", "en_US", "en-US", "en_US.UTF-8", "zh-Hans-CN".
_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:[_-][A-Za-z0-9]+)*")

# CLDR parent-locale overrides: locales whose fallback parent is NOT simply
# their truncated form. The big one for us is Latin American Spanish, where
# every Central/South American country falls back through the ``es-419``
# umbrella before reaching generic (Iberian-ish) ``es``.
#
# Source: CLDR supplementalData <parentLocales>. Kept as an explicit map so
# adding a dialect is a one-line change and the behavior is testable.
_LATIN_AMERICAN_ES = (
    # Central America (+ Mexico)
    "es-MX",
    "es-GT",
    "es-HN",
    "es-SV",
    "es-NI",
    "es-CR",
    "es-PA",
    "es-BZ",
    # South America
    "es-AR",
    "es-BO",
    "es-CL",
    "es-CO",
    "es-EC",
    "es-PY",
    "es-PE",
    "es-UY",
    "es-VE",
    # Caribbean + US Spanish (also parented to 419 by CLDR)
    "es-CU",
    "es-DO",
    "es-PR",
    "es-US",
)
PARENT_LOCALES: dict = {loc: "es-419" for loc in _LATIN_AMERICAN_ES}
PARENT_LOCALES["es-419"] = "es"


def normalize_locale(raw: Optional[str]) -> Optional[str]:
    """Normalize a raw locale string to ``ll-CC`` (or ``ll``) form.

    Strips encoding/modifier suffixes (``.UTF-8``, ``@euro``), converts
    underscores to hyphens, lowercases the language subtag and uppercases a
    2-letter region subtag. Returns ``None`` for empty/``"C"``/``"POSIX"``
    placeholders so callers fall through to the next source.
    """
    if not raw:
        return None

    # Drop encoding (".UTF-8") and modifiers ("@euro").
    candidate = raw.split(".", 1)[0].split("@", 1)[0].strip()
    if not candidate or candidate.upper() in ("C", "POSIX"):
        return None

    match = _LOCALE_RE.match(candidate)
    if not match:
        return None

    parts = re.split(r"[_-]", match.group(0))
    lang = parts[0].lower()
    if len(parts) == 1:
        return lang

    tail = parts[1:]
    # A trailing 2-letter subtag is a region -> uppercase it. Anything else
    # (e.g. a 4-letter script like "Hans") is title-cased, matching BCP-47.
    normalized_tail = []
    for part in tail:
        if len(part) == 2:
            normalized_tail.append(part.upper())
        elif len(part) == 4:
            normalized_tail.append(part.capitalize())
        else:
            normalized_tail.append(part.lower())
    return "-".join([lang, *normalized_tail])


def language_of(locale: str) -> str:
    """Return the bare language subtag of a locale (``en-US`` -> ``en``)."""
    return locale.split("-", 1)[0].lower()


def fallback_chain(locale: str, default: str = DEFAULT_LOCALE) -> list[str]:
    """Build the lookup chain for a locale, most-specific first.

    Honors CLDR parent-locale overrides (see :data:`PARENT_LOCALES`), so
    Latin American Spanish resolves through the ``es-419`` umbrella::

        es-AR  -> ["es-AR", "es-419", "es", "en-US"]
        zh-Hans-CN -> ["zh-Hans-CN", "zh-Hans", "zh", "en-US"]

    The default locale is always appended last (deduplicated) so a missing
    key can never escape without at least trying the base catalog.
    """
    chain: list[str] = []
    current: Optional[str] = locale
    while current and current not in chain:
        chain.append(current)
        override = PARENT_LOCALES.get(current)
        if override:
            current = override
        elif "-" in current:
            current = current.rsplit("-", 1)[0]
        else:
            current = None
    if default not in chain:
        chain.append(default)
    return chain


def detect_locale(
    config_value: Optional[str] = None, default: str = DEFAULT_LOCALE
) -> str:
    """Resolve the active locale using the full precedence chain.

    Args:
        config_value: The persisted ``locale`` config value, if any. Passed
            in (rather than imported) to keep this module free of a hard
            dependency on ``code_puppy.config`` and trivially testable.
        default: Locale to fall back to when nothing else resolves.
    """
    override = normalize_locale(os.environ.get("CODE_PUPPY_LOCALE"))
    if override:
        return override

    for var in _POSIX_LOCALE_VARS:
        candidate = normalize_locale(os.environ.get(var))
        if candidate:
            return candidate

    from_config = normalize_locale(config_value)
    if from_config:
        return from_config

    return normalize_locale(default) or DEFAULT_LOCALE
