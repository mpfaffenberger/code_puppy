"""
MCP Add Command - Adds new MCP servers from JSON configuration or wizard.
"""

import json
import logging
import os
from typing import List, Optional

from code_puppy.messaging import emit_info
from code_puppy.state_management import is_tui_mode

from .base import MCPCommandBase
from .wizard_utils import run_interactive_install_wizard

# Configure logging
logger = logging.getLogger(__name__)


class AddCommand(MCPCommandBase):
    """
    Command handler for adding MCP servers.

    Adds new MCP servers from JSON configuration or interactive wizard.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Add a new MCP server from JSON configuration or launch wizard.

        Usage:
            /mcp add                    - Launch interactive wizard
            /mcp add <json>             - Add server from JSON config

        Example JSON:
            /mcp add {"name": "test", "type": "stdio", "command": "echo", "args": ["hello"]}

        Args:
            args: Command arguments - JSON config or empty for wizard
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        # Check if in TUI mode and guide user to use Ctrl+T instead
        if is_tui_mode() and not args:
            emit_info(
                "💡 In TUI mode, press Ctrl+T to open the MCP Install Wizard",
                message_group=group_id,
            )
            emit_info(
                "   The wizard provides a better interface for browsing and installing MCP servers.",
                message_group=group_id,
            )
            return

        try:
            if args:
                # Parse JSON from arguments
                json_str = " ".join(args)

                try:
                    config_dict = json.loads(json_str)
                except json.JSONDecodeError as e:
                    emit_info(f"Invalid JSON: {e}", message_group=group_id)
                    emit_info(
                        "Usage: /mcp add <json> or /mcp add (for wizard)",
                        message_group=group_id,
                    )
                    emit_info(
                        'Example: /mcp add {"name": "test", "type": "stdio", "command": "echo"}',
                        message_group=group_id,
                    )
                    return

                # Validate required fields
                if "name" not in config_dict:
                    emit_info("Missing required field: 'name'", message_group=group_id)
                    return
                if "type" not in config_dict:
                    emit_info("Missing required field: 'type'", message_group=group_id)
                    return

                # Add the server
                success = self._add_server_from_json(config_dict, group_id)

                if success:
                    # Reload MCP servers
                    try:
                        from code_puppy.agent import reload_mcp_servers

                        reload_mcp_servers()
                    except ImportError:
                        pass

                    emit_info(
                        "Use '/mcp list' to see all servers", message_group=group_id
                    )

            else:
                # No arguments - launch interactive wizard with server templates
                success = run_interactive_install_wizard(self.manager, group_id)

                if success:
                    # Reload the agent to pick up new server
                    try:
                        from code_puppy.agent import reload_mcp_servers

                        reload_mcp_servers()
                    except ImportError:
                        pass

        except ImportError as e:
            logger.error(f"Failed to import: {e}")
            emit_info("Required module not available", message_group=group_id)
        except Exception as e:
            logger.error(f"Error in add command: {e}")
            emit_info(f"[red]Error adding server: {e}[/red]", message_group=group_id)

    def _add_server_from_json(self, config_dict: dict, group_id: str) -> bool:
        """
        Add a server from JSON configuration.

        Args:
            config_dict: Server configuration dictionary
            group_id: Message group ID

        Returns:
            True if successful, False otherwise
        """
        try:
            from code_puppy.config import MCP_SERVERS_FILE
            from code_puppy.mcp.managed_server import ServerConfig

            # Extract required fields
            name = config_dict.pop("name")
            server_type = config_dict.pop("type")
            enabled = config_dict.pop("enabled", True)

            # Everything else goes into config
            server_config = ServerConfig(
                id=f"{name}_{hash(name)}",
                name=name,
                type=server_type,
                enabled=enabled,
                config=config_dict,  # Remaining fields are server-specific config
            )

            # Register the server
            server_id = self.manager.register_server(server_config)

            if not server_id:
                emit_info(f"Failed to add server '{name}'", message_group=group_id)
                return False

            emit_info(
                f"✅ Added server '{name}' (ID: {server_id})", message_group=group_id
            )

            # Save to mcp_servers.json for persistence
            if os.path.exists(MCP_SERVERS_FILE):
                with open(MCP_SERVERS_FILE, "r") as f:
                    data = json.load(f)
                    servers = data.get("mcp_servers", {})
            else:
                servers = {}
                data = {"mcp_servers": servers}

            # Add new server
            servers[name] = config_dict.copy()
            servers[name]["type"] = server_type

            # Save back
            os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
            with open(MCP_SERVERS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            logger.error(f"Error adding server from JSON: {e}")
            emit_info(f"[red]Failed to add server: {e}[/red]", message_group=group_id)
            return False
