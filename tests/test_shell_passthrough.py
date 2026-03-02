"""Tests for shell pass-through feature.

The `!` prefix allows users to run shell commands directly from the
Code Puppy prompt without any agent processing.
"""

import asyncio
import subprocess
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from code_puppy.command_line.shell_passthrough import (
    SHELL_PASSTHROUGH_PREFIX,
    _BANNER_NAME,
    _format_banner,
    execute_shell_passthrough,
    extract_command,
    is_shell_passthrough,
)


class TestIsShellPassthrough:
    """Test detection of shell pass-through input."""

    def test_simple_command(self):
        """A simple command like `!ls` is detected as pass-through."""
        assert is_shell_passthrough("!ls") is True

    def test_command_with_args(self):
        """Commands with arguments like `!ls -la` are detected."""
        assert is_shell_passthrough("!ls -la") is True

    def test_command_with_leading_whitespace(self):
        """Leading whitespace before `!` is tolerated."""
        assert is_shell_passthrough("  !git status") is True

    def test_command_with_trailing_whitespace(self):
        """Trailing whitespace after the command is tolerated."""
        assert is_shell_passthrough("!pwd  ") is True

    def test_complex_command(self):
        """Complex commands with pipes are detected."""
        assert is_shell_passthrough("!cat file.txt | grep 'hello'") is True

    def test_bare_bang_is_not_passthrough(self):
        """A lone `!` with nothing after it should NOT be a pass-through."""
        assert is_shell_passthrough("!") is False

    def test_bang_with_only_whitespace_is_not_passthrough(self):
        """A `!` followed by only whitespace is NOT a pass-through."""
        assert is_shell_passthrough("!   ") is False

    def test_empty_string(self):
        """An empty string is NOT a pass-through."""
        assert is_shell_passthrough("") is False

    def test_regular_prompt(self):
        """Regular text without `!` prefix is NOT a pass-through."""
        assert is_shell_passthrough("write me a python script") is False

    def test_slash_command(self):
        """Slash commands like `/help` are NOT pass-throughs."""
        assert is_shell_passthrough("/help") is False

    def test_bang_in_middle_of_text(self):
        """A `!` in the middle of text is NOT a pass-through."""
        assert is_shell_passthrough("hello! world") is False

    def test_prefix_constant(self):
        """Verify the prefix constant is `!`."""
        assert SHELL_PASSTHROUGH_PREFIX == "!"


class TestExtractCommand:
    """Test command extraction from pass-through input."""

    def test_simple_command(self):
        """Extract a simple command from `!ls`."""
        assert extract_command("!ls") == "ls"

    def test_command_with_args(self):
        """Extract a command with arguments."""
        assert extract_command("!git status") == "git status"

    def test_strips_surrounding_whitespace(self):
        """Surrounding whitespace is stripped from both prefix and command."""
        assert extract_command("  !  pwd  ") == "pwd"

    def test_preserves_inner_whitespace(self):
        """Whitespace within the command itself is preserved."""
        assert extract_command("!echo  hello   world") == "echo  hello   world"

    def test_pipe_command(self):
        """Commands with pipes are extracted correctly."""
        assert extract_command("!ls | head -5") == "ls | head -5"

    def test_complex_command(self):
        """Complex commands with special chars are extracted verbatim."""
        assert extract_command("!find . -name '*.py' -exec wc -l {} +") == (
            "find . -name '*.py' -exec wc -l {} +"
        )


class TestFormatBanner:
    """Test banner formatting."""

    def test_banner_uses_config_color(self):
        """Banner should use the color from get_banner_color."""
        with patch(
            "code_puppy.command_line.shell_passthrough.get_banner_color",
            return_value="medium_sea_green",
        ):
            banner = _format_banner()
            assert "medium_sea_green" in banner
            assert "SHELL PASSTHROUGH" in banner

    def test_banner_name_constant(self):
        """Verify the banner name matches what config.py expects."""
        assert _BANNER_NAME == "shell_passthrough"

    def test_banner_matches_rich_renderer_pattern(self):
        """Banner format should match [bold white on {color}] pattern."""
        with patch(
            "code_puppy.command_line.shell_passthrough.get_banner_color",
            return_value="red",
        ):
            banner = _format_banner()
            assert "[bold white on red]" in banner
            assert "[/bold white on red]" in banner


