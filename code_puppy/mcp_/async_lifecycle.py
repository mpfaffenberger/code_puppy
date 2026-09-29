"""
Async server lifecycle management using pydantic-ai's context managers.

This module properly manages MCP server lifecycles by maintaining async contexts
within the same task, allowing servers to start and stay running.
"""

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
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
    task: Optional[asyncio.Task] = None
    ready: asyncio.Future[bool] = field(
        default_factory=lambda: asyncio.get_running_loop().create_future()
    )
    stopping: bool = False


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
            True if ready, False on failure, timeout, or an explicit stop.
            Duplicate starts share the pending result (the first toolset wins).
            Cancelling the creating caller cancels and joins its pending start;
            cancelling a duplicate waiter only abandons that wait.
        """
        # Publish pending starts before yielding: stop and duplicate starts must
        # see the same lifecycle, including while OAuth blocks __aenter__.
        async with self._lock:
            context = self._servers.get(server_id)
            owner = context is None
            if context is None:
                context = ManagedServerContext(
                    server_id=server_id,
                    server=server,
                    exit_stack=AsyncExitStack(),
                    start_time=datetime.now(),
                )
                self._servers[server_id] = context
                context.task = asyncio.create_task(
                    self._server_lifecycle_task(context),
                    name=f"mcp_server_{server_id}",
                )
                context.task.add_done_callback(
                    lambda task: self._lifecycle_finished(context, task)
                )
            elif context.stopping:
                return False

        try:
            # A duplicate waiter cannot cancel the shared startup result.
            started = await asyncio.shield(context.ready)
            return started and self.is_running(server_id)
        except asyncio.CancelledError:
            # The caller that created a pending start owns its cancellation.
            # Duplicate callers can abandon their wait without stopping it.
            if owner:
                await self._stop_context(context)
            raise

    def _lifecycle_finished(
        self, context: ManagedServerContext, task: asyncio.Task
    ) -> None:
        """Finalize even a task cancelled before its coroutine first executes.

        This synchronous callback is atomic on the owning event loop. Identity
        checking prevents an old lifecycle from removing a replacement.
        """
        if self._servers.get(context.server_id) is context:
            del self._servers[context.server_id]
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.debug("Server %s lifecycle failed: %s", context.server_id, error)
        if not context.ready.done():
            context.ready.set_result(False)

    async def _server_lifecycle_task(self, context: ManagedServerContext) -> None:
        """Enter, run, and exit the toolset in one task (required by AnyIO)."""
        server_id = context.server_id
        server = context.server
        try:
            # Wrappers need their leaf's timeout. None explicitly disables the
            # deadline; generic toolsets without one retain the 10s fallback.
            timeout = getattr(unwrap_toolset(server), "init_timeout", 10.0)
            async with asyncio.timeout(timeout):
                await context.exit_stack.enter_async_context(server)
            if context.stopping:
                return
            context.start_time = datetime.now()
            context.ready.set_result(True)
            logger.info("Server %s started successfully", server_id)

            while True:
                await asyncio.sleep(1)
                if not toolset_is_running(server):
                    logger.warning("Server %s stopped unexpectedly", server_id)
                    break
        except asyncio.CancelledError:
            logger.info("Server %s lifecycle task cancelled", server_id)
            raise
        except TimeoutError:
            logger.error("Timed out waiting for server %s to start", server_id)
        except Exception:
            # The False startup result reports failure to callers immediately;
            # preserve details at debug level for /mcp logs.
            logger.debug("Error in server %s lifecycle", server_id, exc_info=True)
        finally:
            context.stopping = True
            try:
                await context.exit_stack.aclose()
            except (Exception, BaseExceptionGroup):
                logger.debug(
                    "Server %s cleanup raised (suppressed)", server_id, exc_info=True
                )

    async def _stop_context(self, context: ManagedServerContext) -> None:
        """Cancel once, then join without holding the registry lock.

        Shield the join so cancelling a stop caller (or a second stop) cannot
        inject another cancellation into the toolset's async cleanup.
        """
        task = context.task
        assert task is not None
        if not context.stopping:
            context.stopping = True
            task.cancel()
        await asyncio.shield(asyncio.gather(task, return_exceptions=True))

    async def stop_server(self, server_id: str) -> bool:
        """Stop a pending or running server and wait for its context to close.

        Return False only when no lifecycle is registered. Concurrent stops
        join the same cleanup; no task is awaited under the registry lock.
        """
        async with self._lock:
            context = self._servers.get(server_id)
        if context is None:
            logger.warning("Server %s not found", server_id)
            return False
        await self._stop_context(context)
        logger.info("Stopped server %s", server_id)
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
        return bool(
            context
            and context.ready.done()
            and context.ready.result()
            and not context.stopping
            and toolset_is_running(context.server)
        )

    def list_servers(self) -> Dict[str, Dict[str, Any]]:
        """
        List registered servers, including pending starts and cleanup.

        Returns:
            Dictionary of server IDs to server info
        """
        servers = {}
        for server_id, context in self._servers.items():
            uptime = (datetime.now() - context.start_time).total_seconds()
            servers[server_id] = {
                "type": unwrap_toolset(context.server).__class__.__name__,
                "is_running": self.is_running(server_id),
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
