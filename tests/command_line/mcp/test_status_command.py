"""Tests for MCP status command."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def status_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.status_command import StatusCommand

        return StatusCommand()


class TestStatusCommand:
    def test_generates_group_id(self, status_cmd):
        with (
            patch("code_puppy.command_line.mcp.list_command.emit_info"),
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
        ):
            status_cmd.manager.list_servers.return_value = []
            status_cmd.execute([])

    def test_no_args_delegates_to_list(self, status_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.list_command.emit_info"
            ) as mock_list_emit,
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
        ):
            status_cmd.manager.list_servers.return_value = []
            status_cmd.execute([], group_id="g1")
            assert mock_list_emit.called

    def test_server_not_found(self, status_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value=None,
            ),
            patch("code_puppy.command_line.mcp.status_command.suggest_similar_servers"),
            patch("code_puppy.command_line.mcp.status_command.emit_info") as mock_emit,
        ):
            status_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_detailed_status_basic(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "tracker_uptime": 3600.0,
            "error_message": None,
            "recent_events_count": 5,
            "tracker_metadata": {"key": "val"},
            "recent_events": [],
        }
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info") as mock_emit,
            patch("code_puppy.command_line.mcp.status_command.emit_error"),
            patch("code_puppy.mcp_.async_lifecycle.get_lifecycle_manager") as mock_lm,
        ):
            mock_lm.return_value.is_running.return_value = True
            status_cmd.execute(["myserver"], group_id="g1")
            assert mock_emit.called

    def test_detailed_status_not_exists(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {"exists": False}
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info") as mock_emit,
        ):
            status_cmd.execute(["myserver"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_detailed_status_quarantined_with_error(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {
            "exists": True,
            "type": "sse",
            "state": "error",
            "enabled": False,
            "quarantined": True,
            "tracker_uptime": None,
            "error_message": "connection refused",
            "recent_events_count": 0,
            "tracker_metadata": {},
            "recent_events": [],
        }
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
            patch("code_puppy.command_line.mcp.status_command.emit_error"),
            patch(
                "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager",
                side_effect=Exception("nope"),
            ),
        ):
            status_cmd.execute(["myserver"], group_id="g1")

    def test_detailed_status_with_timedelta_uptime(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "tracker_uptime": timedelta(hours=2, minutes=30),
            "error_message": None,
            "recent_events_count": 0,
            "tracker_metadata": {},
            "recent_events": [],
        }
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
            patch("code_puppy.command_line.mcp.status_command.emit_error"),
            patch("code_puppy.mcp_.async_lifecycle.get_lifecycle_manager") as mock_lm,
        ):
            mock_lm.return_value.is_running.return_value = False
            status_cmd.execute(["myserver"], group_id="g1")

    def test_detailed_status_with_recent_events(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {
            "exists": True,
            "type": "stdio",
            "state": "running",
            "enabled": True,
            "quarantined": False,
            "tracker_uptime": 60.0,
            "error_message": None,
            "recent_events_count": 2,
            "tracker_metadata": {},
            "recent_events": [
                {"timestamp": "2024-01-01T10:00:00", "message": "started"},
                {"timestamp": "2024-01-01T10:05:00", "message": "connected"},
            ],
        }
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info") as mock_emit,
            patch("code_puppy.command_line.mcp.status_command.emit_error"),
            patch("code_puppy.mcp_.async_lifecycle.get_lifecycle_manager") as mock_lm,
        ):
            mock_lm.return_value.is_running.return_value = True
            status_cmd.execute(["myserver"], group_id="g1")
            # Should show recent events
            assert any("Recent Events" in str(c) for c in mock_emit.call_args_list)

    def test_detailed_status_unknown_state(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {
            "exists": True,
            "type": "stdio",
            "state": "some_unknown_state",
            "enabled": True,
            "quarantined": False,
            "tracker_uptime": None,
            "error_message": None,
            "recent_events_count": 0,
            "tracker_metadata": {},
            "recent_events": [],
        }
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
            patch("code_puppy.command_line.mcp.status_command.emit_error"),
            patch(
                "code_puppy.mcp_.async_lifecycle.get_lifecycle_manager",
                side_effect=Exception,
            ),
        ):
            status_cmd.execute(["myserver"], group_id="g1")

    def test_detailed_status_exception(self, status_cmd):
        status_cmd.manager.get_server_status.side_effect = RuntimeError("boom")
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
            patch("code_puppy.command_line.mcp.status_command.emit_error") as mock_err,
        ):
            status_cmd.execute(["myserver"], group_id="g1")
            assert "boom" in str(mock_err.call_args)

    def test_execute_exception(self, status_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.status_command.find_server_id_by_name",
                side_effect=RuntimeError("fail"),
            ),
            patch("code_puppy.command_line.mcp.status_command.emit_info") as mock_emit,
        ):
            status_cmd.execute(["srv"], group_id="g1")
            assert any(
                "Failed to get server status" in str(c)
                for c in mock_emit.call_args_list
            )

    def test_detailed_generates_group_id(self, status_cmd):
        status_cmd.manager.get_server_status.return_value = {"exists": False}
        with (
            patch("code_puppy.command_line.mcp.status_command.emit_info"),
        ):
            status_cmd._show_detailed_server_status("id1", "srv")
