"""
MCP Remove Command - Removes an MCP server.
"""

import json
import logging
import os
from typing import List, Optional

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
            emit_info("Usage: /mcp remove <server_name>", message_group=group_id)
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Capture binding info BEFORE removal so we can report what got
            # cleaned up. The manager itself wipes bindings inside
            # remove_server(), but the user deserves to see it.
            try:
                from code_puppy.mcp_.agent_bindings import get_agents_for_server

                bound_agents = get_agents_for_server(server_name)
            except Exception:
                bound_agents = []

            # Actually remove the server (this also wipes bindings)
            success = self.manager.remove_server(server_id)

            if success:
                emit_info(f"✓ Removed server: {server_name}", message_group=group_id)
                if bound_agents:
                    emit_info(
                        f"  ✓ Also unbound from {len(bound_agents)} agent(s): "
                        f"{', '.join(bound_agents)}",
                        message_group=group_id,
                    )

                # Also remove from mcp_servers.json
                from code_puppy.config import MCP_SERVERS_FILE

                if os.path.exists(MCP_SERVERS_FILE):
                    try:
                        with open(MCP_SERVERS_FILE, "r") as f:
                            data = json.load(f)
                            servers = data.get("mcp_servers", {})

                        # Remove the server if it exists
                        if server_name in servers:
                            del servers[server_name]

                            # Save back
                            with open(MCP_SERVERS_FILE, "w") as f:
                                json.dump(data, f, indent=2)
                    except Exception as e:
                        logger.warning(f"Could not update mcp_servers.json: {e}")
            else:
                emit_info(
                    f"✗ Failed to remove server: {server_name}", message_group=group_id
                )

        except Exception as e:
            logger.error(f"Error removing server '{server_name}': {e}")
            emit_error(f"Error removing server: {e}", message_group=group_id)
