"""
MCP Interactive Wizard Utilities - Shared interactive installation wizard functions.

Provides interactive functionality for installing and configuring MCP servers.
"""

import logging
from typing import Any, Dict, Optional

from code_puppy.messaging import emit_info, emit_prompt

# Configure logging
logger = logging.getLogger(__name__)


def run_interactive_install_wizard(manager, group_id: str) -> bool:
    """
    Run the interactive MCP server installation wizard.

    Args:
        manager: MCP manager instance
        group_id: Message group ID for grouping related messages

    Returns:
        True if installation was successful, False otherwise
    """
    try:
        # Show welcome message
        emit_info("🚀 MCP Server Installation Wizard", message_group=group_id)
        emit_info(
            "This wizard will help you install pre-configured MCP servers",
            message_group=group_id,
        )
        emit_info("", message_group=group_id)

        # Let user select a server
        selected_server = interactive_server_selection(group_id)
        if not selected_server:
            return False

        # Get custom name
        server_name = interactive_get_server_name(selected_server, group_id)
        if not server_name:
            return False

        # Configure the server
        return interactive_configure_server(
            manager, selected_server, server_name, group_id
        )

    except ImportError:
        emit_info("[red]Server catalog not available[/red]", message_group=group_id)
        return False
    except Exception as e:
        logger.error(f"Error in interactive wizard: {e}")
        emit_info(f"[red]Wizard error: {e}[/red]", message_group=group_id)
        return False


def interactive_server_selection(group_id: str):
    """
    Interactive server selection from catalog.

    Returns selected server or None if cancelled.
    """
    # This is a simplified version - the full implementation would have
    # category browsing, search, etc. For now, we'll just show popular servers
    try:
        from code_puppy.mcp.server_registry_catalog import catalog

        servers = catalog.get_popular(10)
        if not servers:
            emit_info(
                "[red]No servers available in catalog[/red]", message_group=group_id
            )
            return None

        emit_info("Popular MCP Servers:", message_group=group_id)
        for i, server in enumerate(servers, 1):
            indicators = []
            if server.verified:
                indicators.append("✓")
            if server.popular:
                indicators.append("⭐")

            indicator_str = ""
            if indicators:
                indicator_str = " " + "".join(indicators)

            emit_info(
                f"{i:2}. {server.display_name}{indicator_str}", message_group=group_id
            )
            emit_info(f"    {server.description[:80]}...", message_group=group_id)

        choice = emit_prompt(
            "Enter number (1-{}) or 'q' to quit: ".format(len(servers))
        )

        if choice.lower() == "q":
            return None

        try:
            index = int(choice) - 1
            if 0 <= index < len(servers):
                return servers[index]
            else:
                emit_info("[red]Invalid selection[/red]", message_group=group_id)
                return None
        except ValueError:
            emit_info("[red]Invalid input[/red]", message_group=group_id)
            return None

    except Exception as e:
        logger.error(f"Error in server selection: {e}")
        return None


def interactive_get_server_name(selected_server, group_id: str) -> Optional[str]:
    """
    Get custom server name from user.

    Returns server name or None if cancelled.
    """
    default_name = selected_server.name
    server_name = emit_prompt(f"Enter name for this server [{default_name}]: ").strip()

    if not server_name:
        server_name = default_name

    return server_name


def interactive_configure_server(
    manager, selected_server, server_name: str, group_id: str
) -> bool:
    """
    Configure and install the selected server.

    Returns True if successful, False otherwise.
    """
    try:
        # Check if server already exists
        from .utils import find_server_id_by_name

        existing_server = find_server_id_by_name(manager, server_name)
        if existing_server:
            override = emit_prompt(
                f"Server '{server_name}' already exists. Override? [y/N]: "
            )
            if not override.lower().startswith("y"):
                emit_info("Installation cancelled", message_group=group_id)
                return False

        # For now, use defaults - a full implementation would collect env vars, etc.
        # requirements = selected_server.get_requirements()  # TODO: Use for validation
        env_vars = {}
        cmd_args = {}

        # Show confirmation
        emit_info(f"Installing: {selected_server.display_name}", message_group=group_id)
        emit_info(f"Name: {server_name}", message_group=group_id)

        confirm = emit_prompt("Proceed with installation? [Y/n]: ")
        if confirm.lower().startswith("n"):
            emit_info("Installation cancelled", message_group=group_id)
            return False

        # Install the server (simplified version)
        return install_server_from_catalog(
            manager, selected_server, server_name, env_vars, cmd_args, group_id
        )

    except Exception as e:
        logger.error(f"Error configuring server: {e}")
        emit_info(f"[red]Configuration error: {e}[/red]", message_group=group_id)
        return False


def install_server_from_catalog(
    manager,
    selected_server,
    server_name: str,
    env_vars: Dict[str, Any],
    cmd_args: Dict[str, Any],
    group_id: str,
) -> bool:
    """
    Install a server from the catalog with the given configuration.

    Returns True if successful, False otherwise.
    """
    try:
        import json
        import os

        from code_puppy.config import MCP_SERVERS_FILE
        from code_puppy.mcp.managed_server import ServerConfig

        # Create server configuration
        config_dict = selected_server.get_config_template()

        # Apply environment variables and command args
        if env_vars:
            config_dict.update(env_vars)
        if cmd_args:
            config_dict.update(cmd_args)

        # Create ServerConfig
        server_config = ServerConfig(
            id=f"{server_name}_{hash(server_name)}",
            name=server_name,
            type=selected_server.type,
            enabled=True,
            config=config_dict,
        )

        # Register with manager
        server_id = manager.register_server(server_config)

        if not server_id:
            emit_info(
                "[red]Failed to register server with manager[/red]",
                message_group=group_id,
            )
            return False

        # Save to mcp_servers.json for persistence
        if os.path.exists(MCP_SERVERS_FILE):
            with open(MCP_SERVERS_FILE, "r") as f:
                data = json.load(f)
                servers = data.get("mcp_servers", {})
        else:
            servers = {}
            data = {"mcp_servers": servers}

        # Add new server
        servers[server_name] = config_dict.copy()
        servers[server_name]["type"] = selected_server.type

        # Save back
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        emit_info(
            f"[green]✓ Successfully installed server: {server_name}[/green]",
            message_group=group_id,
        )
        emit_info(
            "Use '/mcp start {}' to start the server".format(server_name),
            message_group=group_id,
        )

        return True

    except Exception as e:
        logger.error(f"Error installing server: {e}")
        emit_info(f"[red]Installation failed: {e}[/red]", message_group=group_id)
        return False
