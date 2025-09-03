"""
MCP Test Command - Tests connectivity to a specific MCP server.
"""

import logging
from typing import List, Optional

from code_puppy.messaging import emit_info

from .base import MCPCommandBase
from .utils import find_server_id_by_name, suggest_similar_servers

# Configure logging
logger = logging.getLogger(__name__)


class TestCommand(MCPCommandBase):
    """
    Command handler for testing MCP server connectivity.

    Tests connectivity and basic functionality of a specific MCP server.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Test connectivity to a specific MCP server.

        Args:
            args: Command arguments, expects [server_name]
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        if not args:
            emit_info("Usage: /mcp test <server_name>", message_group=group_id)
            return

        server_name = args[0]

        try:
            # Find server by name
            server_id = find_server_id_by_name(self.manager, server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                suggest_similar_servers(self.manager, server_name, group_id=group_id)
                return

            # Get managed server
            managed_server = self.manager.get_server(server_id)
            if not managed_server:
                emit_info(
                    f"Server '{server_name}' not accessible", message_group=group_id
                )
                return

            emit_info(
                f"🔍 Testing connectivity to server: {server_name}",
                message_group=group_id,
            )

            # Basic connectivity test - try to get the pydantic server
            try:
                managed_server.get_pydantic_server()  # Test server instantiation
                emit_info(
                    "✓ Server instance created successfully", message_group=group_id
                )

                # Try to get server info if available
                emit_info(
                    f"  • Server type: {managed_server.config.type}",
                    message_group=group_id,
                )
                emit_info(
                    f"  • Server enabled: {managed_server.is_enabled()}",
                    message_group=group_id,
                )
                emit_info(
                    f"  • Server quarantined: {managed_server.is_quarantined()}",
                    message_group=group_id,
                )

                if not managed_server.is_enabled():
                    emit_info(
                        "  • Server is disabled - enable it with '/mcp start'",
                        message_group=group_id,
                    )

                if managed_server.is_quarantined():
                    emit_info(
                        "  • Server is quarantined - may have recent errors",
                        message_group=group_id,
                    )

                emit_info(
                    f"✓ Connectivity test passed for: {server_name}",
                    message_group=group_id,
                )

            except Exception as test_error:
                emit_info(
                    f"✗ Connectivity test failed: {test_error}", message_group=group_id
                )

        except Exception as e:
            logger.error(f"Error testing server '{server_name}': {e}")
            emit_info(f"[red]Error testing server: {e}[/red]", message_group=group_id)
