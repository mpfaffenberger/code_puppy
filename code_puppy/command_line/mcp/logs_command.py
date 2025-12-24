"""
MCP Logs Command - Shows server logs from persistent log files.
"""

import logging
from typing import List, Optional

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from code_puppy.mcp_.mcp_logs import (
    clear_logs,
    get_log_file_path,
    get_log_stats,
    list_servers_with_logs,
    read_logs,
)
from code_puppy.messaging import emit_error, emit_info

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class LogsCommand(MCPCommandBase):
    """
    Command handler for showing MCP server logs.

    Shows logs from persistent log files stored in ~/.code_puppy/mcp_logs/.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Show logs for a server.

        Usage:
            /mcp logs                    - List servers with logs
            /mcp logs <server_name>      - Show last 50 lines
            /mcp logs <server_name> 100  - Show last 100 lines
            /mcp logs <server_name> all  - Show all logs
            /mcp logs <server_name> --clear - Clear logs for server

        Args:
            args: Command arguments
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        # No args - list servers with logs
        if not args:
            self._list_servers_with_logs(group_id)
            return

        server_name = args[0]

        # Check for --clear flag
        if len(args) > 1 and args[1] == "--clear":
            self._clear_logs(server_name, group_id)
            return

        # Determine number of lines
        lines = 50  # Default
        show_all = False

        if len(args) > 1:
            if args[1].lower() == "all":
                show_all = True
            else:
                try:
                    lines = int(args[1])
                    if lines <= 0:
                        emit_info(
                            "Lines must be positive, using default: 50",
                            message_group=group_id,
                        )
                        lines = 50
                except ValueError:
                    emit_info(
                        f"Invalid number '{args[1]}', using default: 50",
                        message_group=group_id,
                    )

        self._show_logs(server_name, lines if not show_all else None, group_id)

    def _list_servers_with_logs(self, group_id: str) -> None:
        """List all servers that have log files."""
        servers = list_servers_with_logs()

        if not servers:
            emit_info(
                "📋 No MCP server logs found.\n"
                "Logs are created when servers are started.",
                message_group=group_id,
            )
            return

        lines = ["📋 **Servers with logs:**\n"]

        for server in servers:
            stats = get_log_stats(server)
            size_kb = stats["total_size_bytes"] / 1024
            size_str = (
                f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"
            )
            rotated = (
                f" (+{stats['rotated_count']} rotated)"
                if stats["rotated_count"]
                else ""
            )
            lines.append(
                f"  • **{server}** - {stats['line_count']} lines, {size_str}{rotated}"
            )

        lines.append("\n**Usage:** `/mcp logs <server_name> [lines|all]`")

        emit_info("\n".join(lines), message_group=group_id)

    def _show_logs(self, server_name: str, lines: Optional[int], group_id: str) -> None:
        """
        Show logs for a specific server.

        Args:
            server_name: Name of the server
            lines: Number of lines to show, or None for all
            group_id: Message group ID
        """
        try:
            # Verify server exists in manager
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                # Server not configured, but might have logs from before
                stats = get_log_stats(server_name)
                if not stats["exists"]:
                    emit_info(
                        f"Server '{server_name}' not found and has no logs.",
                        message_group=group_id,
                    )
                    suggest_similar_servers(
                        self.manager, server_name, group_id=group_id
                    )
                    return

            # Read logs
            log_lines = read_logs(server_name, lines=lines)

            if not log_lines:
                emit_info(
                    f"📋 No logs found for server: **{server_name}**\n"
                    f"Log file: `{get_log_file_path(server_name)}`",
                    message_group=group_id,
                )
                return

            # Get stats for header
            stats = get_log_stats(server_name)
            total_lines = stats["line_count"]
            showing = len(log_lines)

            # Format header
            if lines is None:
                header = f"📋 Logs for {server_name} (all {total_lines} lines)"
            else:
                header = (
                    f"📋 Logs for {server_name} (last {showing} of {total_lines} lines)"
                )

            # Format log content with syntax highlighting
            log_content = "\n".join(log_lines)

            # Create a panel with the logs
            syntax = Syntax(
                log_content,
                "log",
                theme="monokai",
                word_wrap=True,
                line_numbers=False,
            )

            panel = Panel(
                syntax,
                title=header,
                subtitle=f"Log file: {get_log_file_path(server_name)}",
                border_style="dim",
            )

            emit_info(panel, message_group=group_id)

            # Show hint for more options
            if lines is not None and showing < total_lines:
                emit_info(
                    Text.from_markup(
                        f"[dim]💡 Use `/mcp logs {server_name} all` to see all logs, "
                        f"or `/mcp logs {server_name} <number>` for specific count[/dim]"
                    ),
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error getting logs for server '{server_name}': {e}")
            emit_error(f"Error getting logs: {e}", message_group=group_id)

    def _clear_logs(self, server_name: str, group_id: str) -> None:
        """
        Clear logs for a specific server.

        Args:
            server_name: Name of the server
            group_id: Message group ID
        """
        try:
            stats = get_log_stats(server_name)

            if not stats["exists"] and stats["rotated_count"] == 0:
                emit_info(
                    f"No logs to clear for server: {server_name}",
                    message_group=group_id,
                )
                return

            # Clear the logs
            clear_logs(server_name, include_rotated=True)

            cleared_count = 1 + stats["rotated_count"]
            emit_info(
                f"🗑️  Cleared {cleared_count} log file(s) for **{server_name}**",
                message_group=group_id,
            )

        except Exception as e:
            logger.error(f"Error clearing logs for server '{server_name}': {e}")
            emit_error(f"Error clearing logs: {e}", message_group=group_id)
