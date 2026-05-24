"""Tests for ``/mcp silence-warning`` and ``/mcp unsilence-warning``."""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.command_line.mcp.silence_warning_command import (
    SilenceWarningCommand,
    UnsilenceWarningCommand,
)


class TestSilenceWarningCommand:
    """Toggling the unbound-server warning silence flag from the CLI."""

    def test_silence_flips_flag_when_currently_active(self):
        cmd = SilenceWarningCommand()
        with (
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "get_mcp_unbound_warning_silenced",
                return_value=False,
            ),
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "set_mcp_unbound_warning_silenced"
            ) as mock_set,
            patch(
                "code_puppy.command_line.mcp.silence_warning_command.emit_info"
            ) as mock_emit,
        ):
            cmd.execute([])

        mock_set.assert_called_once_with(True)
        assert mock_emit.call_count == 1

    def test_silence_is_noop_when_already_silenced(self):
        cmd = SilenceWarningCommand()
        with (
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "get_mcp_unbound_warning_silenced",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "set_mcp_unbound_warning_silenced"
            ) as mock_set,
            patch(
                "code_puppy.command_line.mcp.silence_warning_command.emit_info"
            ) as mock_emit,
        ):
            cmd.execute([])

        mock_set.assert_not_called()
        # We still emit feedback so the user knows their command did something.
        assert mock_emit.call_count == 1


class TestUnsilenceWarningCommand:
    def test_unsilence_flips_flag_when_currently_silenced(self):
        cmd = UnsilenceWarningCommand()
        with (
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "get_mcp_unbound_warning_silenced",
                return_value=True,
            ),
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "set_mcp_unbound_warning_silenced"
            ) as mock_set,
            patch("code_puppy.command_line.mcp.silence_warning_command.emit_info"),
        ):
            cmd.execute([])

        mock_set.assert_called_once_with(False)

    def test_unsilence_is_noop_when_already_active(self):
        cmd = UnsilenceWarningCommand()
        with (
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "get_mcp_unbound_warning_silenced",
                return_value=False,
            ),
            patch(
                "code_puppy.command_line.mcp.silence_warning_command."
                "set_mcp_unbound_warning_silenced"
            ) as mock_set,
            patch("code_puppy.command_line.mcp.silence_warning_command.emit_info"),
        ):
            cmd.execute([])

        mock_set.assert_not_called()


class TestHandlerRouting:
    """The MCP handler dict should expose both subcommands."""

    def test_handler_registers_silence_subcommands(self):
        from code_puppy.command_line.mcp.handler import MCPCommandHandler

        handler = MCPCommandHandler()
        assert "silence-warning" in handler._commands
        assert "unsilence-warning" in handler._commands
        assert isinstance(handler._commands["silence-warning"], SilenceWarningCommand)
        assert isinstance(
            handler._commands["unsilence-warning"], UnsilenceWarningCommand
        )
