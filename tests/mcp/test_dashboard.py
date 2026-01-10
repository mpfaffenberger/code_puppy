"""
Comprehensive tests for code_puppy/mcp_/dashboard.py

Provides full coverage of MCPDashboard functionality including:
- Dashboard rendering with various server states
- Individual server row formatting
- Status and health indicators
- Uptime and latency formatting
- Metrics summarization
- Console output
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

from rich.console import Console
from rich.table import Table

from code_puppy.mcp_.dashboard import MCPDashboard
from code_puppy.mcp_.status_tracker import ServerState


class TestMCPDashboardInit:
    """Tests for MCPDashboard initialization."""

    def test_init_creates_console(self):
        """Test that initialization creates a Console instance."""
        dashboard = MCPDashboard()
        assert dashboard._console is not None
        assert isinstance(dashboard._console, Console)

    def test_init_multiple_instances_are_independent(self):
        """Test that multiple dashboard instances have independent consoles."""
        dashboard1 = MCPDashboard()
        dashboard2 = MCPDashboard()
        assert dashboard1._console is not dashboard2._console


class TestRenderDashboard:
    """Tests for render_dashboard() method."""

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_render_dashboard_with_servers(self, mock_get_manager):
        """Test dashboard rendering with multiple servers."""
        # Mock servers
        server1 = Mock()
        server1.id = "server-1"
        server1.name = "test-server"
        server1.type = "stdio"
        server1.state = ServerState.RUNNING
        server1.health = {"is_healthy": True}
        server1.start_time = datetime.now() - timedelta(hours=2)
        server1.latency_ms = 45.5

        server2 = Mock()
        server2.id = "server-2"
        server2.name = "another-server"
        server2.type = "sse"
        server2.state = ServerState.STOPPED
        server2.health = {"is_healthy": False, "error": "Connection failed"}
        server2.start_time = None
        server2.latency_ms = None

        mock_manager = Mock()
        mock_manager.list_servers.return_value = [server1, server2]
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        assert isinstance(table, Table)
        assert table.title == "MCP Server Status Dashboard"
        # Should have header + 2 server rows
        assert len(table.rows) == 2

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_render_dashboard_empty_servers(self, mock_get_manager):
        """Test dashboard rendering when no servers exist."""
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        assert isinstance(table, Table)
        # Should have 1 row for empty state message
        assert len(table.rows) == 1

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_render_dashboard_error_state(self, mock_get_manager):
        """Test dashboard rendering when manager raises exception."""
        mock_manager = Mock()
        mock_manager.list_servers.side_effect = Exception("Connection failed")
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        assert isinstance(table, Table)
        # Should have 1 row for error state
        assert len(table.rows) == 1

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_render_dashboard_columns(self, mock_get_manager):
        """Test that dashboard has correct columns."""
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        # Check column count
        assert len(table.columns) == 6
        # Check column headers
        headers = [col.header for col in table.columns]
        assert "Name" in headers
        assert "Type" in headers
        assert "State" in headers
        assert "Health" in headers
        assert "Uptime" in headers
        assert "Latency" in headers


class TestRenderServerRow:
    """Tests for render_server_row() method."""

    def test_render_server_row_with_all_data(self):
        """Test rendering server row with complete data."""
        server = Mock()
        server.id = "test-server-id"
        server.name = "test-server"
        server.type = "stdio"
        server.state = ServerState.RUNNING
        server.health = {"is_healthy": True}
        server.start_time = datetime.now() - timedelta(hours=1)
        server.latency_ms = 50.0

        dashboard = MCPDashboard()
        row = dashboard.render_server_row(server)

        assert len(row) == 6
        assert row[0] == "test-server"  # name
        assert row[1] == "STDIO"  # type
        assert "Run" in row[2]  # state indicator
        assert "✓" in row[3]  # health indicator
        assert row[4] != "-"  # uptime
        assert "50" in row[5]  # latency

    def test_render_server_row_with_minimal_id_name(self):
        """Test rendering server row when name is None uses short ID."""
        server = Mock()
        server.id = "abcdef123456"
        server.name = None
        server.type = "sse"
        server.state = ServerState.STOPPED
        server.health = None
        server.start_time = None
        server.latency_ms = None

        dashboard = MCPDashboard()
        row = dashboard.render_server_row(server)

        assert row[0] == "abcdef12"  # first 8 chars of ID
        assert row[1] == "SSE"
        assert row[4] == "-"
        assert row[5] == "-"

    def test_render_server_row_none_type(self):
        """Test rendering server row when type is None."""
        server = Mock()
        server.id = "server-1"
        server.name = "test"
        server.type = None
        server.state = ServerState.ERROR
        server.health = {"is_healthy": False, "error": "Failed"}
        server.start_time = datetime.now() - timedelta(seconds=30)
        server.latency_ms = 100.0

        dashboard = MCPDashboard()
        row = dashboard.render_server_row(server)

        assert row[1] == "UNK"  # unknown type


class TestRenderStateIndicator:
    """Tests for render_state_indicator() method."""

    def test_running_state(self):
        """Test RUNNING state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.RUNNING)
        assert "green" in indicator.lower() or "✓" in indicator
        assert "Run" in indicator

    def test_stopped_state(self):
        """Test STOPPED state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.STOPPED)
        assert "red" in indicator.lower() or "✗" in indicator
        assert "Stop" in indicator

    def test_error_state(self):
        """Test ERROR state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.ERROR)
        assert "red" in indicator.lower() or "⚠" in indicator
        assert "Err" in indicator

    def test_starting_state(self):
        """Test STARTING state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.STARTING)
        assert "yellow" in indicator.lower() or "⏳" in indicator
        assert "Start" in indicator

    def test_stopping_state(self):
        """Test STOPPING state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.STOPPING)
        assert "yellow" in indicator.lower() or "⏳" in indicator
        assert "Stop" in indicator

    def test_quarantined_state(self):
        """Test QUARANTINED state indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_state_indicator(ServerState.QUARANTINED)
        assert "yellow" in indicator.lower() or "⏸" in indicator
        assert "Quar" in indicator

    def test_unknown_state_fallback(self):
        """Test unknown state falls back to default."""
        dashboard = MCPDashboard()
        # Create a mock state that doesn't match any known states
        unknown_state = Mock()
        unknown_state.value = "unknown"
        indicator = dashboard.render_state_indicator(unknown_state)
        assert "Unk" in indicator or "?" in indicator


class TestRenderHealthIndicator:
    """Tests for render_health_indicator() method."""

    def test_healthy_indicator(self):
        """Test healthy status indicator."""
        dashboard = MCPDashboard()
        health = {"is_healthy": True}
        indicator = dashboard.render_health_indicator(health)
        assert "green" in indicator.lower() or "✓" in indicator

    def test_unhealthy_with_error_indicator(self):
        """Test unhealthy status with error."""
        dashboard = MCPDashboard()
        health = {"is_healthy": False, "error": "Connection failed"}
        indicator = dashboard.render_health_indicator(health)
        assert "red" in indicator.lower() or "✗" in indicator

    def test_unhealthy_without_error_indicator(self):
        """Test unhealthy status without error details."""
        dashboard = MCPDashboard()
        health = {"is_healthy": False}
        indicator = dashboard.render_health_indicator(health)
        assert "yellow" in indicator.lower() or "?" in indicator

    def test_none_health_indicator(self):
        """Test None health indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_health_indicator(None)
        assert "dim" in indicator.lower() or "?" in indicator

    def test_empty_health_dict_indicator(self):
        """Test empty health dict indicator."""
        dashboard = MCPDashboard()
        indicator = dashboard.render_health_indicator({})
        assert "dim" in indicator.lower() or "?" in indicator


