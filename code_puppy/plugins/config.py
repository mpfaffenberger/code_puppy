"""Central config helpers for the plugin system.

Follows the same pattern as ``agent_skills.config`` — a ``disabled_plugins``
JSON list in ``puppy.cfg`` controls which plugins are suppressed at runtime.

Plugins listed here are still *loaded* (their ``register_callbacks.py`` is
imported) but their callbacks are **skipped** during dispatch.  This means
toggling takes effect immediately without a restart.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Set

from code_puppy.config import get_value, set_value

logger = logging.getLogger(__name__)

# Hidden config key. When truthy, builtin plugins cannot be disabled and are
# hidden from the /plugins menu. A general-purpose deployment lock: managed
# distributions (corporate forks, kiosk installs) can flip it to protect the
# shipped plugin set from being switched off by end users.
LOCK_BUILTIN_KEY = "lock_builtin_plugins"


def get_lock_builtin_plugins() -> bool:
    """Whether builtin plugins are locked (un-disableable + hidden)."""
    raw = get_value(LOCK_BUILTIN_KEY)
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def set_lock_builtin_plugins(locked: bool) -> None:
    """Set the builtin-plugin lock. Idempotent at the config layer."""
    set_value(LOCK_BUILTIN_KEY, "true" if locked else "false")


def is_builtin_plugin(plugin_name: str) -> bool:
    """True if *plugin_name* is a builtin (shipped in code_puppy/plugins/).

    Filesystem ground-truth so the check is independent of plugin load order.
    """
    import code_puppy.plugins as plugins_pkg

    plugin_dir = Path(plugins_pkg.__file__).parent / plugin_name
    return plugin_dir.is_dir() and (plugin_dir / "register_callbacks.py").exists()


def get_disabled_plugins() -> Set[str]:
    """Return the set of explicitly disabled plugin names.

    Reads from ``disabled_plugins`` config key (JSON list in puppy.cfg).
    """
    config_value = get_value("disabled_plugins")
    if config_value:
        try:
            disabled_list = json.loads(config_value)
            if isinstance(disabled_list, list):
                return set(disabled_list)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse disabled_plugins config: {e}")
    return set()


def is_plugin_disabled(plugin_name: str) -> bool:
    """Check whether *plugin_name* is currently disabled."""
    return plugin_name in get_disabled_plugins()


def set_plugin_disabled(plugin_name: str, disabled: bool) -> bool:
    """Disable or re-enable a plugin by name.

    Returns ``True`` if the state changed, ``False`` if it was already in the
    requested state (or if the change was refused).

    When the builtin lock is active, requests to *disable* a builtin plugin
    are refused outright — re-enabling is always allowed so the lock can
    never strand a builtin in the disabled set.
    """
    if disabled and get_lock_builtin_plugins() and is_builtin_plugin(plugin_name):
        logger.warning(
            f"Refusing to disable builtin plugin '{plugin_name}': "
            f"builtin plugins are locked ({LOCK_BUILTIN_KEY})."
        )
        return False

    disabled_plugins = get_disabled_plugins()

    if disabled:
        if plugin_name in disabled_plugins:
            logger.info(f"Plugin already disabled: {plugin_name}")
            return False
        disabled_plugins.add(plugin_name)
        logger.info(f"Disabled plugin: {plugin_name}")
    else:
        if plugin_name not in disabled_plugins:
            logger.info(f"Plugin already enabled: {plugin_name}")
            return False
        disabled_plugins.remove(plugin_name)
        logger.info(f"Enabled plugin: {plugin_name}")

    set_value("disabled_plugins", json.dumps(sorted(disabled_plugins)))
    return True
