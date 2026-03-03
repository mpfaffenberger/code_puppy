"""Tests for MCP restart command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def restart_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.restart_command import RestartCommand

        return RestartCommand()


class TestRestartCommand:
    def test_no_args_shows_usage(self, restart_cmd):
        with patch(
            "code_puppy.command_line.mcp.restart_command.emit_info"
        ) as mock_emit:
            restart_cmd.execute([], group_id="g1")
            assert "Usage" in str(mock_emit.call_args)

    def test_generates_group_id(self, restart_cmd):
        with patch("code_puppy.command_line.mcp.restart_command.emit_info"):
            restart_cmd.execute([])

    def test_server_not_found(self, restart_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value=None,
            ),
            patch(
                "code_puppy.command_line.mcp.restart_command.suggest_similar_servers"
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info") as mock_emit,
        ):
            restart_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_full_restart_success(self, restart_cmd):
        restart_cmd.manager.reload_server.return_value = True
        restart_cmd.manager.start_server_sync.return_value = True
        mock_agent = MagicMock()
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info") as mock_emit,
            patch("code_puppy.agents.get_current_agent", return_value=mock_agent),
        ):
            restart_cmd.execute(["myserver"], group_id="g1")
            restart_cmd.manager.stop_server_sync.assert_called_once_with("id1")
            restart_cmd.manager.reload_server.assert_called_once_with("id1")
            restart_cmd.manager.start_server_sync.assert_called_once_with("id1")
            mock_agent.reload_code_generation_agent.assert_called_once()
            mock_agent.update_mcp_tool_cache_sync.assert_called_once()
            # Check that success message was emitted
            assert any("Restarted" in str(c) for c in mock_emit.call_args_list)

    def test_restart_agent_reload_fails(self, restart_cmd):
        restart_cmd.manager.reload_server.return_value = True
        restart_cmd.manager.start_server_sync.return_value = True
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info"),
            patch(
                "code_puppy.agents.get_current_agent", side_effect=Exception("no agent")
            ),
        ):
            # Should not raise - just logs warning
            restart_cmd.execute(["myserver"], group_id="g1")

    def test_start_fails_after_reload(self, restart_cmd):
        restart_cmd.manager.reload_server.return_value = True
        restart_cmd.manager.start_server_sync.return_value = False
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info") as mock_emit,
        ):
            restart_cmd.execute(["myserver"], group_id="g1")
            assert any("Failed to start" in str(c) for c in mock_emit.call_args_list)

    def test_reload_fails(self, restart_cmd):
        restart_cmd.manager.reload_server.return_value = False
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info") as mock_emit,
        ):
            restart_cmd.execute(["myserver"], group_id="g1")
            assert any("Failed to reload" in str(c) for c in mock_emit.call_args_list)

    def test_exception(self, restart_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                side_effect=RuntimeError("boom"),
            ),
            patch("code_puppy.command_line.mcp.restart_command.emit_info") as mock_emit,
        ):
            restart_cmd.execute(["srv"], group_id="g1")
            assert any("Failed to restart" in str(c) for c in mock_emit.call_args_list)
