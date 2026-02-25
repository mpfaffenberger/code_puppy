"""Tests for MCP command utilities.

Covers format_state_indicator, format_uptime, find_server_id_by_name,
and suggest_similar_servers functions.
"""

from unittest.mock import MagicMock, patch

from rich.text import Text

from code_puppy.command_line.mcp.utils import (
    find_server_id_by_name,
    format_state_indicator,
    format_uptime,
    suggest_similar_servers,
)
from code_puppy.mcp_.managed_server import ServerState

# =============================================================================
# Tests for format_state_indicator
# =============================================================================


class TestFormatStateIndicator:
    """Tests for format_state_indicator function."""

    def test_running_state(self):
        """Test RUNNING state returns green checkmark."""
        result = format_state_indicator(ServerState.RUNNING)
        assert isinstance(result, Text)
        assert "Run" in result.plain
        assert "✓" in result.plain

    def test_stopped_state(self):
        """Test STOPPED state returns red X."""
        result = format_state_indicator(ServerState.STOPPED)
        assert isinstance(result, Text)
        assert "Stop" in result.plain
        assert "✗" in result.plain

    def test_starting_state(self):
        """Test STARTING state returns yellow arrow."""
        result = format_state_indicator(ServerState.STARTING)
        assert isinstance(result, Text)
        assert "Start" in result.plain
        assert "↗" in result.plain

    def test_stopping_state(self):
        """Test STOPPING state returns yellow arrow."""
        result = format_state_indicator(ServerState.STOPPING)
        assert isinstance(result, Text)
        assert "Stop" in result.plain
        assert "↙" in result.plain

    def test_error_state(self):
        """Test ERROR state returns red warning."""
        result = format_state_indicator(ServerState.ERROR)
        assert isinstance(result, Text)
        assert "Err" in result.plain
        assert "⚠" in result.plain

    def test_quarantined_state(self):
        """Test QUARANTINED state returns yellow pause."""
        result = format_state_indicator(ServerState.QUARANTINED)
        assert isinstance(result, Text)
        assert "Quar" in result.plain
        assert "⏸" in result.plain

    def test_unknown_state_fallback(self):
        """Test unknown state falls back to dim unknown indicator."""
        # Create a mock state that isn't in the map
        mock_state = MagicMock()
        result = format_state_indicator(mock_state)
        assert isinstance(result, Text)
        assert "Unk" in result.plain
        assert "?" in result.plain


# =============================================================================
# Tests for format_uptime
# =============================================================================


class TestFormatUptime:
    """Tests for format_uptime function."""

    def test_none_uptime(self):
        """Test None uptime returns dash."""
        assert format_uptime(None) == "-"

    def test_zero_uptime(self):
        """Test zero uptime returns dash."""
        assert format_uptime(0) == "-"

    def test_negative_uptime(self):
        """Test negative uptime returns dash."""
        assert format_uptime(-10) == "-"

    def test_seconds_only(self):
        """Test uptime less than 60 seconds shows seconds."""
        assert format_uptime(30) == "30s"
        assert format_uptime(1) == "1s"
        assert format_uptime(59) == "59s"

    def test_seconds_with_decimals(self):
        """Test uptime with decimal seconds truncates to int."""
        assert format_uptime(30.7) == "30s"
        assert format_uptime(45.9) == "45s"

    def test_minutes_and_seconds(self):
        """Test uptime between 1 minute and 1 hour shows minutes and seconds."""
        assert format_uptime(60) == "1m 0s"
        assert format_uptime(90) == "1m 30s"
        assert format_uptime(125) == "2m 5s"
        assert format_uptime(3599) == "59m 59s"

    def test_hours_and_minutes(self):
        """Test uptime >= 1 hour shows hours and minutes."""
        assert format_uptime(3600) == "1h 0m"
        assert format_uptime(3660) == "1h 1m"
        assert format_uptime(7200) == "2h 0m"
        assert format_uptime(7320) == "2h 2m"
        assert format_uptime(86400) == "24h 0m"  # 1 day


# =============================================================================
# Tests for find_server_id_by_name
# =============================================================================


