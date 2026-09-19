"""Message catalog format, loader, and the missing-key fallback chain.

Catalogs are JSON files under ``code_puppy/i18n/locales/<locale>.json``.
Plugin-owned catalogs can register Traversable resources with
:func:`register_plugin_catalog`; legacy override/language-pack directories use
:func:`add_catalog_dir`.

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
import threading
from importlib.resources.abc import Traversable

from .locale import DEFAULT_LOCALE, fallback_chain
from .plugin_catalog import (
    CatalogEntry,
    PluginCatalogProvider as _PluginCatalogProvider,
    _is_valid_entry,
    canonical_plugin_namespace,
    is_safe_locale as _is_safe_locale,
    read_plugin_catalogs as _read_plugin_catalogs,
    resource_name as _resource_name,
)

logger = logging.getLogger(__name__)

# Kept private for existing tests and diagnostics that inspect canonical owners.
_canonical_plugin_namespace = canonical_plugin_namespace

# A catalog entry is a bare string or a plural-forms mapping.
Catalog = dict[str, CatalogEntry]

# Bundled catalogs ship next to this module.
_BUILTIN_DIR = os.path.join(os.path.dirname(__file__), "locales")

# Legacy extra directories are merged after builtin and plugin catalogs so
# later registrations preserve their historical override behavior.
_extra_dirs: list[str] = []


# Plugin contributions are staged while one plugin import executes and committed
# only when the loader reports that the whole import completed. This keeps a
# a plugin that registers a catalog and then crashes from leaking partial state.
_plugin_catalogs: dict[str, _PluginCatalogProvider] = {}
_pending_plugin_catalogs: dict[object, dict[str, _PluginCatalogProvider]] = {}

# locale -> merged catalog. Cleared by reset() / registration changes.
_cache: dict[str, Catalog] = {}

# Bumped whenever registration or plugin state changes. A loader that released
# the lock for file I/O uses this to detect that its result went stale mid-flight
# and must not poison the cache (see load_catalog).
_generation = 0

# Guards all catalog registrations, _cache, and _generation. lookup() runs on
# every t() call, which the message queue can dispatch from both the main thread
# and its daemon thread, so these globals are genuinely shared mutable state.
_lock = threading.RLock()


def add_catalog_dir(path: str) -> None:
    """Register an additional directory of ``<locale>.json`` catalogs.

    Later-registered dirs win over earlier ones, and all registered dirs win
    over the builtin catalogs. Registering invalidates the cache.
    """
    global _generation
    with _lock:
        if path not in _extra_dirs:
            _extra_dirs.append(path)
            _cache.clear()
            _generation += 1


def reset() -> None:
    """Drop cached catalogs and legacy directory registrations.

    Loaded plugin providers survive: their modules may already be imported and
    cannot be expected to execute registration code again. Tests needing full
    process isolation use :func:`_reset_plugin_catalogs_for_testing` as well.
    """
    global _generation
    with _lock:
        _cache.clear()
        _extra_dirs.clear()
        _generation += 1


def _reset_plugin_catalogs_for_testing() -> None:
    """Clear plugin providers in addition to :func:`reset` (test isolation)."""
    global _generation
    with _lock:
        _cache.clear()
        _plugin_catalogs.clear()
        _pending_plugin_catalogs.clear()
        _generation += 1


def _search_dirs() -> list[str]:
    # Extra dirs are searched last so their entries overwrite the builtins
    # during the dict merge below. Caller must hold _lock.
    return [_BUILTIN_DIR, *_extra_dirs]


def _error_text(error: Exception) -> str:
    """Render an exception defensively for a fail-soft public boundary."""
    try:
        return str(error)
    except MemoryError:
        raise
    except Exception:  # noqa: BLE001 - broken third-party exception rendering.
        return f"<{type(error).__name__}>"


def register_plugin_catalog(
    resource: Traversable | os.PathLike[str],
) -> bool:
    """Stage plugin-owned locale JSON resources during normal plugin loading.

    ``resource`` may be an :mod:`importlib.resources` Traversable or a
    :class:`pathlib.Path`. Ownership is derived from the active plugin loader;
    callers cannot provide it. The provider is validated atomically and becomes
    visible only after the surrounding plugin import succeeds.

    Returns ``True`` when accepted (including an identical repeat), otherwise
    logs an actionable warning and returns ``False`` without changing catalogs.
    """
    from code_puppy.callbacks import _get_loading_transaction

    transaction = _get_loading_transaction()
    if transaction is None:
        resource_label = _resource_name(resource)
        logger.warning(
            "Rejecting plugin i18n catalog from %s: registration must run during "
            "normal plugin loading",
            resource_label,
        )
        return False
    owner = transaction.owner
    transaction_id = transaction.transaction_id

    # Traversable implementations are plugin code and may block. Never pin the
    # transaction guard across I/O; parse into detached immutable state first,
    # then recheck/stage while loader deactivation is excluded.
    try:
        provider = _read_plugin_catalogs(owner, resource)
    except MemoryError:
        raise
    except Exception as exc:  # noqa: BLE001 - public registration is fail-soft.
        resource_label = _resource_name(resource)
        error_text = _error_text(exc)
        logger.warning(
            "Rejecting i18n catalogs for plugin %r from %s: %s",
            owner,
            resource_label,
            error_text,
        )
        return False

    with transaction.guard:
        if not all(context.active for context in transaction.lineage()):
            logger.warning(
                "Rejecting i18n catalogs for plugin %r from %s: plugin loading "
                "finished before registration completed",
                owner,
                provider.resource,
            )
            return False

        with _lock:
            pending = _pending_plugin_catalogs.get(transaction_id, {})
            lineage_providers = [
                other
                for context in transaction.lineage()
                for other in _pending_plugin_catalogs.get(
                    context.transaction_id, {}
                ).values()
            ]
            previous = next(
                (
                    other
                    for other in (*_plugin_catalogs.values(), *lineage_providers)
                    if other.owner == owner
                ),
                None,
            )
            if previous is not None:
                if (
                    previous.namespace == provider.namespace
                    and previous.catalogs == provider.catalogs
                ):
                    return True
                logger.warning(
                    "Rejecting i18n catalogs for plugin %r from %s: owner already "
                    "registered a different catalog provider",
                    owner,
                    provider.resource,
                )
                return False

            for other in (*_plugin_catalogs.values(), *lineage_providers):
                if other.owner != owner and other.namespace == provider.namespace:
                    logger.warning(
                        "Rejecting i18n catalogs for plugin %r from %s: namespace "
                        "%r collides with plugin %r",
                        owner,
                        provider.resource,
                        provider.namespace,
                        other.owner,
                    )
                    return False
            staged = dict(pending)
            staged[owner] = provider
            _pending_plugin_catalogs[transaction_id] = staged
    return True


def _merge_pending_provider(
    target: dict[str, _PluginCatalogProvider], provider: _PluginCatalogProvider
) -> bool:
    """Merge one child savepoint into its parent without replacing conflicts."""
    previous = target.get(provider.owner) or _plugin_catalogs.get(provider.owner)
    if previous is not None:
        if (
            previous.namespace == provider.namespace
            and previous.catalogs == provider.catalogs
        ):
            return True
        logger.warning(
            "Rejecting i18n catalogs for plugin %r from %s: owner already "
            "registered a different catalog provider",
            provider.owner,
            provider.resource,
        )
        return False

    for other in (*_plugin_catalogs.values(), *target.values()):
        if other.owner != provider.owner and other.namespace == provider.namespace:
            logger.warning(
                "Rejecting i18n catalogs for plugin %r from %s: namespace %r "
                "collides with plugin %r",
                provider.owner,
                provider.resource,
                provider.namespace,
                other.owner,
            )
            return False
    target[provider.owner] = provider
    return True


def _finish_plugin_catalog_load(
    transaction_id: object,
    *,
    parent_transaction_id: object | None,
    succeeded: bool,
) -> None:
    """Roll back, atomically transfer, or atomically publish one savepoint."""
    global _generation, _plugin_catalogs
    with _lock:
        providers = _pending_plugin_catalogs.get(transaction_id, {})
        if not succeeded or not providers:
            _pending_plugin_catalogs.pop(transaction_id, None)
            return

        try:
            if parent_transaction_id is not None:
                prospective_parent = dict(
                    _pending_plugin_catalogs.get(parent_transaction_id, {})
                )
                for provider in providers.values():
                    if not _merge_pending_provider(prospective_parent, provider):
                        prospective_parent = None
                        break
            else:
                prospective_registry = dict(_plugin_catalogs)
                for provider in providers.values():
                    if not _merge_pending_provider(prospective_registry, provider):
                        prospective_registry = None
                        break
                changed = (
                    prospective_registry is not None
                    and prospective_registry != _plugin_catalogs
                )
                next_generation = _generation + 1 if changed else _generation
        except BaseException:
            # A closed transaction is never eligible for retry. Discard only its
            # savepoint; prospective parent/registry copies kept globals intact.
            _pending_plugin_catalogs.pop(transaction_id, None)
            raise

        _pending_plugin_catalogs.pop(transaction_id, None)
        if parent_transaction_id is not None:
            if prospective_parent is not None:
                _pending_plugin_catalogs[parent_transaction_id] = prospective_parent
        elif changed and prospective_registry is not None:
            _plugin_catalogs = prospective_registry
            _cache.clear()
            _generation = next_generation


def _plugin_state_changed() -> None:
    """Invalidate snapshots after an enabled/disabled plugin state change."""
    global _generation
    with _lock:
        _cache.clear()
        _generation += 1


def _disabled_plugin_owners() -> set[str]:
    try:
        from code_puppy.plugins.config import get_disabled_plugins

        return get_disabled_plugins()
    except Exception:  # noqa: BLE001 - translation remains fail-soft on config errors.
        return set()


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

    valid: Catalog = {}
    for key, entry in data.items():
        if _is_valid_entry(entry):
            valid[key] = entry
        else:
            logger.warning("Skipping malformed i18n entry %r in catalog %s", key, path)
    return valid


def _merge_catalog_snapshot(
    locale: str,
    dirs: list[str],
    providers: list[tuple[str, _PluginCatalogProvider]],
) -> Catalog:
    """Build one catalog from a stable registration snapshot."""
    merged: Catalog = _load_file(os.path.join(dirs[0], f"{locale}.json"))
    disabled = _disabled_plugin_owners() if providers else set()
    for owner, provider in providers:
        if owner in disabled:
            continue
        for key, entry in provider.catalogs.get(locale, {}).items():
            # Never expose retained provider mappings through a mutable catalog.
            merged[key] = entry if isinstance(entry, str) else dict(entry)
    for directory in dirs[1:]:
        merged.update(_load_file(os.path.join(directory, f"{locale}.json")))
    return merged


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

    # Usually one pass. A bounded optimistic retry avoids stale current-call
    # results if registrations change during I/O; pathological churn falls back
    # to one synchronized build rather than spinning forever.
    for _attempt in range(3):
        with _lock:
            cached = _cache.get(locale)
            if cached is not None:
                return cached
            dirs = _search_dirs()
            providers = sorted(_plugin_catalogs.items())
            gen = _generation

        merged = _merge_catalog_snapshot(locale, dirs, providers)

        with _lock:
            if gen == _generation:
                return _cache.setdefault(locale, merged)

    with _lock:
        cached = _cache.get(locale)
        if cached is not None:
            return cached
        merged = _merge_catalog_snapshot(
            locale, _search_dirs(), sorted(_plugin_catalogs.items())
        )
        return _cache.setdefault(locale, merged)


def available_locales() -> list[str]:
    """Return the sorted set of locales that ship a ``<locale>.json`` catalog.

    Scans the builtin dir plus any registered extra dirs. Useful for driving
    ``/set locale`` autocomplete and for validating the shipped catalogs.
    """
    found = set()
    with _lock:
        dirs = _search_dirs()
        providers = list(_plugin_catalogs.items())
    for directory in dirs:
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        for name in entries:
            if name.endswith(".json"):
                found.add(name[: -len(".json")])
    disabled = _disabled_plugin_owners() if providers else set()
    for owner, provider in providers:
        if owner not in disabled:
            found.update(provider.catalogs)
    return sorted(found)


def lookup(
    key: str, locale: str, default_locale: str = DEFAULT_LOCALE
) -> CatalogEntry | None:
    """Find ``key`` walking the locale fallback chain, most-specific first.

    Returns the raw catalog entry (string or plural dict), or ``None`` if the
    key is absent from every catalog in the chain.
    """
    for candidate in fallback_chain(locale, default_locale):
        entry = load_catalog(candidate).get(key)
        if entry is not None:
            return entry
    return None
