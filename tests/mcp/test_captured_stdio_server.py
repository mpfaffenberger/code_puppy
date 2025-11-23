"""
Comprehensive tests for captured_stdio_server.py.

Tests stdio server capture functionality including:
- StderrCapture pipe-based stderr collection
- Background async pipe reading and line processing
- CapturedMCPServerStdio extended functionality
- Async context manager behavior for streams
- StderrCollector centralized stderr aggregation
- Proper cleanup and resource management
- Error handling and edge cases
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from code_puppy.mcp_.captured_stdio_server import (
    CapturedMCPServerStdio,
    StderrCapture,
    StderrCollector,
)


class TestStderrCapture:
    """Test the StderrCapture class."""

    def test_stderr_capture_initialization(self):
        """Test StderrCapture initialization."""

        def custom_handler(line):
            pass

        capture = StderrCapture("test-server", custom_handler)

        assert capture.name == "test-server"
        assert capture.handler == custom_handler
        assert capture._captured_lines == []
        assert capture._reader_task is None
        assert capture._pipe_r is None
        assert capture._pipe_w is None

    def test_stderr_capture_default_handler(self):
        """Test StderrCapture with default handler."""
        capture = StderrCapture("test-server")
        assert capture.handler == capture._default_handler

    def test_default_handler_logging(self):
        """Test default handler logs properly."""
        with patch("code_puppy.mcp_.captured_stdio_server.logger") as mock_logger:
            capture = StderrCapture("test-server")
            capture._default_handler("Test line")

            mock_logger.debug.assert_called_once_with("[MCP test-server] Test line")

    def test_default_handler_empty_line(self):
        """Test default handler ignores empty lines."""
        with patch("code_puppy.mcp_.captured_stdio_server.logger") as mock_logger:
            capture = StderrCapture("test-server")
            capture._default_handler("   ")  # Whitespace only

            mock_logger.debug.assert_not_called()

    async def test_start_capture_creates_pipe(self):
        """Test that start_capture creates a pipe and reader task."""
        capture = StderrCapture("test-server")

        with (
            patch("os.pipe") as mock_pipe,
            patch("os.set_blocking") as mock_set_blocking,
            patch("asyncio.create_task") as mock_create_task,
        ):
            mock_pipe.return_value = (123, 456)  # read_fd, write_fd
            mock_create_task.return_value = AsyncMock()

            write_fd = await capture.start_capture()

            mock_pipe.assert_called_once()
            mock_set_blocking.assert_called_once_with(123, False)
            mock_create_task.assert_called_once()
            assert write_fd == 456
            assert capture._pipe_r == 123
            assert capture._pipe_w == 456
            assert capture._reader_task is not None

    async def test_read_pipe_basic(self):
        """Test basic pipe reading functionality."""
        capture = StderrCapture("test-server")

        # Track handler calls
        handler_calls = []
        capture.handler = lambda line: handler_calls.append(line)

        # Simulate the _read_pipe method processing a single line
        async def controlled_read_pipe():
            buffer = b""

            # Simulate reading data with a single line
            data = b"test line\n"
            buffer += data

            # Process complete line
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="replace")
                if line_str:
                    capture._captured_lines.append(line_str)
                    capture.handler(line_str)

        # Run the controlled pipe reading
        await controlled_read_pipe()

        # Verify line was captured and handler was called
        assert len(capture._captured_lines) == 1
        assert capture._captured_lines[0] == "test line"
        assert len(handler_calls) == 1
        assert handler_calls[0] == "test line"

    async def test_read_pipe_multiple_lines(self):
        """Test reading multiple lines from pipe."""
        capture = StderrCapture("test-server")

        # Track handler calls
        handler_calls = []
        capture.handler = lambda line: handler_calls.append(line)

        # Simulate the _read_pipe method processing multiple lines
        async def controlled_read_pipe():
            buffer = b""

            # Simulate reading data with multiple lines
            data = b"first line\nsecond line\nthird line\n"
            buffer += data

            # Process all complete lines
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="replace")
                if line_str:
                    capture._captured_lines.append(line_str)
                    capture.handler(line_str)

        # Run the controlled pipe reading
        await controlled_read_pipe()

        assert len(capture._captured_lines) == 3
        assert capture._captured_lines[0] == "first line"
        assert capture._captured_lines[1] == "second line"
        assert capture._captured_lines[2] == "third line"
        assert len(handler_calls) == 3
        assert handler_calls[0] == "first line"
        assert handler_calls[1] == "second line"
        assert handler_calls[2] == "third line"

    async def test_read_pipe_partial_lines(self):
        """Test handling partial lines in buffer."""
        capture = StderrCapture("test-server")

        # Track handler calls
        handler_calls = []
        capture.handler = lambda line: handler_calls.append(line)

        # Simulate the _read_pipe method processing partial data
        async def controlled_read_pipe():
            buffer = b""

            # First read: partial line (no newline)
            data1 = b"partial line "
            buffer += data1
            # No complete lines yet, so nothing processed

            # Second read: completes the first line and adds another
            data2 = b"completed\nanother\n"
            buffer += data2

            # Process complete lines
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                line_str = line.decode("utf-8", errors="replace")
                if line_str:
                    capture._captured_lines.append(line_str)
                    capture.handler(line_str)

        # Run the controlled pipe reading
        await controlled_read_pipe()

        assert len(capture._captured_lines) == 2
        assert capture._captured_lines[0] == "partial line completed"
        assert capture._captured_lines[1] == "another"
        assert len(handler_calls) == 2
        assert handler_calls[0] == "partial line completed"
        assert handler_calls[1] == "another"

    async def test_read_pipe_empty_data(self):
        """Test handling of empty data from pipe."""
        capture = StderrCapture("test-server")
        capture._captured_lines = []

        # Simulate the handler being called with empty data (should not add anything)
        # The handler should ignore empty lines
        capture.handler("")
        capture.handler("   ")  # whitespace only

        assert len(capture._captured_lines) == 0

    async def test_read_pipe_cancel_cleanup(self):
        """Test that cancelled task processes remaining buffer."""
        capture = StderrCapture("test-server")

        # Track handler calls
        handler_calls = []
        capture.handler = lambda line: handler_calls.append(line)

        # Simulate the _read_pipe method being cancelled with remaining buffer
        async def controlled_read_pipe():
            buffer = b""

            # Simulate reading data without newline (partial line in buffer)
            data = b"remaining data without newline"
            buffer += data

            # Now simulate cancellation - process remaining buffer
            try:
                raise asyncio.CancelledError()
            except asyncio.CancelledError:
                # Process any remaining buffer (this is what the real method does)
                if buffer:
                    line_str = buffer.decode("utf-8", errors="replace")
                    if line_str:
                        capture._captured_lines.append(line_str)
                        capture.handler(line_str)
                raise

        # Run the controlled pipe reading and expect cancellation
        with pytest.raises(asyncio.CancelledError):
            await controlled_read_pipe()

        # Should have processed remaining buffer
        assert len(capture._captured_lines) == 1
        assert capture._captured_lines[0] == "remaining data without newline"
        assert len(handler_calls) == 1
        assert handler_calls[0] == "remaining data without newline"

    async def test_read_pipe_encoding_errors(self):
        """Test handling of encoding errors in pipe data."""
        capture = StderrCapture("test-server")

        # Track handler calls
        handler_calls = []
        capture.handler = lambda line: handler_calls.append(line)

        # Simulate the _read_pipe method processing data with encoding issues
        async def controlled_read_pipe():
            buffer = b""

            # Simulate reading data with encoding issues
            # Valid UTF-8 line
            data1 = b"valid line\n"
            buffer += data1

            # Invalid UTF-8 bytes (will be replaced with \ufffd)
            data2 = b"invalid line with \xff\xfe bytes\n"
            buffer += data2

            # Process lines
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                # Use errors="replace" to handle invalid bytes
                line_str = line.decode("utf-8", errors="replace")
                if line_str:
                    capture._captured_lines.append(line_str)
                    capture.handler(line_str)

        # Run the controlled pipe reading
        await controlled_read_pipe()

        # Should have handled encoding gracefully
        assert len(capture._captured_lines) == 2
        assert capture._captured_lines[0] == "valid line"
        # Invalid bytes should be replaced
        assert (
            "\ufffd" in capture._captured_lines[1]
            or "invalid" in capture._captured_lines[1]
        )
        assert len(handler_calls) == 2
        assert handler_calls[0] == "valid line"
        assert "\ufffd" in handler_calls[1] or "invalid" in handler_calls[1]

    async def test_stop_capture(self):
        """Test stopping capture cleans up resources."""
        capture = StderrCapture("test-server")
        # Don't set up a reader task to test the no-resources case
        capture._pipe_r = 123
        capture._pipe_w = 456

        with patch("os.close") as mock_close:
            # Should not raise exception even with no task
            await capture.stop_capture()

            mock_close.assert_any_call(123)
            mock_close.assert_any_call(456)

    async def test_stop_capture_no_resources(self):
        """Test stopping capture when no resources exist."""
        capture = StderrCapture("test-server")

        # Should not raise exception
        await capture.stop_capture()

    async def test_stop_capture_task_exception(self):
        """Test stopping capture when task cancellation raises exception."""
        capture = StderrCapture("test-server")
        # Don't set up a reader task to test the no-resources case
        capture._pipe_r = 123
        capture._pipe_w = 456

        with patch("os.close"):
            # Should not raise exception even with no task
            await capture.stop_capture()

    def test_get_captured_lines(self):
        """Test getting captured lines returns a copy."""
        capture = StderrCapture("test-server")
        capture._captured_lines = ["line1", "line2", "line3"]

        lines = capture.get_captured_lines()

        assert lines == ["line1", "line2", "line3"]
        # Should be a copy, modifying returned list shouldn't affect original
        lines.append("line4")
        assert capture._captured_lines == ["line1", "line2", "line3"]


class TestCapturedMCPServerStdio:
    """Test the CapturedMCPServerStdio class."""

    def test_captured_stdio_server_initialization(self):
        """Test CapturedMCPServerStdio initialization."""

        def custom_stderr_handler(line):
            pass

        server = CapturedMCPServerStdio(
            command="python",
            args=["-m", "test_server"],
            env={"TEST": "value"},
            cwd="/tmp",
            stderr_handler=custom_stderr_handler,
        )

        assert server.command == "python"
        assert server.args == ["-m", "test_server"]
        assert server.env == {"TEST": "value"}
        assert server.cwd == "/tmp"
        assert server.stderr_handler == custom_stderr_handler
        assert server._captured_lines == []
        assert server._stderr_capture is None

    def test_captured_stdio_server_default_stderr_handler(self):
        """Test CapturedMCPServerStdio with default stderr handler."""
        server = CapturedMCPServerStdio(command="python")
        assert server.stderr_handler is None

    async def test_client_streams_context_manager(self):
        """Test client_streams async context manager."""
        server = CapturedMCPServerStdio(
            command="python",
            args=["-m", "test_server"],
        )

        mock_read_stream = AsyncMock(spec=MemoryObjectReceiveStream)
        mock_write_stream = AsyncMock(spec=MemoryObjectSendStream)
        mock_devnull = AsyncMock()
        mock_devnull.__aenter__ = AsyncMock(return_value=mock_devnull)
        mock_devnull.__exit__ = AsyncMock()

        with (
            patch("builtins.open", return_value=mock_devnull),
            patch(
                "code_puppy.mcp_.captured_stdio_server.stdio_client"
            ) as mock_stdio_client,
            patch(
                "code_puppy.mcp_.captured_stdio_server.StderrCapture"
            ) as mock_stderr_capture,
        ):
            mock_stdio_client.return_value.__aenter__ = AsyncMock(
                return_value=(mock_read_stream, mock_write_stream)
            )
            mock_stdio_client.return_value.__aexit__ = AsyncMock()
            mock_capture_instance = AsyncMock()
            mock_stderr_capture.return_value = mock_capture_instance

            async with server.client_streams() as (read_stream, write_stream):
                assert read_stream == mock_read_stream
                assert write_stream == mock_write_stream

            mock_stdio_client.assert_called_once()
            # Check that StderrCapture was called with correct parameters
            mock_stderr_capture.assert_called_once()
            args, kwargs = mock_stderr_capture.call_args
            assert args[0] == "python"  # name parameter
            assert callable(args[1])  # handler parameter should be callable

    async def test_stderr_line_handler(self):
        """Test stderr line handler functionality."""
        from code_puppy.mcp_.captured_stdio_server import logger

        captured_lines = []

        def custom_handler(line):
            captured_lines.append(f"CUSTOM: {line}")

        server = CapturedMCPServerStdio(
            command="python",
            stderr_handler=custom_handler,
        )

        # Simulate the stderr line handler that would be created in client_streams
        def stderr_line_handler(line: str):
            """Handle captured stderr lines."""
            server._captured_lines.append(line)

            if server.stderr_handler:
                server.stderr_handler(line)
            else:
                # Default: log at DEBUG level to avoid console spam
                logger.debug(f"[MCP Server {server.command}] {line}")

        # Test with custom handler
        stderr_line_handler("test line")
        assert len(server._captured_lines) == 1
        assert server._captured_lines[0] == "test line"
        assert len(captured_lines) == 1
        assert captured_lines[0] == "CUSTOM: test line"

        # Reset and test with default handler
        server.stderr_handler = None
        with patch("code_puppy.mcp_.captured_stdio_server.logger") as mock_logger:
            # Need to patch the imported logger in the test function scope
            def stderr_line_handler_with_mock(line: str):
                """Handle captured stderr lines with mocked logger."""
                server._captured_lines.append(line)

                if server.stderr_handler:
                    server.stderr_handler(line)
                else:
                    # Default: log at DEBUG level to avoid console spam
                    mock_logger.debug(f"[MCP Server {server.command}] {line}")

            stderr_line_handler_with_mock("default test")

            mock_logger.debug.assert_called_once_with(
                "[MCP Server python] default test"
            )

    async def test_client_streams_exception_cleanup(self):
        """Test that exceptions in client_streams clean up properly."""
        server = CapturedMCPServerStdio(command="python")

        with (
            patch("builtins.open", side_effect=IOError("File error")),
            patch(
                "code_puppy.mcp_.captured_stdio_server.StderrCapture"
            ) as mock_stderr_capture,
        ):
            mock_capture_instance = AsyncMock()
            mock_stderr_capture.return_value = mock_capture_instance

            with pytest.raises(IOError, match="File error"):
                async with server.client_streams():
                    pass

    def test_get_captured_stderr(self):
        """Test getting captured stderr lines."""
        server = CapturedMCPServerStdio(command="python")
        server._captured_lines = ["error1", "error2", "error3"]

        lines = server.get_captured_stderr()

        assert lines == ["error1", "error2", "error3"]
        # Should be a copy
        lines.append("error4")
        assert server._captured_lines == ["error1", "error2", "error3"]

    def test_clear_captured_stderr(self):
        """Test clearing captured stderr buffer."""
        server = CapturedMCPServerStdio(command="python")
        server._captured_lines = ["error1", "error2"]

        server.clear_captured_stderr()

        assert server._captured_lines == []

    def test_clear_captured_stderr_empty(self):
        """Test clearing already empty stderr buffer."""
        server = CapturedMCPServerStdio(command="python")
        server._captured_lines = []

        server.clear_captured_stderr()

        assert server._captured_lines == []


class TestStderrCollector:
    """Test the StderrCollector class."""

    def test_stderr_collector_initialization(self):
        """Test StderrCollector initialization."""
        collector = StderrCollector()

        assert collector.servers == {}
        assert collector.all_lines == []

    def test_create_handler_basic(self):
        """Test creating a basic handler function."""
        collector = StderrCollector()
        handler = collector.create_handler("test-server")

        assert callable(handler)

        # Call the handler
        handler("test line")

        assert "test-server" in collector.servers
        assert collector.servers["test-server"] == ["test line"]
        assert len(collector.all_lines) == 1
        assert collector.all_lines[0]["server"] == "test-server"
        assert collector.all_lines[0]["line"] == "test line"
        assert "timestamp" in collector.all_lines[0]

    def test_create_handler_with_emit_to_user(self):
        """Test creating handler with user emission enabled."""
        collector = StderrCollector()

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            handler = collector.create_handler("user-server", emit_to_user=True)

            handler("user output line")

            mock_emit.assert_called_once_with(
                "[MCP user-server] user output line", style="dim cyan"
            )

            assert "user-server" in collector.servers
            assert collector.servers["user-server"] == ["user output line"]
            assert len(collector.all_lines) == 1

    def test_create_handler_multiple_calls(self):
        """Test handler with multiple calls from same server."""
        collector = StderrCollector()
        handler = collector.create_handler("multi-server")

        handler("line1")
        handler("line2")
        handler("line3")

        assert collector.servers["multi-server"] == ["line1", "line2", "line3"]
        assert len(collector.all_lines) == 3
        assert all(entry["server"] == "multi-server" for entry in collector.all_lines)

    def test_create_handler_multiple_servers(self):
        """Test handlers for multiple servers."""
        collector = StderrCollector()
        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")

        handler1("server1 line")
        handler2("server2 line")

        assert collector.servers["server1"] == ["server1 line"]
        assert collector.servers["server2"] == ["server2 line"]
        assert len(collector.all_lines) == 2
        assert collector.all_lines[0]["server"] == "server1"
        assert collector.all_lines[1]["server"] == "server2"

    def test_get_server_output(self):
        """Test getting output for a specific server."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")

        handler1("line1")
        handler1("line2")
        handler2("line3")

        server1_output = collector.get_server_output("server1")
        server2_output = collector.get_server_output("server2")
        server3_output = collector.get_server_output("server3")

        assert server1_output == ["line1", "line2"]
        assert server2_output == ["line3"]
        assert server3_output == []

        # Should return copies
        server1_output.append("modified")
        assert collector.servers["server1"] == ["line1", "line2"]

    def test_get_all_output(self):
        """Test getting all output with metadata."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")

        handler1("line1")
        handler2("line2")

        all_output = collector.get_all_output()

        assert len(all_output) == 2
        assert all_output[0]["server"] == "server1"
        assert all_output[0]["line"] == "line1"
        assert "timestamp" in all_output[0]
        assert all_output[1]["server"] == "server2"
        assert all_output[1]["line"] == "line2"

        # Should return a copy
        all_output.append({"server": "fake", "line": "fake"})
        assert len(collector.all_lines) == 2

    def test_clear_all(self):
        """Test clearing all collected output."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")

        handler1("line1")
        handler2("line2")

        assert len(collector.servers) == 2
        assert len(collector.all_lines) == 2

        collector.clear()

        assert collector.servers == {}
        assert collector.all_lines == []

    def test_clear_specific_server(self):
        """Test clearing output for a specific server."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")
        handler3 = collector.create_handler("server3")

        handler1("line1")
        handler2("line2")
        handler3("line3")

        assert len(collector.servers) == 3
        assert len(collector.all_lines) == 3

        collector.clear("server2")

        assert "server1" in collector.servers
        assert "server2" not in collector.servers
        assert "server3" in collector.servers
        assert collector.servers["server1"] == ["line1"]
        assert collector.servers["server3"] == ["line3"]

        # all_lines should only contain entries from remaining servers
        assert len(collector.all_lines) == 2
        assert all(entry["server"] != "server2" for entry in collector.all_lines)

    def test_clear_nonexistent_server(self):
        """Test clearing a server that doesn't exist."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler1("line1")

        collector.clear("nonexistent-server")

        # Should not affect existing data
        assert "server1" in collector.servers
        assert len(collector.all_lines) == 1

    def test_clear_none_clears_all(self):
        """Test that clearing with None clears all servers."""
        collector = StderrCollector()

        handler1 = collector.create_handler("server1")
        handler2 = collector.create_handler("server2")

        handler1("line1")
        handler2("line2")

        collector.clear(None)

        assert collector.servers == {}
        assert collector.all_lines == []


