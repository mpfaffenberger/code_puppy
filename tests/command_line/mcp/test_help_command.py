"""Tests for MCP help command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def help_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.help_command import HelpCommand

        return HelpCommand()


class TestHelpCommand:
    def test_execute_emits_help(self, help_cmd):
        with patch("code_puppy.command_line.mcp.help_command.emit_info") as mock_emit:
            help_cmd.execute([], group_id="g1")
            mock_emit.assert_called_once()
            text = mock_emit.call_args[0][0]
            assert "MCP Server Management Commands" in text.plain

    def test_execute_generates_group_id_if_none(self, help_cmd):
        with patch("code_puppy.command_line.mcp.help_command.emit_info") as mock_emit:
            help_cmd.execute([])
            assert mock_emit.called

    def test_execute_contains_all_sections(self, help_cmd):
        with patch("code_puppy.command_line.mcp.help_command.emit_info") as mock_emit:
            help_cmd.execute([], group_id="g1")
            text = mock_emit.call_args[0][0].plain
            assert "Registry Commands" in text
            assert "Core Commands" in text
            assert "Management Commands" in text
            assert "Status Indicators" in text
            assert "Examples" in text

    def test_execute_handles_exception(self, help_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.help_command.emit_info",
                side_effect=Exception("fail"),
            ),
            patch("code_puppy.command_line.mcp.help_command.emit_error") as mock_err,
        ):
            help_cmd.execute([], group_id="g1")
            mock_err.assert_called_once()
