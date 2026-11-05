"""
MCP List Command - Lists all registered MCP servers in a formatted table.
"""

import logging
from typing import List, Optional

from rich.table import Table
from rich.text import Text

from code_puppy.i18n import ngettext, t
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
                emit_info(t("mcp.server.none_registered"), message_group=group_id)
                return

            # Create table for server list. Every cell and heading is Text so
            # server data and translations are never parsed as Rich markup.
            table = Table(title=Text(t("mcp.list.title"), style="table.title"))
            table.add_column(
                Text(t("mcp.list.column.name")), style="cyan", no_wrap=True
            )
            table.add_column(Text(t("mcp.list.column.type")), style="dim", no_wrap=True)
            table.add_column(
                Text(t("mcp.list.column.state")), justify="center", no_wrap=True
            )
            table.add_column(Text(t("mcp.list.column.enabled")), justify="center")
            table.add_column(Text(t("mcp.list.column.uptime")), style="dim")
            table.add_column(Text(t("mcp.list.column.status")), style="dim")

            for server in servers:
                # Format state with appropriate color and icon
                state_display = format_state_indicator(server.state)

                # Format enabled status
                enabled_display = "✓" if server.enabled else "✗"
                enabled_style = "green" if server.enabled else "red"

                # Format uptime
                uptime_display = format_uptime(server.uptime_seconds)

                # Format status message
                status_display = server.error_message or t("mcp.list.status_ok")
                if server.quarantined:
                    status_display = t("mcp.list.status_quarantined")

                table.add_row(
                    Text(server.name),
                    Text(server.type.upper()),
                    state_display,
                    Text(enabled_display, style=enabled_style),
                    Text(uptime_display),
                    Text(status_display),
                )

            emit_info(table, message_group=group_id)

            # Show summary
            total = len(servers)
            running = sum(
                1 for s in servers if s.state == ServerState.RUNNING and s.enabled
            )
            emit_info(
                "\n" + ngettext("mcp.list.summary", total, running=running),
                message_group=group_id,
            )

        except Exception as e:
            logger.error(f"Error listing MCP servers: {e}")
            emit_error(t("mcp.list.error", error=e), message_group=group_id)
