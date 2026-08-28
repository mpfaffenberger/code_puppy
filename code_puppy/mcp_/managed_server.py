"""
ManagedMCPServer wrapper class implementation.

This module provides a managed wrapper around pydantic-ai MCP server classes
that adds management capabilities while maintaining 100% compatibility.
"""

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional

import httpx
from fastmcp.client.transports import SSETransport, StreamableHttpTransport
from pydantic_ai import RunContext
from pydantic_ai.mcp import CallToolFunc, MCPToolset, ToolResult
from pydantic_ai.toolsets import AbstractToolset

from code_puppy.http_utils import create_async_client, get_cert_bundle_path
from code_puppy.mcp_.blocking_startup import BlockingStdioToolset
from code_puppy.mcp_.tool_arg_coercion import coerce_tool_args


def _expand_env_vars(value: Any) -> Any:
    """
    Recursively expand environment variables in config values.

    Supports $VAR and ${VAR} syntax. Works with:
    - Strings: expands env vars
    - Dicts: recursively expands all string values
    - Lists: recursively expands all string elements
    - Other types: returned as-is

    Args:
        value: The value to expand env vars in

    Returns:
        The value with env vars expanded
    """
    if isinstance(value, str):
        return os.path.expandvars(value)
    elif isinstance(value, dict):
        return {k: _expand_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_expand_env_vars(item) for item in value]
    return value


def _build_tool_prefix(server_name: str, config: Dict[str, Any]) -> str:
    """Build the pydantic-ai MCP tool prefix for a configured server."""
    configured_prefix = _expand_env_vars(config.get("tool_prefix"))
    if configured_prefix:
        return f"{server_name}_{configured_prefix}"
    return server_name


def _httpx_client_factory(
    http_client: httpx.AsyncClient,
) -> Callable[..., httpx.AsyncClient]:
    """Adapt a pre-built ``httpx.AsyncClient`` to fastmcp's factory shape.

    fastmcp's HTTP transports accept an ``httpx_client_factory`` rather than
    a client instance; returning the same client from the factory preserves
    our custom CA bundle / proxy / retry configuration.
    """

    def factory(
        headers: Optional[Dict[str, str]] = None,
        timeout: Any = None,
        auth: Any = None,
    ) -> httpx.AsyncClient:
        return http_client

    return factory


