"""
Health monitoring system for MCP servers.

This module provides continuous health monitoring for MCP servers with
automatic recovery actions when consecutive failures are detected.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

import httpx

from .managed_server import ManagedMCPServer

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Status of a health check for an MCP server."""

    timestamp: datetime
    is_healthy: bool
    latency_ms: Optional[float]
    error: Optional[str]
    check_type: str  # "ping", "list_tools", "get_request", etc.


@dataclass
class HealthCheckResult:
    """Result of performing a health check."""

    success: bool
    latency_ms: float
    error: Optional[str]


class HealthMonitor:
    """
    Continuous health monitoring system for MCP servers.

    Features:
    - Background monitoring tasks using asyncio
    - Server type-specific health checks
    - Health history tracking with configurable limit
    - Custom health check registration
    - Automatic recovery triggering on consecutive failures
    - Configurable check intervals

    Example usage:
        monitor = HealthMonitor(check_interval=30)
        await monitor.start_monitoring("server-1", managed_server)

        # Check current health
        is_healthy = monitor.is_healthy("server-1")

        # Get health history
        history = monitor.get_health_history("server-1", limit=50)
    """

    def __init__(self, check_interval: int = 30):
        """
        Initialize the health monitor.

        Args:
            check_interval: Interval between health checks in seconds
        """
        self.check_interval = check_interval
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        self.health_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.custom_health_checks: Dict[str, Callable] = {}
        self.consecutive_failures: Dict[str, int] = defaultdict(int)
        self.last_check_time: Dict[str, datetime] = {}

        # Register default health checks for each server type
        self._register_default_health_checks()

        logger.info(f"Health monitor initialized with {check_interval}s check interval")

    def _register_default_health_checks(self) -> None:
        """Register default health check methods for each server type."""
        self.register_health_check("sse", self._check_sse_health)
        self.register_health_check("http", self._check_http_health)
        self.register_health_check("stdio", self._check_stdio_health)

    async def start_monitoring(self, server_id: str, server: ManagedMCPServer) -> None:
        """
        Start continuous health monitoring for a server.

        Args:
            server_id: Unique identifier for the server
            server: The managed MCP server instance to monitor
        """
        if server_id in self.monitoring_tasks:
            logger.warning(f"Server {server_id} is already being monitored")
            return

        logger.info(f"Starting health monitoring for server {server_id}")

        # Create background monitoring task
        task = asyncio.create_task(
            self._monitoring_loop(server_id, server), name=f"health_monitor_{server_id}"
        )
        self.monitoring_tasks[server_id] = task

        # Perform initial health check
        try:
            health_status = await self.check_health(server)
            self._record_health_status(server_id, health_status)
        except Exception as e:
            logger.error(f"Initial health check failed for {server_id}: {e}")
            error_status = HealthStatus(
                timestamp=datetime.now(),
                is_healthy=False,
                latency_ms=None,
                error=str(e),
                check_type="initial",
            )
            self._record_health_status(server_id, error_status)

    async def stop_monitoring(self, server_id: str) -> None:
        """
        Stop health monitoring for a server.

        Args:
            server_id: Unique identifier for the server
        """
        task = self.monitoring_tasks.pop(server_id, None)
        if task:
            logger.info(f"Stopping health monitoring for server {server_id}")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Clean up tracking data
            self.consecutive_failures.pop(server_id, None)
            self.last_check_time.pop(server_id, None)
        else:
            logger.warning(f"No monitoring task found for server {server_id}")

    async def check_health(self, server: ManagedMCPServer) -> HealthStatus:
        """
        Perform a health check for a server.

        Args:
            server: The managed MCP server to check

        Returns:
            HealthStatus object with check results
        """
        server_type = server.config.type.lower()
        check_func = self.custom_health_checks.get(server_type)

        if not check_func:
            logger.warning(
                f"No health check function registered for server type: {server_type}"
            )
            return HealthStatus(
                timestamp=datetime.now(),
                is_healthy=False,
                latency_ms=None,
                error=f"No health check registered for type '{server_type}'",
                check_type="unknown",
            )

        try:
            result = await self.perform_health_check(server)
            return HealthStatus(
                timestamp=datetime.now(),
                is_healthy=result.success,
                latency_ms=result.latency_ms,
                error=result.error,
                check_type=server_type,
            )
        except Exception as e:
            logger.error(f"Health check failed for server {server.config.id}: {e}")
            return HealthStatus(
                timestamp=datetime.now(),
                is_healthy=False,
                latency_ms=None,
                error=str(e),
                check_type=server_type,
            )

    async def perform_health_check(self, server: ManagedMCPServer) -> HealthCheckResult:
        """
        Perform the actual health check based on server type.

        Args:
            server: The managed MCP server to check

        Returns:
            HealthCheckResult with timing and success information
        """
        server_type = server.config.type.lower()
        check_func = self.custom_health_checks.get(server_type)

        if not check_func:
            return HealthCheckResult(
                success=False,
                latency_ms=0.0,
                error=f"No health check function for type '{server_type}'",
            )

        start_time = time.time()
        try:
            result = await check_func(server)
            latency_ms = (time.time() - start_time) * 1000

            if isinstance(result, bool):
                return HealthCheckResult(
                    success=result,
                    latency_ms=latency_ms,
                    error=None if result else "Health check returned False",
                )
            elif isinstance(result, HealthCheckResult):
                # Update latency if not already set
                if result.latency_ms == 0.0:
                    result.latency_ms = latency_ms
                return result
            else:
                return HealthCheckResult(
                    success=False,
                    latency_ms=latency_ms,
                    error=f"Invalid health check result type: {type(result)}",
                )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return HealthCheckResult(success=False, latency_ms=latency_ms, error=str(e))

    def register_health_check(self, server_type: str, check_func: Callable) -> None:
        """
        Register a custom health check function for a server type.

        Args:
            server_type: The server type ("sse", "http", "stdio")
            check_func: Async function that takes a ManagedMCPServer and returns
                       bool or HealthCheckResult
        """
        self.custom_health_checks[server_type.lower()] = check_func
        logger.info(f"Registered health check for server type: {server_type}")

    def get_health_history(
        self, server_id: str, limit: int = 100
    ) -> List[HealthStatus]:
        """
        Get health check history for a server.

        Args:
            server_id: Unique identifier for the server
            limit: Maximum number of history entries to return

        Returns:
            List of HealthStatus objects, most recent first
        """
        history = self.health_history.get(server_id, deque())
        # Convert deque to list and limit results
        result = list(history)[-limit:] if limit > 0 else list(history)
        # Reverse to get most recent first
        result.reverse()
        return result

    def is_healthy(self, server_id: str) -> bool:
        """
        Check if a server is currently healthy based on latest status.

        Args:
            server_id: Unique identifier for the server

        Returns:
            True if server is healthy, False otherwise
        """
        history = self.health_history.get(server_id)
        if not history:
            return False

        # Get most recent health status
        latest_status = history[-1]
        return latest_status.is_healthy

    async def _monitoring_loop(self, server_id: str, server: ManagedMCPServer) -> None:
        """
        Main monitoring loop that runs in the background.

        Args:
            server_id: Unique identifier for the server
            server: The managed MCP server to monitor
        """
        logger.info(f"Starting monitoring loop for server {server_id}")

        while True:
            try:
                # Wait for check interval
                await asyncio.sleep(self.check_interval)

                # Skip if server is not enabled
                if not server.is_enabled():
                    continue

                # Perform health check
                health_status = await self.check_health(server)
                self._record_health_status(server_id, health_status)

                # Handle consecutive failures
                if not health_status.is_healthy:
                    self.consecutive_failures[server_id] += 1
                    logger.warning(
                        f"Health check failed for {server_id}: {health_status.error} "
                        f"(consecutive failures: {self.consecutive_failures[server_id]})"
                    )

                    # Trigger recovery on consecutive failures
                    await self._handle_consecutive_failures(server_id, server)
                else:
                    # Reset consecutive failure count on success
                    if self.consecutive_failures[server_id] > 0:
                        logger.info(
                            f"Server {server_id} recovered after health check success"
                        )
                        self.consecutive_failures[server_id] = 0

                self.last_check_time[server_id] = datetime.now()

            except asyncio.CancelledError:
                logger.info(f"Monitoring loop cancelled for server {server_id}")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop for {server_id}: {e}")
                # Continue monitoring despite errors
                await asyncio.sleep(5)  # Brief delay before retrying

    def _record_health_status(self, server_id: str, status: HealthStatus) -> None:
        """
        Record a health status in the history.

        Args:
            server_id: Unique identifier for the server
            status: The health status to record
        """
        self.health_history[server_id].append(status)

        # Log health status changes
        if status.is_healthy:
            logger.debug(
                f"Server {server_id} health check passed ({status.latency_ms:.1f}ms)"
            )
        else:
            logger.warning(f"Server {server_id} health check failed: {status.error}")

    async def _handle_consecutive_failures(
        self, server_id: str, server: ManagedMCPServer
    ) -> None:
        """
        Handle consecutive health check failures.

        Args:
            server_id: Unique identifier for the server
            server: The managed MCP server
        """
        failure_count = self.consecutive_failures[server_id]

        # Trigger recovery actions based on failure count
        if failure_count >= 3:
            logger.error(
                f"Server {server_id} has {failure_count} consecutive failures, triggering recovery"
            )

            try:
                # Attempt to recover the server
                await self._trigger_recovery(server_id, server, failure_count)
            except Exception as e:
                logger.error(f"Recovery failed for server {server_id}: {e}")

        # Quarantine server after many consecutive failures
        if failure_count >= 5:
            logger.critical(
                f"Quarantining server {server_id} after {failure_count} consecutive failures"
            )
            try:
                # Calculate quarantine duration with exponential backoff
                quarantine_duration = min(
                    30 * (2 ** (failure_count - 5)), 1800
                )  # Max 30 minutes
                server.quarantine(quarantine_duration)
            except Exception as e:
                logger.error(f"Failed to quarantine server {server_id}: {e}")

    async def _trigger_recovery(
        self, server_id: str, server: ManagedMCPServer, failure_count: int
    ) -> None:
        """
        Trigger recovery actions for a failing server.

        Args:
            server_id: Unique identifier for the server
            server: The managed MCP server
            failure_count: Number of consecutive failures
        """
        logger.info(
            f"Triggering recovery for server {server_id} (failure count: {failure_count})"
        )

        try:
            # For now, just disable and re-enable the server
            # In the future, this could include more sophisticated recovery actions
            server.disable()
            await asyncio.sleep(1)  # Brief delay
            server.enable()

            logger.info(f"Recovery attempt completed for server {server_id}")

        except Exception as e:
            logger.error(f"Recovery action failed for server {server_id}: {e}")
            raise

    async def _check_sse_health(self, server: ManagedMCPServer) -> HealthCheckResult:
        """
        Health check for SSE servers using GET request.

        Args:
            server: The managed MCP server to check

        Returns:
            HealthCheckResult with check results
        """
        try:
            config = server.config.config
            url = config.get("url")
            if not url:
                return HealthCheckResult(
                    success=False,
                    latency_ms=0.0,
                    error="No URL configured for SSE server",
                )

            # Add health endpoint if available, otherwise use base URL
            health_url = (
                f"{url.rstrip('/')}/health" if not url.endswith("/health") else url
            )

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(health_url)

                if response.status_code == 404:
                    # Try base URL if health endpoint doesn't exist
                    response = await client.get(url)

                success = 200 <= response.status_code < 400
                error = (
                    None
                    if success
                    else f"HTTP {response.status_code}: {response.reason_phrase}"
                )

                return HealthCheckResult(
                    success=success,
                    latency_ms=0.0,  # Will be filled by perform_health_check
                    error=error,
                )

        except Exception as e:
            return HealthCheckResult(success=False, latency_ms=0.0, error=str(e))

    async def _check_http_health(self, server: ManagedMCPServer) -> HealthCheckResult:
        """
        Health check for HTTP servers using GET request.

        Args:
            server: The managed MCP server to check

        Returns:
            HealthCheckResult with check results
        """
        # HTTP servers use the same check as SSE servers
        return await self._check_sse_health(server)

    async def _check_stdio_health(self, server: ManagedMCPServer) -> HealthCheckResult:
        """
        Health check for stdio servers using ping command.

        Args:
            server: The managed MCP server to check

        Returns:
            HealthCheckResult with check results
        """
        try:
            # Get the pydantic server instance
            server.get_pydantic_server()

            # Try to get available tools as a health check
            # This requires the server to be responsive
            try:
                # Attempt to list tools - this is a good health check for MCP servers
                # Note: This is a simplified check. In a real implementation,
                # we'd need to send an actual MCP message

                # For now, we'll check if we can create the server instance
                # and if it appears to be configured correctly
                config = server.config.config
                command = config.get("command")

                if not command:
                    return HealthCheckResult(
                        success=False,
                        latency_ms=0.0,
                        error="No command configured for stdio server",
                    )

                # Basic validation that command exists
                import shutil

                if not shutil.which(command):
                    return HealthCheckResult(
                        success=False,
                        latency_ms=0.0,
                        error=f"Command '{command}' not found in PATH",
                    )

                # If we get here, basic checks passed
                return HealthCheckResult(success=True, latency_ms=0.0, error=None)

            except Exception as e:
                return HealthCheckResult(
                    success=False,
                    latency_ms=0.0,
                    error=f"Server communication failed: {str(e)}",
                )

        except Exception as e:
            return HealthCheckResult(success=False, latency_ms=0.0, error=str(e))

    async def shutdown(self) -> None:
        """
        Shutdown all monitoring tasks gracefully.
        """
        logger.info("Shutting down health monitor")

        # Cancel all monitoring tasks
        tasks = list(self.monitoring_tasks.values())
        for task in tasks:
            task.cancel()

        # Wait for all tasks to complete
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.monitoring_tasks.clear()
        self.consecutive_failures.clear()
        self.last_check_time.clear()

        logger.info("Health monitor shutdown complete")
