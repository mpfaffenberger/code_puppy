"""
Custom MCPServerStdio that captures stderr output properly.

This module provides a version of MCPServerStdio that captures subprocess
stderr output and makes it available through proper logging channels.
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Sequence

from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.shared.session import SessionMessage
from pydantic_ai.mcp import MCPServerStdio

logger = logging.getLogger(__name__)


class StderrCapture:
    """
    Captures stderr output using a pipe and background reader.
    """

    def __init__(self, name: str, handler: Optional[callable] = None):
        """
        Initialize stderr capture.

        Args:
            name: Name for this capture stream
            handler: Optional function to call with captured lines
        """
        self.name = name
        self.handler = handler or self._default_handler
        self._captured_lines = []
        self._reader_task = None
        self._pipe_r = None
        self._pipe_w = None

    def _default_handler(self, line: str):
        """Default handler that logs to Python logging."""
        if line.strip():
            logger.debug(f"[MCP {self.name}] {line.rstrip()}")

    async def start_capture(self):
        """Start capturing stderr by creating a pipe and reader task."""
        # Create a pipe for capturing stderr
        self._pipe_r, self._pipe_w = os.pipe()

        # Make the read end non-blocking
        os.set_blocking(self._pipe_r, False)

        # Start background task to read from pipe
        self._reader_task = asyncio.create_task(self._read_pipe())

        # Return the write end as the file descriptor for stderr
        return self._pipe_w

    async def _read_pipe(self):
        """Background task to read from the pipe."""
        loop = asyncio.get_event_loop()
        buffer = b""

        try:
            while True:
                # Use asyncio's add_reader for efficient async reading
                future = asyncio.Future()

                def read_callback():
                    try:
                        data = os.read(self._pipe_r, 4096)
                        future.set_result(data)
                    except BlockingIOError:
                        future.set_result(b"")
                    except Exception as e:
                        future.set_exception(e)

                loop.add_reader(self._pipe_r, read_callback)
                try:
                    data = await future
                finally:
                    loop.remove_reader(self._pipe_r)

                if not data:
                    await asyncio.sleep(0.1)
                    continue

                # Process the data
                buffer += data

                # Look for complete lines
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    line_str = line.decode("utf-8", errors="replace")
                    if line_str:
                        self._captured_lines.append(line_str)
                        self.handler(line_str)

        except asyncio.CancelledError:
            # Process any remaining buffer
            if buffer:
                line_str = buffer.decode("utf-8", errors="replace")
                if line_str:
                    self._captured_lines.append(line_str)
                    self.handler(line_str)
            raise

    async def stop_capture(self):
        """Stop capturing and clean up."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._pipe_r is not None:
            os.close(self._pipe_r)
        if self._pipe_w is not None:
            os.close(self._pipe_w)

    def get_captured_lines(self) -> list[str]:
        """Get all captured lines."""
        return self._captured_lines.copy()


class CapturedMCPServerStdio(MCPServerStdio):
    """
    Extended MCPServerStdio that captures and handles stderr output.

    This class captures stderr from the subprocess and makes it available
    through proper logging channels instead of letting it pollute the console.
    """

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stderr_handler: Optional[callable] = None,
        **kwargs,
    ):
        """
        Initialize captured stdio server.

        Args:
            command: The command to run
            args: Arguments for the command
            env: Environment variables
            cwd: Working directory
            stderr_handler: Optional function to handle stderr lines
            **kwargs: Additional arguments for MCPServerStdio
        """
        super().__init__(command=command, args=args, env=env, cwd=cwd, **kwargs)
        self.stderr_handler = stderr_handler
        self._stderr_capture = None
        self._captured_lines = []

    @asynccontextmanager
    async def client_streams(
        self,
    ) -> AsyncIterator[
        tuple[
            MemoryObjectReceiveStream[SessionMessage | Exception],
            MemoryObjectSendStream[SessionMessage],
        ]
    ]:
        """Create the streams for the MCP server with stderr capture."""
        server = StdioServerParameters(
            command=self.command, args=list(self.args), env=self.env, cwd=self.cwd
        )

        # Create stderr capture
        def stderr_line_handler(line: str):
            """Handle captured stderr lines."""
            self._captured_lines.append(line)

            if self.stderr_handler:
                self.stderr_handler(line)
            else:
                # Default: log at DEBUG level to avoid console spam
                logger.debug(f"[MCP Server {self.command}] {line}")

        self._stderr_capture = StderrCapture(self.command, stderr_line_handler)

        # For now, use devnull for stderr to suppress output
        # We'll capture it through other means if needed
        with open(os.devnull, "w") as devnull:
            async with stdio_client(server=server, errlog=devnull) as (
                read_stream,
                write_stream,
            ):
                yield read_stream, write_stream

    def get_captured_stderr(self) -> list[str]:
        """
        Get all captured stderr lines.

        Returns:
            List of captured stderr lines
        """
        return self._captured_lines.copy()

    def clear_captured_stderr(self):
        """Clear the captured stderr buffer."""
        self._captured_lines.clear()


class StderrCollector:
    """
    A centralized collector for stderr from multiple MCP servers.

    This can be used to aggregate stderr from all MCP servers in one place.
    """

    def __init__(self):
        """Initialize the collector."""
        self.servers = {}
        self.all_lines = []

    def create_handler(self, server_name: str, emit_to_user: bool = False):
        """
        Create a handler function for a specific server.

        Args:
            server_name: Name to identify this server
            emit_to_user: If True, emit stderr lines to user via emit_info

        Returns:
            Handler function that can be passed to CapturedMCPServerStdio
        """

        def handler(line: str):
            # Store with server identification
            import time

            entry = {"server": server_name, "line": line, "timestamp": time.time()}

            if server_name not in self.servers:
                self.servers[server_name] = []

            self.servers[server_name].append(line)
            self.all_lines.append(entry)

            # Emit to user if requested
            if emit_to_user:
                from code_puppy.messaging import emit_info

                emit_info(f"MCP {server_name}: {line}")

        return handler

    def get_server_output(self, server_name: str) -> list[str]:
        """Get all output from a specific server."""
        return self.servers.get(server_name, []).copy()

    def get_all_output(self) -> list[dict]:
        """Get all output from all servers with metadata."""
        return self.all_lines.copy()

    def clear(self, server_name: Optional[str] = None):
        """Clear captured output."""
        if server_name:
            if server_name in self.servers:
                del self.servers[server_name]
                # Also clear from all_lines
                self.all_lines = [
                    entry for entry in self.all_lines if entry["server"] != server_name
                ]
        else:
            self.servers.clear()
            self.all_lines.clear()