def _with_inherited_ca_bundle(
    env: Optional[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    """Propagate our CA bundle into a stdio server's child environment.

    A stdio MCP server is a subprocess (often ``uvx``/``npx`` launching a
    Python or Node program) that makes its own HTTPS calls. The stdio
    transport does NOT pass code_puppy's environment to that child
    -- it runs with only the ``env`` dict we hand it (plus a minimal set the
    MCP SDK adds back). So a ``SSL_CERT_FILE`` that lets code_puppy itself
    reach the internet (see ``get_cert_bundle_path``) never reaches the
    child, and the child falls back to certifi's bundle.

    Behind a corporate TLS-interception proxy (Zscaler/Netskope/etc.) that
    certifi bundle is missing the proxy's private root, so the child dies on
    its first request with::

        ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
        self-signed certificate in certificate chain

    even though code_puppy, curl, and the browser all work. This copies our
    resolved bundle into the child env as ``SSL_CERT_FILE`` (honored by
    Python's ``ssl``) and ``REQUESTS_CA_BUNDLE`` (honored by ``requests`` and
    friends), so the child trusts exactly what the parent trusts.

    It is additive and non-destructive: a value the user already set in the
    server's ``env`` config always wins, and if no bundle is resolvable we
    return ``env`` unchanged. We never disable verification.
    """
    bundle = get_cert_bundle_path()
    if not bundle:
        return env
    out: Dict[str, str] = dict(env or {})
    out.setdefault("SSL_CERT_FILE", bundle)
    out.setdefault("REQUESTS_CA_BUNDLE", bundle)
    return out


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


async def _input_schema_for_tool(
    call_tool: CallToolFunc, name: str
) -> Optional[Dict[str, Any]]:
    """Best-effort lookup of an MCP tool's JSON inputSchema.

    ``call_tool`` is pydantic-ai's ``MCPToolset.direct_call_tool`` — either
    the bound method itself or a ``functools.partial`` around it — so
    unwrapping ``.func``/``__self__`` yields the toolset, which exposes a
    (cached) ``list_tools()``. The ``name`` here is already prefix-stripped,
    matching the raw tool names returned by ``list_tools()``.

    Returns ``None`` if the schema cannot be resolved for any reason -- callers
    must treat that as "don't coerce".
    """
    func = getattr(call_tool, "func", call_tool)  # unwrap functools.partial
    server = getattr(func, "__self__", None)
    list_tools = getattr(server, "list_tools", None)
    if list_tools is None:
        return None
    try:
        tools = await list_tools()
    except Exception:
        return None
    for tool in tools:
        if getattr(tool, "name", None) == name:
            return getattr(tool, "inputSchema", None)
    return None


async def process_tool_call(
    ctx: RunContext[Any],
    call_tool: CallToolFunc,
    name: str,
    tool_args: dict[str, Any],
) -> ToolResult:
    """A tool call processor that coerces args and passes along the deps.

    pydantic-ai forwards MCP tool args without coercing them against each tool's
    real JSON Schema, so models that emit stringified arrays/bools/numbers cause
    downstream validation failures. We coerce here before forwarding.
    """
    from rich.console import Console

    from code_puppy.config import get_banner_color

    console = Console()
    color = get_banner_color("mcp_tool_call")
    banner = f"[bold white on {color}] MCP TOOL CALL [/bold white on {color}]"
    console.print(f"\n{banner} 🔧 [bold cyan]{name}[/bold cyan]")

    input_schema = await _input_schema_for_tool(call_tool, name)
    tool_args = coerce_tool_args(tool_args, input_schema)

    return await call_tool(name, tool_args, metadata={"deps": ctx.deps})


class ManagedMCPServer:
    """
    Managed wrapper around pydantic-ai MCP toolsets.

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
        toolset = managed.get_pydantic_server()  # PrefixedToolset over MCPToolset
    """

    def __init__(self, server_config: ServerConfig):
        """
        Initialize managed server with configuration.

        Args:
            server_config: Server configuration containing type, connection details, etc.
        """
        self.config = server_config
        self._toolset: Optional[MCPToolset] = None
        self._pydantic_server: Optional[AbstractToolset[Any]] = None
        self._state = ServerState.STOPPED
        self._enabled = server_config.enabled
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
            self._state = ServerState.ERROR
            self._error_message = str(e)

    def get_pydantic_server(self) -> AbstractToolset[Any]:
        """
        Get the pydantic-ai toolset for this server.

        Returns the ``MCPToolset`` wrapped in a ``PrefixedToolset`` (the
        public replacement for the old ``tool_prefix=`` kwarg), ready to be
        passed to ``Agent(toolsets=...)``.

        Raises:
            RuntimeError: If server creation failed or server is not available
        """
        if self._pydantic_server is None:
            raise RuntimeError(f"Server {self.config.name} is not available")

        if not self.is_enabled() or self.is_quarantined():
            raise RuntimeError(f"Server {self.config.name} is disabled or quarantined")

        return self._pydantic_server

    def _toolset_kwargs(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Map our config keys onto ``MCPToolset`` constructor kwargs.

        ``timeout`` (time allowed for the initialize handshake) maps to
        ``init_timeout``; ``read_timeout`` keeps its name. Omitted keys fall
        through to pydantic-ai's defaults (5s / 300s — same as the old
        ``MCPServer*`` defaults).

        ``prefer_tasks=False``: pydantic-ai v2 defaults to task-augmented
        execution (SEP-1686) for tools whose server marks task support
        'optional'. Pinned off to preserve the direct-call semantics our
        timeout/stderr-capture/blocking-startup plumbing was built against;
        servers that *require* tasks still get them regardless of this flag.

        ``tool_error_behavior="failed"``: a failing MCP tool must not end the
        session. The default ``"retry"`` exhausts the retry budget and then
        raises ``UnexpectedModelBehavior``, which is not an ``McpError`` and
        so reaches the generic handler in ``run_agent_task`` and aborts the
        run. ``"failed"`` hands the model a failed tool result instead, like
        a native tool returning an error string. Bound repeated failures with
        ``UsageLimits`` at the run level.
        """
        kwargs: Dict[str, Any] = {
            "process_tool_call": process_tool_call,
            "prefer_tasks": False,
            "tool_error_behavior": "failed",
        }
        if "timeout" in config:
            kwargs["init_timeout"] = config["timeout"]
        if "read_timeout" in config:
            kwargs["read_timeout"] = config["read_timeout"]
        return kwargs

    def _create_server(self) -> None:
        """
        Create the appropriate ``MCPToolset`` based on config type.

        Raises:
            ValueError: If server type is unsupported or config is invalid
            Exception: If server creation fails
        """
        server_type = self.config.type.lower()
        config = self.config.config
        tool_prefix = _build_tool_prefix(self.config.name, config)

        if server_type == "sse":
            if "url" not in config:
                raise ValueError("SSE server requires 'url' in config")

            # Build the SSE transport explicitly — fastmcp's URL inference
            # would pick streamable-HTTP for URLs not ending in /sse, but our
            # config declares the transport type authoritatively.
            http_client = config.get("http_client")
            if http_client is None and config.get("headers"):
                # Create HTTP client if headers are provided but no client
                # specified (preserves CA bundle / proxy / retry behavior).
                http_client = self._get_http_client()

            read_timeout = config.get("read_timeout")
            transport = SSETransport(
                url=_expand_env_vars(config["url"]),
                sse_read_timeout=read_timeout if read_timeout is not None else 300,
                httpx_client_factory=(
                    _httpx_client_factory(http_client)
                    if http_client is not None
                    else None
                ),
            )
            self._toolset = MCPToolset(transport, **self._toolset_kwargs(config))

        elif server_type == "stdio":
            if "command" not in config:
                raise ValueError("Stdio server requires 'command' in config")

            # Handle command and arguments (expand env vars)
            command = _expand_env_vars(config["command"])
            args = config.get("args", [])
            if isinstance(args, str):
                # If args is a string, split it then expand
                args = [_expand_env_vars(a) for a in args.split()]
            else:
                args = _expand_env_vars(args)

            env = _expand_env_vars(config["env"]) if "env" in config else None
            # Always run (even with no configured env) so the child trusts
            # our CA bundle; see _with_inherited_ca_bundle for why.
            env = _with_inherited_ca_bundle(env)
            cwd = _expand_env_vars(config["cwd"]) if "cwd" in config else None

            # Default timeout of 60s for stdio servers - some servers like
            # Serena take a while to start. Users can override in config.
            stdio_config = dict(config)
            stdio_config.setdefault("timeout", 60)

            self._toolset = BlockingStdioToolset(
                command=command,
                args=list(args) if args else [],
                env=env,
                cwd=cwd,
                server_name=tool_prefix,
                emit_stderr=False,  # Logs go to file (use /mcp logs to view)
                message_group=uuid.uuid4(),
                **self._toolset_kwargs(stdio_config),
            )

        elif server_type == "http":
            if "url" not in config:
                raise ValueError("HTTP server requires 'url' in config")

            headers = (
                _expand_env_vars(config["headers"]) if config.get("headers") else None
            )
            transport = StreamableHttpTransport(
                url=_expand_env_vars(config["url"]),
                headers=headers,
            )
            self._toolset = MCPToolset(transport, **self._toolset_kwargs(config))

        else:
            raise ValueError(f"Unsupported server type: {server_type}")

        # The prefixed wrapper is what agents (and the lifecycle manager)
        # consume; tool names come out as f"{tool_prefix}_{name}", matching
        # the old tool_prefix= behavior.
        self._pydantic_server = self._toolset.prefixed(tool_prefix)

    def _get_http_client(self) -> httpx.AsyncClient:
        """
        Create httpx.AsyncClient with headers from config.

        Returns:
            Configured async HTTP client with custom headers
        """
        headers = self.config.config.get("headers", {})

        # Expand environment variables in headers
        resolved_headers = {}
        if isinstance(headers, dict):
            for k, v in headers.items():
                if isinstance(v, str):
                    resolved_headers[k] = os.path.expandvars(v)
                else:
                    resolved_headers[k] = v

        timeout = self.config.config.get("timeout", 30)
        client = create_async_client(headers=resolved_headers, timeout=timeout)
        return client

    def enable(self) -> None:
        """Enable server availability."""
        self._enabled = True
        if self._state == ServerState.STOPPED and self._pydantic_server is not None:
            self._state = ServerState.RUNNING
            self._start_time = datetime.now()

    def disable(self) -> None:
        """Disable server availability."""
        self._enabled = False
        if self._state == ServerState.RUNNING:
            self._state = ServerState.STOPPED
            self._stop_time = datetime.now()

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
        self._state = ServerState.QUARANTINED

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
            return False

        return True

    def get_captured_stderr(self) -> list[str]:
        """
        Get captured stderr output if this is a stdio server.

        Returns:
            List of captured stderr lines, or empty list if not applicable
        """
        if isinstance(self._toolset, BlockingStdioToolset):
            return self._toolset.get_captured_stderr()
        return []

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """
        Wait until the server is ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False otherwise
        """
        if isinstance(self._toolset, BlockingStdioToolset):
            try:
                await self._toolset.wait_until_ready(timeout)
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
        if isinstance(self._toolset, BlockingStdioToolset):
            await self._toolset.ensure_ready(timeout)

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
