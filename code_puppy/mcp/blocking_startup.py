"""
MCP Server with blocking startup capability and stderr capture.

This module provides MCP servers that:
1. Capture stderr output from stdio servers
2. Block until fully initialized before allowing operations
3. Emit stderr to users via emit_info with message groups
"""

import asyncio
import os
import tempfile
import threading
import uuid
from contextlib import asynccontextmanager
from typing import List, Optional

from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic_ai.mcp import MCPServerStdio

from code_puppy.messaging import emit_info


class StderrFileCapture:
    """Captures stderr to a file and monitors it in a background thread."""

    def __init__(
        self,
        server_name: str,
        emit_to_user: bool = True,
        message_group: Optional[uuid.UUID] = None,
    ):
        self.server_name = server_name
        self.emit_to_user = emit_to_user
        self.message_group = message_group or uuid.uuid4()
        self.temp_file = None
        self.temp_path = None
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()
        self.captured_lines = []

    def start(self):
        """Start capture by creating temp file and monitor thread."""
        # Create temp file
        self.temp_file = tempfile.NamedTemporaryFile(
            mode="w+", delete=False, suffix=".err"
        )
        self.temp_path = self.temp_file.name

        # Start monitoring thread
        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        return self.temp_file

    def _monitor_file(self):
        """Monitor the temp file for new content."""
        if not self.temp_path:
            return

        last_pos = 0
        while not self.stop_monitoring.is_set():
            try:
                with open(self.temp_path, "r") as f:
                    f.seek(last_pos)
                    new_content = f.read()
                    if new_content:
                        last_pos = f.tell()
                        # Process new lines
                        for line in new_content.splitlines():
                            if line.strip():
                                self.captured_lines.append(line)
                                if self.emit_to_user:
                                    emit_info(
                                        f"[bold white on blue] MCP {self.server_name} [/bold white on blue] {line}",
                                        style="dim cyan",
                                        message_group=self.message_group,
                                    )

            except Exception:
                pass  # File might not exist yet or be deleted

            self.stop_monitoring.wait(0.1)  # Check every 100ms

    def stop(self):
        """Stop monitoring and clean up."""
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)

        if self.temp_file:
            try:
                self.temp_file.close()
            except Exception:
                pass

        if self.temp_path and os.path.exists(self.temp_path):
            try:
                # Read any remaining content
                with open(self.temp_path, "r") as f:
                    content = f.read()
                    for line in content.splitlines():
                        if line.strip() and line not in self.captured_lines:
                            self.captured_lines.append(line)
                            if self.emit_to_user:
                                emit_info(
                                    f"[bold white on blue] MCP {self.server_name} [/bold white on blue] {line}",
                                    style="dim cyan",
                                    message_group=self.message_group,
                                )

                os.unlink(self.temp_path)
            except Exception:
                pass

    def get_captured_lines(self) -> List[str]:
        """Get all captured lines."""
        return self.captured_lines.copy()


class SimpleCapturedMCPServerStdio(MCPServerStdio):
    """
    MCPServerStdio that captures stderr to a file and optionally emits to user.
    """

    def __init__(
        self,
        command: str,
        args=(),
        env=None,
        cwd=None,
        emit_stderr: bool = True,
        message_group: Optional[uuid.UUID] = None,
        **kwargs,
    ):
        super().__init__(command=command, args=args, env=env, cwd=cwd, **kwargs)
        self.emit_stderr = emit_stderr
        self.message_group = message_group or uuid.uuid4()
        self._stderr_capture = None

    @asynccontextmanager
    async def client_streams(self):
        """Create streams with stderr capture."""
        server = StdioServerParameters(
            command=self.command, args=list(self.args), env=self.env, cwd=self.cwd
        )

        # Create stderr capture
        server_name = getattr(self, "tool_prefix", self.command)
        self._stderr_capture = StderrFileCapture(
            server_name, self.emit_stderr, self.message_group
        )
        stderr_file = self._stderr_capture.start()

        try:
            async with stdio_client(server=server, errlog=stderr_file) as (
                read_stream,
                write_stream,
            ):
                yield read_stream, write_stream
        finally:
            self._stderr_capture.stop()

    def get_captured_stderr(self) -> List[str]:
        """Get captured stderr lines."""
        if self._stderr_capture:
            return self._stderr_capture.get_captured_lines()
        return []


