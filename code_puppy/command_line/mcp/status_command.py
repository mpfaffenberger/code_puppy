"""
MCP Status Command - Shows detailed status for MCP servers.
"""

import logging
from datetime import datetime
from typing import List, Optional

from rich.panel import Panel

from code_puppy.mcp.managed_server import ServerState
from code_puppy.messaging import emit_info

from .base import MCPCommandBase
from .list_command import ListCommand
from .utils import (
    find_server_id_by_name,
    format_state_indicator,
    format_uptime,
    suggest_similar_servers,
)

# Configure logging
logger = logging.getLogger(__name__)


class StatusCommand(MCPCommandBase):
    """
    Command handler for showing MCP server status.

    Shows detailed status for a specific server or brief status for all servers.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Show detailed status for a specific server or all servers.

        Args:
            args: Command arguments, expects [server_name] (optional)
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            if args:
                # Show detailed status for specific server
                server_name = args[0]
                server_id = find_server_id_by_name(self.manager, server_name)

                if not server_id:
                    emit_info(
                        f"Server '{server_name}' not found", message_group=group_id
                    )
                    suggest_similar_servers(
                        self.manager, server_name, group_id=group_id
                    )
                    return

                self._show_detailed_server_status(server_id, server_name, group_id)
            else:
                # Show brief status for all servers
                list_command = ListCommand()
                list_command.execute([], group_id=group_id)

        except Exception as e:
            logger.error(f"Error showing server status: {e}")
            emit_info(f"Failed to get server status: {e}", message_group=group_id)

    def _show_detailed_server_status(
        self, server_id: str, server_name: str, group_id: Optional[str] = None
    ) -> None:
        """
        Show comprehensive status information for a specific server.

        Args:
            server_id: ID of the server
            server_name: Name of the server
            group_id: Optional message group ID
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            status = self.manager.get_server_status(server_id)

            if not status.get("exists", True):
                emit_info(
                    f"Server '{server_name}' not found or not accessible",
                    message_group=group_id,
                )
                return

            # Create detailed status panel
            status_lines = []

            # Basic information
            status_lines.append(f"[bold]Server:[/bold] {server_name}")
            status_lines.append(f"[bold]ID:[/bold] {server_id}")
            status_lines.append(
                f"[bold]Type:[/bold] {status.get('type', 'unknown').upper()}"
            )

            # State and status
            state = status.get("state", "unknown")
            state_display = format_state_indicator(
                ServerState(state)
                if state in [s.value for s in ServerState]
                else ServerState.STOPPED
            )
            status_lines.append(f"[bold]State:[/bold] {state_display}")

            enabled = status.get("enabled", False)
            status_lines.append(
                f"[bold]Enabled:[/bold] {'✓ Yes' if enabled else '✗ No'}"
            )

            # Check async lifecycle manager status if available
            try:
                from code_puppy.mcp.async_lifecycle import get_lifecycle_manager

                lifecycle_mgr = get_lifecycle_manager()
                if lifecycle_mgr.is_running(server_id):
                    status_lines.append(
                        "[bold]Process:[/bold] [green]✓ Active (subprocess/connection running)[/green]"
                    )
                else:
                    status_lines.append("[bold]Process:[/bold] [dim]Not active[/dim]")
            except Exception:
                pass  # Lifecycle manager not available

            quarantined = status.get("quarantined", False)
            if quarantined:
                status_lines.append("[bold]Quarantined:[/bold] [yellow]⚠ Yes[/yellow]")

            # Timing information
            uptime = status.get("tracker_uptime")
            if uptime:
                uptime_str = format_uptime(
                    uptime.total_seconds()
                    if hasattr(uptime, "total_seconds")
                    else uptime
                )
                status_lines.append(f"[bold]Uptime:[/bold] {uptime_str}")

            # Error information
            error_msg = status.get("error_message")
            if error_msg:
                status_lines.append(f"[bold]Error:[/bold] [red]{error_msg}[/red]")

            # Event information
            event_count = status.get("recent_events_count", 0)
            status_lines.append(f"[bold]Recent Events:[/bold] {event_count}")

            # Metadata
            metadata = status.get("tracker_metadata", {})
            if metadata:
                status_lines.append(f"[bold]Metadata:[/bold] {len(metadata)} keys")

            # Create and show the panel
            panel_content = "\n".join(status_lines)
            panel = Panel(
                panel_content, title=f"🔌 {server_name} Status", border_style="cyan"
            )

            emit_info(panel, message_group=group_id)

            # Show recent events if available
            recent_events = status.get("recent_events", [])
            if recent_events:
                emit_info("\n📋 Recent Events:", message_group=group_id)
                for event in recent_events[-5:]:  # Show last 5 events
                    timestamp = datetime.fromisoformat(event["timestamp"])
                    time_str = timestamp.strftime("%H:%M:%S")
                    emit_info(
                        f"  {time_str}: {event['message']}", message_group=group_id
                    )

        except Exception as e:
            logger.error(
                f"Error getting detailed status for server '{server_name}': {e}"
            )
            emit_info(
                f"[red]Error getting server status: {e}[/red]", message_group=group_id
            )
