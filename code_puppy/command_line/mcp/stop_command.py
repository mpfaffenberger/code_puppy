"""
MCP Stop Command - Stops a specific MCP server.
"""

import logging
from typing import List, Optional

from rich.text import Text

from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info

from ...agents import get_current_agent
from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class StopCommand(MCPCommandBase):
    """
    Command handler for stopping MCP servers.

    Stops a specific MCP server by name and reloads the agent.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Stop a specific MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info(
                Text(t("mcp.server.usage", command="stop"), style="yellow"),
                message_group=group_id,
            )
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(
                    t("mcp.server.not_found", server=server_name),
                    message_group=group_id,
                )
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Stop the server (disable and stop process)
            success = self.manager.stop_server_sync(server_id)

            if success:
                emit_info(
                    t("mcp.server.stopped", server=server_name),
                    message_group=group_id,
                )

                # Reload the agent to remove the disabled server
                try:
                    agent = get_current_agent()
                    agent.reload_code_generation_agent()
                    # Update MCP tool cache immediately so token counts reflect the change
                    agent.update_mcp_tool_cache_sync()
                    emit_info(
                        t("mcp.server.agent_reloaded"),
                        message_group=group_id,
                    )
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
            else:
                emit_info(
                    t("mcp.server.stop_failed", server=server_name),
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error stopping server '{server_name}': {e}")
            emit_error(t("mcp.server.stop_error", error=e), message_group=group_id)
