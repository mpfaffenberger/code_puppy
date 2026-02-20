"""Tests for MCP test command."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def test_cmd():
    with patch("code_puppy.command_line.mcp.base.get_mcp_manager") as mock_mgr:
        mock_mgr.return_value = MagicMock()
        from code_puppy.command_line.mcp.test_command import TestCommand

        return TestCommand()


class TestTestCommand:
    def test_no_args_shows_usage(self, test_cmd):
        with patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit:
            test_cmd.execute([], group_id="g1")
            assert "Usage" in str(mock_emit.call_args)

    def test_generates_group_id(self, test_cmd):
        with patch("code_puppy.command_line.mcp.test_command.emit_info"):
            test_cmd.execute([])  # no group_id

    def test_server_not_found(self, test_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value=None,
            ),
            patch("code_puppy.command_line.mcp.test_command.suggest_similar_servers"),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.execute(["missing"], group_id="g1")
            assert "not found" in str(mock_emit.call_args_list)

    def test_server_not_accessible(self, test_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.manager.get_server.return_value = None
            test_cmd.execute(["myserver"], group_id="g1")
            assert "not accessible" in str(mock_emit.call_args_list)

    def test_successful_test_enabled(self, test_cmd):
        mock_server = MagicMock()
        mock_server.config.type = "stdio"
        mock_server.is_enabled.return_value = True
        mock_server.is_quarantined.return_value = False

        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.manager.get_server.return_value = mock_server
            test_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("Connectivity test passed" in c for c in calls)

    def test_successful_test_disabled(self, test_cmd):
        mock_server = MagicMock()
        mock_server.config.type = "stdio"
        mock_server.is_enabled.return_value = False
        mock_server.is_quarantined.return_value = False

        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.manager.get_server.return_value = mock_server
            test_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("disabled" in c for c in calls)

    def test_successful_test_quarantined(self, test_cmd):
        mock_server = MagicMock()
        mock_server.config.type = "stdio"
        mock_server.is_enabled.return_value = True
        mock_server.is_quarantined.return_value = True

        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.manager.get_server.return_value = mock_server
            test_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("quarantined" in c for c in calls)

    def test_pydantic_server_fails(self, test_cmd):
        mock_server = MagicMock()
        mock_server.get_pydantic_server.side_effect = Exception("connect failed")

        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                return_value="id1",
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_info") as mock_emit,
        ):
            test_cmd.manager.get_server.return_value = mock_server
            test_cmd.execute(["myserver"], group_id="g1")
            calls = [str(c) for c in mock_emit.call_args_list]
            assert any("test failed" in c for c in calls)

    def test_outer_exception(self, test_cmd):
        with (
            patch(
                "code_puppy.command_line.mcp.test_command.find_server_id_by_name",
                side_effect=Exception("boom"),
            ),
            patch("code_puppy.command_line.mcp.test_command.emit_error") as mock_err,
        ):
            test_cmd.execute(["myserver"], group_id="g1")
            mock_err.assert_called_once()
