"""Tests for MCP start-all command."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.managed_server import ServerState


@pytest.fixture
def start_all_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.start_all_command import StartAllCommand

        return StartAllCommand()


def _make_server(name, state, server_id=None):
    s = MagicMock()
    s.name = name
    s.id = server_id or f"id-{name}"
    s.state = state
    return s


class TestStartAllCommand:
    def test_no_servers(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = []
        with patch(
            "code_puppy.command_line.mcp.start_all_command.emit_info"
        ) as mock_emit:
            start_all_cmd.execute([], group_id="g1")
            assert mock_emit.called

    def test_generates_group_id(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = []
        with patch("code_puppy.command_line.mcp.start_all_command.emit_info"):
            start_all_cmd.execute([])

    def test_all_already_running(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
        ]
        with patch(
            "code_puppy.command_line.mcp.start_all_command.emit_info"
        ) as mock_emit:
            start_all_cmd.execute([], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("already running" in c for c in calls)

    def test_start_success(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.STOPPED),
        ]
        start_all_cmd.manager.start_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.start_all_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.start_all_command.get_current_agent"
            ) as mock_agent,
        ):
            start_all_cmd.execute([], group_id="g1")
            start_all_cmd.manager.start_server_sync.assert_called_once()
            mock_agent.return_value.reload_code_generation_agent.assert_called_once()

    def test_start_failure(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.STOPPED),
        ]
        start_all_cmd.manager.start_server_sync.return_value = False
        with patch(
            "code_puppy.command_line.mcp.start_all_command.emit_info"
        ) as mock_emit:
            start_all_cmd.execute([], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Failed" in c for c in calls)

    def test_mixed_results(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.RUNNING),
            _make_server("s2", ServerState.STOPPED),
            _make_server("s3", ServerState.STOPPED),
        ]
        start_all_cmd.manager.start_server_sync.side_effect = [True, False]
        with (
            patch("code_puppy.command_line.mcp.start_all_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_all_command.get_current_agent"),
        ):
            start_all_cmd.execute([], group_id="g1")

    def test_agent_reload_fails(self, start_all_cmd):
        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.STOPPED),
        ]
        start_all_cmd.manager.start_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.start_all_command.emit_info"),
            patch(
                "code_puppy.command_line.mcp.start_all_command.get_current_agent",
                side_effect=Exception("no agent"),
            ),
        ):
            start_all_cmd.execute([], group_id="g1")  # should not raise

    def test_outer_exception(self, start_all_cmd):
        start_all_cmd.manager.list_servers.side_effect = Exception("boom")
        with patch(
            "code_puppy.command_line.mcp.start_all_command.emit_info"
        ) as mock_emit:
            start_all_cmd.execute([], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Failed to start" in c for c in calls)

    def test_async_loop_exists(self, start_all_cmd):
        """Test the asyncio.get_running_loop() path."""

        start_all_cmd.manager.list_servers.return_value = [
            _make_server("s1", ServerState.STOPPED),
        ]
        start_all_cmd.manager.start_server_sync.return_value = True
        with (
            patch("code_puppy.command_line.mcp.start_all_command.emit_info"),
            patch("code_puppy.command_line.mcp.start_all_command.get_current_agent"),
            patch("time.sleep"),
            patch("asyncio.get_running_loop", return_value=MagicMock()),
        ):
            start_all_cmd.execute([], group_id="g1")