class BlockingMCPServerStdio(SimpleCapturedMCPServerStdio):
    """
    MCP Server that blocks until fully initialized.

    This server ensures that initialization is complete before
    allowing any operations, preventing race conditions.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialized = asyncio.Event()
        self._init_error: Optional[Exception] = None
        self._initialization_task = None

    async def __aenter__(self):
        """Enter context and track initialization."""
        try:
            # Start initialization
            result = await super().__aenter__()

            # Mark as initialized
            self._initialized.set()

            # Emit success message
            server_name = getattr(self, "tool_prefix", self.command)
            emit_info(
                f"✅ MCP Server '{server_name}' initialized successfully",
                style="green",
                message_group=self.message_group,
            )

            return result

        except Exception as e:
            # Store error and mark as initialized (with error)
            self._init_error = e
            self._initialized.set()

            # Emit error message
            server_name = getattr(self, "tool_prefix", self.command)
            emit_info(
                f"❌ MCP Server '{server_name}' failed to initialize: {e}",
                style="red",
                message_group=self.message_group,
            )

            raise

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """
        Wait until the server is ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready, False if timeout or error

        Raises:
            TimeoutError: If server doesn't initialize within timeout
            Exception: If server initialization failed
        """
        try:
            await asyncio.wait_for(self._initialized.wait(), timeout=timeout)

            # Check if there was an initialization error
            if self._init_error:
                raise self._init_error

            return True

        except asyncio.TimeoutError:
            server_name = getattr(self, "tool_prefix", self.command)
            raise TimeoutError(
                f"Server '{server_name}' initialization timeout after {timeout}s"
            )

    async def ensure_ready(self, timeout: float = 30.0):
        """
        Ensure server is ready before proceeding.

        This is a convenience method that raises if not ready.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If server doesn't initialize within timeout
            Exception: If server initialization failed
        """
        await self.wait_until_ready(timeout)

    def is_ready(self) -> bool:
        """
        Check if server is ready without blocking.

        Returns:
            True if server is initialized and ready
        """
        return self._initialized.is_set() and self._init_error is None


class StartupMonitor:
    """
    Monitor for tracking multiple server startups.

    This class helps coordinate startup of multiple MCP servers
    and ensures all are ready before proceeding.
    """

    def __init__(self, message_group: Optional[uuid.UUID] = None):
        self.servers = {}
        self.startup_times = {}
        self.message_group = message_group or uuid.uuid4()

    def add_server(self, name: str, server: BlockingMCPServerStdio):
        """Add a server to monitor."""
        self.servers[name] = server

    async def wait_all_ready(self, timeout: float = 30.0) -> dict:
        """
        Wait for all servers to be ready.

        Args:
            timeout: Maximum time to wait for all servers

        Returns:
            Dictionary of server names to ready status
        """
        import time

        results = {}

        # Create tasks for all servers
        async def wait_server(name: str, server: BlockingMCPServerStdio):
            start = time.time()
            try:
                await server.wait_until_ready(timeout)
                self.startup_times[name] = time.time() - start
                results[name] = True
                emit_info(
                    f"   {name}: Ready in {self.startup_times[name]:.2f}s",
                    style="dim green",
                    message_group=self.message_group,
                )
            except Exception as e:
                self.startup_times[name] = time.time() - start
                results[name] = False
                emit_info(
                    f"   {name}: Failed after {self.startup_times[name]:.2f}s - {e}",
                    style="dim red",
                    message_group=self.message_group,
                )

        # Wait for all servers in parallel
        emit_info(
            f"⏳ Waiting for {len(self.servers)} MCP servers to initialize...",
            style="cyan",
            message_group=self.message_group,
        )

        tasks = [
            asyncio.create_task(wait_server(name, server))
            for name, server in self.servers.items()
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

        # Report summary
        ready_count = sum(1 for r in results.values() if r)
        total_count = len(results)

        if ready_count == total_count:
            emit_info(
                f"✅ All {total_count} servers ready!",
                style="green bold",
                message_group=self.message_group,
            )
        else:
            emit_info(
                f"⚠️  {ready_count}/{total_count} servers ready",
                style="yellow",
                message_group=self.message_group,
            )

        return results

    def get_startup_report(self) -> str:
        """Get a report of startup times."""
        lines = ["Server Startup Times:"]
        for name, time_taken in self.startup_times.items():
            status = "✅" if self.servers[name].is_ready() else "❌"
            lines.append(f"  {status} {name}: {time_taken:.2f}s")
        return "\n".join(lines)


async def start_servers_with_blocking(
    *servers: BlockingMCPServerStdio,
    timeout: float = 30.0,
    message_group: Optional[uuid.UUID] = None,
):
    """
    Start multiple servers and wait for all to be ready.

    Args:
        *servers: Variable number of BlockingMCPServerStdio instances
        timeout: Maximum time to wait for all servers
        message_group: Optional UUID for grouping log messages

    Returns:
        List of ready servers

    Example:
        server1 = BlockingMCPServerStdio(...)
        server2 = BlockingMCPServerStdio(...)
        ready = await start_servers_with_blocking(server1, server2)
    """
    monitor = StartupMonitor(message_group=message_group)

    for i, server in enumerate(servers):
        name = getattr(server, "tool_prefix", f"server-{i}")
        monitor.add_server(name, server)

    # Start all servers
    async def start_server(server):
        async with server:
            await asyncio.sleep(0.1)  # Keep context alive briefly
            return server

    # Start servers in parallel
    [asyncio.create_task(start_server(server)) for server in servers]

    # Wait for all to be ready
    results = await monitor.wait_all_ready(timeout)

    # Get the report
    emit_info(monitor.get_startup_report(), message_group=monitor.message_group)

    # Return ready servers
    ready_servers = [
        server for name, server in monitor.servers.items() if results.get(name, False)
    ]

    return ready_servers
