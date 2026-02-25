"""Tests for MCP stop-all command."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.managed_server import ServerState


@pytest.fixture
def stop_all_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.stop_all_command import StopAllCommand

        return StopAllCommand()


def _make_server(name, state):
    s = MagicMock()
    s.name = name
    s.id = f"id-{name}"
    s.state = state
    return s


class TestStopAllCommand:
    def test_no_servers(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = []
        with patch(
            "code_puppy.command_line.mcp.stop_all_command.emit_info"
        ) as mock_emit:
            stop_all_cmd.execute([], group_id="g1")
            assert "No servers registered" in str(mock_emit.call_args)

    def test_generates_group_id(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = []
        with patch("code_puppy.command_line.mcp.stop_all_command.emit_info"):
            stop_all_cmd.execute([])

    def test_no_running_servers(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.STOPPED),
        ]
        with patch(
            "code_puppy.command_line.mcp.stop_all_command.emit_info"
        ) as mock_emit:
            stop_all_cmd.execute([], group_id="g1")
            assert "No servers are currently running" in str(mock_emit.call_args)

    def test_stop_success(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
        ]
        stop_all_cmd.manager.stop_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.stop_all_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.stop_all_command.get_current_agent"
            ) as mock_agent,
        ):
            stop_all_cmd.execute([], group_id="g1")
            stop_all_cmd.manager.stop_server_sync.assert_called_once()
            mock_agent.return_value.reload_code_generation_agent.assert_called_once()

    def test_stop_failure(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
        ]
        stop_all_cmd.manager.stop_server_sync.return_value = False
        with patch(
            "code_puppy.command_line.mcp.stop_all_command.emit_info"
        ) as mock_emit:
            stop_all_cmd.execute([], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Failed" in c for c in calls)

    def test_agent_reload_fails(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
        ]
        stop_all_cmd.manager.stop_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.stop_all_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.stop_all_command.get_current_agent",
                side_effect=Exception("no agent"),
            ),
        ):
            stop_all_cmd.execute([], group_id="g1")

    def test_outer_exception(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.side_effect = Exception("boom")
        with patch(
            "code_puppy.command_line.mcp.stop_all_command.emit_info"
        ) as mock_emit:
            stop_all_cmd.execute([], group_id="g1")
            assert "Failed to stop" in str(mock_emit.call_args)

    def test_async_loop_exists(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
        ]
        stop_all_cmd.manager.stop_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.stop_all_command.emit_info"),
            patch("code_puppy.command_line.mcp.stop_all_command.get_current_agent"),
            patch("time.sleep"),
            patch("asyncio.get_running_loop", return_value=MagicMock()),
        ):
            stop_all_cmd.execute([], group_id="g1")

    def test_mixed_stop_results(self, stop_all_cmd):
        stop_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
            _make_server("s2", ServerState.RUNNING),
        ]
        stop_all_cmd.manager.stop_server_sync.side_effect = [True, False]
        with (
            patch("code_puppy.command_line.mcp.stop_all_command.emit_info"),
            patch("code_puppy.command_line.mcp.stop_all_command.get_current_agent"),
        ):
            stop_all_cmd.execute([], group_id="g1")