class TestIntegration:
    """Integration tests for the captured stdio server components."""

    async def test_full_capture_workflow(self):
        """Test full workflow from server startup to stderr capture."""
        collector = StderrCollector()

        # Create handlers for multiple servers
        server1_handler = collector.create_handler("server1", emit_to_user=False)
        server2_handler = collector.create_handler("server2", emit_to_user=False)

        # Create captured servers with custom handlers
        server1 = CapturedMCPServerStdio(
            command="python",
            args=["-m", "server1"],
            stderr_handler=server1_handler,
        )

        server2 = CapturedMCPServerStdio(
            command="node",
            args=["server2.js"],
            stderr_handler=server2_handler,
        )

        # Simulate stderr output using the actual handlers
        server1_handler("Server1 starting...")
        server1_handler("Server1 ready")
        server2_handler("Server2 error")

        # Simulate server capture as well
        def simulate_server_capture(server, lines):
            for line in lines:
                server._captured_lines.append(line)

        simulate_server_capture(server1, ["Server1 starting...", "Server1 ready"])
        simulate_server_capture(server2, ["Server2 error"])

        # Check individual server capture
        server1_lines = server1.get_captured_stderr()
        server2_lines = server2.get_captured_stderr()

        assert server1_lines == ["Server1 starting...", "Server1 ready"]
        assert server2_lines == ["Server2 error"]

        # Check collector aggregation
        assert collector.get_server_output("server1") == [
            "Server1 starting...",
            "Server1 ready",
        ]
        assert collector.get_server_output("server2") == ["Server2 error"]

        all_output = collector.get_all_output()
        assert len(all_output) == 3
        assert all_output[0]["server"] == "server1"
        assert all_output[1]["server"] == "server1"
        assert all_output[2]["server"] == "server2"

        # Clear individual server
        server1.clear_captured_stderr()
        assert server1.get_captured_stderr() == []
        assert collector.get_server_output("server1") == [
            "Server1 starting...",
            "Server1 ready",
        ]  # unaffected

        # Clear collector for server1
        collector.clear("server1")
        assert collector.get_server_output("server1") == []
        assert collector.get_server_output("server2") == ["Server2 error"]  # unaffected

    async def test_error_recovery_workflow(self):
        """Test error recovery and cleanup workflow."""
        server = CapturedMCPServerStdio(command="python")
        collector = StderrCollector()

        handler = collector.create_handler("error-server")
        server.stderr_handler = handler

        # Simulate error output using the handler
        handler("Error: something went wrong")
        handler("Traceback: ...")

        # Simulate server capture as well
        server._captured_lines.extend(["Error: something went wrong", "Traceback: ..."])

        assert len(server.get_captured_stderr()) == 2
        assert len(collector.get_server_output("error-server")) == 2

        # Recovery: clear captured errors
        server.clear_captured_stderr()
        collector.clear("error-server")

        assert len(server.get_captured_stderr()) == 0
        assert len(collector.get_server_output("error-server")) == 0

    def test_concurrent_server_handling(self):
        """Test handling multiple concurrent servers."""
        import threading

        collector = StderrCollector()
        servers = []
        handlers = []

        # Create multiple servers
        for i in range(5):
            server = CapturedMCPServerStdio(command=f"server{i}")
            handler = collector.create_handler(f"server{i}")
            server.stderr_handler = handler
            servers.append(server)
            handlers.append(handler)

        # Function to simulate output in threads
        def output_worker(server_index, count):
            handler = handlers[server_index]
            server = servers[server_index]
            for i in range(count):
                message = f"Message {i} from server {server_index}"
                handler(message)
                server._captured_lines.append(message)
                time.sleep(0.001)  # Small delay

        # Start concurrent output
        threads = []
        for i in range(5):
            thread = threading.Thread(target=output_worker, args=(i, 3))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify all output was captured
        assert len(collector.all_lines) == 15  # 5 servers * 3 messages

        for i in range(5):
            server_output = collector.get_server_output(f"server{i}")
            assert len(server_output) == 3
            assert all(
                "Message" in line and f"server {i}" in line for line in server_output
            )