class TestFormatUptime:
    """Tests for format_uptime() method."""

    def test_format_uptime_seconds(self):
        """Test formatting uptime less than 1 minute."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(seconds=45)
        result = dashboard.format_uptime(start_time)
        assert "s" in result
        assert any(char.isdigit() for char in result)

    def test_format_uptime_minutes(self):
        """Test formatting uptime in minutes."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(minutes=15, seconds=30)
        result = dashboard.format_uptime(start_time)
        assert "m" in result
        assert "15" in result or "16" in result  # Allow rounding

    def test_format_uptime_hours(self):
        """Test formatting uptime in hours."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(hours=3, minutes=45)
        result = dashboard.format_uptime(start_time)
        assert "h" in result
        assert "3" in result or "4" in result  # Allow rounding

    def test_format_uptime_days(self):
        """Test formatting uptime in days."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(days=5, hours=12)
        result = dashboard.format_uptime(start_time)
        assert "d" in result
        assert "5" in result

    def test_format_uptime_none(self):
        """Test formatting None uptime."""
        dashboard = MCPDashboard()
        result = dashboard.format_uptime(None)
        assert result == "-"

    def test_format_uptime_negative(self):
        """Test formatting negative uptime (clock skew)."""
        dashboard = MCPDashboard()
        # Future timestamp (shouldn't happen, but handle gracefully)
        future_time = datetime.now() + timedelta(hours=1)
        result = dashboard.format_uptime(future_time)
        assert result == "0s"

    def test_format_uptime_exception_handling(self):
        """Test that exceptions in format_uptime are handled gracefully."""
        dashboard = MCPDashboard()
        # Pass an object that will cause an error
        result = dashboard.format_uptime("invalid")
        assert result == "?"

    def test_format_uptime_exact_hour(self):
        """Test formatting uptime of exactly 1 hour."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(hours=1)
        result = dashboard.format_uptime(start_time)
        assert "1h" in result

    def test_format_uptime_hour_and_minute(self):
        """Test formatting uptime with hours and minutes."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(hours=2, minutes=30)
        result = dashboard.format_uptime(start_time)
        assert "2h" in result
        assert "30m" in result

    def test_format_uptime_minutes_and_seconds(self):
        """Test formatting uptime with minutes and seconds."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(minutes=5, seconds=45)
        result = dashboard.format_uptime(start_time)
        assert "5m" in result or "6m" in result

    def test_format_uptime_exact_minutes_no_seconds(self):
        """Test formatting exact minutes without seconds."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(minutes=30)
        result = dashboard.format_uptime(start_time)
        assert "30m" in result
        # Should not have seconds suffix since seconds == 0
        assert "s" not in result or "ms" in result


