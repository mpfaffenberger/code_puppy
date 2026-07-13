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
import re
import threading
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

# Guards ALL access to _cache and _extra_dirs. lookup() runs on every t() call,
# which the message queue can dispatch from both the main thread and its daemon
# thread, so these globals are genuinely shared mutable state.
_lock = threading.RLock()

# A locale used to build a filename must be a plain BCP-47-ish tag. This is a
# defense-in-depth guard so the exported load_catalog()/lookup() can't be
# tricked into path traversal (e.g. "../../../../etc/passwd") even if a caller
# skips normalize_locale().
_SAFE_LOCALE_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")


def _is_safe_locale(locale: str) -> bool:
    return bool(locale) and _SAFE_LOCALE_RE.match(locale) is not None


def add_catalog_dir(path: str) -> None:
    """Register an additional directory of ``<locale>.json`` catalogs.

    Later-registered dirs win over earlier ones, and all registered dirs win
    over the builtin catalogs. Registering invalidates the cache.
    """
    with _lock:
        if path not in _extra_dirs:
            _extra_dirs.append(path)
            _cache.clear()


def reset() -> None:
    """Drop cached catalogs (and registered dirs). Mostly for tests."""
    with _lock:
        _cache.clear()
        _extra_dirs.clear()


def _search_dirs() -> List[str]:
    # Extra dirs are searched last so their entries overwrite the builtins
    # during the dict merge below. Caller must hold _lock.
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
    if not _is_safe_locale(locale):
        # Reject anything that could escape the locales dir (path traversal)
        # or otherwise isn't a plain locale tag. Defense-in-depth for the
        # exported API; the normal path already normalizes upstream.
        logger.warning("Refusing to load unsafe locale name: %r", locale)
        return {}

    with _lock:
        cached = _cache.get(locale)
        if cached is not None:
            return cached
        dirs = _search_dirs()

    merged: Catalog = {}
    for directory in dirs:
        merged.update(_load_file(os.path.join(directory, f"{locale}.json")))

    with _lock:
        # Another thread may have populated it concurrently; either value is
        # correct, prefer the already-cached one for identity stability.
        return _cache.setdefault(locale, merged)


def available_locales() -> List[str]:
    """Return the sorted set of locales that ship a ``<locale>.json`` catalog.

    Scans the builtin dir plus any registered extra dirs. Useful for driving
    ``/set locale`` autocomplete and for validating the shipped catalogs.
    """
    found = set()
    with _lock:
        dirs = _search_dirs()
    for directory in dirs:
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
