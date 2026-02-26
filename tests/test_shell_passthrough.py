"""Tests for shell pass-through feature.

The `!` prefix allows users to run shell commands directly from the
Code Puppy prompt without any agent processing.
"""

import subprocess
from unittest.mock import MagicMock, call, patch

import pytest

from code_puppy.command_line.shell_passthrough import (
    SHELL_PASSTHROUGH_PREFIX,
    execute_shell_passthrough,
    extract_command,
    is_shell_passthrough,
)


class TestIsShellPassthrough:
    """Test detection of shell pass-through input."""

    def test_simple_command(self):
        assert is_shell_passthrough("!ls") is True

    def test_command_with_args(self):
        assert is_shell_passthrough("!ls -la") is True

    def test_command_with_leading_whitespace(self):
        assert is_shell_passthrough("  !git status") is True

    def test_command_with_trailing_whitespace(self):
        assert is_shell_passthrough("!pwd  ") is True

    def test_complex_command(self):
        assert is_shell_passthrough("!cat file.txt | grep 'hello'") is True

    def test_bare_bang_is_not_passthrough(self):
        """A lone `!` with nothing after it should NOT be a pass-through."""
        assert is_shell_passthrough("!") is False

    def test_bang_with_only_whitespace_is_not_passthrough(self):
        assert is_shell_passthrough("!   ") is False

    def test_empty_string(self):
        assert is_shell_passthrough("") is False

    def test_regular_prompt(self):
        assert is_shell_passthrough("write me a python script") is False

    def test_slash_command(self):
        assert is_shell_passthrough("/help") is False

    def test_bang_in_middle_of_text(self):
        """A `!` in the middle of text is NOT a pass-through."""
        assert is_shell_passthrough("hello! world") is False

    def test_prefix_constant(self):
        """Verify the prefix is what we expect."""
        assert SHELL_PASSTHROUGH_PREFIX == "!"


class TestExtractCommand:
    """Test command extraction from pass-through input."""

    def test_simple_command(self):
        assert extract_command("!ls") == "ls"

    def test_command_with_args(self):
        assert extract_command("!git status") == "git status"

    def test_strips_surrounding_whitespace(self):
        assert extract_command("  !  pwd  ") == "pwd"

    def test_preserves_inner_whitespace(self):
        assert extract_command("!echo  hello   world") == "echo  hello   world"

    def test_pipe_command(self):
        assert extract_command("!ls | head -5") == "ls | head -5"

    def test_complex_command(self):
        assert extract_command("!find . -name '*.py' -exec wc -l {} +") == (
            "find . -name '*.py' -exec wc -l {} +"
        )


class TestExecuteShellPassthrough:
    """Test shell command execution."""

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_success")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_successful_command(self, mock_info, mock_success, mock_run):
        """Successful commands show a success message."""
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hello")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["shell"] is True
        assert call_kwargs[0][0] == "echo hello"
        mock_success.assert_called_once()

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_warning")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_failed_command_shows_exit_code(self, mock_info, mock_warning, mock_run):
        """Non-zero exit codes show warning with the exit code."""
        mock_run.return_value = MagicMock(returncode=1)

        execute_shell_passthrough("!false")

        mock_warning.assert_called_once()
        # The warning message should contain the exit code
        warning_arg = mock_warning.call_args[0][0]
        assert "1" in str(warning_arg)

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_warning")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_exit_code_127(self, mock_info, mock_warning, mock_run):
        """Exit code 127 (command not found) is reported properly."""
        mock_run.return_value = MagicMock(returncode=127)

        execute_shell_passthrough("!nonexistentcommand")

        mock_warning.assert_called_once()
        warning_arg = mock_warning.call_args[0][0]
        assert "127" in str(warning_arg)

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_warning")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_keyboard_interrupt(self, mock_info, mock_warning, mock_run):
        """Ctrl+C during execution shows interrupted message."""
        mock_run.side_effect = KeyboardInterrupt()

        execute_shell_passthrough("!sleep 999")

        mock_warning.assert_called_once()
        warning_arg = mock_warning.call_args[0][0]
        assert "Interrupted" in str(warning_arg)

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_warning")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_generic_exception(self, mock_info, mock_warning, mock_run):
        """Generic exceptions are caught and reported."""
        mock_run.side_effect = OSError("permission denied")

        execute_shell_passthrough("!forbidden")

        mock_warning.assert_called_once()
        warning_arg = mock_warning.call_args[0][0]
        assert "permission denied" in str(warning_arg)

    @patch("code_puppy.command_line.shell_passthrough.emit_warning")
    def test_empty_command_after_bang(self, mock_warning):
        """An empty command (just spaces after !) shows usage hint."""
        # This shouldn't normally happen because is_shell_passthrough
        # filters it, but defense in depth!
        execute_shell_passthrough("!")

        mock_warning.assert_called_once()
        warning_arg = mock_warning.call_args[0][0]
        assert "Usage" in str(warning_arg) or "Empty" in str(warning_arg)

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_success")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    def test_inherits_stdio(self, mock_info, mock_success, mock_run):
        """Command should inherit stdin/stdout/stderr from parent."""
        import sys

        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hello")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["stdin"] is sys.stdin
        assert call_kwargs["stdout"] is sys.stdout
        assert call_kwargs["stderr"] is sys.stderr

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_success")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    @patch("code_puppy.command_line.shell_passthrough.os.getcwd", return_value="/tmp")
    def test_uses_current_working_directory(
        self, mock_cwd, mock_info, mock_success, mock_run
    ):
        """Command should run in the current working directory."""
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!ls")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough.emit_info")
    @patch("code_puppy.command_line.shell_passthrough.emit_success")
    def test_header_shows_command(self, mock_success, mock_info, mock_run):
        """The header message should display the command being run."""
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!git status")

        mock_info.assert_called_once()
        header_arg = mock_info.call_args[0][0]
        assert "git status" in str(header_arg)
