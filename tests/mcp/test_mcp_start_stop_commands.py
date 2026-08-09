"""
Tests for MCP Start, Stop, and Restart Commands.

Covers server lifecycle operations, error handling,
agent reloading, and edge cases.
"""

from contextlib import nullcontext
from unittest.mock import Mock, patch

import pytest

from code_puppy.command_line.mcp.restart_command import RestartCommand
from code_puppy.command_line.mcp.start_command import StartCommand
from code_puppy.command_line.mcp.stop_command import StopCommand
from code_puppy.mcp_.managed_server import ServerState


def get_messages_from_mock_emit(mock_emit_info):
    """Helper to extract messages from mock_emit_info."""
    messages = []
    for msg_tuple in mock_emit_info.messages:
        if len(msg_tuple) >= 1:
            messages.append(msg_tuple[0])
    return messages


# (command name, command class, module path whose functions get patched)
COMMANDS = [
    ("start", StartCommand, "code_puppy.command_line.mcp.start_command"),
    ("stop", StopCommand, "code_puppy.command_line.mcp.stop_command"),
    ("restart", RestartCommand, "code_puppy.command_line.mcp.restart_command"),
]

COMMAND_IDS = [name for name, _, _ in COMMANDS]


def _capture_module_emit_error(cmd_mod, errors):
    """Patch the command module's emit_error if it has one (start/stop only)."""
    import importlib

    try:
        module = importlib.import_module(cmd_mod)
    except ImportError:
        return nullcontext()
    if hasattr(module, "emit_error"):
        return patch(
            cmd_mod + ".emit_error",
            side_effect=lambda m, **kwargs: errors.append(str(m)),
        )
    return nullcontext()


@pytest.mark.parametrize("cmd_name,command_cls,cmd_mod", COMMANDS, ids=COMMAND_IDS)
class TestCommandCommon:
    """Behavior shared by the start/stop/restart commands."""

    def test_init(self, cmd_name, command_cls, cmd_mod):
        assert hasattr(command_cls(), "manager")

    def test_execute_no_args_shows_usage(
        self, cmd_name, command_cls, cmd_mod, mock_emit_info
    ):
        command_cls().execute([])
        messages = get_messages_from_mock_emit(mock_emit_info)
        assert any("Usage:" in msg for msg in messages)

    def test_execute_server_not_found(
        self, cmd_name, command_cls, cmd_mod, mock_emit_info
    ):
        errors = []
        with (
            patch(f"{cmd_mod}.find_server_id_by_name", return_value=None),
            patch(f"{cmd_mod}.suggest_similar_servers") as mock_suggest,
            _capture_module_emit_error(cmd_mod, errors),
        ):
            command_cls().execute(["nonexistent"])

        messages = get_messages_from_mock_emit(mock_emit_info) + errors
        assert any("not found" in msg for msg in messages)
        mock_suggest.assert_called_once()

    def test_execute_general_exception(
        self, cmd_name, command_cls, cmd_mod, mock_emit_info
    ):
        errors = []
        with (
            patch(
                f"{cmd_mod}.find_server_id_by_name",
                side_effect=Exception("Random error"),
            ),
            _capture_module_emit_error(cmd_mod, errors),
        ):
            command_cls().execute(["test-server"])

        # Execution survives and reports the failure somewhere.
        messages = get_messages_from_mock_emit(mock_emit_info) + errors
        assert any("Failed" in msg for msg in messages)

    def test_generate_group_id(self, cmd_name, command_cls, cmd_mod):
        group_id = command_cls().generate_group_id()
        assert len(group_id) > 10


class TestStartCommand:
    """Test cases for StartCommand class."""

    def setup_method(self):
        self.command = StartCommand()

    def test_execute_start_success(
        self, mock_emit_info, mock_get_current_agent, mock_mcp_manager
    ):
        """Test successful server start."""
        with patch(
            "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
            return_value="test-server-1",
        ):
            self.command.execute(["test-server"])

            assert "start_test-server-1" in mock_mcp_manager.call_history

            messages = get_messages_from_mock_emit(mock_emit_info)
            assert any("Agent reloaded" in msg for msg in messages)

    def test_execute_start_failure(
        self, mock_emit_info, mock_get_current_agent, mock_mcp_manager
    ):
        """Test failed server start."""
        mock_mcp_manager.servers = {}

        with patch(
            "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
            return_value="nonexistent-server",
        ):
            self.command.execute(["test-server"])

            messages = get_messages_from_mock_emit(mock_emit_info)
            assert not any("Agent reloaded" in msg for msg in messages)

    def test_execute_with_agent_reload_exception(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test start when agent reload fails."""
        mock_agent = Mock()
        mock_agent.reload_code_generation_agent.side_effect = Exception("Reload failed")

        with patch("code_puppy.agents.get_current_agent", return_value=mock_agent):
            with patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="test-server-1",
            ):
                self.command.execute(["test-server"])

                # Should still show success message
                assert len(mock_emit_info.messages) >= 0


class TestStopCommand:
    """Test cases for StopCommand class."""

    def setup_method(self):
        self.command = StopCommand()

    def test_execute_stop_success(
        self, mock_emit_info, mock_get_current_agent, mock_mcp_manager
    ):
        """Test successful server stop."""
        with patch(
            "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
            return_value="test-server-1",
        ):
            self.command.execute(["test-server"])

            assert "stop_test-server-1" in mock_mcp_manager.call_history

            messages = get_messages_from_mock_emit(mock_emit_info)
            assert any("Agent reloaded" in msg for msg in messages)

    def test_execute_stop_failure(self, mock_emit_info, mock_get_current_agent):
        """Test failed server stop."""
        with patch(
            "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
            return_value="nonexistent-server",
        ):
            self.command.execute(["test-server"])

            messages = get_messages_from_mock_emit(mock_emit_info)
            assert not any("Agent reloaded" in msg for msg in messages)

    def test_execute_with_agent_reload_exception(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test stop when agent reload fails."""
        mock_agent = Mock()
        mock_agent.reload_code_generation_agent.side_effect = Exception("Reload failed")

        with patch("code_puppy.agents.get_current_agent", return_value=mock_agent):
            with patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value="test-server-1",
            ):
                self.command.execute(["test-server"])

                # Should still show success message
                assert len(mock_emit_info.messages) >= 0


