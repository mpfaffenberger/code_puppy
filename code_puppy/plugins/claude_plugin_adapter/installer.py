import logging
import shutil
from pathlib import Path

from code_puppy.messaging import emit_info, emit_error
from code_puppy.plugins.claude_plugin_adapter.config import (
    get_claude_plugins_dir,
    get_installed_plugins,
)
from code_puppy.plugins.claude_plugin_adapter.adapters.skills import sync_skills_adapter
from code_puppy.plugins.claude_plugin_adapter.adapters.mcp import sync_mcp_adapter
from code_puppy.plugins.claude_plugin_adapter.adapters.agents import sync_agents_adapter

logger = logging.getLogger(__name__)


def install_plugin(plugin_path_str: str) -> bool:
    """Install a plugin from a local directory (copied into claude_plugins)."""
    source_dir = Path(plugin_path_str).resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        emit_error(
            f"Cannot install: path {source_dir} does not exist or is not a directory."
        )
        return False

    plugin_name = source_dir.name
    dest_dir = get_claude_plugins_dir() / plugin_name

    if dest_dir.exists():
        emit_info(f"Plugin {plugin_name} is already installed. Overwriting...")
        shutil.rmtree(dest_dir)

    try:
        shutil.copytree(source_dir, dest_dir)
    except Exception as e:
        emit_error(f"Failed to copy plugin files: {e}")
        return False

    # Sync adapters
    _sync_plugin(plugin_name)

    # Reload agent
    _trigger_agent_reload()
    emit_info(f"Successfully installed Claude plugin '{plugin_name}'")
    return True


def uninstall_plugin(plugin_name: str) -> bool:
    """Uninstall a plugin and remove its hooks/agents/mcp/skills."""
    plugins = get_installed_plugins()
    if plugin_name not in plugins:
        emit_error(f"Plugin '{plugin_name}' is not installed.")
        return False

    # Run syncs with uninstall=True BEFORE removing the directory
    try:
        sync_agents_adapter(plugin_name, uninstall=True)
        sync_mcp_adapter(plugin_name, uninstall=True)
        sync_skills_adapter(plugin_name, uninstall=True)
    except Exception as e:
        logger.error(f"Failed to clean up synced assets for {plugin_name}: {e}")

    # Remove directory
    dest_dir = get_claude_plugins_dir() / plugin_name
    try:
        shutil.rmtree(dest_dir)
    except Exception as e:
        emit_error(f"Failed to remove plugin directory: {e}")
        return False

    _trigger_agent_reload()
    emit_info(f"Successfully uninstalled Claude plugin '{plugin_name}'")
    return True


def _sync_plugin(plugin_name: str):
    """Run all adapters for a plugin."""
    try:
        sync_skills_adapter(plugin_name)
        sync_mcp_adapter(plugin_name)
        sync_agents_adapter(plugin_name)
    except Exception as e:
        logger.error(f"Failed to sync plugin {plugin_name}: {e}")


def _trigger_agent_reload():
    """Trigger agent reload to pick up new tools/agents."""
    try:
        from code_puppy.agents.agent_manager import get_current_agent

        current = get_current_agent()
        if current:
            current.reload_code_generation_agent()

        # Also re-initialize the hook engine by firing the agent_reload hook
        from code_puppy.callbacks import _trigger_callbacks_sync

        _trigger_callbacks_sync("agent_reload")
    except Exception as e:
        logger.error(f"Error during agent reload: {e}")
