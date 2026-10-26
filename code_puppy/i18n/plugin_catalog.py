"""Validation and in-memory representation for plugin-owned message catalogs."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path
from types import MappingProxyType

from .interpolation import placeholder_names
from .locale import DEFAULT_LOCALE, normalize_locale
from .plurals import CATEGORIES

CatalogEntry = str | Mapping[str, str]

# Traversable operations are fail-soft for ordinary provider errors, but each
# broad boundary names MemoryError explicitly so process exhaustion propagates.
_SAFE_LOCALE_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_WIN_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


@dataclass(frozen=True)
class PluginCatalogProvider:
    """A validated, in-memory catalog contribution from one loaded plugin."""

    owner: str
    namespace: str
    resource: str
    catalogs: Mapping[str, Mapping[str, CatalogEntry]]


def is_safe_locale(locale: str) -> bool:
    """Return whether *locale* is safe to use in a catalog filename."""
    if not locale or _SAFE_LOCALE_RE.match(locale) is None:
        return False
    return locale.lower() not in _WIN_RESERVED


def canonical_plugin_namespace(owner: str) -> str:
    """Build the public key prefix for a loader-derived plugin owner."""
    canonical = re.sub(r"[-_.]+", "-", owner).lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", canonical):
        raise ValueError(
            "plugin name cannot form a catalog namespace; use letters, digits, "
            "dots, underscores, or hyphens"
        )
    return f"plugin.{canonical}."


def resource_name(resource: object) -> str:
    """Render an untrusted resource for diagnostics without raising normally."""
    try:
        if isinstance(resource, os.PathLike):
            return os.fspath(resource)
        rendered = str(resource)
        if not rendered.startswith("<"):
            return rendered
        name = getattr(resource, "name", None)
        return str(name) if name else f"<{type(resource).__name__}>"
    except MemoryError:
        raise
    except Exception:  # noqa: BLE001 - diagnostics must not mask rejection.
        return f"<{type(resource).__name__}>"


def _is_valid_entry(entry: object) -> bool:
    if isinstance(entry, str):
        return True
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("other"), str)
        and all(
            isinstance(category, str) and isinstance(text, str)
            for category, text in entry.items()
        )
    )


class _DuplicateCatalogKey(ValueError):
    """Raised while decoding a JSON object containing a repeated key."""


def _catalog_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateCatalogKey(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _freeze_catalog(data: dict[str, object]) -> Mapping[str, CatalogEntry]:
    frozen: dict[str, CatalogEntry] = {}
    for key, value in data.items():
        frozen[key] = value if isinstance(value, str) else MappingProxyType(dict(value))
    return MappingProxyType(frozen)


def _validate_localized_catalog(
    locale: str,
    source: Mapping[str, CatalogEntry],
    localized: Mapping[str, CatalogEntry],
) -> None:
    unknown = sorted(set(localized) - set(source))
    if unknown:
        raise ValueError(
            f"catalog {locale}.json key {unknown[0]!r} is missing from "
            f"{DEFAULT_LOCALE}.json"
        )

    for key, entry in localized.items():
        source_entry = source[key]
        source_is_plural = not isinstance(source_entry, str)
        localized_is_plural = not isinstance(entry, str)
        if source_is_plural != localized_is_plural:
            raise ValueError(
                f"catalog {locale}.json key {key!r} entry shape must match "
                f"{DEFAULT_LOCALE}.json"
            )

        localized_forms = entry if localized_is_plural else {"other": entry}
        for category, text in localized_forms.items():
            if source_is_plural:
                source_text = source_entry.get(category) or source_entry["other"]
            else:
                source_text = source_entry
            if placeholder_names(text) != placeholder_names(source_text):
                raise ValueError(
                    f"catalog {locale}.json key {key!r} placeholders for "
                    f"{category!r} must match {DEFAULT_LOCALE}.json"
                )


def read_plugin_catalogs(
    owner: str, resource: Traversable | os.PathLike[str]
) -> PluginCatalogProvider:
    """Read, validate, and freeze one plugin locale resource directory."""
    if isinstance(resource, os.PathLike):
        resource = Path(resource)
    if not all(hasattr(resource, attr) for attr in ("is_dir", "iterdir", "open")):
        raise TypeError(
            "resource must be an importlib.resources Traversable or pathlib.Path"
        )

    resource_label = resource_name(resource)
    try:
        is_dir = resource.is_dir()
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 - resource implementations vary.
        raise ValueError(
            f"cannot inspect locale resource {resource_label}: {exc}"
        ) from exc
    if not is_dir:
        raise ValueError(
            f"locale resource {resource_label} is missing or is not a directory; "
            "include the JSON files as package data"
        )

    try:
        entries = sorted(resource.iterdir(), key=lambda entry: entry.name)
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 - resource implementations vary.
        raise ValueError(
            f"cannot list locale resource {resource_label}: {exc}"
        ) from exc

    namespace = canonical_plugin_namespace(owner)
    catalogs: dict[str, Mapping[str, CatalogEntry]] = {}
    for entry in entries:
        if not entry.name.endswith(".json"):
            continue
        locale = entry.name[: -len(".json")]
        if not is_safe_locale(locale):
            raise ValueError(f"unsafe locale filename {entry.name!r}")
        canonical_locale = normalize_locale(locale)
        if canonical_locale != locale:
            expected = (
                f"{canonical_locale}.json" if canonical_locale else "a BCP-47 tag"
            )
            raise ValueError(
                f"catalog filename {entry.name!r} is not canonical; use {expected!r}"
            )
        if locale in catalogs:
            raise ValueError(f"duplicate locale catalog {entry.name!r}")
        try:
            if not entry.is_file():
                raise ValueError(f"catalog resource {entry.name!r} is not a file")
            with entry.open("r", encoding="utf-8") as stream:
                data = json.load(stream, object_pairs_hook=_catalog_object)
        except MemoryError:
            raise
        except Exception as exc:  # noqa: BLE001 - Traversable implementations vary.
            raise ValueError(f"invalid catalog {entry.name!r}: {exc}") from exc
        if not isinstance(data, dict):
            raise TypeError(f"catalog {entry.name!r} root must be a JSON object")

        invalid_keys = [key for key in data if not key.startswith(namespace)]
        if invalid_keys:
            raise ValueError(
                f"catalog {entry.name!r} key {invalid_keys[0]!r} is outside required "
                f"namespace {namespace!r}"
            )
        for key, value in data.items():
            if not _is_valid_entry(value):
                raise ValueError(
                    f"catalog {entry.name!r} has invalid value for key {key!r}; "
                    "expected a string or plural object with a string 'other' value"
                )
            if not isinstance(value, str):
                unsupported = sorted(set(value) - set(CATEGORIES))
                if unsupported:
                    raise ValueError(
                        f"catalog {entry.name!r} key {key!r} uses unsupported plural "
                        f"category {unsupported[0]!r}"
                    )
        catalogs[locale] = _freeze_catalog(data)

    source = catalogs.get(DEFAULT_LOCALE)
    if source is None:
        raise ValueError(
            f"locale resource {resource_label} must include {DEFAULT_LOCALE}.json "
            "as the source catalog"
        )
    for locale, localized in catalogs.items():
        if locale != DEFAULT_LOCALE:
            _validate_localized_catalog(locale, source, localized)

    return PluginCatalogProvider(
        owner, namespace, resource_label, MappingProxyType(catalogs)
    )
