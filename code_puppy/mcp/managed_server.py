"""
ManagedMCPServer wrapper class implementation.

This module provides a managed wrapper around pydantic-ai MCP server classes
that adds management capabilities while maintaining 100% compatibility.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, Optional, Union

import httpx
from pydantic_ai import RunContext
from pydantic_ai.mcp import (
    CallToolFunc,
    MCPServerSSE,
    MCPServerStdio,
    MCPServerStreamableHTTP,
    ToolResult,
)

from code_puppy.http_utils import create_async_client
from code_puppy.mcp.blocking_startup import BlockingMCPServerStdio
from code_puppy.messaging import emit_info

# Configure logging
logger = logging.getLogger(__name__)


class ServerState(Enum):
    """Enumeration of possible server states."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"
    QUARANTINED = "quarantined"


@dataclass
class ServerConfig:
    """Configuration for an MCP server."""

    id: str
    name: str
    type: str  # "sse", "stdio", or "http"
    enabled: bool = True
    config: Dict = field(default_factory=dict)  # Raw config from JSON


async def process_tool_call(
    ctx: RunContext[Any],
    call_tool: CallToolFunc,
    name: str,
    tool_args: dict[str, Any],
) -> ToolResult:
    """A tool call processor that passes along the deps."""
    group_id = uuid.uuid4()
    emit_info(
        f"\n[bold white on purple] MCP Tool Call - {name}[/bold white on purple]",
        message_group=group_id,
    )
    emit_info("\nArgs:", message_group=group_id)
    emit_info(json.dumps(tool_args, indent=2), message_group=group_id)
    return await call_tool(name, tool_args, {"deps": ctx.deps})


