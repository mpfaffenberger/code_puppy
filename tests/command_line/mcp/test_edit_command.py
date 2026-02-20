"""Tests for MCP edit command."""

import json
from unittest.mock import MagicMock, mock_open, patch

import pytest


@pytest.fixture
def edit_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.edit_command import EditCommand

        return EditCommand()


class TestEditCommand:
    def test_no_args_shows_usage(self, edit_cmd):
        with patch("code_puppy.command_line.mcp.edit_command.emit_info") as mock_emit:
            edit_cmd.execute([], group_id="g1")
            assert mock_emit.call_count == 2

    def test_generates_group_id(self, edit_cmd):
        with patch("code_puppy.command_line.mcp.edit_command.emit_info"):
            edit_cmd.execute([])  # no group_id

    def test_config_file_not_exists(self, edit_cmd):
        with (
            patch("os.path.exists", return_value=False),
            patch("code_puppy.command_line.mcp.edit_command.emit_error") as mock_err,
            patch("code_puppy.command_line.mcp.edit_command.emit_info"),
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            assert "No MCP servers configured" in str(mock_err.call_args)

    def test_server_not_found(self, edit_cmd):
        data = {"mcp_servers": {"other": {"type": "stdio", "command": "echo"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch("code_puppy.command_line.mcp.edit_command.emit_error") as mock_err,
            patch("code_puppy.command_line.mcp.edit_command.emit_warning"),
            patch("code_puppy.command_line.mcp.edit_command.emit_info"),
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            assert "not found" in str(mock_err.call_args)

    def test_server_not_found_shows_available(self, edit_cmd):
        data = {"mcp_servers": {"alpha": {"type": "stdio"}, "beta": {"type": "sse"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch("code_puppy.command_line.mcp.edit_command.emit_error"),
            patch("code_puppy.command_line.mcp.edit_command.emit_warning") as mock_warn,
            patch("code_puppy.command_line.mcp.edit_command.emit_info") as mock_info,
        ):
            edit_cmd.execute(["missing"], group_id="g1")
            mock_warn.assert_called_once()
            # Should show available server names
            assert mock_info.call_count >= 2  # alpha + beta

    def test_successful_edit(self, edit_cmd):
        data = {"mcp_servers": {"myserver": {"type": "stdio", "command": "echo"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch(
                "code_puppy.command_line.mcp.edit_command.run_custom_server_form",
                return_value=True,
            ) as mock_form,
            patch(
                "code_puppy.command_line.mcp.edit_command.reload_mcp_servers",
                create=True,
            ),
        ):
            # Patch the import inside execute
            with patch.dict("sys.modules", {"code_puppy.agent": MagicMock()}):
                edit_cmd.execute(["myserver"], group_id="g1")
            mock_form.assert_called_once()
            assert mock_form.call_args[1]["edit_mode"] is True
            assert mock_form.call_args[1]["existing_name"] == "myserver"

    def test_successful_edit_no_reload(self, edit_cmd):
        """Test edit when reload_mcp_servers import fails."""
        data = {"mcp_servers": {"myserver": {"type": "stdio", "command": "echo"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch(
                "code_puppy.command_line.mcp.edit_command.run_custom_server_form",
                return_value=True,
            ),
        ):
            # Make the import fail
            import sys

            saved = sys.modules.get("code_puppy.agent")
            sys.modules["code_puppy.agent"] = None  # will cause ImportError
            try:
                edit_cmd.execute(["myserver"], group_id="g1")
            finally:
                if saved is not None:
                    sys.modules["code_puppy.agent"] = saved
                else:
                    sys.modules.pop("code_puppy.agent", None)

    def test_form_returns_false(self, edit_cmd):
        data = {"mcp_servers": {"myserver": {"type": "stdio", "command": "echo"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch(
                "code_puppy.command_line.mcp.edit_command.run_custom_server_form",
                return_value=False,
            ),
        ):
            edit_cmd.execute(["myserver"], group_id="g1")

    def test_json_decode_error(self, edit_cmd):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data="{bad json")),
            patch("code_puppy.command_line.mcp.edit_command.emit_error") as mock_err,
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            assert "Error reading config" in str(mock_err.call_args)

    def test_generic_load_exception(self, edit_cmd):
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", side_effect=PermissionError("denied")),
            patch("code_puppy.command_line.mcp.edit_command.emit_error") as mock_err,
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            assert "Error loading server config" in str(mock_err.call_args)

    def test_execute_exception(self, edit_cmd):
        with (
            patch.object(
                edit_cmd, "_load_server_config", side_effect=Exception("boom")
            ),
            patch("code_puppy.command_line.mcp.edit_command.emit_error") as mock_err,
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            mock_err.assert_called_once()

    def test_server_type_defaults_to_stdio(self, edit_cmd):
        """Server without explicit type defaults to stdio."""
        data = {"mcp_servers": {"myserver": {"command": "echo"}}}
        with (
            patch("os.path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(data))),
            patch(
                "code_puppy.command_line.mcp.edit_command.run_custom_server_form",
                return_value=False,
            ) as mock_form,
        ):
            edit_cmd.execute(["myserver"], group_id="g1")
            assert mock_form.call_args[1]["existing_type"] == "stdio"