class TestFormatLatency:
    """Tests for format_latency() method."""

    def test_format_latency_fast(self):
        """Test formatting fast latency (< 50ms)."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(25.5)
        assert "green" in result.lower()
        assert "26" in result  # Rounds to 26ms

    def test_format_latency_acceptable(self):
        """Test formatting acceptable latency (50-200ms)."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(100.0)
        assert "yellow" in result.lower()
        assert "100" in result

    def test_format_latency_slow(self):
        """Test formatting slow latency (200-1000ms)."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(500.0)
        assert "red" in result.lower()
        assert "500" in result

    def test_format_latency_very_slow(self):
        """Test formatting very slow latency (1-30 seconds)."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(5000.0)
        assert "red" in result.lower()
        assert "5.0s" in result or "5.0s" in result

    def test_format_latency_timeout(self):
        """Test formatting timeout latency (30+ seconds)."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(35000.0)
        assert "red" in result.lower()
        assert "timeout" in result

    def test_format_latency_none(self):
        """Test formatting None latency."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(None)
        assert result == "-"

    def test_format_latency_negative(self):
        """Test formatting negative latency."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(-10.0)
        assert result == "invalid"

    def test_format_latency_zero(self):
        """Test formatting zero latency."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(0.0)
        assert "green" in result.lower()
        assert "0" in result

    def test_format_latency_invalid_type(self):
        """Test formatting invalid latency type."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency("invalid")
        assert result == "error"

    def test_format_latency_boundary_50ms(self):
        """Test latency boundary at 50ms."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(50.0)
        assert "yellow" in result.lower()  # Should be acceptable, not fast

    def test_format_latency_boundary_200ms(self):
        """Test latency boundary at 200ms."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(200.0)
        assert "red" in result.lower()  # Should be slow, not acceptable

    def test_format_latency_boundary_1000ms(self):
        """Test latency boundary at 1000ms."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(1000.0)
        assert "red" in result.lower()
        assert "s" in result  # Should be formatted in seconds


