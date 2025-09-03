"""
MCP Stop All Command - Stops all running MCP servers.
"""

import logging
import time
from typing import List, Optional

from code_puppy.mcp.managed_server import ServerState
from code_puppy.messaging import emit_info

from .base import MCPCommandBase

# Configure logging
logger = logging.getLogger(__name__)


class StopAllCommand(MCPCommandBase):
    """
    Command handler for stopping all MCP servers.

    Stops all running MCP servers and provides a summary of results.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Stop all running MCP servers.

        Args:
            args: Command arguments (unused)
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            servers = self.manager.list_servers()

            if not servers:
                emit_info("No servers registered", message_group=group_id)
                return

            stopped_count = 0
            failed_count = 0

            # Count running servers
            running_servers = [s for s in servers if s.state == ServerState.RUNNING]

            if not running_servers:
                emit_info("No servers are currently running", message_group=group_id)
                return

            emit_info(
                f"Stopping {len(running_servers)} running server(s)...",
                message_group=group_id,
            )

            for server_info in running_servers:
                server_id = server_info.id
                server_name = server_info.name

                # Try to stop the server
                success = self.manager.stop_server_sync(server_id)

                if success:
                    stopped_count += 1
                    emit_info(f"  ✓ Stopped: {server_name}", message_group=group_id)
                else:
                    failed_count += 1
                    emit_info(f"  ✗ Failed: {server_name}", message_group=group_id)

            # Summary
            emit_info("", message_group=group_id)
            if stopped_count > 0:
                emit_info(f"Stopped {stopped_count} server(s)", message_group=group_id)
            if failed_count > 0:
                emit_info(
                    f"Failed to stop {failed_count} server(s)", message_group=group_id
                )

            # Reload agent if any servers were stopped
            if stopped_count > 0:
                # Give async tasks a moment to complete before reloading agent
                try:
                    import asyncio

                    asyncio.get_running_loop()  # Check if in async context
                    # If we're in async context, wait a bit for servers to stop
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, servers will stop when needed

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

        except Exception as e:
            logger.error(f"Error stopping all servers: {e}")
            emit_info(f"Failed to stop servers: {e}", message_group=group_id)
