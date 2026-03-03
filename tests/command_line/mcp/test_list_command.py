"""Tests for MCP list command."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.mcp_.managed_server import ServerState


@pytest.fixture
def list_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.list_command import ListCommand

        cmd = ListCommand()
        return cmd


def _make_server(
    name="srv",
    type_="stdio",
    state=ServerState.RUNNING,
    enabled=True,
    uptime=120.0,
    error_message=None,
    quarantined=False,
):
    s = MagicMock()
    s.name = name
    s.type = type_
    s.state = state
    s.enabled = enabled
    s.uptime_seconds = uptime
    s.error_message = error_message
    s.quarantined = quarantined
    return s


class TestListCommand:
    def test_generates_group_id(self, list_cmd):
        with patch("code_puppy.command_line.mcp.list_command.emit_info"):
            list_cmd.manager.list_servers.return_value = []
            list_cmd.execute([])  # no group_id

    def test_no_servers(self, list_cmd):
        list_cmd.manager.list_servers.return_value = []
        with patch("code_puppy.command_line.mcp.list_command.emit_info") as mock_emit:
            list_cmd.execute([], group_id="g1")
            assert "No MCP servers registered" in str(mock_emit.call_args)

    def test_servers_displayed(self, list_cmd):
        list_cmd.manager.list_servers.return_value = [
            _make_server("a", state=ServerState.RUNNING, enabled=True),
            _make_server(
                "b", state=ServerState.STOPPED, enabled=False, error_message="err"
            ),
            _make_server(
                "c", state=ServerState.RUNNING, enabled=True, quarantined=True
            ),
        ]
        with patch("code_puppy.command_line.mcp.list_command.emit_info") as mock_emit:
            list_cmd.execute([], group_id="g1")
            # Table + summary = at least 2 calls
            assert mock_emit.call_count >= 2

    def test_disabled_server(self, list_cmd):
        list_cmd.manager.list_servers.return_value = [
            _make_server("x", enabled=False, state=ServerState.STOPPED),
        ]
        with patch("code_puppy.command_line.mcp.list_command.emit_info"):
            list_cmd.execute([], group_id="g1")

    def test_exception(self, list_cmd):
        list_cmd.manager.list_servers.side_effect = RuntimeError("boom")
        with patch("code_puppy.command_line.mcp.list_command.emit_error") as mock_err:
            list_cmd.execute([], group_id="g1")
            assert "boom" in str(mock_err.call_args)
