"""Manager-facing lifecycle coordination, separate from context ownership.

The async lifecycle manager owns MCP contexts. This mixin owns user requests,
status reporting, and deduplicated tasks shared by sync and async entry points.
"""

import asyncio
import logging
from typing import Any, Dict

from .managed_server import ServerState

logger = logging.getLogger(__name__)


class ManagerLifecycleMixin:
    """Coordinate starts/stops without claiming readiness before startup succeeds."""

    def is_autostart_suppressed(self, server_id: str) -> bool:
        """Whether stop/failure requires an explicit start before agent autostart."""
        return server_id in getattr(self, "_autostart_suppressed", set())

    def _set_autostart_suppressed(self, server_id: str, suppressed: bool) -> None:
        if not hasattr(self, "_autostart_suppressed"):
            self._autostart_suppressed = set()
        if suppressed:
            self._autostart_suppressed.add(server_id)
        else:
            self._autostart_suppressed.discard(server_id)

    def _disable_for_lifecycle(self, server_id: str) -> None:
        from .agent_bindings import invalidate_agent_mcp_cache

        # Suppress before disabling/invalidation: rebuilding must not restart it.
        self._set_autostart_suppressed(server_id, True)
        self._managed_servers[server_id].disable()
        invalidate_agent_mcp_cache()

    def _lifecycle_tasks(self, operation):
        name = f"_pending_{operation}_tasks"
        if not hasattr(self, name):
            setattr(self, name, {})
        return getattr(self, name)

    def _track_lifecycle_task(self, operation, server_id, coroutine):
        tasks = self._lifecycle_tasks(operation)
        task = asyncio.get_running_loop().create_task(
            coroutine, name=f"{operation}_server_{server_id}"
        )
        tasks[server_id] = task

        def cleanup(completed):
            # A completed predecessor must never remove its replacement.
            if tasks.get(server_id) is completed:
                tasks.pop(server_id, None)

        task.add_done_callback(cleanup)
        return task

    def _request_start(self, server_id):
        if server_id not in self._managed_servers:
            return None
        stopping = self._lifecycle_tasks("stop").get(server_id)
        if stopping is not None and not stopping.done():
            # Do not queue an implicit restart behind a user's stop request.
            return None
        self._set_autostart_suppressed(server_id, False)
        pending = self._lifecycle_tasks("start").get(server_id)
        if pending is not None and not pending.done():
            return pending
        self.status_tracker.set_status(server_id, ServerState.STARTING)
        return self._track_lifecycle_task(
            "start", server_id, self._start_server_process(server_id)
        )

    async def start_server(self, server_id: str) -> bool:
        """Start a process, returning True only once it is actually ready."""
        task = self._request_start(server_id)
        return await asyncio.shield(task) if task is not None else False

    async def _start_server_process(self, server_id):
        from .agent_bindings import invalidate_agent_mcp_cache

        # Retain the historic patch/import hook on manager.py.
        from .manager import get_lifecycle_manager

        managed = self._managed_servers[server_id]
        try:
            server = managed.get_pydantic_server()
            started = await get_lifecycle_manager().start_server(server_id, server)
            # A lifecycle implementation may suppress cancellation. Stop still wins.
            stopping = self._lifecycle_tasks("stop").get(server_id)
            if stopping is not None and not stopping.done():
                return False
            if not started:
                raise RuntimeError("Server process failed to start")
            managed.enable()
            self.status_tracker.set_status(server_id, ServerState.RUNNING)
            self.status_tracker.record_start_time(server_id)
            self.status_tracker.record_event(
                server_id, "started", {"message": "Server started and process running"}
            )
            invalidate_agent_mcp_cache()
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._disable_for_lifecycle(server_id)
            self.status_tracker.set_status(server_id, ServerState.ERROR)
            self.status_tracker.record_event(
                server_id, "start_error", {"error": str(exc)}
            )
            logger.warning("Failed to start server %s: %s", server_id, exc)
            return False

    def start_server_sync(self, server_id: str) -> bool:
        """Schedule startup; True means accepted, not ready.

        Without a running loop we cannot retain a live MCP context, so report
        failure rather than pretend that enabling a config started a process.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            if server_id in self._managed_servers:
                self._disable_for_lifecycle(server_id)
            logger.warning(
                "Cannot start MCP server without an event loop: %s", server_id
            )
            return False
        return self._request_start(server_id) is not None

    async def wait_for_pending_starts(self, timeout: float = 15.0) -> None:
        """Wait for readiness without cancelling startup on timeout."""
        tasks = [
            task for task in self._lifecycle_tasks("start").values() if not task.done()
        ]
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=timeout)
            if pending:
                logger.warning(
                    "Timed out waiting for %d pending MCP server start(s)", len(pending)
                )

    def _request_stop(self, server_id):
        managed = self._managed_servers.get(server_id)
        if managed is None:
            return None
        pending = self._lifecycle_tasks("stop").get(server_id)
        if pending is not None and not pending.done():
            return pending
        # Synchronous invalidation is essential: a queued start must not get
        # its first execution between stop_server_sync and its background task.
        self._disable_for_lifecycle(server_id)
        self.status_tracker.set_status(server_id, ServerState.STOPPING)
        starting = self._lifecycle_tasks("start").get(server_id)
        if starting is not None and not starting.done():
            starting.cancel()
        return self._track_lifecycle_task(
            "stop", server_id, self._stop_server_process(server_id, starting)
        )

    async def stop_server(self, server_id: str) -> bool:
        """Cancel and drain startup, then release any established context."""
        task = self._request_stop(server_id)
        return await asyncio.shield(task) if task is not None else False

    async def _stop_server_process(self, server_id, starting):
        from .manager import get_lifecycle_manager

        try:
            if starting is not None:
                await asyncio.gather(starting, return_exceptions=True)
            stopped = await get_lifecycle_manager().stop_server(server_id)
            self.status_tracker.set_status(server_id, ServerState.STOPPED)
            self.status_tracker.record_stop_time(server_id)
            self.status_tracker.record_event(
                server_id,
                "stopped" if stopped else "disabled",
                {"message": "Server disabled and process stopped"},
            )
            return True
        except Exception as exc:
            self.status_tracker.set_status(server_id, ServerState.ERROR)
            self.status_tracker.record_event(
                server_id, "stop_error", {"error": str(exc)}
            )
            logger.warning("Failed to stop server %s: %s", server_id, exc)
            return False

    def stop_server_sync(self, server_id: str) -> bool:
        """Disable immediately and schedule context cleanup when a loop exists."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            managed = self._managed_servers.get(server_id)
            if managed is None:
                return False
            self._disable_for_lifecycle(server_id)
            self.status_tracker.set_status(server_id, ServerState.STOPPED)
            self.status_tracker.record_stop_time(server_id)
            return True
        return self._request_stop(server_id) is not None

    def reload_server(self, server_id: str) -> bool:
        """
        Reload a server configuration.

        Args:
            server_id: ID of server to reload

        Returns:
            True if server was reloaded, False if not found or failed
        """
        from .manager import ManagedMCPServer

        config = self.registry.get(server_id)
        if config is None:
            logger.warning(f"Attempted to reload non-existent server: {server_id}")
            return False

        try:
            # Remove old managed server
            if server_id in self._managed_servers:
                old_server = self._managed_servers[server_id]
                logger.debug(f"Removing old server instance: {old_server.config.name}")
                del self._managed_servers[server_id]

            # Create new managed server
            managed_server = ManagedMCPServer(config)
            self._managed_servers[server_id] = managed_server

            # Update status tracker - always start as STOPPED
            # Servers must be explicitly started with /mcp start
            self.status_tracker.set_status(server_id, ServerState.STOPPED)

            # Record reload event
            self.status_tracker.record_event(
                server_id, "reloaded", {"message": "Server configuration reloaded"}
            )

            logger.info(f"Reloaded server: {config.name} (ID: {server_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to reload server {server_id}: {e}")
            self.status_tracker.set_status(server_id, ServerState.ERROR)
            self.status_tracker.record_event(
                server_id,
                "reload_error",
                {"error": str(e), "message": f"Error reloading server: {e}"},
            )
            return False

    def get_server_status(self, server_id: str) -> Dict[str, Any]:
        """
        Get comprehensive status for a server.

        Args:
            server_id: ID of server to get status for

        Returns:
            Dictionary containing comprehensive status information
        """
        # Get basic status from managed server
        managed_server = self._managed_servers.get(server_id)
        if managed_server is None:
            return {
                "server_id": server_id,
                "exists": False,
                "error": "Server not found",
            }

        try:
            # Get status from managed server
            status = managed_server.get_status()

            # Add status tracker information
            tracker_summary = self.status_tracker.get_server_summary(server_id)
            recent_events = self.status_tracker.get_events(server_id, limit=5)

            # Combine all information
            comprehensive_status = {
                **status,  # Include all managed server status
                "tracker_state": tracker_summary["state"],
                "tracker_metadata": tracker_summary["metadata"],
                "recent_events_count": tracker_summary["recent_events_count"],
                "tracker_uptime": tracker_summary["uptime"],
                "last_event_time": tracker_summary["last_event_time"],
                "recent_events": [
                    {
                        "timestamp": event.timestamp.isoformat(),
                        "event_type": event.event_type,
                        "details": event.details,
                    }
                    for event in recent_events
                ],
            }

            return comprehensive_status

        except Exception as e:
            logger.error(f"Error getting status for server {server_id}: {e}")
            return {"server_id": server_id, "exists": True, "error": str(e)}
