"""Central config helpers for the plugin system.

Follows the same pattern as ``agent_skills.config`` — a ``disabled_plugins``
JSON list in ``mist.cfg`` controls which plugins are suppressed at runtime.

Plugins listed here are still *loaded* (their ``register_callbacks.py`` is
imported) but their callbacks are **skipped** during dispatch.  This means
toggling takes effect immediately without a restart.
"""

from __future__ import annotations

import json
import logging
from typing import Set

from code_puppy.config import get_value, set_value

logger = logging.getLogger(__name__)


def get_disabled_plugins() -> Set[str]:
    """Return the set of explicitly disabled plugin names.

    Reads from ``disabled_plugins`` config key (JSON list in mist.cfg).
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
    requested state.
    """
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
