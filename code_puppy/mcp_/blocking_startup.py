"""Stdio MCP toolset with blocking startup and stderr capture.

This module provides an ``MCPToolset`` subclass for stdio servers that:
1. Captures subprocess stderr to persistent log files
   (``~/.code_puppy/mcp_logs/<server_name>.log``) via the *public*
   ``fastmcp`` ``StdioTransport(log_file=...)`` seam — no stream overrides
2. Blocks until fully initialized before allowing operations
   (``wait_until_ready`` / ``ensure_ready``)
3. Optionally emits stderr to users (disabled by default to reduce noise)
"""

import asyncio
import os
import threading
import uuid
from collections import deque
from pathlib import Path
from typing import Any, List, Optional, Sequence

from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset

from code_puppy.mcp_.mcp_logs import get_log_file_path, rotate_log_if_needed, write_log
from code_puppy.messaging import emit_info


class StderrFileCapture:
    """Monitors a server's persistent stderr log file and buffers new lines.

    The stderr *writing* is handled by fastmcp's ``StdioTransport`` (we hand
    it the log path via ``log_file=``); this class rotates the log, writes
    session start/stop markers, and tails the file so captured lines can be
    surfaced in-memory (and optionally echoed to the user).

    Logs live at ``~/.code_puppy/mcp_logs/<server_name>.log``.
    """

    def __init__(
        self,
        server_name: str,
        emit_to_user: bool = False,  # Disabled by default to reduce console noise
        message_group: Optional[uuid.UUID] = None,
    ):
        self.server_name = server_name
        self.emit_to_user = emit_to_user
        self.message_group = message_group or uuid.uuid4()
        self.log_path = None
        self.monitor_thread = None
        self.stop_monitoring = threading.Event()
        self.captured_lines: deque = deque(maxlen=1000)
        self._last_read_pos = 0

    def start(self) -> Path:
        """Rotate the log, write a start marker, and begin tailing.

        Returns the log path that the stdio transport should append stderr to.
        """
        # Rotate log if needed
        rotate_log_if_needed(self.server_name)

        # Get persistent log path
        self.log_path = get_log_file_path(self.server_name)

        # Write startup marker
        write_log(self.server_name, "--- Server starting ---", "INFO")

        self.stop_monitoring.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_file)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        return Path(self.log_path)

    def _monitor_file(self):
        """Monitor the log file for new content."""
        if not self.log_path:
            return

        # Start reading from current position (end of file before we started)
        try:
            self._last_read_pos = os.path.getsize(self.log_path)
        except OSError:
            self._last_read_pos = 0

        while not self.stop_monitoring.is_set():
            self._drain_new_lines()
            self.stop_monitoring.wait(0.1)  # Check every 100ms

    def _drain_new_lines(self, dedupe: bool = False) -> None:
        """Read any unseen content from the log file into the buffer."""
        if not self.log_path:
            return
        try:
            with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_read_pos)
                new_content = f.read()
                if not new_content:
                    return
                self._last_read_pos = f.tell()
                for line in new_content.splitlines():
                    if not line.strip():
                        continue
                    if dedupe and line in self.captured_lines:
                        continue
                    self.captured_lines.append(line)
                    if self.emit_to_user:
                        emit_info(
                            f"MCP {self.server_name}: {line}",
                            message_group=self.message_group,
                        )
        except Exception:
            pass  # File might not exist yet or be deleted

    def stop(self):
        """Stop monitoring, flush remaining lines, and write a stop marker."""
        self.stop_monitoring.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)

        # Write shutdown marker
        write_log(self.server_name, "--- Server stopped ---", "INFO")

        # Read any remaining content for in-memory capture
        if self.log_path and os.path.exists(self.log_path):
            self._drain_new_lines(dedupe=True)

        # Note: We do NOT delete the log file - it's persistent!

    def get_captured_lines(self) -> List[str]:
        """Get all captured lines from this session."""
        return list(self.captured_lines)


