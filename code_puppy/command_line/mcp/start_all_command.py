"""
MCP Start All Command - Starts all registered MCP servers.
"""

import logging
import time
from typing import List, Optional

from rich.text import Text

from code_puppy.mcp_.managed_server import ServerState
from code_puppy.messaging import emit_info

from ...agents import get_current_agent
from .base import MCPCommandBase

# Configure logging
logger = logging.getLogger(__name__)


class StartAllCommand(MCPCommandBase):
    """
    Command handler for starting all MCP servers.

    Starts all registered MCP servers and provides a summary of results.
    """

    def execute(self, args: List[str], group_id: Optional[str] = None) -> None:
        """
        Start all registered MCP servers.

        Args:
            args: Command arguments (unused)
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            group_id = self.generate_group_id()

        try:
            servers = self.manager.list_servers()

            if not servers:
                emit_info(
                    "[yellow]No servers registered[/yellow]", message_group=group_id
                )
                return

            started_count = 0
            failed_count = 0
            already_running = 0

            emit_info(f"Starting {len(servers)} servers...", message_group=group_id)

            for server_info in servers:
                server_id = server_info.id
                server_name = server_info.name

                # Skip if already running
                if server_info.state == ServerState.RUNNING:
                    already_running += 1
                    emit_info(
                        f"  • {server_name}: already running", message_group=group_id
                    )
                    continue

                # Try to start the server
                success = self.manager.start_server_sync(server_id)

                if success:
                    started_count += 1
                    emit_info(
                        Text.from_markup(f"  [green]✓ Started: {server_name}[/green]"),
                        message_group=group_id,
                    )
                else:
                    failed_count += 1
                    emit_info(
                        Text.from_markup(f"  [red]✗ Failed: {server_name}[/red]"),
                        message_group=group_id,
                    )

            # Summary
            emit_info("", message_group=group_id)
            if started_count > 0:
                emit_info(
                    Text.from_markup(
                        f"[green]Started {started_count} server(s)[/green]"
                    ),
                    message_group=group_id,
                )
            if already_running > 0:
                emit_info(
                    f"{already_running} server(s) already running",
                    message_group=group_id,
                )
            if failed_count > 0:
                emit_info(
                    Text.from_markup(
                        f"[yellow]Failed to start {failed_count} server(s)[/yellow]"
                    ),
                    message_group=group_id,
                )

            # Reload agent if any servers were started
            if started_count > 0:
                # Give async tasks a moment to complete before reloading agent
                try:
                    import asyncio

                    asyncio.get_running_loop()  # Check if in async context
                    # If we're in async context, wait a bit for servers to start
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, servers will start when agent uses them

                try:
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

        except Exception as e:
            logger.error(f"Error starting all servers: {e}")
            emit_info(
                Text.from_markup(f"[red]Failed to start servers: {e}[/red]"),
                message_group=group_id,
            )