class TestExecuteShellPassthrough:
    """Test shell command execution."""

    def _mock_console(self):
        """Create a mock Rich Console for capturing print calls."""
        return MagicMock()

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_successful_command(self, mock_get_console, mock_run):
        """Successful commands show a success message."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hello")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["shell"] is True
        assert call_kwargs[0][0] == "echo hello"

        # Should have printed banner, context line, and success
        assert console.print.call_count == 3
        last_call = str(console.print.call_args_list[-1])
        assert "Done" in last_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_failed_command_shows_exit_code(self, mock_get_console, mock_run):
        """Non-zero exit codes show the exit code."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=1)

        execute_shell_passthrough("!false")

        last_call = str(console.print.call_args_list[-1])
        assert "Exit code 1" in last_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_exit_code_127(self, mock_get_console, mock_run):
        """Exit code 127 (command not found) is reported properly."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=127)

        execute_shell_passthrough("!nonexistentcommand")

        last_call = str(console.print.call_args_list[-1])
        assert "127" in last_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_keyboard_interrupt(self, mock_get_console, mock_run):
        """Ctrl+C during execution shows interrupted message."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.side_effect = KeyboardInterrupt()

        execute_shell_passthrough("!sleep 999")

        last_call = str(console.print.call_args_list[-1])
        assert "Interrupted" in last_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_generic_exception(self, mock_get_console, mock_run):
        """Generic exceptions are caught and reported."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.side_effect = OSError("permission denied")

        execute_shell_passthrough("!forbidden")

        last_call = str(console.print.call_args_list[-1])
        assert "permission denied" in last_call

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_empty_command_after_bang(self, mock_get_console):
        """An empty command (just spaces after !) shows usage hint."""
        console = self._mock_console()
        mock_get_console.return_value = console

        execute_shell_passthrough("!")

        console.print.assert_called_once()
        call_arg = str(console.print.call_args)
        assert "Usage" in call_arg or "Empty" in call_arg

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_inherits_stdio(self, mock_get_console, mock_run):
        """Command should inherit stdin/stdout/stderr from parent."""
        import sys

        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hello")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["stdin"] is sys.stdin
        assert call_kwargs["stdout"] is sys.stdout
        assert call_kwargs["stderr"] is sys.stderr

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.os.getcwd", return_value="/tmp")
    def test_uses_current_working_directory(
        self, mock_cwd, mock_get_console, mock_run
    ):
        """Command should run in the current working directory."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!ls")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_banner_shown_before_command(self, mock_get_console, mock_run):
        """The banner should display with SHELL PASSTHROUGH label."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!git status")

        first_call = str(console.print.call_args_list[0])
        assert "SHELL PASSTHROUGH" in first_call
        assert "git status" in first_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_context_hint_shown(self, mock_get_console, mock_run):
        """A context line should clarify this bypasses the AI."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hi")

        second_call = str(console.print.call_args_list[1])
        assert "Bypassing AI" in second_call

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_rich_markup_escaped_in_command(self, mock_get_console, mock_run):
        """Commands with Rich markup chars should be escaped to prevent injection."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo [bold red]oops[/bold red]")

        assert mock_run.call_args[0][0] == "echo [bold red]oops[/bold red]"

    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_rich_markup_escaped_in_error(self, mock_get_console, mock_run):
        """Error messages with Rich markup chars should be escaped."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.side_effect = OSError("[red]bad[/red]")

        execute_shell_passthrough("!broken")

        last_call = str(console.print.call_args_list[-1])
        assert "Shell error" in last_call


class TestInitialCommandPassthrough:
    """Test that shell passthrough works for initial_command and -p paths.

    Regression tests for the bug where `code-puppy "!ls"` or
    `code-puppy -p "!ls"` would send the command to the AI agent
    instead of executing it directly in the shell.
    """

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_execute_single_prompt_calls_passthrough(
        self, mock_run, mock_console
    ):
        """execute_single_prompt with '!ls' should run shell, not the agent."""
        from code_puppy.cli_runner import execute_single_prompt

        mock_console.return_value = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        with patch(
            "code_puppy.cli_runner.get_current_agent"
        ) as mock_agent, patch(
            "code_puppy.cli_runner.run_prompt_with_attachments"
        ) as mock_run_prompt:
            asyncio.run(execute_single_prompt("!ls -la", mock_renderer))

            # Shell command should have been executed
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == "ls -la"
            # Agent should NOT have been called
            mock_agent.assert_not_called()
            mock_run_prompt.assert_not_called()

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_execute_single_prompt_normal_prompt_skips_passthrough(
        self, mock_run, mock_console
    ):
        """execute_single_prompt with normal text should NOT call passthrough."""
        from code_puppy.cli_runner import execute_single_prompt

        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        mock_response = MagicMock()
        mock_response.output = "Hello!"
        mock_response.all_messages.return_value = []

        with patch(
            "code_puppy.cli_runner.get_current_agent"
        ), patch(
            "code_puppy.cli_runner.run_prompt_with_attachments",
            new_callable=AsyncMock,
            return_value=mock_response,
        ), patch(
            "code_puppy.messaging.get_message_bus"
        ), patch(
            "code_puppy.messaging.message_queue.emit_info"
        ):
            asyncio.run(execute_single_prompt("write me a script", mock_renderer))

            # Shell passthrough should NOT have been called
            mock_run.assert_not_called()