class BlockingStdioToolset(MCPToolset):
    """Stdio ``MCPToolset`` that captures stderr and tracks readiness.

    Replaces the deprecated ``MCPServerStdio`` subclasses
    (``SimpleCapturedMCPServerStdio`` / ``BlockingMCPServerStdio``): stderr
    goes to a persistent log file through fastmcp's public
    ``StdioTransport(log_file=...)`` hook, and ``wait_until_ready`` /
    ``ensure_ready`` let other tasks block until the server's ``initialize``
    handshake has completed (or failed).
    """

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        env: Optional[dict] = None,
        cwd: Optional[str] = None,
        *,
        server_name: Optional[str] = None,
        emit_stderr: bool = False,
        message_group: Optional[uuid.UUID] = None,
        **toolset_kwargs: Any,
    ):
        """Build a blocking stdio toolset.

        Args:
            command: The command to run.
            args: Arguments for the command.
            env: Environment variables for the subprocess.
            cwd: Working directory for the subprocess.
            server_name: Name used for the stderr log file and user-facing
                messages. Defaults to ``command``.
            emit_stderr: Echo captured stderr lines to the user.
            message_group: Message group for user-facing output.
            **toolset_kwargs: Forwarded to ``MCPToolset`` (``init_timeout``,
                ``read_timeout``, ``process_tool_call``, ...).
        """
        self.command = command
        self.args = list(args)
        self.env = env
        self.cwd = cwd
        self.server_name = server_name or command
        self.emit_stderr = emit_stderr
        self.message_group = message_group or uuid.uuid4()
        self._stderr_capture: Optional[StderrFileCapture] = None
        self._ready_event = asyncio.Event()
        self._init_error: Optional[BaseException] = None

        # keep_alive=False so stopping the toolset actually terminates the
        # subprocess (parity with the old MCPServerStdio semantics) instead
        # of fastmcp's default of keeping it warm across connections.
        transport = StdioTransport(
            command=command,
            args=self.args,
            env=env,
            cwd=cwd,
            keep_alive=False,
            log_file=Path(get_log_file_path(self.server_name)),
        )
        super().__init__(transport, **toolset_kwargs)

    async def __aenter__(self):
        """Enter the toolset context, tracking readiness and stderr."""
        starting = not self.is_running
        if starting:
            self._stderr_capture = StderrFileCapture(
                self.server_name, self.emit_stderr, self.message_group
            )
            self._stderr_capture.start()

        try:
            result = await super().__aenter__()
        except BaseException as e:
            # Unwrap ExceptionGroup if present (Python 3.11+)
            if isinstance(e, BaseExceptionGroup):
                self._init_error = e.exceptions[0]
                error_details = f"{e.exceptions[0]}"
            else:
                self._init_error = e
                error_details = str(e)

            self._ready_event.set()
            if starting and self._stderr_capture is not None:
                self._stderr_capture.stop()

            # Point the user to /mcp logs; error_details stay out of the prompt
            # (already in the log file — no stack-trace spam on every run).
            emit_info(
                f"MCP server '{self.server_name}' didn't start. "
                f"Run [cyan]/mcp logs {self.server_name}[/cyan] to investigate, "
                f"or unbind it via [cyan]/agents → B[/cyan].",
                style="yellow",
                message_group=self.message_group,
            )
            import logging as _logging

            _logging.getLogger(__name__).debug(
                "MCP server %s init error: %s", self.server_name, error_details
            )
            raise

        self._init_error = None
        self._ready_event.set()
        return result

    async def __aexit__(self, *args: Any):
        result = await super().__aexit__(*args)
        if not self.is_running and self._stderr_capture is not None:
            self._stderr_capture.stop()
        return result

    def get_captured_stderr(self) -> List[str]:
        """Get captured stderr lines from the current/most recent session."""
        if self._stderr_capture:
            return self._stderr_capture.get_captured_lines()
        return []

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """Wait until the server is ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if server is ready

        Raises:
            TimeoutError: If server doesn't initialize within timeout
            Exception: If server initialization failed
        """
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Server '{self.server_name}' initialization timeout after {timeout}s"
            ) from None

        # Check if there was an initialization error
        if self._init_error:
            raise self._init_error

        return True

    async def ensure_ready(self, timeout: float = 30.0):
        """Ensure server is ready before proceeding, raising if not."""
        await self.wait_until_ready(timeout)

    def is_ready(self) -> bool:
        """Check if server is ready without blocking."""
        return self._ready_event.is_set() and self._init_error is None


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

    def add_server(self, name: str, server: BlockingStdioToolset):
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
        async def wait_server(name: str, server: BlockingStdioToolset):
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
            f"Waiting for {len(self.servers)} MCP servers to initialize...",
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
                f"All {total_count} servers ready!",
                style="green bold",
                message_group=self.message_group,
            )
        else:
            emit_info(
                f"{ready_count}/{total_count} servers ready",
                style="yellow",
                message_group=self.message_group,
            )

        return results

    def get_startup_report(self) -> str:
        """Get a report of startup times."""
        lines = ["Server Startup Times:"]
        for name, time_taken in self.startup_times.items():
            status = "[ok]" if self.servers[name].is_ready() else "[failed]"
            lines.append(f"  {status} {name}: {time_taken:.2f}s")
        return "\n".join(lines)