class TestFindServerIdByName:
    """Tests for find_server_id_by_name function."""

    def test_find_exact_match(self):
        """Test finding server with exact name match."""
        mock_server = MagicMock()
        mock_server.name = "MyServer"
        mock_server.id = "server-123"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [mock_server]

        result = find_server_id_by_name(mock_manager, "MyServer")
        assert result == "server-123"

    def test_find_case_insensitive_match(self):
        """Test finding server with case-insensitive name match."""
        mock_server = MagicMock()
        mock_server.name = "MyServer"
        mock_server.id = "server-456"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [mock_server]

        # Test lowercase
        assert find_server_id_by_name(mock_manager, "myserver") == "server-456"
        # Test uppercase
        assert find_server_id_by_name(mock_manager, "MYSERVER") == "server-456"
        # Test mixed case
        assert find_server_id_by_name(mock_manager, "mYsErVeR") == "server-456"

    def test_server_not_found(self):
        """Test returns None when server not found."""
        mock_server = MagicMock()
        mock_server.name = "ExistingServer"
        mock_server.id = "server-789"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [mock_server]

        result = find_server_id_by_name(mock_manager, "NonExistent")
        assert result is None

    def test_empty_server_list(self):
        """Test returns None when no servers registered."""
        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = []

        result = find_server_id_by_name(mock_manager, "AnyServer")
        assert result is None

    def test_multiple_servers_finds_correct_one(self):
        """Test finding correct server among multiple."""
        server1 = MagicMock(name="Server1", id="id-1")
        server1.name = "Server1"
        server1.id = "id-1"

        server2 = MagicMock(name="Server2", id="id-2")
        server2.name = "Server2"
        server2.id = "id-2"

        server3 = MagicMock(name="Server3", id="id-3")
        server3.name = "Server3"
        server3.id = "id-3"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [server1, server2, server3]

        assert find_server_id_by_name(mock_manager, "Server2") == "id-2"

    def test_exception_returns_none(self):
        """Test returns None and logs error when exception occurs."""
        mock_manager = MagicMock()
        mock_manager.list_servers.side_effect = Exception("Connection failed")

        mock_logger = MagicMock()
        with patch("logging.getLogger", return_value=mock_logger):
            result = find_server_id_by_name(mock_manager, "AnyServer")

            assert result is None
            mock_logger.error.assert_called_once()
            assert "AnyServer" in str(mock_logger.error.call_args)


# =============================================================================
# Tests for suggest_similar_servers
# =============================================================================


class TestSuggestSimilarServers:
    """Tests for suggest_similar_servers function."""

    def test_no_servers_registered(self):
        """Test emits message when no servers registered."""
        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = []

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            suggest_similar_servers(mock_manager, "AnyServer")

            mock_emit.assert_called_once()
            args, kwargs = mock_emit.call_args
            assert "No servers are registered" in args[0]

    def test_partial_match_suggestion(self):
        """Test suggests servers with partial name match."""
        server1 = MagicMock()
        server1.name = "my-api-server"

        server2 = MagicMock()
        server2.name = "api-backend"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [server1, server2]

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            suggest_similar_servers(mock_manager, "api")

            mock_emit.assert_called_once()
            args, kwargs = mock_emit.call_args
            assert "Did you mean" in args[0]
            assert "my-api-server" in args[0]
            assert "api-backend" in args[0]

    def test_no_partial_match_shows_all(self):
        """Test shows all available servers when no partial match."""
        server1 = MagicMock()
        server1.name = "alpha-server"

        server2 = MagicMock()
        server2.name = "beta-server"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [server1, server2]

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            suggest_similar_servers(mock_manager, "gamma")

            mock_emit.assert_called_once()
            args, kwargs = mock_emit.call_args
            assert "Available servers" in args[0]
            assert "alpha-server" in args[0]
            assert "beta-server" in args[0]

    def test_case_insensitive_partial_match(self):
        """Test partial matching is case insensitive."""
        server = MagicMock()
        server.name = "MyAPIServer"

        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = [server]

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            suggest_similar_servers(mock_manager, "api")

            mock_emit.assert_called_once()
            args, kwargs = mock_emit.call_args
            assert "Did you mean" in args[0]
            assert "MyAPIServer" in args[0]

    def test_group_id_passed_through(self):
        """Test message_group is passed to emit_info."""
        mock_manager = MagicMock()
        mock_manager.list_servers.return_value = []

        with patch("code_puppy.messaging.emit_info") as mock_emit:
            suggest_similar_servers(mock_manager, "test", group_id="group-123")

            mock_emit.assert_called_once()
            args, kwargs = mock_emit.call_args
            assert kwargs.get("message_group") == "group-123"

    def test_exception_logs_error(self):
        """Test exception is caught and logged."""
        mock_manager = MagicMock()
        mock_manager.list_servers.side_effect = Exception("Database error")

        mock_logger = MagicMock()
        with patch("logging.getLogger", return_value=mock_logger):
            # Should not raise
            suggest_similar_servers(mock_manager, "test")

            mock_logger.error.assert_called_once()
            assert "suggesting similar servers" in str(mock_logger.error.call_args)
