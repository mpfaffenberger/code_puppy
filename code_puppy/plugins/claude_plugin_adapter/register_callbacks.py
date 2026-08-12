import logging
from typing import Optional, Union
from code_puppy.callbacks import register_callback
from code_puppy.plugins.claude_plugin_adapter.config import get_installed_plugins
from code_puppy.plugins.claude_plugin_adapter.adapters.skills import sync_skills_adapter
from code_puppy.plugins.claude_plugin_adapter.adapters.mcp import sync_mcp_adapter
from code_puppy.plugins.claude_plugin_adapter.adapters.agents import sync_agents_adapter
from code_puppy.plugins.claude_plugin_adapter.installer import install_plugin, uninstall_plugin

logger = logging.getLogger(__name__)

def _on_startup():
    logger.info("claude_plugin_adapter: Initializing and resyncing plugins...")
    plugins = get_installed_plugins()
    for plugin_name in plugins:
        try:
            sync_skills_adapter(plugin_name)
            sync_mcp_adapter(plugin_name)
            sync_agents_adapter(plugin_name)
        except Exception as e:
            logger.error(f"Failed to sync adapter for {plugin_name}: {e}")

def _custom_command(command: str, args: str) -> Union[bool, str, None]:
    if command == "plugin":
        parts = args.strip().split()
        if not parts:
            return "Usage: /plugin install <path> | /plugin uninstall <name>"
            
        action = parts[0]
        
        if action == "install":
            if len(parts) < 2:
                return "Usage: /plugin install <path>"
            install_plugin(parts[1])
            return True
            
        elif action == "uninstall":
            if len(parts) < 2:
                return "Usage: /plugin uninstall <name>"
            uninstall_plugin(parts[1])
            return True
            
    return None

def _custom_command_help() -> list[tuple[str, str]]:
    return [
        ("/plugin install <path>", "Install a Claude plugin from a directory"),
        ("/plugin uninstall <name>", "Uninstall a Claude plugin by name")
    ]

register_callback("startup", _on_startup)
register_callback("custom_command", _custom_command)
register_callback("custom_command_help", _custom_command_help)
