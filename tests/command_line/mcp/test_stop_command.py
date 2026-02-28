"""Tests for MCP stop command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def stop_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.stop_command import StopCommand

        return StopCommand()


class TestStopCommand:
    def test_no_args_shows_usage(self, stop_cmd):
        with patch("code_puppy.command_line.mcp.stop_command.emit_info") as mock_emit:
            stop_cmd.execute([], group_id="g1")
            assert mock_emit.called

    def test_generates_group_id(self, stop_cmd):
        with patch("code_puppy.command_line.mcp.stop_command.emit_info"):
            stop_cmd.execute([])

    def test_server_not_found(self, stop_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value=None,
            ),
            patch("code_puppy.command_line.mcp.stop_command.suggest_similar_servers"),
            patch("code_puppy.command_line.mcp.stop_command.emit_info") as mock_emit,
        ):
            stop_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_stop_success(self, stop_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.stop_command.emit_info") as mock_emit,
            patch(
                "code_puppy.command_line.mcp.stop_command.get_current_agent"
            ) as mock_agent,
        ):
            stop_cmd.manager.stop_server_sync.return_value = True
            stop_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Stopped" in c for c in calls)
            mock_agent.return_value.reload_code_generation_agent.assert_called_once()

    def test_stop_success_agent_reload_fails(self, stop_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.stop_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.stop_command.get_current_agent",
                side_effect=Exception("no agent"),
            ),
        ):
            stop_cmd.manager.stop_server_sync.return_value = True
            stop_cmd.execute(["myserver"], group_id="g1")

    def test_stop_failure(self, stop_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.stop_command.emit_info") as mock_emit,
        ):
            stop_cmd.manager.stop_server_sync.return_value = False
            stop_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Failed" in c for c in calls)

    def test_outer_exception(self, stop_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.command_line.mcp.stop_command.emit_error") as mock_err,
        ):
            stop_cmd.execute(["myserver"], group_id="g1")
            mock_err.assert_called_once()
