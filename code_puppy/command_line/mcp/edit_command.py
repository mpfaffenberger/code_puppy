"""MCP Edit Command - Edit existing MCP server configurations.

Provides a TUI for editing custom MCP server configurations.
"""

import json
import logging
import os
from typing import List, Optional

from code_puppy.config import MCP_SERVERS_FILE
from code_puppy.messaging import emit_info
from code_puppy.tui_state import is_tui_mode

from .base import MCPCommandBase
from .custom_server_form import run_custom_server_form

# Configure logging
logger = logging.getLogger(__name__)


class EditCommand(MCPCommandBase):
    """Command handler for editing existing MCP servers.

    Opens the same TUI form as /mcp install custom, but pre-populated
    with the existing server's configuration.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """Edit an existing MCP server configuration.

        Args:
            args: Server name to edit
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            # If in TUI mode, show message
            if is_tui_mode():
                emit_info(
                    "In TUI mode, use Ctrl+T to manage MCP servers",
                    message_group=group_id,
                )
                return

            # Need a server name
            if not args:
                emit_info(
                    "[yellow]Usage: /mcp edit <server_name>[/yellow]",
                    message_group=group_id,
                )
                emit_info(
                    "Use '/mcp list' to see available servers.",
                    message_group=group_id,
                )
                return

            server_name = args[0]

            # Load existing server config
            server_config = self._load_server_config(server_name, group_id)
            if server_config is None:
                return

            server_type, config_dict = server_config

            # Run the form in edit mode
            success = run_custom_server_form(
                self.manager,
                edit_mode=True,
                existing_name=server_name,
                existing_type=server_type,
                existing_config=config_dict,
            )

            if success:
                # Reload MCP servers to pick up changes
                try:
                    from code_puppy.agent import reload_mcp_servers

                    reload_mcp_servers()
                except ImportError:
                    pass

        except Exception as e:
            logger.error(f"Error editing server: {e}")
            emit_info(f"[red]Error: {e}[/red]", message_group=group_id)

    def _load_server_config(
        self, server_name: str, group_id: str
    ) -> Optional[tuple[str, dict]]:
        """Load an existing server configuration from mcp_servers.json.

        Args:
            server_name: Name of the server to load
            group_id: Message group ID for output

        Returns:
            Tuple of (server_type, config_dict) or None if not found
        """
        if not os.path.exists(MCP_SERVERS_FILE):
            emit_info(
                "[red]No MCP servers configured yet.[/red]",
                message_group=group_id,
            )
            emit_info(
                "Use '/mcp install' to add a server first.",
                message_group=group_id,
            )
            return None

        try:
            with open(MCP_SERVERS_FILE, "r") as f:
                data = json.load(f)

            servers = data.get("mcp_servers", {})

            if server_name not in servers:
                emit_info(
                    f"[red]Server '{server_name}' not found.[/red]",
                    message_group=group_id,
                )
                # Show available servers
                if servers:
                    emit_info(
                        "\n[yellow]Available servers:[/yellow]",
                        message_group=group_id,
                    )
                    for name in sorted(servers.keys()):
                        emit_info(f"  • {name}", message_group=group_id)
                return None

            config = servers[
                server_name
            ].copy()  # Make a copy to avoid modifying original

            # Extract type from config (default to stdio)
            server_type = config.pop("type", "stdio")

            return (server_type, config)

        except json.JSONDecodeError as e:
            emit_info(
                f"[red]Error reading config file: {e}[/red]",
                message_group=group_id,
            )
            return None
        except Exception as e:
            emit_info(
                f"[red]Error loading server config: {e}[/red]",
                message_group=group_id,
            )
            return None
