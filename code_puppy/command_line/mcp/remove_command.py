"""
MCP Remove Command - Removes an MCP server.
"""

import logging
from typing import List, Optional

from code_puppy.i18n import ngettext, t
from code_puppy.messaging import emit_error, emit_info

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class RemoveCommand(MCPCommandBase):
    """
    Command handler for removing MCP servers.

    Removes a specific MCP server from the manager and configuration.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Remove an MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info(t("mcp.server.usage", command="remove"), message_group=group_id)
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

            # Capture binding info BEFORE removal so we can report what got
            # cleaned up (remove_server wipes bindings itself).
            try:
                from code_puppy.mcp_.agent_bindings import get_agents_for_server

                bound_agents = get_agents_for_server(server_name)
            except Exception:
                bound_agents = []

            # Actually remove the server (this also wipes bindings)
            success = self.manager.remove_server(server_id)

            if success:
                emit_info(
                    t("mcp.server.removed", server=server_name),
                    message_group=group_id,
                )
                if bound_agents:
                    emit_info(
                        "  "
                        + ngettext(
                            "mcp.server.unbound",
                            len(bound_agents),
                            agents=", ".join(bound_agents),
                        ),
                        message_group=group_id,
                    )

                # Also remove from mcp_servers.json
                from code_puppy.command_line.mcp.mcp_servers_store import (
                    remove_mcp_server,
                )

                try:
                    remove_mcp_server(server_name)
                except Exception as e:
                    logger.warning(f"Could not update mcp_servers.json: {e}")
            else:
                emit_info(
                    t("mcp.server.remove_failed", server=server_name),
                    message_group=group_id,
                )

        except Exception as e:
            logger.error(f"Error removing server '{server_name}': {e}")
            emit_error(t("mcp.server.remove_error", error=e), message_group=group_id)
