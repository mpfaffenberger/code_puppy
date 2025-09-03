"""
Async server lifecycle management using pydantic-ai's context managers.

This module properly manages MCP server lifecycles by maintaining async contexts
within the same task, allowing servers to start and stay running.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Union

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

logger = logging.getLogger(__name__)


@dataclass
class ManagedServerContext:
    """Represents a managed MCP server with its async context."""

    server_id: str
    server: Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]
    exit_stack: AsyncExitStack
    start_time: datetime
    task: asyncio.Task  # The task that manages this server's lifecycle


class AsyncServerLifecycleManager:
    """
    Manages MCP server lifecycles asynchronously.

    This properly maintains async contexts within the same task,
    allowing servers to start and stay running independently of agents.
    """

    def __init__(self):
        """Initialize the async lifecycle manager."""
        self._servers: Dict[str, ManagedServerContext] = {}
        self._lock = asyncio.Lock()
        logger.info("AsyncServerLifecycleManager initialized")

    async def start_server(
        self,
        server_id: str,
        server: Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP],
    ) -> bool:
        """
        Start an MCP server and maintain its context.

        This creates a dedicated task that enters the server's context
        and keeps it alive until explicitly stopped.

        Args:
            server_id: Unique identifier for the server
            server: The pydantic-ai MCP server instance

        Returns:
            True if server started successfully, False otherwise
        """
        async with self._lock:
            # Check if already running
            if server_id in self._servers:
                if self._servers[server_id].server.is_running:
                    logger.info(f"Server {server_id} is already running")
                    return True
                else:
                    # Server exists but not running, clean it up
                    logger.warning(
                        f"Server {server_id} exists but not running, cleaning up"
                    )
                    await self._stop_server_internal(server_id)

            # Create a task that will manage this server's lifecycle
            task = asyncio.create_task(
                self._server_lifecycle_task(server_id, server),
                name=f"mcp_server_{server_id}",
            )

            # Wait briefly for the server to start
            await asyncio.sleep(0.1)

            # Check if task failed immediately
            if task.done():
                try:
                    await task
                except Exception as e:
                    logger.error(f"Failed to start server {server_id}: {e}")
                    return False

            logger.info(f"Server {server_id} starting in background task")
            return True

    async def _server_lifecycle_task(
        self,
        server_id: str,
        server: Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP],
    ) -> None:
        """
        Task that manages a server's lifecycle.

        This task enters the server's context and keeps it alive
        until the server is stopped or an error occurs.
        """
        exit_stack = AsyncExitStack()

        try:
            logger.info(f"Starting server lifecycle for {server_id}")

            # Enter the server's context
            await exit_stack.enter_async_context(server)

            # Store the managed context
            async with self._lock:
                self._servers[server_id] = ManagedServerContext(
                    server_id=server_id,
                    server=server,
                    exit_stack=exit_stack,
                    start_time=datetime.now(),
                    task=asyncio.current_task(),
                )

            logger.info(f"Server {server_id} started successfully")

            # Keep the task alive until cancelled
            while True:
                await asyncio.sleep(1)

                # Check if server is still running
                if not server.is_running:
                    logger.warning(f"Server {server_id} stopped unexpectedly")
                    break

        except asyncio.CancelledError:
            logger.info(f"Server {server_id} lifecycle task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in server {server_id} lifecycle: {e}")
        finally:
            # Clean up the context
            await exit_stack.aclose()

            # Remove from managed servers
            async with self._lock:
                if server_id in self._servers:
                    del self._servers[server_id]

            logger.info(f"Server {server_id} lifecycle ended")

    async def stop_server(self, server_id: str) -> bool:
        """
        Stop a running MCP server.

        This cancels the lifecycle task, which properly exits the context.

        Args:
            server_id: ID of the server to stop

        Returns:
            True if server was stopped, False if not found
        """
        async with self._lock:
            return await self._stop_server_internal(server_id)

    async def _stop_server_internal(self, server_id: str) -> bool:
        """
        Internal method to stop a server (must be called with lock held).
        """
        if server_id not in self._servers:
            logger.warning(f"Server {server_id} not found")
            return False

        context = self._servers[server_id]

        # Cancel the lifecycle task
        # This will cause the task to exit and clean up properly
        context.task.cancel()

        try:
            await context.task
        except asyncio.CancelledError:
            pass  # Expected

        logger.info(f"Stopped server {server_id}")
        return True

    def is_running(self, server_id: str) -> bool:
        """
        Check if a server is running.

        Args:
            server_id: ID of the server

        Returns:
            True if server is running, False otherwise
        """
        context = self._servers.get(server_id)
        return context.server.is_running if context else False

    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        List all running servers.

        Returns:
            Dictionary of server IDs to server info
        """
        servers = {}
        for server_id, context in self._servers.items():
            uptime = (datetime.now() - context.start_time).total_seconds()
            servers[server_id] = {
                "type": context.server.__class__.__name__,
                "is_running": context.server.is_running,
                "uptime_seconds": uptime,
                "start_time": context.start_time.isoformat(),
            }
        return servers

    async def stop_all(self) -> None:
        """Stop all running servers."""
        server_ids = list(self._servers.keys())

        for server_id in server_ids:
            await self.stop_server(server_id)

        logger.info("All MCP servers stopped")


# Global singleton instance
_lifecycle_manager: Optional[AsyncServerLifecycleManager] = None


def get_lifecycle_manager() -> AsyncServerLifecycleManager:
    """Get the global lifecycle manager instance."""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = AsyncServerLifecycleManager()
    return _lifecycle_manager
