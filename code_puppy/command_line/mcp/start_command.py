"""
MCP Start Command - Starts a specific MCP server.
"""

import logging
import time
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

            # Start the server (enable and start process)
            success = self.manager.start_server_sync(server_id)

            if success:
                # This and subsequent messages will auto-group with the first message
                emit_success(
                    f"Started server: {server_name}",
                    message_group=group_id,
                )

                # Give async tasks a moment to complete
                try:
                    import asyncio

                    asyncio.get_running_loop()  # Check if in async context
                    # If we're in async context, wait a bit for server to start
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, server will start when agent uses it

                # Reload the agent to pick up the newly enabled server
                try:
                    agent = get_current_agent()
                    agent.reload_code_generation_agent()
                    # Update MCP tool cache immediately so token counts reflect the change
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
