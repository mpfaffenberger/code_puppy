"""
Comprehensive tests for blocking_startup.py MCP toolset startup functionality.

Tests cover stderr capture, blocking initialization, startup monitoring,
and timeout/error scenarios for the MCPToolset-based stdio server.
"""

import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.mcp import MCPToolset

from code_puppy.mcp_.blocking_startup import (
    BlockingStdioToolset,
    StartupMonitor,
    StderrFileCapture,
)


class TestStderrFileCapture:
    """Test StderrFileCapture for logging server stderr."""

    def test_initialization(self):
        """Test StderrFileCapture initialization."""
        capture = StderrFileCapture("test-server")
        assert capture.server_name == "test-server"
        assert capture.emit_to_user is False
        assert capture.message_group is not None
        assert capture.log_path is None
        assert len(capture.captured_lines) == 0

    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters."""
        msg_group = uuid.uuid4()
        capture = StderrFileCapture(
            "my-server",
            emit_to_user=True,
            message_group=msg_group,
        )
        assert capture.server_name == "my-server"
        assert capture.emit_to_user is True
        assert capture.message_group == msg_group

    def test_get_captured_lines_empty(self):
        """Test getting captured lines when none exist."""
        capture = StderrFileCapture("test-server")
        assert capture.get_captured_lines() == []

    def test_get_captured_lines_returns_copy(self):
        """Test that get_captured_lines returns a copy."""
        capture = StderrFileCapture("test-server")
        capture.captured_lines.extend(["line1", "line2"])
        lines = capture.get_captured_lines()
        assert lines == ["line1", "line2"]
        lines.append("line3")
        assert list(capture.captured_lines) == ["line1", "line2"]

    def test_stop_without_start(self):
        """Test stopping without starting doesn't error."""
        capture = StderrFileCapture("test-server")
        capture.stop()  # Should not raise
        assert capture.log_path is None

    @patch("code_puppy.mcp_.blocking_startup.rotate_log_if_needed")
    @patch("code_puppy.mcp_.blocking_startup.get_log_file_path")
    @patch("code_puppy.mcp_.blocking_startup.write_log")
    def test_start_returns_log_path(self, mock_write_log, mock_get_path, mock_rotate):
        """Test that start rotates the log and returns its path."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            log_path = capture.start()

            assert log_path == Path(temp_path)
            assert capture.log_path == temp_path
            mock_rotate.assert_called_once_with("test-server")

            capture.stop()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @patch("code_puppy.mcp_.blocking_startup.rotate_log_if_needed")
    @patch("code_puppy.mcp_.blocking_startup.get_log_file_path")
    @patch("code_puppy.mcp_.blocking_startup.write_log")
    def test_start_and_stop_cycle(self, mock_write_log, mock_get_path, mock_rotate):
        """Test complete start and stop cycle writes both markers."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            capture.start()
            capture.stop()

            assert mock_write_log.call_count >= 2  # Start and stop markers
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @patch("code_puppy.mcp_.blocking_startup.rotate_log_if_needed")
    @patch("code_puppy.mcp_.blocking_startup.get_log_file_path")
    @patch("code_puppy.mcp_.blocking_startup.write_log")
    def test_monitor_thread_stops_cleanly(
        self, mock_write_log, mock_get_path, mock_rotate
    ):
        """Test that monitor thread stops cleanly on stop()."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            capture.start()

            monitor_thread = capture.monitor_thread
            assert monitor_thread is not None
            assert monitor_thread.is_alive()

            capture.stop()

            monitor_thread.join(timeout=2)
            assert not monitor_thread.is_alive()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @patch("code_puppy.mcp_.blocking_startup.rotate_log_if_needed")
    @patch("code_puppy.mcp_.blocking_startup.get_log_file_path")
    @patch("code_puppy.mcp_.blocking_startup.write_log")
    def test_tail_picks_up_new_lines(self, mock_write_log, mock_get_path, mock_rotate):
        """Lines appended after start() land in captured_lines."""
        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".log") as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            capture.start()

            with open(temp_path, "a", encoding="utf-8") as f:
                f.write("boom from server\n")

            deadline = 2.0
            import time

            waited = 0.0
            while waited < deadline and not capture.captured_lines:
                time.sleep(0.05)
                waited += 0.05

            capture.stop()
            assert "boom from server" in capture.get_captured_lines()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def _toolset(command="echo", **kwargs) -> BlockingStdioToolset:
    return BlockingStdioToolset(command, **kwargs)


class TestBlockingStdioToolset:
    """Test BlockingStdioToolset blocking initialization."""

    def test_initialization(self):
        """Test BlockingStdioToolset initialization."""
        server = _toolset()
        assert server.command == "echo"
        assert server.server_name == "echo"
        assert server.emit_stderr is False
        assert not server._ready_event.is_set()
        assert server._init_error is None
        assert not server.is_ready()

    def test_initialization_with_custom_params(self):
        """server_name, emit_stderr and message_group are honored."""
        msg_group = uuid.uuid4()
        server = _toolset(
            args=["hello"],
            server_name="my-server",
            emit_stderr=True,
            message_group=msg_group,
        )
        assert server.args == ["hello"]
        assert server.server_name == "my-server"
        assert server.emit_stderr is True
        assert server.message_group == msg_group

    def test_is_an_mcp_toolset(self):
        """The blocking server is a plain MCPToolset subclass (no deprecated base)."""
        assert isinstance(_toolset(), MCPToolset)

    def test_get_captured_stderr_without_context(self):
        """Test get_captured_stderr when not in context."""
        assert _toolset().get_captured_stderr() == []

    @pytest.mark.asyncio
    async def test_wait_until_ready_already_initialized(self):
        """Test wait_until_ready when already initialized."""
        server = _toolset()
        server._ready_event.set()

        result = await server.wait_until_ready(timeout=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout(self):
        """Test wait_until_ready timeout."""
        with pytest.raises(TimeoutError):
            await _toolset().wait_until_ready(timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_until_ready_with_error(self):
        """Test wait_until_ready when initialization has error."""
        server = _toolset()
        server._init_error = RuntimeError("Init failed")
        server._ready_event.set()

        with pytest.raises(RuntimeError, match="Init failed"):
            await server.wait_until_ready(timeout=1)

    @pytest.mark.asyncio
    async def test_ensure_ready_success(self):
        """Test ensure_ready when server is ready."""
        server = _toolset()
        server._ready_event.set()

        await server.ensure_ready(timeout=1)  # Should not raise

    @pytest.mark.asyncio
    async def test_ensure_ready_timeout(self):
        """Test ensure_ready timeout."""
        with pytest.raises(TimeoutError):
            await _toolset().ensure_ready(timeout=0.1)

    def test_is_ready_states(self):
        """is_ready reflects event + error state."""
        server = _toolset()
        assert not server.is_ready()

        server._ready_event.set()
        assert server.is_ready()

        server._init_error = RuntimeError("Error")
        assert not server.is_ready()

    @pytest.mark.asyncio
    async def test_aenter_success(self):
        """Test __aenter__ success case."""
        server = _toolset()

        with (
            patch.object(MCPToolset, "__aenter__", new_callable=AsyncMock) as mock,
            patch.object(
                BlockingStdioToolset, "is_running", new=property(lambda self: False)
            ),
            patch("code_puppy.mcp_.blocking_startup.StderrFileCapture") as cap_cls,
        ):
            mock.return_value = server
            result = await server.__aenter__()

            assert result is server
            assert server.is_ready()
            cap_cls.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_aenter_with_exception(self):
        """Test __aenter__ with initialization exception."""
        server = _toolset()
        test_error = RuntimeError("Init failed")

        with (
            patch.object(MCPToolset, "__aenter__", new_callable=AsyncMock) as mock,
            patch.object(
                BlockingStdioToolset, "is_running", new=property(lambda self: False)
            ),
            patch("code_puppy.mcp_.blocking_startup.StderrFileCapture"),
            patch("code_puppy.mcp_.blocking_startup.emit_info") as mock_emit,
        ):
            mock.side_effect = test_error

            with pytest.raises(RuntimeError):
                await server.__aenter__()

            assert server._init_error is test_error
            assert server._ready_event.is_set()
            assert not server.is_ready()
            # User gets pointed at /mcp logs
            assert "/mcp logs" in mock_emit.call_args[0][0]

    @pytest.mark.asyncio
    async def test_aenter_unwraps_exception_group(self):
        """Test exception group unwrapping in __aenter__."""
        server = _toolset()
        error1 = RuntimeError("Error 1")
        group = BaseExceptionGroup("boom", [error1, RuntimeError("Error 2")])

        with (
            patch.object(MCPToolset, "__aenter__", new_callable=AsyncMock) as mock,
            patch.object(
                BlockingStdioToolset, "is_running", new=property(lambda self: False)
            ),
            patch("code_puppy.mcp_.blocking_startup.StderrFileCapture"),
            patch("code_puppy.mcp_.blocking_startup.emit_info"),
        ):
            mock.side_effect = group

            with pytest.raises(BaseExceptionGroup):
                await server.__aenter__()

            # First exception should be stored
            assert server._init_error is error1

    @pytest.mark.asyncio
    async def test_aexit_stops_capture_when_stopped(self):
        """__aexit__ stops the stderr capture once the toolset is down."""
        server = _toolset()
        capture = server._stderr_capture = __import__(
            "unittest.mock", fromlist=["MagicMock"]
        ).MagicMock()

        with (
            patch.object(MCPToolset, "__aexit__", new_callable=AsyncMock) as mock,
            patch.object(
                BlockingStdioToolset, "is_running", new=property(lambda self: False)
            ),
        ):
            mock.return_value = None
            await server.__aexit__(None, None, None)

        capture.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_wait_until_ready_signaled_later(self):
        """Test wait_until_ready when initialized signal arrives."""
        server = _toolset()

        async def delayed_init():
            await asyncio.sleep(0.1)
            server._ready_event.set()

        asyncio.create_task(delayed_init())

        result = await server.wait_until_ready(timeout=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout_message_includes_server_name(self):
        """Test that timeout message includes server name."""
        server = _toolset("my-special-server", server_name="my-tool")

        with pytest.raises(TimeoutError) as exc_info:
            await server.wait_until_ready(timeout=0.01)

        assert "my-tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_concurrent_wait_until_ready_calls(self):
        """Test multiple concurrent wait_until_ready calls."""
        server = _toolset()

        async def delayed_init():
            await asyncio.sleep(0.1)
            server._ready_event.set()

        asyncio.create_task(delayed_init())

        results = await asyncio.gather(
            server.wait_until_ready(timeout=1),
            server.wait_until_ready(timeout=1),
            server.wait_until_ready(timeout=1),
        )

        assert all(results)


class TestStartupMonitor:
    """Test StartupMonitor for coordinating multiple servers."""

    def test_initialization(self):
        """Test StartupMonitor initialization."""
        monitor = StartupMonitor()
        assert monitor.servers == {}
        assert monitor.startup_times == {}
        assert monitor.message_group is not None

    def test_initialization_with_message_group(self):
        """Test initialization with custom message group."""
        msg_group = uuid.uuid4()
        monitor = StartupMonitor(message_group=msg_group)
        assert monitor.message_group == msg_group

    def test_add_server(self):
        """Test adding a server to monitor."""
        monitor = StartupMonitor()
        server = _toolset()

        monitor.add_server("test-server", server)

        assert "test-server" in monitor.servers
        assert monitor.servers["test-server"] is server

    def test_add_multiple_servers(self):
        """Test adding multiple servers."""
        monitor = StartupMonitor()
        server1 = _toolset("echo")
        server2 = _toolset("cat")

        monitor.add_server("server1", server1)
        monitor.add_server("server2", server2)

        assert len(monitor.servers) == 2
        assert monitor.servers["server1"] is server1
        assert monitor.servers["server2"] is server2

    def test_startup_monitor_servers_dict_isolation(self):
        """Test that server dict is isolated per monitor."""
        monitor1 = StartupMonitor()
        monitor2 = StartupMonitor()

        server1 = _toolset("echo")
        server2 = _toolset("cat")

        monitor1.add_server("test", server1)
        monitor2.add_server("test", server2)

        assert monitor1.servers["test"] is server1
        assert monitor2.servers["test"] is server2
        assert monitor1.servers is not monitor2.servers

    @pytest.mark.asyncio
    async def test_wait_all_ready_empty(self):
        """Test wait_all_ready with no servers."""
        monitor = StartupMonitor()

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert results == {}

    @pytest.mark.asyncio
    async def test_wait_all_ready_single_server_success(self):
        """Test wait_all_ready with one ready server."""
        monitor = StartupMonitor()
        server = _toolset()
        server._ready_event.set()  # Mark as ready
        monitor.add_server("test", server)

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert results["test"] is True
        assert "test" in monitor.startup_times

    @pytest.mark.asyncio
    async def test_wait_all_ready_single_server_timeout(self):
        """Test wait_all_ready with timeout."""
        monitor = StartupMonitor()
        monitor.add_server("test", _toolset())  # Won't initialize

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=0.1)

        assert results["test"] is False

    @pytest.mark.asyncio
    async def test_wait_all_ready_mixed_success_failure(self):
        """Test wait_all_ready with mixed results."""
        monitor = StartupMonitor()

        server1 = _toolset("echo")
        server1._ready_event.set()  # Ready
        monitor.add_server("server1", server1)

        monitor.add_server("server2", _toolset("cat"))  # Won't initialize

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=0.1)

        assert results["server1"] is True
        assert results["server2"] is False

    @pytest.mark.asyncio
    async def test_monitor_parallel_server_waits(self):
        """Test that monitor handles parallel server waits."""
        monitor = StartupMonitor()

        servers_data = [
            ("fast", 0.05),
            ("medium", 0.1),
            ("slow", 0.15),
        ]

        async def init_server(server, delay):
            await asyncio.sleep(delay)
            server._ready_event.set()

        for name, delay in servers_data:
            server = _toolset()
            monitor.add_server(name, server)
            asyncio.create_task(init_server(server, delay))

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert all(results.values())

    @pytest.mark.asyncio
    async def test_server_initialization_timing(self):
        """Test that startup times are recorded."""
        monitor = StartupMonitor()
        server = _toolset()
        monitor.add_server("test", server)

        async def delayed_init():
            await asyncio.sleep(0.1)
            server._ready_event.set()

        asyncio.create_task(delayed_init())

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert results["test"] is True
        assert "test" in monitor.startup_times
        assert monitor.startup_times["test"] >= 0.1  # At least delay time

    def test_get_startup_report_empty(self):
        """Test startup report with no servers."""
        report = StartupMonitor().get_startup_report()
        assert "Server Startup Times:" in report

    def test_get_startup_report_with_servers(self):
        """Test startup report with servers."""
        monitor = StartupMonitor()
        server = _toolset()
        server._ready_event.set()
        monitor.add_server("test-server", server)
        monitor.startup_times["test-server"] = 1.5

        report = monitor.get_startup_report()
        assert "Server Startup Times:" in report
        assert "test-server" in report
        assert "1.50s" in report

    def test_get_startup_report_shows_status(self):
        """Test that startup report shows ready status."""
        monitor = StartupMonitor()

        ready_server = _toolset("echo")
        ready_server._ready_event.set()
        monitor.add_server("ready", ready_server)
        monitor.startup_times["ready"] = 1.0

        failed_server = _toolset("cat")
        failed_server._init_error = RuntimeError("Failed")
        failed_server._ready_event.set()
        monitor.add_server("failed", failed_server)
        monitor.startup_times["failed"] = 2.0

        report = monitor.get_startup_report()
        assert "[ok]" in report
        assert "[failed]" in report
