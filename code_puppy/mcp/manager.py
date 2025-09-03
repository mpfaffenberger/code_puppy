"""
MCPManager - Central coordinator for all MCP server operations.

This module provides the main MCPManager class that coordinates all MCP server
operations while maintaining pydantic-ai compatibility. It serves as the central
point for managing servers, registering configurations, and providing servers
to agents.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP

from .async_lifecycle import get_lifecycle_manager
from .managed_server import ManagedMCPServer, ServerConfig, ServerState
from .registry import ServerRegistry
from .status_tracker import ServerStatusTracker

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ServerInfo:
    """Information about a registered server."""

    id: str
    name: str
    type: str
    enabled: bool
    state: ServerState
    quarantined: bool
    uptime_seconds: Optional[float]
    error_message: Optional[str]
    health: Optional[Dict[str, Any]] = None
    start_time: Optional[datetime] = None
    latency_ms: Optional[float] = None


class MCPManager:
    """
    Central coordinator for all MCP server operations.

    This class manages the lifecycle of MCP servers while maintaining
    100% pydantic-ai compatibility. It coordinates between the registry,
    status tracker, and managed servers to provide a unified interface
    for server management.

    The critical method get_servers_for_agent() returns actual pydantic-ai
    server instances for use with Agent objects.

    Example usage:
        manager = get_mcp_manager()

        # Register a server
        config = ServerConfig(
            id="",  # Auto-generated
            name="filesystem",
            type="stdio",
            config={"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem"]}
        )
        server_id = manager.register_server(config)

        # Get servers for agent use
        servers = manager.get_servers_for_agent()  # Returns actual pydantic-ai instances
    """

    def __init__(self):
        """Initialize the MCP manager with all required components."""
        # Initialize core components
        self.registry = ServerRegistry()
        self.status_tracker = ServerStatusTracker()

        # Active managed servers (server_id -> ManagedMCPServer)
        self._managed_servers: Dict[str, ManagedMCPServer] = {}

        # Load existing servers from registry
        self._initialize_servers()

        logger.info("MCPManager initialized with core components")

    def _initialize_servers(self) -> None:
        """Initialize managed servers from registry configurations."""
        configs = self.registry.list_all()
        initialized_count = 0

        for config in configs:
            try:
                managed_server = ManagedMCPServer(config)
                self._managed_servers[config.id] = managed_server

                # Update status tracker - always start as STOPPED
                # Servers must be explicitly started with /mcp start
                self.status_tracker.set_status(config.id, ServerState.STOPPED)

                initialized_count += 1
                logger.debug(
                    f"Initialized managed server: {config.name} (ID: {config.id})"
                )

            except Exception as e:
                logger.error(f"Failed to initialize server {config.name}: {e}")
                # Update status tracker with error state
                self.status_tracker.set_status(config.id, ServerState.ERROR)
                self.status_tracker.record_event(
                    config.id,
                    "initialization_error",
                    {"error": str(e), "message": f"Failed to initialize: {e}"},
                )

        logger.info(f"Initialized {initialized_count} servers from registry")

    def register_server(self, config: ServerConfig) -> str:
        """
        Register a new server configuration.

        Args:
            config: Server configuration to register

        Returns:
            Server ID of the registered server

        Raises:
            ValueError: If configuration is invalid or server already exists
            Exception: If server initialization fails
        """
        # Register with registry (validates config and assigns ID)
        server_id = self.registry.register(config)

        try:
            # Create managed server instance
            managed_server = ManagedMCPServer(config)
            self._managed_servers[server_id] = managed_server

            # Update status tracker - always start as STOPPED
            # Servers must be explicitly started with /mcp start
            self.status_tracker.set_status(server_id, ServerState.STOPPED)

            # Record registration event
            self.status_tracker.record_event(
                server_id,
                "registered",
                {
                    "name": config.name,
                    "type": config.type,
                    "message": "Server registered successfully",
                },
            )

            logger.info(
                f"Successfully registered server: {config.name} (ID: {server_id})"
            )
            return server_id

        except Exception as e:
            # Remove from registry if initialization failed
            self.registry.unregister(server_id)
            logger.error(f"Failed to initialize registered server {config.name}: {e}")
            raise

    def get_servers_for_agent(
        self,
    ) -> List[Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]]:
        """
        Get pydantic-ai compatible servers for agent use.

        This is the critical method that must return actual pydantic-ai server
        instances (not wrappers). Only returns enabled, non-quarantined servers.
        Handles errors gracefully by logging but not crashing.

        Returns:
            List of actual pydantic-ai MCP server instances ready for use
        """
        servers = []

        for server_id, managed_server in self._managed_servers.items():
            try:
                # Only include enabled, non-quarantined servers
                if managed_server.is_enabled() and not managed_server.is_quarantined():
                    # Get the actual pydantic-ai server instance
                    pydantic_server = managed_server.get_pydantic_server()
                    servers.append(pydantic_server)

                    logger.debug(
                        f"Added server to agent list: {managed_server.config.name}"
                    )
                else:
                    logger.debug(
                        f"Skipping server {managed_server.config.name}: "
                        f"enabled={managed_server.is_enabled()}, "
                        f"quarantined={managed_server.is_quarantined()}"
                    )

            except Exception as e:
                # Log error but don't crash - continue with other servers
                logger.error(
                    f"Error getting server {managed_server.config.name} for agent: {e}"
                )
                # Record error event
                self.status_tracker.record_event(
                    server_id,
                    "agent_access_error",
                    {
                        "error": str(e),
                        "message": f"Error accessing server for agent: {e}",
                    },
                )
                continue

        logger.debug(f"Returning {len(servers)} servers for agent use")
        return servers

    def get_server(self, server_id: str) -> Optional[ManagedMCPServer]:
        """
        Get managed server by ID.

        Args:
            server_id: ID of server to retrieve

        Returns:
            ManagedMCPServer instance if found, None otherwise
        """
        return self._managed_servers.get(server_id)

    def get_server_by_name(self, name: str) -> Optional[ServerConfig]:
        """
        Get server configuration by name.

        Args:
            name: Name of server to retrieve

        Returns:
            ServerConfig if found, None otherwise
        """
        return self.registry.get_by_name(name)

    def update_server(self, server_id: str, config: ServerConfig) -> bool:
        """
        Update server configuration.

        Args:
            server_id: ID of server to update
            config: New configuration

        Returns:
            True if server was updated, False if not found
        """
        # Update in registry
        if not self.registry.update(server_id, config):
            return False

        # Update managed server if it exists
        managed_server = self._managed_servers.get(server_id)
        if managed_server:
            managed_server.config = config
            # Clear cached server to force recreation on next use
            managed_server.server = None
            logger.info(f"Updated server configuration: {config.name}")

        return True

    def list_servers(self) -> List[ServerInfo]:
        """
        Get information about all registered servers.

        Returns:
            List of ServerInfo objects with current status
        """
        server_infos = []

        for server_id, managed_server in self._managed_servers.items():
            try:
                status = managed_server.get_status()
                uptime = self.status_tracker.get_uptime(server_id)
                summary = self.status_tracker.get_server_summary(server_id)

                # Get health information from metadata
                health_info = self.status_tracker.get_metadata(server_id, "health")
                if health_info is None:
                    # Create basic health info based on state
                    health_info = {
                        "is_healthy": status["state"] == "running",
                        "error": status.get("error_message"),
                    }

                # Get latency from metadata
                latency_ms = self.status_tracker.get_metadata(server_id, "latency_ms")

                server_info = ServerInfo(
                    id=server_id,
                    name=managed_server.config.name,
                    type=managed_server.config.type,
                    enabled=managed_server.is_enabled(),
                    state=ServerState(status["state"]),
                    quarantined=managed_server.is_quarantined(),
                    uptime_seconds=uptime.total_seconds() if uptime else None,
                    error_message=status.get("error_message"),
                    health=health_info,
                    start_time=summary.get("start_time"),
                    latency_ms=latency_ms,
                )

                server_infos.append(server_info)

            except Exception as e:
                logger.error(f"Error getting info for server {server_id}: {e}")
                # Create error info
                config = self.registry.get(server_id)
                if config:
                    server_info = ServerInfo(
                        id=server_id,
                        name=config.name,
                        type=config.type,
                        enabled=False,
                        state=ServerState.ERROR,
                        quarantined=False,
                        uptime_seconds=None,
                        error_message=str(e),
                        health={"is_healthy": False, "error": str(e)},
                        start_time=None,
                        latency_ms=None,
                    )
                    server_infos.append(server_info)

        return server_infos

    async def start_server(self, server_id: str) -> bool:
        """
        Start a server (enable it and start the subprocess/connection).

        This both enables the server for agent use AND starts the actual process.
        For stdio servers, this starts the subprocess.
        For SSE/HTTP servers, this establishes the connection.

        Args:
            server_id: ID of server to start

        Returns:
            True if server was started, False if not found or failed
        """
        managed_server = self._managed_servers.get(server_id)
        if managed_server is None:
            logger.warning(f"Attempted to start non-existent server: {server_id}")
            return False

        try:
            # First enable the server
            managed_server.enable()
            self.status_tracker.set_status(server_id, ServerState.RUNNING)
            self.status_tracker.record_start_time(server_id)

            # Try to actually start it if we have an async context
            try:
                # Get the pydantic-ai server instance
                pydantic_server = managed_server.get_pydantic_server()

                # Start the server using the async lifecycle manager
                lifecycle_mgr = get_lifecycle_manager()
                started = await lifecycle_mgr.start_server(server_id, pydantic_server)

                if started:
                    logger.info(
                        f"Started server process: {managed_server.config.name} (ID: {server_id})"
                    )
                    self.status_tracker.record_event(
                        server_id,
                        "started",
                        {"message": "Server started and process running"},
                    )
                else:
                    logger.warning(
                        f"Could not start process for server {server_id}, but it's enabled"
                    )
                    self.status_tracker.record_event(
                        server_id,
                        "enabled",
                        {"message": "Server enabled (process will start when used)"},
                    )
            except Exception as e:
                # Process start failed, but server is still enabled
                logger.warning(f"Could not start process for server {server_id}: {e}")
                self.status_tracker.record_event(
                    server_id,
                    "enabled",
                    {"message": "Server enabled (process will start when used)"},
                )

            return True

        except Exception as e:
            logger.error(f"Failed to start server {server_id}: {e}")
            self.status_tracker.set_status(server_id, ServerState.ERROR)
            self.status_tracker.record_event(
                server_id,
                "start_error",
                {"error": str(e), "message": f"Error starting server: {e}"},
            )
            return False

    def start_server_sync(self, server_id: str) -> bool:
        """
        Synchronous wrapper for start_server.
        """
        try:
            asyncio.get_running_loop()
            # We're in an async context, but we need to wait for completion
            # Create a future and schedule the coroutine

            # Use run_in_executor to run the async function synchronously
            async def run_async():
                return await self.start_server(server_id)

            # Schedule the task and wait briefly for it to complete
            task = asyncio.create_task(run_async())

            # Give it a moment to complete - this fixes the race condition
            import time

            time.sleep(0.1)  # Small delay to let async tasks progress

            # Check if task completed, if not, fall back to sync enable
            if task.done():
                try:
                    result = task.result()
                    return result
                except Exception:
                    pass

            # If async didn't complete, enable synchronously
            managed_server = self._managed_servers.get(server_id)
            if managed_server:
                managed_server.enable()
                self.status_tracker.set_status(server_id, ServerState.RUNNING)
                self.status_tracker.record_start_time(server_id)
                logger.info(f"Enabled server synchronously: {server_id}")
                return True
            return False

        except RuntimeError:
            # No async loop, just enable the server
            managed_server = self._managed_servers.get(server_id)
            if managed_server:
                managed_server.enable()
                self.status_tracker.set_status(server_id, ServerState.RUNNING)
                self.status_tracker.record_start_time(server_id)
                logger.info(f"Enabled server (no async context): {server_id}")
                return True
            return False

    async def stop_server(self, server_id: str) -> bool:
        """
        Stop a server (disable it and stop the subprocess/connection).

        This both disables the server AND stops any running process.
        For stdio servers, this stops the subprocess.
        For SSE/HTTP servers, this closes the connection.

        Args:
            server_id: ID of server to stop

        Returns:
            True if server was stopped, False if not found
        """
        managed_server = self._managed_servers.get(server_id)
        if managed_server is None:
            logger.warning(f"Attempted to stop non-existent server: {server_id}")
            return False

        try:
            # First disable the server
            managed_server.disable()
            self.status_tracker.set_status(server_id, ServerState.STOPPED)
            self.status_tracker.record_stop_time(server_id)

            # Try to actually stop it if we have an async context
            try:
                # Stop the server using the async lifecycle manager
                lifecycle_mgr = get_lifecycle_manager()
                stopped = await lifecycle_mgr.stop_server(server_id)

                if stopped:
                    logger.info(
                        f"Stopped server process: {managed_server.config.name} (ID: {server_id})"
                    )
                    self.status_tracker.record_event(
                        server_id,
                        "stopped",
                        {"message": "Server stopped and process terminated"},
                    )
                else:
                    logger.info(f"Server {server_id} disabled (no process was running)")
                    self.status_tracker.record_event(
                        server_id, "disabled", {"message": "Server disabled"}
                    )
            except Exception as e:
                # Process stop failed, but server is still disabled
                logger.warning(f"Could not stop process for server {server_id}: {e}")
                self.status_tracker.record_event(
                    server_id, "disabled", {"message": "Server disabled"}
                )

            return True

        except Exception as e:
            logger.error(f"Failed to stop server {server_id}: {e}")
            self.status_tracker.record_event(
                server_id,
                "stop_error",
                {"error": str(e), "message": f"Error stopping server: {e}"},
            )
            return False

    def stop_server_sync(self, server_id: str) -> bool:
        """
        Synchronous wrapper for stop_server.
        """
        try:
            asyncio.get_running_loop()

            # We're in an async context, but we need to wait for completion
            async def run_async():
                return await self.stop_server(server_id)

            # Schedule the task and wait briefly for it to complete
            task = asyncio.create_task(run_async())

            # Give it a moment to complete - this fixes the race condition
            import time

            time.sleep(0.1)  # Small delay to let async tasks progress

            # Check if task completed, if not, fall back to sync disable
            if task.done():
                try:
                    result = task.result()
                    return result
                except Exception:
                    pass

            # If async didn't complete, disable synchronously
            managed_server = self._managed_servers.get(server_id)
            if managed_server:
                managed_server.disable()
                self.status_tracker.set_status(server_id, ServerState.STOPPED)
                self.status_tracker.record_stop_time(server_id)
                logger.info(f"Disabled server synchronously: {server_id}")
                return True
            return False

        except RuntimeError:
            # No async loop, just disable the server
            managed_server = self._managed_servers.get(server_id)
            if managed_server:
                managed_server.disable()
                self.status_tracker.set_status(server_id, ServerState.STOPPED)
                self.status_tracker.record_stop_time(server_id)
                logger.info(f"Disabled server (no async context): {server_id}")
                return True
            return False

    def reload_server(self, server_id: str) -> bool:
        """
        Reload a server configuration.

        Args:
            server_id: ID of server to reload

        Returns:
            True if server was reloaded, False if not found or failed
        """
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

    def remove_server(self, server_id: str) -> bool:
        """
        Remove a server completely.

        Args:
            server_id: ID of server to remove

        Returns:
            True if server was removed, False if not found
        """
        # Get server name for logging
        config = self.registry.get(server_id)
        server_name = config.name if config else server_id

        # Remove from registry
        registry_removed = self.registry.unregister(server_id)

        # Remove from managed servers
        managed_removed = False
        if server_id in self._managed_servers:
            del self._managed_servers[server_id]
            managed_removed = True

        # Record removal event if server existed
        if registry_removed or managed_removed:
            self.status_tracker.record_event(
                server_id, "removed", {"message": "Server removed"}
            )
            logger.info(f"Removed server: {server_name} (ID: {server_id})")
            return True
        else:
            logger.warning(f"Attempted to remove non-existent server: {server_id}")
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


# Singleton instance
_manager_instance: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    """
    Get the singleton MCPManager instance.

    Returns:
        The global MCPManager instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MCPManager()
    return _manager_instance
