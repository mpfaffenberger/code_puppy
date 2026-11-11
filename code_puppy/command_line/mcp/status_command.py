"""
MCP Status Command - Shows detailed status for MCP servers.
"""

import logging
from datetime import datetime
from typing import List, Optional, Union

from rich.panel import Panel
from rich.text import Text

from code_puppy.i18n import ngettext, t
from code_puppy.mcp_.managed_server import ServerState
from code_puppy.messaging import emit_error, emit_info

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
                        t("mcp.server.not_found", server=server_name),
                        message_group=group_id,
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
            emit_info(t("mcp.status.failed", error=e), message_group=group_id)

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
                    t("mcp.status.not_accessible", server=server_name),
                    message_group=group_id,
                )
                return

            def line(label_key: str, value: Union[str, Text]) -> Text:
                # Bold translated label; the value is never parsed as markup.
                return Text.assemble((t(label_key), "bold"), " ", value)

            # Basic information
            status_lines = [
                line("mcp.status.label.server", server_name),
                line("mcp.status.label.id", server_id),
                line("mcp.status.label.type", status.get("type", "unknown").upper()),
            ]

            # State and status
            state = status.get("state", "unknown")
            state_display = format_state_indicator(
                ServerState(state)
                if state in [s.value for s in ServerState]
                else ServerState.STOPPED
            )
            status_lines.append(line("mcp.status.label.state", state_display.plain))

            enabled = status.get("enabled", False)
            status_lines.append(
                line(
                    "mcp.status.label.enabled",
                    t("mcp.status.enabled_yes" if enabled else "mcp.status.enabled_no"),
                )
            )

            # Check async lifecycle manager status if available
            try:
                from code_puppy.mcp_.async_lifecycle import get_lifecycle_manager

                lifecycle_mgr = get_lifecycle_manager()
                if lifecycle_mgr.is_running(server_id):
                    process = Text(t("mcp.status.process_active"), style="green")
                else:
                    process = Text(t("mcp.status.process_inactive"), style="dim")
                status_lines.append(line("mcp.status.label.process", process))
            except Exception:
                pass  # Lifecycle manager not available

            quarantined = status.get("quarantined", False)
            if quarantined:
                status_lines.append(
                    line(
                        "mcp.status.label.quarantined",
                        Text(t("mcp.status.quarantined_yes"), style="yellow"),
                    )
                )

            # Timing information
            uptime = status.get("tracker_uptime")
            if uptime:
                uptime_str = format_uptime(
                    uptime.total_seconds()
                    if hasattr(uptime, "total_seconds")
                    else uptime
                )
                status_lines.append(line("mcp.status.label.uptime", uptime_str))

            # Error information
            error_msg = status.get("error_message")
            if error_msg:
                status_lines.append(
                    line("mcp.status.label.error", Text(str(error_msg), style="red"))
                )

            # Event information
            event_count = status.get("recent_events_count", 0)
            status_lines.append(
                line("mcp.status.label.recent_events", str(event_count))
            )

            # Metadata
            metadata = status.get("tracker_metadata", {})
            if metadata:
                status_lines.append(
                    line(
                        "mcp.status.label.metadata",
                        ngettext("mcp.status.metadata_keys", len(metadata)),
                    )
                )

            # Create and show the panel
            panel = Panel(
                Text("\n").join(status_lines),
                title=Text(t("mcp.status.title", server=server_name)),
                border_style="cyan",
            )

            emit_info(panel, message_group=group_id)

            # Show recent events if available
            recent_events = status.get("recent_events", [])
            if recent_events:
                emit_info("\n" + t("mcp.status.recent_events"), message_group=group_id)
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
            emit_error(t("mcp.status.error", error=e), message_group=group_id)
