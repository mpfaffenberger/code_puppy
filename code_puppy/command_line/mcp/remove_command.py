"""
MCP Remove Command - Removes an MCP server.
"""

import json
import logging
import os
from typing import List, Optional

from code_puppy.messaging import emit_info

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

            # Actually remove the server
            success = self.manager.remove_server(server_id)

            if success:
                emit_info(f"✓ Removed server: {server_name}", message_group=group_id)

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
            emit_info(f"[red]Error removing server: {e}[/red]", message_group=group_id)
