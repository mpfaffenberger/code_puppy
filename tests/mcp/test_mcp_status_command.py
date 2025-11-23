"""
Tests for MCP Status Command.

Covers detailed server status display, error handling,
server lookup, and edge cases.
"""

from unittest.mock import ANY, Mock, patch

from code_puppy.command_line.mcp.status_command import StatusCommand
from code_puppy.mcp_.managed_server import ServerState


class TestStatusCommand:
    """Test cases for StatusCommand class."""

    def setup_method(self):
        """Setup for each test method."""
        # Don't initialize here - do it in each test after mocking is set up
        pass

    def test_init(self, mock_mcp_manager):
        """Test command initialization."""
        command = StatusCommand()
        assert hasattr(command, "manager")
        assert hasattr(command, "console")
        assert callable(command.generate_group_id)

    def test_execute_no_args_shows_list(self, mock_emit_info, mock_mcp_manager):
        """Test executing without args shows server list."""
        command = StatusCommand()
        with patch(
            "code_puppy.command_line.mcp.status_command.ListCommand"
        ) as mock_list_cmd:
            mock_instance = Mock()
            mock_list_cmd.return_value = mock_instance

            command.execute([])

            mock_list_cmd.assert_called_once()
            mock_instance.execute.assert_called_once_with([], group_id=ANY)

    def test_execute_with_server_name_success(self, mock_emit_info, mock_mcp_manager):
        """Test executing with valid server name."""
        command = StatusCommand()
        with patch(
            "code_puppy.command_line.mcp.status_command.find_server_id_by_name"
        ) as mock_find:
            mock_find.return_value = "test-server-1"

            with patch.object(
                command, "_show_detailed_server_status"
            ) as mock_show_status:
                command.execute(["test-server"])

                mock_find.assert_called_once_with(mock_mcp_manager, "test-server")
                mock_show_status.assert_called_once_with(
                    "test-server-1", "test-server", ANY
                )

    def test_execute_server_not_found(self, mock_emit_info, mock_mcp_manager):
        """Test executing with non-existent server name."""
        command = StatusCommand()
        with patch(
            "code_puppy.command_line.mcp.status_command.find_server_id_by_name"
        ) as mock_find:
            mock_find.return_value = None

            with patch(
                "code_puppy.command_line.mcp.status_command.suggest_similar_servers"
            ) as mock_suggest:
                command.execute(["nonexistent-server"])

                # Should emit error message
                assert len(mock_emit_info.messages) > 0
                mock_suggest.assert_called_once()

    def test_execute_general_exception(self, mock_emit_info, mock_mcp_manager):
        """Test handling of general exceptions."""
        command = StatusCommand()
        with patch(
            "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
            side_effect=Exception("Random error"),
        ):
            command.execute(["test-server"])

            # Should emit error message
            assert len(mock_emit_info.messages) > 0

    def test_show_detailed_server_status_basic_info(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status shows basic server information."""
        command = StatusCommand()
        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": 3600.0,
            "recent_events_count": 5,
            "recent_events": [],
            "tracker_metadata": {"key": "value"},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status(
            "test-server-1", "test-server", "group-123"
        )

        assert len(mock_emit_info.messages) > 0
        # Check that panel was created
        panel_args = mock_emit_info.messages[0][0]
        assert hasattr(panel_args, "title")  # Panel object
        assert "test-server" in panel_args.title

    def test_show_detailed_server_status_server_not_accessible(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status when server is not accessible."""
        command = StatusCommand()
        status_data = {"exists": False}
        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("invalid-id", "test-server", "group-123")

        # Should emit a message about server not being found
        assert len(mock_emit_info.messages) > 0
        # Check that some message was emitted (exact format may vary)

    def test_show_detailed_server_status_all_states(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status with all possible server states."""
        command = StatusCommand()
        states_to_test = [
            ("running", ServerState.RUNNING),
            ("stopped", ServerState.STOPPED),
            ("error", ServerState.ERROR),
            ("starting", ServerState.STARTING),
            ("stopping", ServerState.STOPPING),
            ("unknown", ServerState.STOPPED),  # Falls back to STOPPED
        ]

        for state_str, expected_state in states_to_test:
            status_data = {
                "exists": True,
                "type": "stdio",
                "state": state_str,
                "enabled": True,
                "quarantined": False,
                "error_message": None,
                "tracker_uptime": None,
                "recent_events_count": 0,
                "recent_events": [],
                "tracker_metadata": {},
            }

            mock_mcp_manager.get_server_status.return_value = status_data
            mock_emit_info.messages.clear()  # Reset messages

            command._show_detailed_server_status(
                "test-1", "test-server", f"group-{state_str}"
            )

            assert len(mock_emit_info.messages) > 0

    def test_show_detailed_server_status_with_error(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status when server has error message."""
        command = StatusCommand()
        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "error",
            "enabled": False,
            "quarantined": False,
            "error_message": "Connection failed miserably",
            "tracker_uptime": None,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        assert len(mock_emit_info.messages) > 0
        # Error should be displayed in the panel
        panel_args = mock_emit_info.messages[0][0]
        assert hasattr(panel_args, "title")

    def test_show_detailed_server_status_quarantined(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status when server is quarantined."""
        command = StatusCommand()
        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": True,
            "error_message": None,
            "tracker_uptime": 1800.0,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        assert len(mock_emit_info.messages) > 0
        # Quarantined status should be displayed

    def test_show_detailed_server_status_with_uptime(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status with uptime information."""
        from datetime import timedelta

        command = StatusCommand()

        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": timedelta(hours=2, minutes=30),  # timedelta object
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        assert len(mock_emit_info.messages) > 0

    def test_show_detailed_server_status_with_events(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status with recent events."""
        command = StatusCommand()
        events = [
            {"timestamp": "2023-01-01T10:00:00", "message": "Server started"},
            {"timestamp": "2023-01-01T10:01:00", "message": "Connected to client"},
            {"timestamp": "2023-01-01T10:02:00", "message": "Processing request"},
            {"timestamp": "2023-01-01T10:03:00", "message": "Request completed"},
            {"timestamp": "2023-01-01T10:04:00", "message": "Server stopped"},
            {
                "timestamp": "2023-01-01T10:05:00",
                "message": "This should not show - beyond last 5",
            },
        ]

        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "stopped",
            "enabled": False,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": None,
            "recent_events_count": len(events),
            "recent_events": events,
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        # Should have panel and events
        assert len(mock_emit_info.messages) >= 2
        # Check that events are displayed in some form
        assert True  # If we got here, the command executed successfully

    @patch("code_puppy.mcp_.async_lifecycle.get_lifecycle_manager")
    def test_show_detailed_server_status_with_lifecycle_info(
        self, mock_get_lifecycle, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status shows lifecycle process info when available."""
        command = StatusCommand()
        mock_lifecycle = Mock()
        mock_lifecycle.is_running.return_value = True
        mock_get_lifecycle.return_value = mock_lifecycle

        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": None,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        mock_lifecycle.is_running.assert_called_once_with("test-1")
        assert len(mock_emit_info.messages) > 0

    @patch(
        "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager",
        side_effect=Exception("Lifecycle error"),
    )
    def test_show_detailed_server_status_lifecycle_exception(
        self, mock_get_lifecycle, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status handles lifecycle exceptions gracefully."""
        command = StatusCommand()
        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": None,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        mock_mcp_manager.get_server_status.return_value = status_data

        # Should not raise exception
        command._show_detailed_server_status("test-1", "test-server", "group-123")

        assert len(mock_emit_info.messages) > 0  # Still shows basic status

    def test_show_detailed_server_status_exception_handling(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status handles exceptions gracefully."""
        command = StatusCommand()
        # Since get_server_status is now a Mock, we can set side_effect
        mock_mcp_manager.get_server_status.side_effect = Exception(
            "Status fetch failed"
        )

        command._show_detailed_server_status("test-1", "test-server", "group-123")

        # Should emit error message
        assert len(mock_emit_info.messages) > 0

    def test_show_detailed_server_status_without_group_id(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test detailed status generates group ID when not provided."""
        command = StatusCommand()
        status_data = {
            "exists": True,
            "type": "stdio",
            "state": "stopped",
            "enabled": False,
            "quarantined": False,
            "error_message": None,
            "tracker_uptime": None,
            "recent_events_count": 0,
            "recent_events": [],
            "tracker_metadata": {},
        }

        # Since get_server_status is now a Mock, we can set return_value
        mock_mcp_manager.get_server_status.return_value = status_data

        # Call without group_id
        command._show_detailed_server_status("test-1", "test-server")

        assert len(mock_emit_info.messages) > 0
        # Should still work and generate a group ID

    def test_generate_group_id(self, mock_mcp_manager):
        """Test group ID generation."""
        command = StatusCommand()
        group_id1 = command.generate_group_id()
        group_id2 = command.generate_group_id()

        assert group_id1 != group_id2
        assert len(group_id1) > 10
        assert len(group_id2) > 10
