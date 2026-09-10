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
from typing import Any, Dict, Optional

from pydantic_ai.toolsets import AbstractToolset

from code_puppy.mcp_.toolset_utils import toolset_is_running, unwrap_toolset

logger = logging.getLogger(__name__)


@dataclass
class ManagedServerContext:
    """Represents a managed MCP server with its async context."""

    server_id: str
    server: AbstractToolset[Any]
    exit_stack: AsyncExitStack
    start_time: datetime
    task: asyncio.Task  # The task that manages this server's lifecycle
    cleanup_failed: bool = False


SERVER_STOP_TIMEOUT = 5.0


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
        server: AbstractToolset[Any],
    ) -> bool:
        """
        Start an MCP server toolset and maintain its context.

        This creates a dedicated task that enters the toolset's context
        and keeps it alive until explicitly stopped.

        Args:
            server_id: Unique identifier for the server
            server: The pydantic-ai toolset (``MCPToolset`` or a wrapper)

        Returns:
            True if server started successfully, False otherwise
        """
        # A stale lifecycle must drain without holding the registry lock.
        existing = self._servers.get(server_id)
        if existing is not None:
            if self.is_running(server_id):
                return True
            if not await self.stop_server(server_id):
                return False

        async with self._lock:
            if server_id in self._servers:
                return self.is_running(server_id)

            # Create an event so we know when the server is actually registered
            ready_event = asyncio.Event()

            # Create a task that will manage this server's lifecycle
            task = asyncio.create_task(
                self._server_lifecycle_task(server_id, server, ready_event),
                name=f"mcp_server_{server_id}",
            )

        # Release the lock while waiting for the server to become ready
        try:
            await asyncio.wait_for(ready_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(f"Timed out waiting for server {server_id} to start")
            if task.done():
                try:
                    await task
                except Exception as e:
                    logger.error(f"Server {server_id} task failed: {e}")
            return False

        # Check if task failed during startup
        if task.done():
            try:
                await task
            except Exception as e:
                logger.error(f"Failed to start server {server_id}: {e}")
                return False

        logger.info(f"Server {server_id} started successfully")
        return True

    async def _server_lifecycle_task(
        self,
        server_id: str,
        server: AbstractToolset[Any],
        ready_event: asyncio.Event,
    ) -> None:
        """
        Task that manages a server's lifecycle.

        This task enters the server's context and keeps it alive
        until the server is stopped or an error occurs.
        """
        exit_stack = AsyncExitStack()
        leaf = unwrap_toolset(server)

        try:
            logger.info(f"Starting server lifecycle for {server_id}")
            logger.info(
                f"Server {server_id} _running_count before enter: {getattr(leaf, '_running_count', 'N/A')}"
            )

            # Enter the server's context
            await exit_stack.enter_async_context(server)

            logger.info(
                f"Server {server_id} _running_count after enter: {getattr(leaf, '_running_count', 'N/A')}"
            )

            # Store the managed context
            async with self._lock:
                self._servers[server_id] = ManagedServerContext(
                    server_id=server_id,
                    server=server,
                    exit_stack=exit_stack,
                    start_time=datetime.now(),
                    task=asyncio.current_task(),
                )

            # Signal that the server is registered and ready
            ready_event.set()

            logger.info(
                f"Server {server_id} started successfully and stored in _servers"
            )

            # Keep the task alive until cancelled
            loop_count = 0
            while True:
                await asyncio.sleep(1)
                loop_count += 1

                # Check if server is still running
                running_count = getattr(leaf, "_running_count", "N/A")
                is_running = toolset_is_running(server)
                logger.debug(
                    f"Server {server_id} heartbeat #{loop_count}: "
                    f"is_running={is_running}, _running_count={running_count}"
                )

                if not is_running:
                    logger.warning(
                        f"Server {server_id} stopped unexpectedly! "
                        f"_running_count={running_count}"
                    )
                    break

        except asyncio.CancelledError:
            logger.info(f"Server {server_id} lifecycle task cancelled")
            raise
        except Exception as e:
            # Debug-only: user-facing error already emitted by blocking_startup
            # (/mcp logs hint); full traceback preserved at debug level.
            logger.debug(f"Error in server {server_id} lifecycle: {e}", exc_info=True)
        finally:
            running_count = getattr(leaf, "_running_count", "N/A")
            logger.info(
                f"Server {server_id} lifecycle ending, _running_count={running_count}"
            )

            cleanup_failed = False
            try:
                await exit_stack.aclose()
            except (Exception, BaseExceptionGroup, asyncio.CancelledError):
                cleanup_failed = True
                logger.warning(
                    "MCP cleanup failed for %s; retaining lifecycle", server_id
                )
                logger.debug("MCP cleanup exception for %s", server_id, exc_info=True)

            running_count_after = getattr(leaf, "_running_count", "N/A")
            logger.info(
                f"Server {server_id} context closed, _running_count={running_count_after}"
            )

            # Remove from managed servers
            try:
                async with self._lock:
                    context = self._servers.get(server_id)
                    if context is not None and context.task is asyncio.current_task():
                        if cleanup_failed:
                            context.cleanup_failed = True
                        else:
                            del self._servers[server_id]
            except Exception as e:
                logger.debug(f"Error removing {server_id} from registry: {e}")

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
            context = self._servers.get(server_id)
            if context is None:
                return False
            task = context.task
            if not task.done() and not task.cancelling():
                task.cancel()

        # wait() bounds the caller without cancelling the draining task again.
        # Caller cancellation propagates; cleanup retains its original owner.
        done, _ = await asyncio.wait({task}, timeout=SERVER_STOP_TIMEOUT)
        if not done:
            logger.warning("MCP cleanup deadline exceeded for %s", server_id)
            return False
        if not task.cancelled():
            try:
                task.result()
            except (Exception, BaseExceptionGroup):
                logger.debug(
                    "MCP lifecycle task failed for %s", server_id, exc_info=True
                )
                return False
        return (
            not context.cleanup_failed and self._servers.get(server_id) is not context
        )

    def is_running(self, server_id: str) -> bool:
        """
        Check if a server is running.

        Args:
            server_id: ID of the server

        Returns:
            True if server is running, False otherwise
        """
        context = self._servers.get(server_id)
        return bool(
            context
            and not context.task.done()
            and not context.task.cancelling()
            and toolset_is_running(context.server)
        )

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
                "type": unwrap_toolset(context.server).__class__.__name__,
                "is_running": toolset_is_running(context.server),
                "uptime_seconds": uptime,
                "start_time": context.start_time.isoformat(),
            }
        return servers

    async def stop_all(self) -> None:
        """Drain registered lifecycles concurrently, including cancelled ones."""
        server_ids = list(self._servers)
        results = await asyncio.gather(*(self.stop_server(key) for key in server_ids))
        if not all(results):
            logger.warning("MCP shutdown incomplete; undrained lifecycles retained")


# Global singleton instance
_lifecycle_manager: Optional[AsyncServerLifecycleManager] = None


def get_lifecycle_manager() -> AsyncServerLifecycleManager:
    """Get the global lifecycle manager instance."""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = AsyncServerLifecycleManager()
    return _lifecycle_manager
