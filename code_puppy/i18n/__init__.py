"""English-only stand-in for the 0.0.x translation API.

Translations were dropped in 1.0. 0.0.x plugins still call ``t("key")`` and
register their own catalogs, so this resolves keys against the ``en-US``
catalogs plugins register and falls back to the key itself.

Placeholders are ``{name}`` only, substituted literally: a catalog is data,
and never gets ``str.format``'s attribute or index access.
"""

from __future__ import annotations

import json
from pathlib import Path

LOCALE = "en-US"

_catalog: dict[str, str] = {}


def add_catalog_dir(directory: str | Path, *args: object, **kwargs: object) -> bool:
    """Load ``<directory>/en-US.json``; ``False`` when it is missing or malformed."""
    path = Path(directory) / f"{LOCALE}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    _catalog.update(
        {str(key): value for key, value in data.items() if isinstance(value, str)}
    )
    return True


def register_plugin_catalog(
    plugin: str, directory: str | Path, *args: object, **kwargs: object
) -> bool:
    """0.0.x plugins register their catalog folder under their own name."""
    return add_catalog_dir(directory)


def t(key: str, **params: object) -> str:
    """The English text for ``key`` with ``{name}`` placeholders filled in."""
    text = _catalog.get(key, key)
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def ngettext(key: str, count: int, **params: object) -> str:
    """Plural lookup: ``key.one`` or ``key.other``, then ``key`` itself."""
    variant = f"{key}.one" if count == 1 else f"{key}.other"
    return t(variant if variant in _catalog else key, count=count, **params)


__all__ = ["add_catalog_dir", "ngettext", "register_plugin_catalog", "t"]