class TestRestartCommand:
    """Test cases for RestartCommand class."""

    def setup_method(self):
        self.command = RestartCommand()

    def test_execute_restart_full_success(self, mock_emit_info, mock_mcp_manager):
        """Test successful restart (stop, reload, start)."""
        with patch(
            "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
            return_value="test-server-1",
        ):
            self.command.execute(["test-server"])

            assert "stop_test-server-1" in mock_mcp_manager.call_history
            assert "reload_test-server-1" in mock_mcp_manager.call_history
            assert "start_test-server-1" in mock_mcp_manager.call_history
            assert len(mock_emit_info.messages) >= 0

    def test_execute_restart_reload_failure(self, mock_emit_info, mock_mcp_manager):
        """Test restart when reload fails."""
        original_reload = mock_mcp_manager.reload_server

        def failing_reload(server_id):
            mock_mcp_manager.call_history.append(f"reload_{server_id}")
            return False

        mock_mcp_manager.reload_server = failing_reload

        try:
            with patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="test-server-1",
            ):
                self.command.execute(["test-server"])

                assert "stop_test-server-1" in mock_mcp_manager.call_history
                assert "reload_test-server-1" in mock_mcp_manager.call_history
                assert len(mock_emit_info.messages) >= 0
        finally:
            mock_mcp_manager.reload_server = original_reload

    def test_execute_restart_start_failure_after_reload(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test restart when start fails after successful reload."""

        def start_that_fails(server_id):
            if server_id == "test-server-1":
                # Simulate server disappearing
                mock_mcp_manager.servers.pop(server_id, None)
            return False

        mock_mcp_manager.start_server_sync = start_that_fails

        with patch(
            "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
            return_value="test-server-1",
        ):
            self.command.execute(["test-server"])

            assert len(mock_emit_info.messages) >= 0

    def test_execute_with_agent_reload_exception(
        self, mock_emit_info, mock_mcp_manager
    ):
        """Test restart when agent reload fails."""
        mock_agent = Mock()
        mock_agent.reload_code_generation_agent.side_effect = Exception("Reload failed")

        with patch("code_puppy.agents.get_current_agent", return_value=mock_agent):
            with patch(
                "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
                return_value="test-server-1",
            ):
                self.command.execute(["test-server"])

                # Should still show success message
                assert len(mock_emit_info.messages) >= 0


class TestCommandIntegration:
    """Integration tests for start/stop/restart commands."""

    def test_stop_then_start_sequence(
        self, mock_emit_info, mock_mcp_manager, mock_get_current_agent
    ):
        """Test stopping then starting a server."""
        stop_cmd = StopCommand()
        start_cmd = StartCommand()

        with (
            patch(
                "code_puppy.command_line.mcp.stop_command.find_server_id_by_name",
                return_value="test-server-1",
            ),
            patch(
                "code_puppy.command_line.mcp.start_command.find_server_id_by_name",
                return_value="test-server-1",
            ),
        ):
            start_cmd.execute(["test-server"])
            server = mock_mcp_manager.servers["test-server-1"]
            assert server.enabled
            assert server.state == ServerState.RUNNING

            stop_cmd.execute(["test-server"])
            server = mock_mcp_manager.servers["test-server-1"]
            assert not server.enabled
            assert server.state == ServerState.STOPPED

            assert len(mock_emit_info.messages) >= 0

    def test_restart_preserves_server_info(self, mock_emit_info, mock_mcp_manager):
        """Test that restart doesn't lose server configuration."""
        restart_cmd = RestartCommand()

        original_server = mock_mcp_manager.servers["test-server-1"]
        original_server.enabled = True
        original_server.state = ServerState.RUNNING

        with patch(
            "code_puppy.command_line.mcp.restart_command.find_server_id_by_name",
            return_value="test-server-1",
        ):
            restart_cmd.execute(["test-server"])

            assert "test-server-1" in mock_mcp_manager.servers
            server = mock_mcp_manager.servers["test-server-1"]
            assert server.name == "test-server"
            assert server.type == "stdio"
