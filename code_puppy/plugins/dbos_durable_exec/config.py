"""Plugin-local config accessors for DBOS durable execution."""

from __future__ import annotations

import os

from code_puppy.config import DATA_DIR, get_value, set_config_value

_DEFAULT_SQLITE_FILE = os.path.join(DATA_DIR, "dbos_store.sqlite")

DBOS_DATABASE_URL = os.environ.get(
    "DBOS_SYSTEM_DATABASE_URL", f"sqlite:///{_DEFAULT_SQLITE_FILE}"
)


def is_enabled() -> bool:
    """Return True if 'enable_dbos' in puppy.cfg is truthy. Default: True."""
    cfg_val = get_value("enable_dbos")
    if cfg_val is None:
        return True
    return str(cfg_val).strip().lower() in ("true", "1", "yes", "on")


def feature_capability(name: str) -> bool | None:
    """Expose plugin state through the generic feature-capability callback."""
    return is_enabled() if name == "dbos_durable_exec" else None


def set_enabled(enabled: bool) -> None:
    """Persist the 'enable_dbos' switch to puppy.cfg."""
    set_config_value("enable_dbos", "true" if enabled else "false")