class TestRenderMetricsSummary:
    """Tests for render_metrics_summary() method."""

    def test_metrics_summary_with_all_fields(self):
        """Test metrics summary with all fields present."""
        dashboard = MCPDashboard()
        metrics = {
            "request_count": 150,
            "error_rate": 0.02,  # 2%
            "avg_response_time": 85.5,
        }
        result = dashboard.render_metrics_summary(metrics)
        assert "Req: 150" in result
        assert "Err: 2.0%" in result
        assert "Avg: 86" in result  # Rounds to 86ms

    def test_metrics_summary_high_error_rate(self):
        """Test metrics summary with high error rate."""
        dashboard = MCPDashboard()
        metrics = {
            "request_count": 100,
            "error_rate": 0.15,  # 15%
            "avg_response_time": 50.0,
        }
        result = dashboard.render_metrics_summary(metrics)
        assert "red" in result.lower()
        assert "15.0%" in result

    def test_metrics_summary_medium_error_rate(self):
        """Test metrics summary with medium error rate."""
        dashboard = MCPDashboard()
        metrics = {
            "request_count": 100,
            "error_rate": 0.08,  # 8%
            "avg_response_time": 50.0,
        }
        result = dashboard.render_metrics_summary(metrics)
        assert "yellow" in result.lower()

    def test_metrics_summary_low_error_rate(self):
        """Test metrics summary with low error rate."""
        dashboard = MCPDashboard()
        metrics = {
            "request_count": 100,
            "error_rate": 0.02,  # 2%
            "avg_response_time": 50.0,
        }
        result = dashboard.render_metrics_summary(metrics)
        assert "green" in result.lower()

    def test_metrics_summary_none(self):
        """Test metrics summary with None metrics."""
        dashboard = MCPDashboard()
        result = dashboard.render_metrics_summary(None)
        assert result == "No metrics"

    def test_metrics_summary_empty_dict(self):
        """Test metrics summary with empty dict."""
        dashboard = MCPDashboard()
        result = dashboard.render_metrics_summary({})
        assert result == "No metrics"  # Empty dict returns no metrics message

    def test_metrics_summary_partial_fields(self):
        """Test metrics summary with only some fields."""
        dashboard = MCPDashboard()
        metrics = {"request_count": 50}
        result = dashboard.render_metrics_summary(metrics)
        assert "Req: 50" in result
        assert "No data" in result or "Req: 50" in result

    def test_metrics_summary_only_error_rate(self):
        """Test metrics summary with only error rate."""
        dashboard = MCPDashboard()
        metrics = {"error_rate": 0.05}
        result = dashboard.render_metrics_summary(metrics)
        assert "Err: 5.0%" in result

    def test_metrics_summary_zero_error_rate(self):
        """Test metrics summary with zero error rate."""
        dashboard = MCPDashboard()
        metrics = {"error_rate": 0.0}
        result = dashboard.render_metrics_summary(metrics)
        assert "green" in result.lower()
        assert "0.0%" in result


class TestPrintDashboard:
    """Tests for print_dashboard() method."""

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_print_dashboard_calls_console_print(self, mock_get_manager):
        """Test that print_dashboard calls console.print()."""
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        dashboard._console = MagicMock()
        dashboard.print_dashboard()

        # Should call print twice (once for table, once for spacing)
        assert dashboard._console.print.call_count == 2

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_print_dashboard_integration(self, mock_get_manager):
        """Test print_dashboard with actual console (integration test)."""
        server = Mock()
        server.id = "test-1"
        server.name = "test-server"
        server.type = "stdio"
        server.state = ServerState.RUNNING
        server.health = {"is_healthy": True}
        server.start_time = datetime.now() - timedelta(hours=1)
        server.latency_ms = 50.0

        mock_manager = Mock()
        mock_manager.list_servers.return_value = [server]
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        # Should not raise any exceptions
        dashboard.print_dashboard()


