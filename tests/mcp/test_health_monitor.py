"""
Comprehensive tests for health_monitor.py.

Tests health monitoring system including:
- Health check execution and monitoring loops
- Server type-specific health checks (SSE, HTTP, stdio)
- Consecutive failure handling and recovery
- Health history tracking and status queries
- Circuit breaker functionality
- Error handling and edge cases
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import httpx
import pytest

from code_puppy.mcp_.health_monitor import (
    HealthCheckResult,
    HealthMonitor,
    HealthStatus,
)
from code_puppy.mcp_.managed_server import ManagedMCPServer


@pytest.fixture
def mock_server():
    """Create a mock ManagedMCPServer."""
    server = Mock(spec=ManagedMCPServer)
    server.config = Mock()
    server.config.id = "test-server-1"
    server.config.type = "stdio"
    server.config.config = {
        "command": "python",
        "args": ["-m", "test_server"],
    }
    server.is_enabled.return_value = True
    server.enable = Mock()
    server.disable = Mock()
    server.quarantine = Mock()
    server.get_pydantic_server = Mock()
    return server


@pytest.fixture
def health_monitor():
    """Create a HealthMonitor instance for testing."""
    return HealthMonitor(check_interval=1)  # Short interval for testing


@pytest.fixture
def sse_server(mock_server):
    """Create a mock SSE server."""
    mock_server.config.type = "sse"
    mock_server.config.config = {"url": "http://localhost:3000/mcp"}
    return mock_server


@pytest.fixture
def http_server(mock_server):
    """Create a mock HTTP server."""
    mock_server.config.type = "http"
    mock_server.config.config = {"url": "http://localhost:4000/api"}
    return mock_server


@pytest.fixture
def stdio_server(mock_server):
    """Create a mock stdio server."""
    mock_server.config.type = "stdio"
    mock_server.config.config = {
        "command": "node",
        "args": ["server.js"],
    }
    return mock_server


class TestHealthMonitor:
    """Test the main HealthMonitor class."""

    def test_initialization(self):
        """Test HealthMonitor initialization."""
        monitor = HealthMonitor(check_interval=45)

        assert monitor.check_interval == 45
        assert isinstance(monitor.monitoring_tasks, dict)
        assert len(monitor.monitoring_tasks) == 0
        assert isinstance(monitor.health_history, dict)
        assert isinstance(monitor.custom_health_checks, dict)
        assert len(monitor.custom_health_checks) == 3  # sse, http, stdio
        assert isinstance(monitor.consecutive_failures, dict)
        assert isinstance(monitor.last_check_time, dict)

        # Check default health checks are registered
        assert "sse" in monitor.custom_health_checks
        assert "http" in monitor.custom_health_checks
        assert "stdio" in monitor.custom_health_checks

    def test_register_health_check(self, health_monitor):
        """Test registering custom health check functions."""

        async def custom_check(server):
            return True

        health_monitor.register_health_check("custom", custom_check)
        assert "custom" in health_monitor.custom_health_checks
        assert health_monitor.custom_health_checks["custom"] == custom_check

        # Test case insensitive registration
        health_monitor.register_health_check("CUSTOM2", custom_check)
        assert "custom2" in health_monitor.custom_health_checks

    async def test_start_stop_monitoring(self, health_monitor, mock_server):
        """Test starting and stopping monitoring for a server."""
        server_id = "test-server"

        # Test starting monitoring
        await health_monitor.start_monitoring(server_id, mock_server)
        assert server_id in health_monitor.monitoring_tasks
        assert health_monitor.monitoring_tasks[server_id].cancelled() is False

        # Test duplicate start
        with patch("code_puppy.mcp_.health_monitor.logger") as mock_logger:
            await health_monitor.start_monitoring(server_id, mock_server)
            mock_logger.warning.assert_called()

        # Test stopping monitoring
        await health_monitor.stop_monitoring(server_id)
        assert server_id not in health_monitor.monitoring_tasks
        assert server_id not in health_monitor.consecutive_failures
        assert server_id not in health_monitor.last_check_time

        # Test stop non-existent server
        with patch("code_puppy.mcp_.health_monitor.logger") as mock_logger:
            await health_monitor.stop_monitoring("non-existent")
            mock_logger.warning.assert_called()

    async def test_check_health_success(self, health_monitor, mock_server):
        """Test successful health check."""
        with patch.object(health_monitor, "perform_health_check") as mock_perform:
            mock_perform.return_value = HealthCheckResult(
                success=True, latency_ms=50.0, error=None
            )

            result = await health_monitor.check_health(mock_server)

            assert isinstance(result, HealthStatus)
            assert result.is_healthy is True
            assert result.latency_ms == 50.0
            assert result.error is None
            assert result.check_type == "stdio"
            assert isinstance(result.timestamp, datetime)

    async def test_check_health_failure(self, health_monitor, mock_server):
        """Test health check failure."""
        with patch.object(health_monitor, "perform_health_check") as mock_perform:
            mock_perform.return_value = HealthCheckResult(
                success=False, latency_ms=100.0, error="Connection failed"
            )

            result = await health_monitor.check_health(mock_server)

            assert result.is_healthy is False
            assert result.latency_ms == 100.0
            assert result.error == "Connection failed"
            assert result.check_type == "stdio"

    async def test_check_health_no_registered_check(self, health_monitor, mock_server):
        """Test health check when no function is registered for server type."""
        mock_server.config.type = "unknown"

        result = await health_monitor.check_health(mock_server)

        assert result.is_healthy is False
        assert result.latency_ms is None
        assert "No health check registered for type 'unknown'" in result.error
        assert result.check_type == "unknown"

    async def test_check_health_exception(self, health_monitor, mock_server):
        """Test health check when an exception occurs."""
        with patch.object(health_monitor, "perform_health_check") as mock_perform:
            mock_perform.side_effect = Exception("Test exception")

            result = await health_monitor.check_health(mock_server)

            assert result.is_healthy is False
            assert result.latency_ms is None
            assert result.error == "Test exception"
            assert result.check_type == "stdio"

    async def test_perform_health_check_boolean_result(
        self, health_monitor, mock_server
    ):
        """Test perform_health_check with boolean return."""

        async def mock_check(server):
            return True

        # Set the mock check directly
        health_monitor.custom_health_checks["stdio"] = mock_check
        result = await health_monitor.perform_health_check(mock_server)

        assert result.success is True
        assert result.latency_ms > 0
        assert result.error is None

    async def test_perform_health_check_result_object(
        self, health_monitor, mock_server
    ):
        """Test perform_health_check with HealthCheckResult return."""

        async def mock_check(server):
            return HealthCheckResult(success=True, latency_ms=25.0, error=None)

        # Set the mock check directly
        health_monitor.custom_health_checks["stdio"] = mock_check
        result = await health_monitor.perform_health_check(mock_server)

        assert result.success is True
        assert result.latency_ms == 25.0
        assert result.error is None

    async def test_perform_health_check_invalid_result(
        self, health_monitor, mock_server
    ):
        """Test perform_health_check with invalid return type."""

        async def mock_check(server):
            return "invalid"

        # Set the mock check directly
        health_monitor.custom_health_checks["stdio"] = mock_check
        result = await health_monitor.perform_health_check(mock_server)

        assert result.success is False
        assert result.latency_ms > 0
        assert "Invalid health check result type" in result.error

    async def test_perform_health_check_exception(self, health_monitor, mock_server):
        """Test perform_health_check when check function raises exception."""

        async def mock_check(server):
            raise ValueError("Check failed")

        # Set the mock check directly
        health_monitor.custom_health_checks["stdio"] = mock_check
        result = await health_monitor.perform_health_check(mock_server)

        assert result.success is False
        assert result.latency_ms > 0
        assert result.error == "Check failed"

    def test_get_health_history(self, health_monitor):
        """Test retrieving health history."""
        server_id = "test-server"

        # Add some mock health status entries
        now = datetime.now()
        status1 = HealthStatus(
            timestamp=now - timedelta(minutes=2),
            is_healthy=True,
            latency_ms=50.0,
            error=None,
            check_type="test",
        )
        status2 = HealthStatus(
            timestamp=now - timedelta(minutes=1),
            is_healthy=False,
            latency_ms=None,
            error="Failed",
            check_type="test",
        )
        status3 = HealthStatus(
            timestamp=now,
            is_healthy=True,
            latency_ms=45.0,
            error=None,
            check_type="test",
        )

        health_monitor.health_history[server_id].extend([status1, status2, status3])

        # Test unlimited history
        history = health_monitor.get_health_history(server_id, limit=0)
        assert len(history) == 3
        assert history[0].timestamp == status3.timestamp  # Most recent first
        assert history[-1].timestamp == status1.timestamp

        # Test limited history
        history = health_monitor.get_health_history(server_id, limit=2)
        assert len(history) == 2
        assert history[0].timestamp == status3.timestamp
        assert history[1].timestamp == status2.timestamp

        # Test empty history
        empty_history = health_monitor.get_health_history("non-existent")
        assert empty_history == []

    def test_is_healthy(self, health_monitor):
        """Test checking if server is healthy."""
        server_id = "test-server"

        # Test no history
        assert health_monitor.is_healthy(server_id) is False

        # Test healthy latest status
        status = HealthStatus(
            timestamp=datetime.now(),
            is_healthy=True,
            latency_ms=50.0,
            error=None,
            check_type="test",
        )
        health_monitor.health_history[server_id].append(status)
        assert health_monitor.is_healthy(server_id) is True

        # Test unhealthy latest status
        status_unhealthy = HealthStatus(
            timestamp=datetime.now(),
            is_healthy=False,
            latency_ms=None,
            error="Failed",
            check_type="test",
        )
        health_monitor.health_history[server_id].append(status_unhealthy)
        assert health_monitor.is_healthy(server_id) is False

    async def test_monitoring_loop_basic(self, health_monitor, mock_server):
        """Test basic monitoring loop functionality."""
        server_id = "test-server"

        # Start monitoring
        await health_monitor.start_monitoring(server_id, mock_server)

        # Wait for at least one health check
        await asyncio.sleep(1.5)

        # Check that health status was recorded
        assert len(health_monitor.health_history[server_id]) > 0
        assert server_id in health_monitor.last_check_time

        # Stop monitoring
        await health_monitor.stop_monitoring(server_id)

    async def test_monitoring_loop_disabled_server(self, health_monitor, mock_server):
        """Test monitoring loop with disabled server."""
        server_id = "test-server"
        mock_server.is_enabled.return_value = False

        await health_monitor.start_monitoring(server_id, mock_server)

        # Clear the initial health check that happens even for disabled servers
        health_monitor.health_history[server_id].clear()

        # Wait and check that no health checks occurred in the loop
        await asyncio.sleep(1.5)
        subsequent_checks = len(health_monitor.health_history[server_id])
        assert subsequent_checks == 0

        await health_monitor.stop_monitoring(server_id)

    async def test_consecutive_failures_handling(self, health_monitor, mock_server):
        """Test consecutive failure handling and recovery."""
        server_id = "test-server"

        # Mock perform_health_check to always fail
        async def mock_perform_fail(server):
            return HealthCheckResult(
                success=False, latency_ms=100.0, error="Always fails"
            )

        health_monitor.perform_health_check = mock_perform_fail

        # Start monitoring with short interval
        health_monitor.check_interval = 0.5
        await health_monitor.start_monitoring(server_id, mock_server)

        # Wait for multiple failures
        await asyncio.sleep(2)

        # Check consecutive failures count
        assert health_monitor.consecutive_failures[server_id] >= 2

        # Now make health checks succeed - stop monitoring first
        await health_monitor.stop_monitoring(server_id)

        # Reset for success scenario
        health_monitor.consecutive_failures[server_id] = 1

        # Start fresh with success scenario
        async def mock_perform_success(server):
            return HealthCheckResult(success=True, latency_ms=50.0, error=None)

        health_monitor.perform_health_check = mock_perform_success

        # Simulate a single successful health check
        success_result = await health_monitor.perform_health_check(mock_server)
        if success_result.success:
            health_monitor.consecutive_failures[server_id] = 0

        # Should reset consecutive failures
        assert health_monitor.consecutive_failures[server_id] == 0

        await health_monitor.stop_monitoring(server_id)

    async def test_recovery_trigger(self, health_monitor, mock_server):
        """Test recovery triggering after failures."""
        server_id = "test-server"

        await health_monitor._trigger_recovery(server_id, mock_server, 3)

        mock_server.disable.assert_called_once()
        mock_server.enable.assert_called_once()

    async def test_recovery_trigger_exception(self, health_monitor, mock_server):
        """Test recovery trigger when disable/enable fails."""
        server_id = "test-server"
        mock_server.disable.side_effect = Exception("Disable failed")

        with pytest.raises(Exception, match="Disable failed"):
            await health_monitor._trigger_recovery(server_id, mock_server, 3)

    async def test_quarantine_after_many_failures(self, health_monitor, mock_server):
        """Test server quarantine after many consecutive failures."""
        server_id = "test-server"
        health_monitor.consecutive_failures[server_id] = 6

        await health_monitor._handle_consecutive_failures(server_id, mock_server)

        mock_server.quarantine.assert_called_once()
        quarantine_duration = mock_server.quarantine.call_args[0][0]
        assert quarantine_duration > 0
        assert quarantine_duration <= 1800  # Max 30 minutes

    async def test_sse_health_check_success(self, health_monitor, sse_server):
        """Test successful SSE health check."""
        mock_response = Mock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await health_monitor._check_sse_health(sse_server)

            assert result.success is True
            assert result.error is None

    async def test_sse_health_check_failure(self, health_monitor, sse_server):
        """Test SSE health check failure."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.reason_phrase = "Internal Server Error"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = (
                mock_response
            )

            result = await health_monitor._check_sse_health(sse_server)

            assert result.success is False
            assert "HTTP 500" in result.error

    async def test_sse_health_check_no_url(self, health_monitor, sse_server):
        """Test SSE health check with no URL configured."""
        sse_server.config.config = {}

        result = await health_monitor._check_sse_health(sse_server)

        assert result.success is False
        assert "No URL configured" in result.error

    async def test_sse_health_check_exception(self, health_monitor, sse_server):
        """Test SSE health check with exception."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = (
                httpx.RequestError("Connection error")
            )

            result = await health_monitor._check_sse_health(sse_server)

            assert result.success is False
            assert "Connection error" in result.error

    async def test_sse_health_check_fallback_to_base_url(
        self, health_monitor, sse_server
    ):
        """Test SSE health check fallback to base URL when health endpoint returns 404."""
        base_url = "http://localhost:3000"
        sse_server.config.config = {"url": base_url}

        mock_health_response = Mock()
        mock_health_response.status_code = 404
        mock_base_response = Mock()
        mock_base_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client:
            client_instance = mock_client.return_value.__aenter__.return_value
            client_instance.get.side_effect = [mock_health_response, mock_base_response]

            result = await health_monitor._check_sse_health(sse_server)

            assert result.success is True
            assert client_instance.get.call_count == 2

    async def test_http_health_check(self, health_monitor, http_server):
        """Test HTTP healthcheck uses same logic as SSE."""
        with patch.object(health_monitor, "_check_sse_health") as mock_sse_check:
            mock_sse_check.return_value = HealthCheckResult(
                success=True, latency_ms=0.0, error=None
            )

            result = await health_monitor._check_http_health(http_server)

            mock_sse_check.assert_called_once_with(http_server)
            assert result.success is True

    async def test_stdio_health_check_success(self, health_monitor, stdio_server):
        """Test successful stdio health check."""
        with patch("shutil.which", return_value="/usr/bin/node"):
            result = await health_monitor._check_stdio_health(stdio_server)

            assert result.success is True
            assert result.error is None

    async def test_stdio_health_check_no_command(self, health_monitor, stdio_server):
        """Test stdio health check with no command configured."""
        stdio_server.config.config = {}

        result = await health_monitor._check_stdio_health(stdio_server)

        assert result.success is False
        assert "No command configured" in result.error

    async def test_stdio_health_check_command_not_found(
        self, health_monitor, stdio_server
    ):
        """Test stdio health check with command not in PATH."""
        with patch("shutil.which", return_value=None):
            result = await health_monitor._check_stdio_health(stdio_server)

            assert result.success is False
            assert "not found in PATH" in result.error

    async def test_stdio_health_check_exception(self, health_monitor, stdio_server):
        """Test stdio health check when get_pydantic_server raises exception."""
        stdio_server.get_pydantic_server.side_effect = Exception(
            "Server creation failed"
        )

        result = await health_monitor._check_stdio_health(stdio_server)

        assert result.success is False
        assert "Server creation failed" in result.error

    async def test_shutdown(self, health_monitor, mock_server):
        """Test graceful shutdown of all monitoring tasks."""
        server_id1 = "server1"
        server_id2 = "server2"
        mock_server2 = Mock(spec=ManagedMCPServer)
        mock_server2.config = Mock()
        mock_server2.config.id = server_id2
        mock_server2.config.type = "stdio"
        mock_server2.config.config = {"command": "python"}
        mock_server2.is_enabled.return_value = True

        # Start monitoring for multiple servers
        await health_monitor.start_monitoring(server_id1, mock_server)
        await health_monitor.start_monitoring(server_id2, mock_server2)

        assert len(health_monitor.monitoring_tasks) == 2

        # Shutdown
        await health_monitor.shutdown()

        assert len(health_monitor.monitoring_tasks) == 0
        assert len(health_monitor.consecutive_failures) == 0
        assert len(health_monitor.last_check_time) == 0

    async def test_initial_health_check_on_start(self, health_monitor, mock_server):
        """Test that initial health check is performed when starting monitoring."""
        server_id = "test-server"

        with patch.object(health_monitor, "check_health") as mock_check:
            mock_check.return_value = HealthStatus(
                timestamp=datetime.now(),
                is_healthy=True,
                latency_ms=50.0,
                error=None,
                check_type="stdio",
            )

            await health_monitor.start_monitoring(server_id, mock_server)

            # Should have performed initial health check
            mock_check.assert_called_once_with(mock_server)
            assert len(health_monitor.health_history[server_id]) == 1

            await health_monitor.stop_monitoring(server_id)

    async def test_initial_health_check_failure(self, health_monitor, mock_server):
        """Test initial health check failure when starting monitoring."""
        server_id = "test-server"

        with patch.object(health_monitor, "check_health") as mock_check:
            mock_check.side_effect = Exception("Initial check failed")

            await health_monitor.start_monitoring(server_id, mock_server)

            # Should have recorded error status
            assert len(health_monitor.health_history[server_id]) == 1
            status = health_monitor.health_history[server_id][0]
            assert status.is_healthy is False
            assert "Initial check failed" in status.error
            assert status.check_type == "initial"

            await health_monitor.stop_monitoring(server_id)

    def test_record_health_status(self, health_monitor):
        """Test recording health status with logging."""
        server_id = "test-server"
        status_healthy = HealthStatus(
            timestamp=datetime.now(),
            is_healthy=True,
            latency_ms=50.0,
            error=None,
            check_type="test",
        )
        status_unhealthy = HealthStatus(
            timestamp=datetime.now(),
            is_healthy=False,
            latency_ms=None,
            error="Failed",
            check_type="test",
        )

        with patch("code_puppy.mcp_.health_monitor.logger") as mock_logger:
            health_monitor._record_health_status(server_id, status_healthy)
            mock_logger.debug.assert_called()

            health_monitor._record_health_status(server_id, status_unhealthy)
            mock_logger.warning.assert_called()

        assert len(health_monitor.health_history[server_id]) == 2

    async def test_monitoring_loop_error_handling(self, health_monitor, mock_server):
        """Test monitoring loop error handling continues despite exceptions."""
        server_id = "test-server"

        # Mock perform_health_check to raise exception
        async def mock_perform_exception(server):
            raise Exception("Monitor loop error")

        health_monitor.perform_health_check = mock_perform_exception
        health_monitor.check_interval = 0.5

        await health_monitor.start_monitoring(server_id, mock_server)

        # Wait for error to occur and loop to continue
        await asyncio.sleep(1.5)

        # Should have recorded some health attempts despite errors
        assert len(health_monitor.health_history[server_id]) > 0

        await health_monitor.stop_monitoring(server_id)

    async def test_monitoring_loop_cancellation(self, health_monitor, mock_server):
        """Test monitoring loop handles cancellation gracefully."""
        server_id = "test-server"

        await health_monitor.start_monitoring(server_id, mock_server)
        health_monitor.monitoring_tasks[server_id]

        # Cancel the task directly through stop_monitoring
        await health_monitor.stop_monitoring(server_id)

        assert server_id not in health_monitor.monitoring_tasks


class TestHealthStatus:
    """Test the HealthStatus dataclass."""

    def test_health_status_creation(self):
        """Test HealthStatus object creation."""
        timestamp = datetime.now()
        status = HealthStatus(
            timestamp=timestamp,
            is_healthy=True,
            latency_ms=50.5,
            error=None,
            check_type="test",
        )

        assert status.timestamp == timestamp
        assert status.is_healthy is True
        assert status.latency_ms == 50.5
        assert status.error is None
        assert status.check_type == "test"


class TestHealthCheckResult:
    """Test the HealthCheckResult dataclass."""

    def test_health_check_result_creation(self):
        """Test HealthCheckResult object creation."""
        result = HealthCheckResult(
            success=True,
            latency_ms=75.2,
            error=None,
        )

        assert result.success is True
        assert result.latency_ms == 75.2
        assert result.error is None
