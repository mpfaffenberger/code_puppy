"""
MCP Start Command - Starts a specific MCP server.
"""

import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success

from ...agents import get_current_agent
from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class StartCommand(MCPCommandBase):
    """
    Command handler for starting MCP servers.

    Starts a specific MCP server by name and reloads the agent.
    The server subprocess starts asynchronously in the background.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Start a specific MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info(
                Text.from_markup("[yellow]Usage: /mcp start <server_name>[/yellow]"),
                message_group=group_id,
            )
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_error(
                    f"Server '{server_name}' not found",
                    message_group=group_id,
                )
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Get server info for better messaging (safely handle missing method)
            server_type = "unknown"
            try:
                if hasattr(self.manager, "get_server_by_name"):
                    server_config = self.manager.get_server_by_name(server_name)
                    server_type = (
                        getattr(server_config, "type", "unknown")
                        if server_config
                        else "unknown"
                    )
            except Exception:
                pass  # Default to unknown type if we can't determine it

            # Start the server (schedules async start in background)
            success = self.manager.start_server_sync(server_id)

            if success:
                if server_type == "stdio":
                    # Stdio servers start subprocess asynchronously
                    emit_success(
                        f"🚀 Starting server: {server_name} (subprocess starting in background)",
                        message_group=group_id,
                    )
                    emit_info(
                        Text.from_markup(
                            "[dim]Tip: Use /mcp status to check if the server is fully initialized[/dim]"
                        ),
                        message_group=group_id,
                    )
                else:
                    # SSE/HTTP servers connect on first use
                    emit_success(
                        f"✅ Enabled server: {server_name}",
                        message_group=group_id,
                    )

                # Reload the agent to pick up the newly enabled server
                # NOTE: We don't block or wait - the server will be ready
                # when the next prompt runs (pydantic-ai handles connection)
                try:
                    agent = get_current_agent()
                    agent.reload_code_generation_agent()
                    # Clear MCP tool cache - it will be repopulated on next run
                    agent.update_mcp_tool_cache_sync()
                    emit_info(
                        "Agent reloaded with updated servers",
                        message_group=group_id,
                    )
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
            else:
                emit_error(
                    f"Failed to start server: {server_name}",
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error starting server '{server_name}': {e}")
            emit_error(f"Failed to start server: {e}", message_group=group_id)
