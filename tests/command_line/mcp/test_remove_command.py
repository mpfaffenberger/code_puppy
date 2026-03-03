"""Tests for MCP remove command."""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest


@pytest.fixture
def remove_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.remove_command import RemoveCommand

        return RemoveCommand()


class TestRemoveCommand:
    def test_no_args_shows_usage(self, remove_cmd):
        with patch("code_puppy.command_line.mcp.remove_command.emit_info") as mock_emit:
            remove_cmd.execute([], group_id="g1")
            assert "Usage" in str(mock_emit.call_args)

    def test_generates_group_id(self, remove_cmd):
        with patch("code_puppy.command_line.mcp.remove_command.emit_info"):
            remove_cmd.execute([])

    def test_server_not_found(self, remove_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value=None,
            ),
            patch("code_puppy.command_line.mcp.remove_command.suggest_similar_servers"),
            patch("code_puppy.command_line.mcp.remove_command.emit_info") as mock_emit,
        ):
            remove_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_remove_success_with_config_file(self, remove_cmd):
        data = {"mcp_servers": {"myserver": {"type": "stdio"}}}
        m = mock_open(read_data=json.dumps(data))
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_info") as mock_emit,
            patch("os.path.exists", return_value=True),
            patch("builtins.open", m),
        ):
            remove_cmd.manager.remove_server.return_value = True
            remove_cmd.execute(["myserver"], group_id="g1")
            assert any("Removed" in str(c) for c in mock_emit.call_args_list)

    def test_remove_success_no_config_file(self, remove_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_info"),
            patch("os.path.exists", return_value=False),
        ):
            remove_cmd.manager.remove_server.return_value = True
            remove_cmd.execute(["myserver"], group_id="g1")

    def test_remove_success_config_update_fails(self, remove_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_info"),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=Exception("write error")),
        ):
            remove_cmd.manager.remove_server.return_value = True
            remove_cmd.execute(["myserver"], group_id="g1")  # should not raise

    def test_remove_failure(self, remove_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_info") as mock_emit,
        ):
            remove_cmd.manager.remove_server.return_value = False
            remove_cmd.execute(["myserver"], group_id="g1")
            assert any("Failed" in str(c) for c in mock_emit.call_args_list)

    def test_outer_exception(self, remove_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_error") as mock_err,
        ):
            remove_cmd.execute(["myserver"], group_id="g1")
            mock_err.assert_called_once()

    def test_remove_server_not_in_config(self, remove_cmd):
        """Server removed from manager but not present in config file."""
        data = {"mcp_servers": {"other": {"type": "stdio"}}}
        m = mock_open(read_data=json.dumps(data))
        with (
            patch(
                "code_puppy.command_line.mcp.remove_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.remove_command.emit_info"),
            patch("os.path.exists", return_value=True),
            patch("builtins.open", m),
        ):
            remove_cmd.manager.remove_server.return_value = True
            remove_cmd.execute(["myserver"], group_id="g1")
