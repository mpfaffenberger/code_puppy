"""
MCP Interactive Wizard Utilities - Shared interactive installation wizard functions.

Provides interactive functionality for installing and configuring MCP servers.
"""

import logging
from typing import Any, Dict, Optional

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_prompt

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

        # Collect environment variables and command line arguments
        env_vars = {}
        cmd_args = {}

        # Get environment variables
        required_env_vars = selected_server.get_environment_vars()
        if required_env_vars:
            emit_info(
                Text.from_markup("\n[yellow]Required Environment Variables:[/yellow]"),
                message_group=group_id,
            )
            for var in required_env_vars:
                # Check if already set in environment
                import os

                current_value = os.environ.get(var, "")
                if current_value:
                    emit_info(
                        Text.from_markup(f"  {var}: [green]Already set[/green]"),
                        message_group=group_id,
                    )
                    env_vars[var] = current_value
                else:
                    value = emit_prompt(f"  Enter value for {var}: ").strip()
                    if value:
                        env_vars[var] = value

        # Get command line arguments
        required_cmd_args = selected_server.get_command_line_args()
        if required_cmd_args:
            emit_info(
                Text.from_markup("\n[yellow]Command Line Arguments:[/yellow]"),
                message_group=group_id,
            )
            for arg_config in required_cmd_args:
                name = arg_config.get("name", "")
                prompt = arg_config.get("prompt", name)
                default = arg_config.get("default", "")
                required = arg_config.get("required", True)

                # If required or has default, prompt user
                if required or default:
                    arg_prompt = f"  {prompt}"
                    if default:
                        arg_prompt += f" [{default}]"
                    if not required:
                        arg_prompt += " (optional)"

                    value = emit_prompt(f"{arg_prompt}: ").strip()
                    if value:
                        cmd_args[name] = value
                    elif default:
                        cmd_args[name] = default

        # Configure the server
        return interactive_configure_server(
            manager, selected_server, server_name, group_id, env_vars, cmd_args
        )

    except ImportError:
        emit_error("Server catalog not available", message_group=group_id)
        return False
    except Exception as e:
        logger.error(f"Error in interactive wizard: {e}")
        emit_error(f"Wizard error: {e}", message_group=group_id)
        return False


def interactive_server_selection(group_id: str):
    """
    Interactive server selection from catalog.

    Returns selected server or None if cancelled.
    """
    # This is a simplified version - the full implementation would have
    # category browsing, search, etc. For now, we'll just show popular servers
    try:
        from code_puppy.mcp_.server_registry_catalog import catalog

        servers = catalog.get_popular(10)
        if not servers:
            emit_info("No servers available in catalog", message_group=group_id)
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
                emit_error("Invalid selection", message_group=group_id)
                return None
        except ValueError:
            emit_error("Invalid input", message_group=group_id)
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
    manager,
    selected_server,
    server_name: str,
    group_id: str,
    env_vars: Dict[str, Any],
    cmd_args: Dict[str, Any],
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

        # Show confirmation
        emit_info(f"Installing: {selected_server.display_name}", message_group=group_id)
        emit_info(f"Name: {server_name}", message_group=group_id)

        if env_vars:
            emit_info("Environment Variables:", message_group=group_id)
            for var, value in env_vars.items():
                emit_info(f"  {var}: ***", message_group=group_id)

        if cmd_args:
            emit_info("Command Line Arguments:", message_group=group_id)
            for arg, value in cmd_args.items():
                emit_info(f"  {arg}: {value}", message_group=group_id)

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
        emit_error(f"Configuration error: {e}", message_group=group_id)
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
        from code_puppy.mcp_.managed_server import ServerConfig

        # Set environment variables in the current environment
        for var, value in env_vars.items():
            os.environ[var] = value

        # Get server config with command line argument overrides
        config_dict = selected_server.to_server_config(server_name, **cmd_args)

        # Update the config with actual environment variable values
        if "env" in config_dict:
            for env_key, env_value in config_dict["env"].items():
                # If it's a placeholder like $GITHUB_TOKEN, replace with actual value
                if env_value.startswith("$"):
                    var_name = env_value[1:]  # Remove the $
                    if var_name in env_vars:
                        config_dict["env"][env_key] = env_vars[var_name]

        # Create ServerConfig
        server_config = ServerConfig(
            id=server_name,
            name=server_name,
            type=selected_server.type,
            enabled=True,
            config=config_dict,
        )

        # Register with manager
        server_id = manager.register_server(server_config)

        if not server_id:
            emit_info(
                "Failed to register server with manager",
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
        # Copy the config dict and add type before saving
        save_config = config_dict.copy()
        save_config["type"] = selected_server.type
        servers[server_name] = save_config

        # Save back
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        emit_info(
            Text.from_markup(
                f"[green]✓ Successfully installed server: {server_name}[/green]"
            ),
            message_group=group_id,
        )
        emit_info(
            "Use '/mcp start {}' to start the server".format(server_name),
            message_group=group_id,
        )

        return True

    except Exception as e:
        logger.error(f"Error installing server: {e}")
        emit_error(f"Installation failed: {e}", message_group=group_id)
        return False
