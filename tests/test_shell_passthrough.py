"""Compact smoke tests for shell pass-through.

Trimmed from a much larger suite (round 5 test reduction) while keeping the
core detect/extract/execute paths of shell_passthrough.py covered.
"""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.shell_passthrough import (
    _BANNER_NAME,
    SHELL_PASSTHROUGH_PREFIX,
    _format_banner,
    execute_shell_passthrough,
    extract_command,
    is_shell_passthrough,
)


class TestDetectAndExtract:
    @pytest.mark.parametrize(
        "command",
        ["!ls", "!ls -la", "  !git status", "!pwd  ", "!cat f | grep 'hi'"],
    )
    def test_detects_passthrough(self, command):
        assert is_shell_passthrough(command) is True

    @pytest.mark.parametrize(
        "command",
        ["", "ls", "!", "! ", "!  "],
    )
    def test_rejects_non_passthrough(self, command):
        assert is_shell_passthrough(command) is False

    def test_prefix_constant(self):
        assert SHELL_PASSTHROUGH_PREFIX == "!"

    @pytest.mark.parametrize(
        "command,expected",
        [
            ("!ls -la", "ls -la"),
            ("  !git status  ", "git status"),
            ("!echo 'a b'", "echo 'a b'"),
        ],
    )
    def test_extract_command(self, command, expected):
        assert extract_command(command) == expected

    def test_banner_uses_config_color(self):
        with patch(
            "code_puppy.command_line.shell_passthrough.get_banner_color",
            return_value="cyan",
        ):
            banner = _format_banner()
            assert "cyan" in banner
            assert _BANNER_NAME == "shell_passthrough"


class TestExecute:
    @staticmethod
    def _console():
        return MagicMock()

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_successful_command(self, mock_get_console, mock_run):
        console = self._console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hello")

        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == "echo hello"
        assert mock_run.call_args[1]["shell"] is True
        assert console.print.call_count == 3
        assert "Done" in str(console.print.call_args_list[-1])

    @pytest.mark.parametrize(
        "command,returncode,expected_text",
        [("!false", 1, "Exit code 1"), ("!nope", 127, "127")],
    )
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_nonzero_exit_code_reported(
        self, mock_get_console, mock_run, command, returncode, expected_text
    ):
        console = self._console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=returncode)

        execute_shell_passthrough(command)

        assert expected_text in str(console.print.call_args_list[-1])

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_keyboard_interrupt(self, mock_get_console, mock_run):
        console = self._console()
        mock_get_console.return_value = console
        mock_run.side_effect = KeyboardInterrupt

        execute_shell_passthrough("!sleep 10")

        assert "Interrupted" in str(console.print.call_args_list[-1])

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_execution_error_reported(self, mock_get_console, mock_run):
        console = self._console()
        mock_get_console.return_value = console
        mock_run.side_effect = OSError("boom")

        execute_shell_passthrough("!boom")

        assert "Shell error" in str(console.print.call_args_list[-1])

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_empty_command_after_bang(self, mock_get_console):
        console = self._console()
        mock_get_console.return_value = console

        execute_shell_passthrough("!   ")

        assert "Empty command" in str(console.print.call_args_list[0])

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_rich_markup_escaped_in_command(self, mock_get_console, mock_run):
        console = self._console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo [red]hi[/red]")

        # The command line printed must escape the rich markup so it can't inject.
        printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "\\[red]" in printed or "[red]" not in printed.split("$")[-1]
