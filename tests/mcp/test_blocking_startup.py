"""
Comprehensive tests for blocking_startup.py MCP server startup functionality.

Tests cover stderr capture, blocking initialization, startup monitoring,
and timeout/error scenarios.
"""

import asyncio
import os
import tempfile
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from code_puppy.mcp_.blocking_startup import (
    BlockingMCPServerStdio,
    SimpleCapturedMCPServerStdio,
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
        assert capture.log_file is None
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
        capture.captured_lines = ["line1", "line2"]
        lines = capture.get_captured_lines()
        assert lines == ["line1", "line2"]
        lines.append("line3")
        assert capture.captured_lines == ["line1", "line2"]  # Original unchanged

    def test_stop_without_start(self):
        """Test stopping without starting doesn't error."""
        capture = StderrFileCapture("test-server")
        capture.stop()  # Should not raise
        assert capture.log_file is None

    @patch("code_puppy.mcp_.blocking_startup.rotate_log_if_needed")
    @patch("code_puppy.mcp_.blocking_startup.get_log_file_path")
    @patch("code_puppy.mcp_.blocking_startup.write_log")
    def test_start_creates_log_file(self, mock_write_log, mock_get_path, mock_rotate):
        """Test that start creates and opens log file."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            log_file = capture.start()

            assert log_file is not None
            assert capture.log_file is not None
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
        """Test complete start and stop cycle."""
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            temp_path = tmp.name

        try:
            mock_get_path.return_value = temp_path
            capture = StderrFileCapture("test-server")
            capture.start()

            assert capture.log_file is not None

            capture.stop()

            # After stop, log_file should be closed
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

            # Monitor thread should be stopped
            monitor_thread.join(timeout=2)
            assert not monitor_thread.is_alive()
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestSimpleCapturedMCPServerStdio:
    """Test SimpleCapturedMCPServerStdio."""

    def test_initialization(self):
        """Test SimpleCapturedMCPServerStdio initialization."""
        server = SimpleCapturedMCPServerStdio(
            command="echo",
            args=["hello"],
        )
        assert server.command == "echo"
        assert server.args == ["hello"] or server.args == ("hello",)
        assert server.emit_stderr is True
        assert server.message_group is not None

    def test_initialization_with_emit_false(self):
        """Test initialization with emit_stderr=False."""
        server = SimpleCapturedMCPServerStdio(
            command="echo",
            emit_stderr=False,
        )
        assert server.emit_stderr is False

    def test_initialization_with_custom_message_group(self):
        """Test initialization with custom message group."""
        msg_group = uuid.uuid4()
        server = SimpleCapturedMCPServerStdio(
            command="echo",
            message_group=msg_group,
        )
        assert server.message_group == msg_group

    def test_get_captured_stderr_without_context(self):
        """Test get_captured_stderr when not in context."""
        server = SimpleCapturedMCPServerStdio(command="echo")
        assert server.get_captured_stderr() == []


class TestBlockingMCPServerStdio:
    """Test BlockingMCPServerStdio blocking initialization."""

    def test_initialization(self):
        """Test BlockingMCPServerStdio initialization."""
        server = BlockingMCPServerStdio(command="echo")
        assert server.command == "echo"
        assert not server._initialized.is_set()
        assert server._init_error is None
        assert not server.is_ready()

    @pytest.mark.asyncio
    async def test_wait_until_ready_already_initialized(self):
        """Test wait_until_ready when already initialized."""
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()

        result = await server.wait_until_ready(timeout=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout(self):
        """Test wait_until_ready timeout."""
        server = BlockingMCPServerStdio(command="echo")

        with pytest.raises(TimeoutError):
            await server.wait_until_ready(timeout=0.1)

    @pytest.mark.asyncio
    async def test_wait_until_ready_with_error(self):
        """Test wait_until_ready when initialization has error."""
        server = BlockingMCPServerStdio(command="echo")
        test_error = RuntimeError("Init failed")
        server._init_error = test_error
        server._initialized.set()

        with pytest.raises(RuntimeError, match="Init failed"):
            await server.wait_until_ready(timeout=1)

    @pytest.mark.asyncio
    async def test_ensure_ready_success(self):
        """Test ensure_ready when server is ready."""
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()

        await server.ensure_ready(timeout=1)  # Should not raise

    @pytest.mark.asyncio
    async def test_ensure_ready_timeout(self):
        """Test ensure_ready timeout."""
        server = BlockingMCPServerStdio(command="echo")

        with pytest.raises(TimeoutError):
            await server.ensure_ready(timeout=0.1)

    @pytest.mark.asyncio
    async def test_is_ready_before_initialization(self):
        """Test is_ready before initialization."""
        server = BlockingMCPServerStdio(command="echo")
        assert not server.is_ready()

    @pytest.mark.asyncio
    async def test_is_ready_after_initialization(self):
        """Test is_ready after successful initialization."""
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()

        assert server.is_ready()

    @pytest.mark.asyncio
    async def test_is_ready_with_error(self):
        """Test is_ready when there's an initialization error."""
        server = BlockingMCPServerStdio(command="echo")
        server._init_error = RuntimeError("Error")
        server._initialized.set()

        assert not server.is_ready()

    @pytest.mark.asyncio
    async def test_aenter_success(self):
        """Test __aenter__ success case."""
        server = BlockingMCPServerStdio(command="echo")

        # Mock the parent __aenter__
        async def mock_aenter():
            server._initialized.set()
            return server

        with patch.object(
            SimpleCapturedMCPServerStdio, "__aenter__", new_callable=AsyncMock
        ) as mock:
            mock.return_value = server
            result = await server.__aenter__()

            assert result is server
            assert server.is_ready()

    @pytest.mark.asyncio
    async def test_aenter_with_exception(self):
        """Test __aenter__ with initialization exception."""
        server = BlockingMCPServerStdio(command="echo")
        test_error = RuntimeError("Init failed")

        # Mock the parent __aenter__ to raise
        async def mock_aenter():
            raise test_error

        with patch.object(
            SimpleCapturedMCPServerStdio, "__aenter__", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = test_error

            with pytest.raises(RuntimeError):
                await server.__aenter__()

            assert server._init_error is test_error
            assert server._initialized.is_set()

    @pytest.mark.asyncio
    async def test_wait_until_ready_signaled_later(self):
        """Test wait_until_ready when initialized signal arrives."""
        server = BlockingMCPServerStdio(command="echo")

        # Set initialized event after a delay
        async def delayed_init():
            await asyncio.sleep(0.1)
            server._initialized.set()

        asyncio.create_task(delayed_init())

        result = await server.wait_until_ready(timeout=1)
        assert result is True


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
        server = BlockingMCPServerStdio(command="echo")

        monitor.add_server("test-server", server)

        assert "test-server" in monitor.servers
        assert monitor.servers["test-server"] is server

    def test_add_multiple_servers(self):
        """Test adding multiple servers."""
        monitor = StartupMonitor()
        server1 = BlockingMCPServerStdio(command="echo")
        server2 = BlockingMCPServerStdio(command="cat")

        monitor.add_server("server1", server1)
        monitor.add_server("server2", server2)

        assert len(monitor.servers) == 2
        assert monitor.servers["server1"] is server1
        assert monitor.servers["server2"] is server2

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
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()  # Mark as ready
        monitor.add_server("test", server)

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert results["test"] is True
        assert "test" in monitor.startup_times

    @pytest.mark.asyncio
    async def test_wait_all_ready_single_server_timeout(self):
        """Test wait_all_ready with timeout."""
        monitor = StartupMonitor()
        server = BlockingMCPServerStdio(command="echo")  # Won't initialize
        monitor.add_server("test", server)

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=0.1)

        assert results["test"] is False

    @pytest.mark.asyncio
    async def test_wait_all_ready_mixed_success_failure(self):
        """Test wait_all_ready with mixed results."""
        monitor = StartupMonitor()

        server1 = BlockingMCPServerStdio(command="echo")
        server1._initialized.set()  # Ready
        monitor.add_server("server1", server1)

        server2 = BlockingMCPServerStdio(command="cat")  # Won't initialize
        monitor.add_server("server2", server2)

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=0.1)

        assert results["server1"] is True
        assert results["server2"] is False

    def test_get_startup_report_empty(self):
        """Test startup report with no servers."""
        monitor = StartupMonitor()
        report = monitor.get_startup_report()
        assert "Server Startup Times:" in report

    def test_get_startup_report_with_servers(self):
        """Test startup report with servers."""
        monitor = StartupMonitor()
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()
        monitor.add_server("test-server", server)
        monitor.startup_times["test-server"] = 1.5

        report = monitor.get_startup_report()
        assert "Server Startup Times:" in report
        assert "test-server" in report
        assert "1.50s" in report

    def test_get_startup_report_shows_status(self):
        """Test that startup report shows ready status."""
        monitor = StartupMonitor()

        ready_server = BlockingMCPServerStdio(command="echo")
        ready_server._initialized.set()
        monitor.add_server("ready", ready_server)
        monitor.startup_times["ready"] = 1.0

        failed_server = BlockingMCPServerStdio(command="cat")
        failed_server._init_error = RuntimeError("Failed")
        failed_server._initialized.set()
        monitor.add_server("failed", failed_server)
        monitor.startup_times["failed"] = 2.0

        report = monitor.get_startup_report()
        assert "✅" in report
        assert "❌" in report


class TestStartupEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_initialization_calls(self):
        """Test multiple concurrent wait_until_ready calls."""
        server = BlockingMCPServerStdio(command="echo")

        async def delayed_init():
            await asyncio.sleep(0.1)
            server._initialized.set()

        asyncio.create_task(delayed_init())

        # Multiple concurrent waits
        results = await asyncio.gather(
            server.wait_until_ready(timeout=1),
            server.wait_until_ready(timeout=1),
            server.wait_until_ready(timeout=1),
        )

        assert all(results)

    @pytest.mark.asyncio
    async def test_initialization_error_handling_exception_group(self):
        """Test exception group unwrapping in __aenter__."""
        server = BlockingMCPServerStdio(command="echo")

        # Create a mock ExceptionGroup-like object
        error1 = RuntimeError("Error 1")
        error2 = RuntimeError("Error 2")

        # Create a class that looks like ExceptionGroup
        class MockExceptionGroup(Exception):
            def __init__(self):
                self.exceptions = [error1, error2]

        # Mock the parent __aenter__
        async def mock_aenter():
            raise MockExceptionGroup()

        with patch.object(
            SimpleCapturedMCPServerStdio, "__aenter__", new_callable=AsyncMock
        ) as mock:
            mock.side_effect = mock_aenter

            with pytest.raises(Exception):
                await server.__aenter__()

            # First exception should be stored
            assert server._init_error is not None

    @pytest.mark.asyncio
    async def test_wait_until_ready_timeout_message_includes_server_name(self):
        """Test that timeout message includes server name."""
        server = BlockingMCPServerStdio(command="my-special-server")
        server.tool_prefix = "my-tool"

        with pytest.raises(TimeoutError) as exc_info:
            await server.wait_until_ready(timeout=0.01)

        assert "my-tool" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_monitor_parallel_server_waits(self):
        """Test that monitor handles parallel server waits."""
        monitor = StartupMonitor()

        # Create servers with different delays
        servers_data = [
            ("fast", 0.05),
            ("medium", 0.1),
            ("slow", 0.15),
        ]

        async def init_server(server, delay):
            await asyncio.sleep(delay)
            server._initialized.set()

        for name, delay in servers_data:
            server = BlockingMCPServerStdio(command="echo")
            monitor.add_server(name, server)
            asyncio.create_task(init_server(server, delay))

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        # All should be ready
        assert all(results.values())

    def test_stderr_capture_monitoring_flag(self):
        """Test that monitoring can be disabled."""
        capture = StderrFileCapture("test", emit_to_user=False)
        assert capture.emit_to_user is False

        capture2 = StderrFileCapture("test", emit_to_user=True)
        assert capture2.emit_to_user is True

    @pytest.mark.asyncio
    async def test_server_ready_status_idempotent(self):
        """Test that is_ready() is idempotent."""
        server = BlockingMCPServerStdio(command="echo")
        server._initialized.set()

        # Multiple calls should return same result
        results = [server.is_ready() for _ in range(5)]
        assert all(results)

    def test_startup_monitor_servers_dict_isolation(self):
        """Test that server dict is isolated per monitor."""
        monitor1 = StartupMonitor()
        monitor2 = StartupMonitor()

        server1 = BlockingMCPServerStdio(command="echo")
        server2 = BlockingMCPServerStdio(command="cat")

        monitor1.add_server("test", server1)
        monitor2.add_server("test", server2)

        assert monitor1.servers["test"] is server1
        assert monitor2.servers["test"] is server2
        assert monitor1.servers is not monitor2.servers


class TestServerStartupIntegration:
    """Integration tests for server startup."""

    @pytest.mark.asyncio
    async def test_multiple_servers_with_monitor(self):
        """Test starting multiple servers with monitor."""
        monitor = StartupMonitor()

        # Create and initialize servers
        servers = [BlockingMCPServerStdio(command=f"server-{i}") for i in range(3)]

        for i, server in enumerate(servers):
            monitor.add_server(f"server-{i}", server)
            server._initialized.set()  # Mark as ready

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert len(results) == 3
        assert all(results.values())

    @pytest.mark.asyncio
    async def test_server_initialization_timing(self):
        """Test that startup times are recorded."""
        monitor = StartupMonitor()
        server = BlockingMCPServerStdio(command="echo")
        monitor.add_server("test", server)

        async def delayed_init():
            await asyncio.sleep(0.1)
            server._initialized.set()

        asyncio.create_task(delayed_init())

        with patch("code_puppy.mcp_.blocking_startup.emit_info"):
            results = await monitor.wait_all_ready(timeout=1)

        assert results["test"] is True
        assert "test" in monitor.startup_times
        assert monitor.startup_times["test"] >= 0.1  # At least delay time
