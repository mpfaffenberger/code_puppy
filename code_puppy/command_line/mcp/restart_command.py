"""
MCP Restart Command - Restarts a specific MCP server.
"""

import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.messaging import emit_info

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class RestartCommand(MCPCommandBase):
    """
    Command handler for restarting MCP servers.

    Stops, reloads configuration, and starts a specific MCP server.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Restart a specific MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info("Usage: /mcp restart <server_name>", message_group=group_id)
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Stop the server first
            emit_info(f"Stopping server: {server_name}", message_group=group_id)
            self.manager.stop_server_sync(server_id)

            # Then reload and start it
            emit_info("Reloading configuration...", message_group=group_id)
            reload_success = self.manager.reload_server(server_id)

            if reload_success:
                emit_info(f"Starting server: {server_name}", message_group=group_id)
                start_success = self.manager.start_server_sync(server_id)

                if start_success:
                    emit_info(
                        f"✓ Restarted server: {server_name}", message_group=group_id
                    )

                    # Reload the agent to pick up the server changes
                    try:
                        from code_puppy.agents import get_current_agent

                        agent = get_current_agent()
                        agent.reload_code_generation_agent()
                        # Update MCP tool cache immediately so token counts reflect the change
                        agent.update_mcp_tool_cache_sync()
                        emit_info(
                            Text.from_markup(
                                "[dim]Agent reloaded with updated servers[/dim]"
                            ),
                            message_group=group_id,
                        )
                    except Exception as e:
                        logger.warning(f"Could not reload agent: {e}")
                else:
                    emit_info(
                        f"✗ Failed to start server after reload: {server_name}",
                        message_group=group_id,
                    )
            else:
                emit_info(
                    f"✗ Failed to reload server configuration: {server_name}",
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error restarting server '{server_name}': {e}")
            emit_info(
                Text.from_markup(f"[red]Failed to restart server: {e}[/red]"),
                message_group=group_id,
            )
