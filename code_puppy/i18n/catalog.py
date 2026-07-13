"""Message catalog format, loader, and the missing-key fallback chain.

Catalogs are JSON files under ``code_puppy/i18n/locales/<locale>.json`` (plus
any extra directories registered via :func:`add_catalog_dir`, so plugins and
the private fork can ship their own strings without editing this package).

Catalog shape::

    {
      "startup.welcome": "Welcome to Code Puppy, {name}!",
      "files.deleted": {
        "one": "Deleted {count} file.",
        "other": "Deleted {count} files."
      }
    }

A value is either a plain string or a plural dict keyed by CLDR plural
categories (``zero``/``one``/``two``/``few``/``many``/``other``). Only
``other`` is required in a plural dict; the rest are optional.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Union

from .locale import DEFAULT_LOCALE, fallback_chain

logger = logging.getLogger(__name__)

# A catalog entry is a bare string or a plural-forms mapping.
CatalogEntry = Union[str, Dict[str, str]]
Catalog = Dict[str, CatalogEntry]

# Bundled catalogs ship next to this module.
_BUILTIN_DIR = os.path.join(os.path.dirname(__file__), "locales")

# Extra directories (plugins, private fork) searched *before* the builtin one,
# so downstream strings can override or extend the base catalog.
_extra_dirs: List[str] = []

# locale -> merged catalog. Cleared by reset() / add_catalog_dir().
_cache: Dict[str, Catalog] = {}


def add_catalog_dir(path: str) -> None:
    """Register an additional directory of ``<locale>.json`` catalogs.

    Later-registered dirs win over earlier ones, and all registered dirs win
    over the builtin catalogs. Registering invalidates the cache.
    """
    if path not in _extra_dirs:
        _extra_dirs.append(path)
        _cache.clear()


def reset() -> None:
    """Drop cached catalogs (and registered dirs). Mostly for tests."""
    _cache.clear()
    _extra_dirs.clear()


def _search_dirs() -> List[str]:
    # Extra dirs are searched last so their entries overwrite the builtins
    # during the dict merge below.
    return [_BUILTIN_DIR, *_extra_dirs]


def _load_file(path: str) -> Catalog:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping malformed i18n catalog %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("i18n catalog %s is not a JSON object; skipping", path)
        return {}
    return data


def load_catalog(locale: str) -> Catalog:
    """Load and merge every ``<locale>.json`` for a single locale.

    Does *not* apply the fallback chain — that happens at lookup time so a
    key present in ``en`` but absent in ``fr`` still resolves. Cached per
    locale.
    """
    if locale in _cache:
        return _cache[locale]

    merged: Catalog = {}
    for directory in _search_dirs():
        merged.update(_load_file(os.path.join(directory, f"{locale}.json")))
    _cache[locale] = merged
    return merged


def available_locales() -> List[str]:
    """Return the sorted set of locales that ship a ``<locale>.json`` catalog.

    Scans the builtin dir plus any registered extra dirs. Useful for driving
    ``/set locale`` autocomplete and for validating the shipped catalogs.
    """
    found = set()
    for directory in _search_dirs():
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for name in entries:
            if name.endswith(".json"):
                found.add(name[: -len(".json")])
    return sorted(found)


def lookup(
    key: str, locale: str, default_locale: str = DEFAULT_LOCALE
) -> Optional[CatalogEntry]:
    """Find ``key`` walking the locale fallback chain, most-specific first.

    Returns the raw catalog entry (string or plural dict), or ``None`` if the
    key is absent from every catalog in the chain.
    """
    for candidate in fallback_chain(locale, default_locale):
        entry = load_catalog(candidate).get(key)
        if entry is not None:
            return entry
    return None