class ManagedMCPServer:
    """
    Managed wrapper around pydantic-ai MCP server classes.

    This class provides management capabilities like enable/disable,
    quarantine, and status tracking while maintaining 100% compatibility
    with the existing Agent interface through get_pydantic_server().

    Example usage:
        config = ServerConfig(
            id="123",
            name="test",
            type="sse",
            config={"url": "http://localhost:8080"}
        )
        managed = ManagedMCPServer(config)
        pydantic_server = managed.get_pydantic_server()  # Returns actual MCPServerSSE
    """

    def __init__(self, server_config: ServerConfig):
        """
        Initialize managed server with configuration.

        Args:
            server_config: Server configuration containing type, connection details, etc.
        """
        self.config = server_config
        self._pydantic_server: Optional[
            Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]
        ] = None
        self._state = ServerState.STOPPED
        # Always start disabled - servers must be explicitly started with /mcp start
        self._enabled = False
        self._quarantine_until: Optional[datetime] = None
        self._start_time: Optional[datetime] = None
        self._stop_time: Optional[datetime] = None
        self._error_message: Optional[str] = None

        # Initialize the pydantic server
        try:
            self._create_server()
            # Always start as STOPPED - servers must be explicitly started
            self._state = ServerState.STOPPED
        except Exception as e:
            logger.error(f"Failed to create server {self.config.name}: {e}")
            self._state = ServerState.ERROR
            self._error_message = str(e)

    def get_pydantic_server(
        self,
    ) -> Union[MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP]:
        """
        Get the actual pydantic-ai server instance.

        This method returns the real pydantic-ai MCP server objects for 100% compatibility
        with the existing Agent interface. Do not return custom classes or proxies.

        Returns:
            Actual pydantic-ai MCP server instance (MCPServerSSE, MCPServerStdio, or MCPServerStreamableHTTP)

        Raises:
            RuntimeError: If server creation failed or server is not available
        """
        if self._pydantic_server is None:
            raise RuntimeError(f"Server {self.config.name} is not available")

        if not self.is_enabled() or self.is_quarantined():
            raise RuntimeError(f"Server {self.config.name} is disabled or quarantined")

        return self._pydantic_server

    def _create_server(self) -> None:
        """
        Create appropriate pydantic-ai server based on config type.

        Raises:
            ValueError: If server type is unsupported or config is invalid
            Exception: If server creation fails
        """
        server_type = self.config.type.lower()
        config = self.config.config

        try:
            if server_type == "sse":
                if "url" not in config:
                    raise ValueError("SSE server requires 'url' in config")

                # Prepare arguments for MCPServerSSE
                sse_kwargs = {
                    "url": config["url"],
                }

                # Add optional parameters if provided
                if "timeout" in config:
                    sse_kwargs["timeout"] = config["timeout"]
                if "read_timeout" in config:
                    sse_kwargs["read_timeout"] = config["read_timeout"]
                if "http_client" in config:
                    sse_kwargs["http_client"] = config["http_client"]
                elif config.get("headers"):
                    # Create HTTP client if headers are provided but no client specified
                    sse_kwargs["http_client"] = self._get_http_client()

                self._pydantic_server = MCPServerSSE(
                    **sse_kwargs, process_tool_call=process_tool_call
                )

            elif server_type == "stdio":
                if "command" not in config:
                    raise ValueError("Stdio server requires 'command' in config")

                # Handle command and arguments
                command = config["command"]
                args = config.get("args", [])
                if isinstance(args, str):
                    # If args is a string, split it
                    args = args.split()

                # Prepare arguments for MCPServerStdio
                stdio_kwargs = {"command": command, "args": list(args) if args else []}

                # Add optional parameters if provided
                if "env" in config:
                    stdio_kwargs["env"] = config["env"]
                if "cwd" in config:
                    stdio_kwargs["cwd"] = config["cwd"]
                if "timeout" in config:
                    stdio_kwargs["timeout"] = config["timeout"]
                if "read_timeout" in config:
                    stdio_kwargs["read_timeout"] = config["read_timeout"]

                # Use BlockingMCPServerStdio for proper initialization blocking and stderr capture
                # Create a unique message group for this server
                message_group = uuid.uuid4()
                self._pydantic_server = BlockingMCPServerStdio(
                    **stdio_kwargs,
                    process_tool_call=process_tool_call,
                    tool_prefix=config["name"],
                    emit_stderr=True,  # Always emit stderr for now
                    message_group=message_group,
                )

            elif server_type == "http":
                if "url" not in config:
                    raise ValueError("HTTP server requires 'url' in config")

                # Prepare arguments for MCPServerStreamableHTTP
                http_kwargs = {
                    "url": config["url"],
                }

                # Add optional parameters if provided
                if "timeout" in config:
                    http_kwargs["timeout"] = config["timeout"]
                if "read_timeout" in config:
                    http_kwargs["read_timeout"] = config["read_timeout"]
                if "headers" in config:
                    http_kwargs["headers"] = config.get("headers")
                    # Create HTTP client if headers are provided but no client specified

                self._pydantic_server = MCPServerStreamableHTTP(
                    **http_kwargs, process_tool_call=process_tool_call
                )

            else:
                raise ValueError(f"Unsupported server type: {server_type}")

            logger.info(f"Created {server_type} server: {self.config.name}")

        except Exception as e:
            logger.error(
                f"Failed to create {server_type} server {self.config.name}: {e}"
            )
            raise

    def _get_http_client(self) -> httpx.AsyncClient:
        """
        Create httpx.AsyncClient with headers from config.

        Returns:
            Configured async HTTP client with custom headers
        """
        headers = self.config.config.get("headers", {})
        timeout = self.config.config.get("timeout", 30)
        client = create_async_client(headers=headers, timeout=timeout)
        return client

    def enable(self) -> None:
        """Enable server availability."""
        self._enabled = True
        if self._state == ServerState.STOPPED and self._pydantic_server is not None:
            self._state = ServerState.RUNNING
            self._start_time = datetime.now()
            logger.info(f"Enabled server: {self.config.name}")

    def disable(self) -> None:
        """Disable server availability."""
        self._enabled = False
        if self._state == ServerState.RUNNING:
            self._state = ServerState.STOPPED
            self._stop_time = datetime.now()
            logger.info(f"Disabled server: {self.config.name}")

    def is_enabled(self) -> bool:
        """
        Check if server is enabled.

        Returns:
            True if server is enabled, False otherwise
        """
        return self._enabled

    def quarantine(self, duration: int) -> None:
        """
        Temporarily disable server for specified duration.

        Args:
            duration: Quarantine duration in seconds
        """
        self._quarantine_until = datetime.now() + timedelta(seconds=duration)
        previous_state = self._state
        self._state = ServerState.QUARANTINED
        logger.warning(
            f"Quarantined server {self.config.name} for {duration} seconds "
            f"(was {previous_state.value})"
        )

    def is_quarantined(self) -> bool:
        """
        Check if server is currently quarantined.

        Returns:
            True if server is quarantined, False otherwise
        """
        if self._quarantine_until is None:
            return False

        if datetime.now() >= self._quarantine_until:
            # Quarantine period has expired
            self._quarantine_until = None
            if self._state == ServerState.QUARANTINED:
                # Restore to running state if enabled
                self._state = (
                    ServerState.RUNNING if self._enabled else ServerState.STOPPED
                )
                logger.info(f"Released quarantine for server: {self.config.name}")
            return False

        return True

    def get_captured_stderr(self) -> list[str]:
        """
        Get captured stderr output if this is a stdio server.

        Returns:
            List of captured stderr lines, or empty list if not applicable
        """
        if isinstance(self._pydantic_server, BlockingMCPServerStdio):
            return self._pydantic_server.get_captured_stderr()
        return []

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """
        Wait until the server is ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False otherwise
        """
        if isinstance(self._pydantic_server, BlockingMCPServerStdio):
            try:
                await self._pydantic_server.wait_until_ready(timeout)
                return True
            except Exception:
                return False
        # Non-stdio servers are considered ready immediately
        return True

    async def ensure_ready(self, timeout: float = 30.0):
        """
        Ensure server is ready, raising exception if not.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If server doesn't initialize within timeout
            Exception: If server initialization failed
        """
        if isinstance(self._pydantic_server, BlockingMCPServerStdio):
            await self._pydantic_server.ensure_ready(timeout)

    def get_status(self) -> Dict[str, Any]:
        """
        Return current status information.

        Returns:
            Dictionary containing comprehensive status information
        """
        now = datetime.now()
        uptime = None
        if self._start_time and self._state == ServerState.RUNNING:
            uptime = (now - self._start_time).total_seconds()

        quarantine_remaining = None
        if self.is_quarantined():
            quarantine_remaining = (self._quarantine_until - now).total_seconds()

        return {
            "id": self.config.id,
            "name": self.config.name,
            "type": self.config.type,
            "state": self._state.value,
            "enabled": self._enabled,
            "quarantined": self.is_quarantined(),
            "quarantine_remaining_seconds": quarantine_remaining,
            "uptime_seconds": uptime,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "stop_time": self._stop_time.isoformat() if self._stop_time else None,
            "error_message": self._error_message,
            "config": self.config.config.copy(),  # Copy to prevent modification
            "server_available": (
                self._pydantic_server is not None
                and self._enabled
                and not self.is_quarantined()
                and self._state == ServerState.RUNNING
            ),
        }
