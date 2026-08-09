"""Tests for shell pass-through feature.

The `!` prefix allows users to run shell commands directly from the
Code Puppy prompt without any agent processing.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.command_line.shell_passthrough import (
    _BANNER_NAME,
    SHELL_PASSTHROUGH_PREFIX,
    _format_banner,
    execute_shell_passthrough,
    extract_command,
    is_shell_passthrough,
)


class TestIsShellPassthrough:
    """Test detection of shell pass-through input."""

    @pytest.mark.parametrize(
        "command",
        ["!ls", "!ls -la", "  !git status", "!pwd  ", "!cat file.txt | grep 'hello'"],
    )
    def test_detects_passthrough(self, command):
        """Various real commands (with whitespace/pipes) are detected."""
        assert is_shell_passthrough(command) is True

    @pytest.mark.parametrize(
        "command",
        ["!", "!   ", "", "write me a python script", "/help", "hello! world"],
    )
    def test_rejects_non_passthrough(self, command):
        """Lone bangs, empty/plain text and slash commands are NOT pass-through."""
        assert is_shell_passthrough(command) is False

    def test_prefix_constant(self):
        """Verify the prefix constant is `!`."""
        assert SHELL_PASSTHROUGH_PREFIX == "!"


class TestExtractCommand:
    """Test command extraction from pass-through input."""

    @pytest.mark.parametrize(
        "command,expected",
        [
            ("!ls", "ls"),
            ("!git status", "git status"),
            ("  !  pwd  ", "pwd"),
            ("!echo  hello   world", "echo  hello   world"),
            ("!ls | head -5", "ls | head -5"),
            (
                "!find . -name '*.py' -exec wc -l {} +",
                "find . -name '*.py' -exec wc -l {} +",
            ),
        ],
    )
    def test_extract_command(self, command, expected):
        """Extract the command, stripping the bang and outer whitespace."""
        assert extract_command(command) == expected


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

    @pytest.mark.parametrize(
        "command,returncode,expected_text",
        [
            ("!false", 1, "Exit code 1"),
            ("!nonexistentcommand", 127, "127"),
        ],
    )
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_nonzero_exit_code_reported(
        self, mock_get_console, mock_run, command, returncode, expected_text
    ):
        """Non-zero exit codes (and 127 = command not found) are reported."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=returncode)

        execute_shell_passthrough(command)

        last_call = str(console.print.call_args_list[-1])
        assert expected_text in last_call

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

    @pytest.mark.parametrize(
        "command,error_msg,expected_text",
        [
            ("!forbidden", "permission denied", "permission denied"),
            ("!broken", "[red]bad[/red]", "Shell error"),
        ],
    )
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_execution_error_reported(
        self, mock_get_console, mock_run, command, error_msg, expected_text
    ):
        """Generic exceptions are caught and reported (escaped in the message)."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.side_effect = OSError(error_msg)

        execute_shell_passthrough(command)

        last_call = str(console.print.call_args_list[-1])
        assert expected_text in last_call

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
    def test_uses_current_working_directory(self, mock_cwd, mock_get_console, mock_run):
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


class TestInitialCommandPassthrough:
    """Test that shell passthrough works for initial_command and -p paths.

    Regression tests for the bug where `code-puppy "!ls"` or
    `code-puppy -p "!ls"` would send the command to the AI agent
    instead of executing it directly in the shell.

    Also covers interactive_mode(initial_command=...) as a separate
    entry point that must honour the same passthrough guarantee.
    """

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_interactive_mode_initial_command_calls_passthrough(
        self, mock_run, mock_get_console
    ):
        """interactive_mode with initial_command='!ls -la' should execute shell, not agent.

        The passthrough check fires before any agent code is reached, so
        run_prompt_with_attachments must never be invoked.
        """
        from code_puppy.cli_runner import interactive_mode

        mock_get_console.return_value = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        mock_agent = MagicMock()
        mock_agent.get_user_prompt.return_value = "Enter task:"

        with (
            patch("code_puppy.cli_runner.print_truecolor_warning"),
            patch(
                "code_puppy.cli_runner.get_cancel_agent_display_name",
                return_value="Ctrl+C",
            ),
            patch("code_puppy.messaging.emit_system_message"),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success"),
            patch("code_puppy.messaging.emit_warning"),
            patch("code_puppy.cli_runner.get_current_agent", return_value=mock_agent),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ) as mock_run_prompt,
            patch(
                "code_puppy.command_line.prompt_toolkit_completion.get_input_with_combined_completion",
                side_effect=EOFError,
            ),
        ):
            asyncio.run(interactive_mode(mock_renderer, initial_command="!ls -la"))

            # Shell command should have been executed via subprocess
            mock_run.assert_called_once()
            assert mock_run.call_args[0][0] == "ls -la"
            # Agent processing must NOT have been triggered
            mock_run_prompt.assert_not_called()

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_execute_single_prompt_calls_passthrough(self, mock_run, mock_console):
        """execute_single_prompt with '!ls' should run shell, not the agent."""
        from code_puppy.cli_runner import execute_single_prompt

        mock_console.return_value = MagicMock()
        mock_run.return_value = MagicMock(returncode=0)
        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        with (
            patch("code_puppy.cli_runner.get_current_agent") as mock_agent,
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments"
            ) as mock_run_prompt,
        ):
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

        with (
            patch("code_puppy.cli_runner.get_current_agent"),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
                return_value=(mock_response, None),
            ),
            patch("code_puppy.messaging.get_message_bus"),
            patch("code_puppy.messaging.message_queue.emit_info"),
        ):
            asyncio.run(execute_single_prompt("write me a script", mock_renderer))

            # Shell passthrough should NOT have been called
            mock_run.assert_not_called()


class TestInteractiveBootstrapMarker:
    """Regression guard for the unified-autosave migration code-review B1 finding.

    The TTY-keyed resume marker (``record_terminal_session(...)``) is
    written exactly once at the top of every ``interactive_mode`` boot,
    so a later ``-r`` invocation from the SAME TTY can find the right
    session pickle even after process restart.

    The original unified-autosave migration implementation had an 8-space indent on
    this line, parking it inside the prompt_toolkit ``except ImportError``
    block -- the call only fired when the import FAILED. Tests passed
    because nothing asserted the call fires on the happy boot path.
    This guard locks the behavior down.
    """

    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_record_terminal_session_fires_on_normal_boot(self, mock_get_console):
        from code_puppy.cli_runner import interactive_mode

        mock_get_console.return_value = MagicMock()
        mock_renderer = MagicMock()
        mock_renderer.console = MagicMock()

        mock_agent = MagicMock()
        mock_agent.get_user_prompt.return_value = "Enter task:"

        with (
            patch("code_puppy.cli_runner.print_truecolor_warning"),
            patch(
                "code_puppy.cli_runner.get_cancel_agent_display_name",
                return_value="Ctrl+C",
            ),
            patch("code_puppy.messaging.emit_system_message"),
            patch("code_puppy.messaging.emit_info"),
            patch("code_puppy.messaging.emit_success"),
            patch("code_puppy.messaging.emit_warning"),
            patch("code_puppy.cli_runner.get_current_agent", return_value=mock_agent),
            patch(
                "code_puppy.agents.agent_manager.get_current_agent",
                return_value=mock_agent,
            ),
            patch(
                "code_puppy.cli_runner.run_prompt_with_attachments",
                new_callable=AsyncMock,
            ),
            patch(
                "code_puppy.command_line.prompt_toolkit_completion."
                "get_input_with_combined_completion",
                side_effect=EOFError,
            ),
            patch(
                "code_puppy.cli_runner.get_current_session_name",
                return_value="auto_session_20260101_120000",
            ),
            patch("code_puppy.cli_runner.record_terminal_session") as mock_record,
        ):
            asyncio.run(interactive_mode(mock_renderer))

            # The whole point: marker writes on EVERY boot, not only on
            # the failed-import branch.
            mock_record.assert_called_once_with(
                "auto_session_20260101_120000", overwrite=False
            )
