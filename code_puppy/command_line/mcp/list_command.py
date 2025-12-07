"""
MCP List Command - Lists all registered MCP servers in a formatted table.
"""

import logging
from typing import List, Optional

from rich.table import Table
from rich.text import Text

from code_puppy.mcp_.managed_server import ServerState
from code_puppy.messaging import emit_error, emit_info

from .base import MCPCommandBase
from .utils import format_state_indicator, format_uptime

# Configure logging
logger = logging.getLogger(__name__)


class ListCommand(MCPCommandBase):
    """
    Command handler for listing MCP servers.

    Displays all registered MCP servers in a formatted table with status information.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        List all registered MCP servers in a formatted table.

        Args:
            args: Command arguments (unused for list command)
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            servers = self.manager.list_servers()

            if not servers:
                emit_info("No MCP servers registered", message_group=group_id)
                return

            # Create table for server list
            table = Table(title="🔌 MCP Server Status Dashboard")
            table.add_column("Name", style="cyan", no_wrap=True)
            table.add_column("Type", style="dim", no_wrap=True)
            table.add_column("State", justify="center")
            table.add_column("Enabled", justify="center")
            table.add_column("Uptime", style="dim")
            table.add_column("Status", style="dim")

            for server in servers:
                # Format state with appropriate color and icon
                state_display = format_state_indicator(server.state)

                # Format enabled status
                enabled_display = "✓" if server.enabled else "✗"
                enabled_style = "green" if server.enabled else "red"

                # Format uptime
                uptime_display = format_uptime(server.uptime_seconds)

                # Format status message
                status_display = server.error_message or "OK"
                if server.quarantined:
                    status_display = "Quarantined"

                table.add_row(
                    server.name,
                    server.type.upper(),
                    state_display,
                    Text(enabled_display, style=enabled_style),
                    uptime_display,
                    status_display,
                )

            emit_info(table, message_group=group_id)

            # Show summary
            total = len(servers)
            running = sum(
                1 for s in servers if s.state == ServerState.RUNNING and s.enabled
            )
            emit_info(
                f"\n📊 Summary: {running}/{total} servers running",
                message_group=group_id,
            )

        except Exception as e:
            logger.error(f"Error listing MCP servers: {e}")
            emit_error(f"Error listing servers: {e}", message_group=group_id)
