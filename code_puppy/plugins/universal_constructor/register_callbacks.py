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
    from code_puppy.config import get_universal_constructor_enabled

    # Skip initialization if UC is disabled
    if not get_universal_constructor_enabled():
        logger.debug("Universal Constructor is disabled, skipping initialization")
        return

    logger.debug("Universal Constructor plugin initializing...")

    # Ensure the user tools directory exists
    USER_UC_DIR.mkdir(parents=True, exist_ok=True)

    # Do an initial scan of tools (lazy - will happen on first access)
    registry = get_registry()
    logger.debug(f"UC registry initialized, tools dir: {registry._tools_dir}")

    # Log plugin info at startup
    tools = registry.list_tools(include_disabled=True)
    enabled = [t for t in tools if t.meta.enabled]
    logger.debug(
        f"UC plugin loaded: {len(enabled)}/{len(tools)} tools enabled "
        f"from {USER_UC_DIR}"
    )


# Register startup callback
register_callback("startup", _on_startup)

logger.debug("Universal Constructor plugin callbacks registered")
