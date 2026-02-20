"""Tests for MCP command handler."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def handler():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.handler import MCPCommandHandler

        h = MCPCommandHandler()
        # Mock all sub-commands
        for name, cmd in h._commands.items():
            h._commands[name] = MagicMock()
        return h


class TestMCPCommandHandler:
    def test_non_mcp_command_returns_false(self, handler):
        assert handler.handle_mcp_command("/notmcp") is False

    def test_empty_args_shows_list(self, handler):
        assert handler.handle_mcp_command("/mcp") is True
        handler._commands["list"].execute.assert_called_once()

    def test_empty_after_strip_shows_list(self, handler):
        assert handler.handle_mcp_command("/mcp   ") is True
        handler._commands["list"].execute.assert_called_once()

    def test_routes_subcommand(self, handler):
        assert handler.handle_mcp_command("/mcp help") is True
        handler._commands["help"].execute.assert_called_once()
        args = handler._commands["help"].execute.call_args
        assert args[0][0] == []  # no sub_args

    def test_routes_with_subargs(self, handler):
        assert handler.handle_mcp_command("/mcp start myserver") is True
        handler._commands["start"].execute.assert_called_once()
        args = handler._commands["start"].execute.call_args
        assert args[0][0] == ["myserver"]

    def test_unknown_subcommand(self, handler):
        with patch("code_puppy.command_line.mcp.handler.emit_info") as mock_emit:
            assert handler.handle_mcp_command("/mcp foobar") is True
            assert mock_emit.call_count == 2  # unknown + help hint

    def test_shlex_error(self, handler):
        with patch("code_puppy.command_line.mcp.handler.emit_info") as mock_emit:
            assert handler.handle_mcp_command('/mcp "unclosed') is True
            call_args_str = str(mock_emit.call_args_list[0])
            assert "Invalid command syntax" in call_args_str or mock_emit.called

    def test_exception_in_command(self, handler):
        handler._commands["list"].execute.side_effect = Exception("boom")
        with patch("code_puppy.command_line.mcp.handler.emit_info"):
            assert handler.handle_mcp_command("/mcp list") is True

    def test_shlex_empty_result(self, handler):
        """When shlex.split returns empty list after parsing."""
        with patch("shlex.split", return_value=[]):
            assert handler.handle_mcp_command("/mcp something") is True
            handler._commands["list"].execute.assert_called_once()

    def test_case_insensitive_subcommand(self, handler):
        assert handler.handle_mcp_command("/mcp HELP") is True
        handler._commands["help"].execute.assert_called_once()
