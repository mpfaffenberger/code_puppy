"""Callback registration for the Universal Constructor plugin.

This module registers callbacks to integrate UC with the rest of
Code Puppy. It ensures the plugin is properly loaded and initialized.
"""

import logging

from code_puppy.callbacks import register_callback

from . import USER_UC_DIR
from .registry import get_registry

logger = logging.getLogger(__name__)


def _on_startup() -> None:
    """Initialize UC plugin on application startup."""
    logger.debug("Universal Constructor plugin initializing...")

    # Ensure the user tools directory exists
    USER_UC_DIR.mkdir(parents=True, exist_ok=True)

    # Do an initial scan of tools (lazy - will happen on first access)
    registry = get_registry()
    logger.debug(f"UC registry initialized, tools dir: {registry._tools_dir}")


def _uc_plugin_info() -> dict:
    """Return plugin information for status displays."""
    registry = get_registry()
    tools = registry.list_tools(include_disabled=True)
    enabled = [t for t in tools if t.meta.enabled]

    return {
        "name": "Universal Constructor",
        "version": "1.0.0",
        "tools_dir": str(USER_UC_DIR),
        "total_tools": len(tools),
        "enabled_tools": len(enabled),
    }


# Register callbacks
# The startup callback ensures the directory exists when the app starts
register_callback("startup", _on_startup)
register_callback("plugin_info", _uc_plugin_info)

# Run startup initialization when this module loads
_on_startup()

logger.debug("Universal Constructor plugin callbacks registered")
