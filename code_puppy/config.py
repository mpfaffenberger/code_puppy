"""The 0.0.x configuration API, for plugins written against it.

1.0 keeps its settings in SQLite. This module answers the calls 0.0.x plugins
make most (``get_value``, ``set_value``, the directory constants):

* Keys the runtime owns are *read* from its settings: ``model``, ``yolo_mode``
  and ``message_limit``. Writing them here does not change the runtime; use
  ``/set`` or ``/model``.
* Every other key is read from and written to ``puppy.db``, which the
  migration seeded from ``puppy.cfg``.

New code should not import this module.
"""

from __future__ import annotations

import os

from code_puppy import identity
from code_puppy.legacy_store import LegacyStore
from code_puppy.migrate.translate import is_truthy

CONFIG_DIR = str(identity.config_dir())
DATA_DIR = str(identity.data_dir())
CACHE_DIR = str(identity.cache_dir())
STATE_DIR = str(identity.state_dir())

CONFIG_FILE = os.path.join(CONFIG_DIR, "puppy.cfg")
MCP_SERVERS_FILE = os.path.join(CONFIG_DIR, "mcp_servers.json")
MODELS_FILE = os.path.join(DATA_DIR, "models.json")
EXTRA_MODELS_FILE = os.path.join(DATA_DIR, "extra_models.json")
AGENTS_DIR = os.path.join(DATA_DIR, "agents")
SKILLS_DIR = os.path.join(DATA_DIR, "skills")
AUTOSAVE_DIR = os.path.join(CACHE_DIR, "autosaves")
COMMAND_HISTORY_FILE = os.path.join(STATE_DIR, "command_history.txt")

DEFAULT_SECTION = "puppy"


def _runtime_value(key: str) -> str | None:
    """A key the runtime owns, in the string form 0.0.x returned."""
    from pydantic_ai_pax.config.settings_store import SettingsStore

    settings = SettingsStore().load()
    if key == "model":
        return settings.model
    if key == "yolo_mode":
        return "true" if settings.permissions == "full" else "false"
    return str(settings.request_limit)


RUNTIME_KEYS = frozenset({"model", "yolo_mode", "message_limit"})


def get_value(key: str) -> str | None:
    """The stored value of ``key``, or ``None`` when it was never set."""
    if key in RUNTIME_KEYS:
        return _runtime_value(key)
    return LegacyStore().get(key)


def set_config_value(key: str, value: str) -> None:
    """Store ``value`` under ``key`` for 0.0.x plugins to read back."""
    LegacyStore().set(key, str(value))


def set_value(key: str, value: str) -> None:
    """Store ``value``; an empty value forgets the key, as 0.0.x did."""
    if value is None or value == "":
        LegacyStore().delete(key)
    else:
        set_config_value(key, value)


def get_config_keys() -> list[str]:
    return sorted({*LegacyStore().items(), *RUNTIME_KEYS})


def get_truthy_bool_value(key: str, default: bool = False) -> bool:
    value = get_value(key)
    if value is None or not value.strip():
        return default
    return is_truthy(value)


def get_global_model_name() -> str:
    return get_value("model") or ""


def get_yolo_mode() -> bool:
    return get_truthy_bool_value("yolo_mode", True)


def get_message_limit(default: int = 1000) -> int:
    value = get_value("message_limit")
    return int(value) if value and value.isdigit() else default


def _personality_name(key: str) -> str:
    """A name from the personality plugin's settings, where 1.0 keeps them."""
    from pydantic_ai_pax.config.settings_store import SettingsStore

    from code_puppy import first_run, personality

    declaration = first_run.declaration(SettingsStore())
    value = declaration.settings.get(key) if declaration is not None else None
    if isinstance(value, str) and value:
        return value
    return LegacyStore().get(key) or personality.default_name(key)


def get_puppy_name() -> str:
    return _personality_name("puppy_name")


def get_owner_name() -> str:
    return _personality_name("owner_name")
