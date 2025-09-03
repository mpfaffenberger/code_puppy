"""
MCP Logs Command - Shows recent events/logs for a server.
"""

import logging
from datetime import datetime
from typing import List, Optional

from rich.table import Table
from rich.text import Text

from code_puppy.messaging import emit_info

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class LogsCommand(MCPCommandBase):
    """
    Command handler for showing MCP server logs.

    Shows recent events/logs for a specific MCP server with configurable limit.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Show recent events/logs for a server.

        Args:
            args: Command arguments, expects [server_name] and optional [limit]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info("Usage: /mcp logs <server_name> [limit]", message_group=group_id)
            return

        server_name = args[0]
        limit = 10  # Default limit

        if len(args) > 1:
            try:
                limit = int(args[1])
                if limit <= 0 or limit > 100:
                    emit_info(
                        "Limit must be between 1 and 100, using default: 10",
                        message_group=group_id,
                    )
                    limit = 10
            except ValueError:
                emit_info(
                    f"Invalid limit '{args[1]}', using default: 10",
                    message_group=group_id,
                )

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Get server status which includes recent events
            status = self.manager.get_server_status(server_id)

            if not status.get("exists", True):
                emit_info(
                    f"Server '{server_name}' status not available",
                    message_group=group_id,
                )
                return

            recent_events = status.get("recent_events", [])

            if not recent_events:
                emit_info(
                    f"No recent events for server: {server_name}",
                    message_group=group_id,
                )
                return

            # Show events in a table
            table = Table(title=f"📋 Recent Events for {server_name} (last {limit})")
            table.add_column("Time", style="dim", no_wrap=True)
            table.add_column("Event", style="cyan")
            table.add_column("Details", style="dim")

            # Take only the requested number of events
            events_to_show = (
                recent_events[-limit:] if len(recent_events) > limit else recent_events
            )

            for event in reversed(events_to_show):  # Show newest first
                timestamp = datetime.fromisoformat(event["timestamp"])
                time_str = timestamp.strftime("%H:%M:%S")
                event_type = event["event_type"]

                # Format details
                details = event.get("details", {})
                details_str = details.get("message", "")
                if not details_str and "error" in details:
                    details_str = str(details["error"])

                # Color code event types
                event_style = "cyan"
                if "error" in event_type.lower():
                    event_style = "red"
                elif event_type in ["started", "enabled", "registered"]:
                    event_style = "green"
                elif event_type in ["stopped", "disabled"]:
                    event_style = "yellow"

                table.add_row(
                    time_str, Text(event_type, style=event_style), details_str or "-"
                )
            emit_info(table, message_group=group_id)

        except Exception as e:
            logger.error(f"Error getting logs for server '{server_name}': {e}")
            emit_info(f"[red]Error getting logs: {e}[/red]", message_group=group_id)
