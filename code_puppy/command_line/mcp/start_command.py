"""
MCP Start Command - Starts a specific MCP server.
"""

import logging
import time
from typing import List, Optional

from code_puppy.messaging import emit_info

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
                "[yellow]Usage: /mcp start <server_name>[/yellow]",
                message_group=group_id,
            )
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(
                    f"[red]Server '{server_name}' not found[/red]",
                    message_group=group_id,
                )
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Start the server (enable and start process)
            success = self.manager.start_server_sync(server_id)

            if success:
                # This and subsequent messages will auto-group with the first message
                emit_info(
                    f"[green]✓ Started server: {server_name}[/green]",
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
                    from code_puppy.agents.runtime_manager import (
                        get_runtime_agent_manager,
                    )

                    manager = get_runtime_agent_manager()
                    manager.reload_agent()
                    emit_info(
                        "[dim]Agent reloaded with updated servers[/dim]",
                        message_group=group_id,
                    )
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
            else:
                emit_info(
                    f"[red]✗ Failed to start server: {server_name}[/red]",
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error starting server '{server_name}': {e}")
            emit_info(f"[red]Failed to start server: {e}[/red]", message_group=group_id)
