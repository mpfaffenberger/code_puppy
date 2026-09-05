"""Shared provider credentials, independent of the selected settings profile.

Legacy values remain readable until an explicit save or profile migration.
Migration never overwrites a different shared value and never prints secrets.
"""

from __future__ import annotations

import os
from pathlib import Path
from threading import local

from code_puppy import secret_store
from code_puppy.atomic_io import path_lock
from code_puppy.config_file import load_config, mutate_config

_discovery = local()
_known_names: set[str] = set()


def is_credential_key(key: str, *, discover: bool = True) -> bool:
    name = key.upper()
    if name.endswith(("_API_KEY", "_ACCESS_TOKEN", "_SECRET_KEY")):
        return True
    if name in _known_names:
        return True
    if not discover:
        return False
    if getattr(_discovery, "active", False):
        return False
    _discovery.active = True
    try:
        from code_puppy.provider_credentials import credential_env_var_names

        _known_names.update(credential_env_var_names())
        return name in _known_names
    finally:
        _discovery.active = False


def _name(key: str) -> str:
    return "provider_" + key.upper()


def get(key: str) -> str | None:
    return secret_store.get_secret(_name(key))


def save(key: str, value: str) -> None:
    """Explicit rotation: persist first, then update the caller's environment."""
    from code_puppy import config

    value = value.strip()
    if not value:
        from code_puppy.i18n import t

        raise ValueError(t("credentials.empty"))
    with path_lock(str(Path(config.CONFIG_DIR) / "provider_credentials")):
        secret_store.set_secret(_name(key), value)

        # Explicit rotation supersedes this config's legacy value. Other
        # profiles are still checked for conflicts by batch migration.
        def remove_legacy(parser):
            return (
                parser.remove_option(config.DEFAULT_SECTION, key)
                if parser.has_section(config.DEFAULT_SECTION)
                else False
            )

        mutate_config(str(config.CONFIG_FILE), remove_legacy)
    _known_names.add(key.upper())
    os.environ[key.upper()] = value


def migrate(paths: list[str]) -> None:
    """Migrate configs as a batch, preflighting conflicts before any writes.

    Keep source files intact on storage failure. Only remove a legacy value if
    it still equals the value successfully persisted (concurrent edits survive).
    """
    from code_puppy import config
    from code_puppy.i18n import t

    with path_lock(str(Path(config.CONFIG_DIR) / "provider_credentials")):
        pending: dict[str, str] = {}
        for path in paths:
            parser = load_config(path)
            for key, value in (
                parser.items(config.DEFAULT_SECTION)
                if parser.has_section(config.DEFAULT_SECTION)
                else []
            ):
                if not value or not is_credential_key(key):
                    continue
                existing = pending.get(key) or get(key)
                if existing is not None and existing != value:
                    raise ValueError(t("credentials.migration_conflict", key=key))
                pending[key] = value
        for key, value in pending.items():
            secret_store.set_secret(_name(key), value)
            if get(key) != value:
                raise OSError(t("credentials.migration_failed"))
        if not pending:
            return
        for path in paths:

            def remove_saved(parser):
                changed = False
                if parser.has_section(config.DEFAULT_SECTION):
                    for key, value in pending.items():
                        if (
                            parser.get(config.DEFAULT_SECTION, key, fallback=None)
                            == value
                        ):
                            changed |= parser.remove_option(config.DEFAULT_SECTION, key)
                return changed

            mutate_config(path, remove_saved)