class TestGetDashboardString:
    """Tests for get_dashboard_string() method."""

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_get_dashboard_string_returns_string(self, mock_get_manager):
        """Test that get_dashboard_string returns a string."""
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        result = dashboard.get_dashboard_string()

        assert isinstance(result, str)
        assert len(result) > 0

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_get_dashboard_string_contains_title(self, mock_get_manager):
        """Test that dashboard string contains title."""
        mock_manager = Mock()
        mock_manager.list_servers.return_value = []
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        result = dashboard.get_dashboard_string()

        assert "MCP Server Status Dashboard" in result

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_get_dashboard_string_with_servers(self, mock_get_manager):
        """Test dashboard string with servers."""
        server = Mock()
        server.id = "test-1"
        server.name = "test-server"
        server.type = "stdio"
        server.state = ServerState.RUNNING
        server.health = {"is_healthy": True}
        server.start_time = datetime.now() - timedelta(hours=1)
        server.latency_ms = 50.0

        mock_manager = Mock()
        mock_manager.list_servers.return_value = [server]
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        result = dashboard.get_dashboard_string()

        assert "test-server" in result
        assert "MCP Server Status Dashboard" in result


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_server_with_very_long_name(self, mock_get_manager):
        """Test server with very long name."""
        server = Mock()
        server.id = "server-1"
        server.name = "a" * 200  # Very long name
        server.type = "stdio"
        server.state = ServerState.RUNNING
        server.health = {"is_healthy": True}
        server.start_time = datetime.now() - timedelta(hours=1)
        server.latency_ms = 50.0

        mock_manager = Mock()
        mock_manager.list_servers.return_value = [server]
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        assert isinstance(table, Table)
        assert len(table.rows) == 1

    def test_format_latency_with_float_precision(self):
        """Test format_latency with high precision floats."""
        dashboard = MCPDashboard()
        result = dashboard.format_latency(99.99999)
        assert "99" in result or "100" in result

    def test_format_uptime_with_very_long_duration(self):
        """Test format_uptime with very long duration."""
        dashboard = MCPDashboard()
        start_time = datetime.now() - timedelta(days=365)
        result = dashboard.format_uptime(start_time)
        assert "365d" in result or "d" in result

    @patch("code_puppy.mcp_.dashboard.get_mcp_manager")
    def test_multiple_servers_with_different_states(self, mock_get_manager):
        """Test dashboard with servers in all different states."""
        servers = []
        states = [
            ServerState.RUNNING,
            ServerState.STOPPED,
            ServerState.ERROR,
            ServerState.STARTING,
            ServerState.STOPPING,
            ServerState.QUARANTINED,
        ]

        for idx, state in enumerate(states):
            server = Mock()
            server.id = f"server-{idx}"
            server.name = f"server-{idx}"
            server.type = "stdio"
            server.state = state
            server.health = {"is_healthy": state == ServerState.RUNNING}
            server.start_time = datetime.now() - timedelta(hours=1)
            server.latency_ms = 50.0
            servers.append(server)

        mock_manager = Mock()
        mock_manager.list_servers.return_value = servers
        mock_get_manager.return_value = mock_manager

        dashboard = MCPDashboard()
        table = dashboard.render_dashboard()

        assert len(table.rows) == len(servers)

    def test_health_indicator_with_various_error_messages(self):
        """Test health indicator with various error messages."""
        dashboard = MCPDashboard()

        error_messages = [
            "Connection timeout",
            "Port already in use",
            "Authentication failed",
            "",  # Empty error
        ]

        for error_msg in error_messages:
            health = {"is_healthy": False, "error": error_msg}
            indicator = dashboard.render_health_indicator(health)
            assert indicator is not None
            assert isinstance(indicator, str)
