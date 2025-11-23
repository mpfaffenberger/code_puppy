"""Improved tests for interactive shell mode feature."""

import subprocess
from unittest.mock import MagicMock, Mock, patch

import pytest


# =============================================================================
# TTY DETECTION TESTS
# =============================================================================


class TestTTYDetection:
    """Test the _should_use_tty() function with various command patterns."""

    @pytest.mark.parametrize(
        "command,expected",
        [
            # Always TTY commands
            ("ssh user@host", True),
            ("ssh -i key.pem user@host", True),
            ("telnet example.com", True),
            ("tmux", True),
            ("screen", True),
            # Editors - interactive by default
            ("vim file.txt", True),
            ("vi config.conf", True),
            ("nano test.py", True),
            ("emacs document.org", True),
            # Editors - batch mode (should NOT use TTY)
            ("vim -E -s script.vim", False),
            ("vim -c 'wq' file.txt", False),
            ("emacs --batch", False),
            # REPLs - interactive if no args
            ("python", True),
            ("python3", True),
            ("ipython", True),
            ("node", True),
            # REPLs - non-interactive with script
            ("python script.py", False),
            ("python -c 'print(1)'", False),
            ("node index.js", False),
            # Database CLIs - interactive by default
            ("psql -U postgres", True),
            ("mysql -u root", True),
            ("redis-cli", True),
            # Database CLIs - non-interactive with command
            ("psql -c 'SELECT 1'", False),
            ("mysql --command='SHOW TABLES'", False),
            # Regular commands (should NOT use TTY)
            ("ls -la", False),
            ("grep pattern file.txt", False),
            ("cat /etc/hosts", False),
            ("echo hello", False),
            # Piped commands (should NOT use TTY)
            ("ls | grep test", False),
            ("cat file.txt | wc -l", False),
            # Edge cases
            ("", False),  # Empty command
            ("/usr/bin/python3 script.py", False),  # Full path with script
            ("/usr/local/bin/vim file.txt", True),  # Full path to editor
        ],
    )
    def test_should_use_tty(self, command, expected):
        """Test TTY detection for various command patterns."""
        from code_puppy.command_line.core_commands import _should_use_tty

        assert _should_use_tty(command) == expected


# =============================================================================
# COMMAND EXECUTION TESTS
# =============================================================================


class TestShellCommandExecution:
    """Test the _execute_shell_command() function."""

    def test_execute_regular_command_with_output(self):
        """Test executing a regular command with stdout capture."""
        with patch("subprocess.Popen") as mock_popen:
            # Mock a successful command with output
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.stdout = iter(["line 1", "line 2"])
            mock_process.communicate.return_value = ("", "")
            mock_process.poll.return_value = 0
            mock_popen.return_value = mock_process

            from code_puppy.command_line.core_commands import _execute_shell_command

            returncode = _execute_shell_command("echo hello")

            assert returncode == 0
            # Verify Popen was called with stdout/stderr pipes
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs["shell"] is True
            assert call_kwargs["stdout"] == subprocess.PIPE
            assert call_kwargs["stderr"] == subprocess.PIPE

    def test_execute_tty_command_without_pipes(self):
        """Test executing an interactive command without stdout capture."""
        with patch("subprocess.Popen") as mock_popen:
            # Mock an interactive command (ssh)
            mock_process = MagicMock()
            mock_process.wait.return_value = 0
            mock_process.poll.return_value = 0
            mock_popen.return_value = mock_process

            from code_puppy.command_line.core_commands import _execute_shell_command

            returncode = _execute_shell_command("ssh user@host")

            assert returncode == 0
            # Verify Popen was called WITHOUT stdout/stderr pipes
            call_kwargs = mock_popen.call_args[1]
            assert call_kwargs["shell"] is True
            assert "stdout" not in call_kwargs
            assert "stderr" not in call_kwargs

    def test_execute_command_with_timeout(self):
        """Test that commands respect timeout and terminate gracefully."""
        with patch("subprocess.Popen") as mock_popen:
            # Mock a command that times out
            mock_process = MagicMock()
            mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 60)
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            from code_puppy.command_line.core_commands import _execute_shell_command

            with pytest.raises(subprocess.TimeoutExpired):
                _execute_shell_command("sleep 1000", timeout=1)

            # Verify termination was attempted
            mock_process.send_signal.assert_called_once()

    def test_execute_command_cleanup_on_keyboard_interrupt(self):
        """Test that process is cleaned up when user presses Ctrl+C."""
        with patch("subprocess.Popen") as mock_popen:
            # Mock a command that gets interrupted
            mock_process = MagicMock()
            mock_process.stdout = MagicMock()
            mock_process.stdout.__iter__ = Mock(side_effect=KeyboardInterrupt)
            mock_process.poll.return_value = None
            mock_popen.return_value = mock_process

            from code_puppy.command_line.core_commands import _execute_shell_command

            with pytest.raises(KeyboardInterrupt):
                _execute_shell_command("long_running_command")

            # Verify process was terminated
            mock_process.terminate.assert_called_once()

    def test_execute_command_not_found(self):
        """Test handling of commands that don't exist."""
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.side_effect = FileNotFoundError("command not found")

            from code_puppy.command_line.core_commands import _execute_shell_command

            returncode = _execute_shell_command("nonexistent_command_xyz")

            # Should return standard 'command not found' exit code
            assert returncode == 127


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestShellCommandHandler:
    """Test the /shell command handler."""

    def test_shell_command_with_single_arg(self):
        """Test /shell <command> executes the command."""
        with patch(
            "code_puppy.command_line.core_commands._execute_shell_command"
        ) as mock_exec:
            mock_exec.return_value = 0

            from code_puppy.command_line.core_commands import handle_shell_command

            result = handle_shell_command("/shell echo test")

            assert result is True
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args
            assert "echo test" in call_args[0]

    def test_shell_command_alias(self):
        """Test /! works as an alias for /shell."""
        with patch(
            "code_puppy.command_line.core_commands._execute_shell_command"
        ) as mock_exec:
            mock_exec.return_value = 0

            from code_puppy.command_line.core_commands import handle_shell_command

            result = handle_shell_command("/! ls -la")

            assert result is True
            mock_exec.assert_called_once()


# =============================================================================
# SECURITY TESTS
# =============================================================================


class TestSecurityDocumentation:
    """Ensure security warnings are present in code."""

    def test_security_warning_in_docstring(self):
        """Verify security warning exists in function docstring."""
        from code_puppy.command_line.core_commands import _execute_shell_command

        docstring = _execute_shell_command.__doc__
        assert "SECURITY" in docstring
        assert "shell=True" in docstring
        assert "injection" in docstring.lower()

    def test_shell_true_is_documented(self):
        """Verify shell=True usage is documented in handler."""
        from code_puppy.command_line.core_commands import handle_shell_command

        docstring = handle_shell_command.__doc__
        assert "SECURITY" in docstring or "WARNING" in docstring
        assert "shell=True" in docstring


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================


class TestInteractiveCommandsConfig:
    """Test the INTERACTIVE_COMMANDS configuration."""

    def test_interactive_commands_structure(self):
        """Verify INTERACTIVE_COMMANDS has expected structure."""
        from code_puppy.command_line.core_commands import INTERACTIVE_COMMANDS

        # Should be a dict with category keys
        assert isinstance(INTERACTIVE_COMMANDS, dict)
        assert len(INTERACTIVE_COMMANDS) > 0

        # Check for expected categories
        expected_categories = {"remote", "editors", "repls", "databases"}
        assert expected_categories.issubset(INTERACTIVE_COMMANDS.keys())

        # Each category should be a set
        for category, commands in INTERACTIVE_COMMANDS.items():
            assert isinstance(commands, set)
            assert len(commands) > 0

    def test_get_all_interactive_commands(self):
        """Test flattening of categorized commands."""
        from code_puppy.command_line.core_commands import (
            INTERACTIVE_COMMANDS,
            _get_all_interactive_commands,
        )

        all_commands = _get_all_interactive_commands()

        # Should be a set
        assert isinstance(all_commands, set)

        # Should contain commands from all categories
        assert "ssh" in all_commands
        assert "vim" in all_commands
        assert "python" in all_commands

        # Count should match sum of all categories
        expected_count = sum(len(cmds) for cmds in INTERACTIVE_COMMANDS.values())
        # (May be less due to duplicates across categories, but shouldn't be more)
        assert len(all_commands) <= expected_count


# =============================================================================
# PYTEST FIXTURES
# =============================================================================


@pytest.fixture
def messaging_mocks():
    """Fixture to mock all messaging functions."""
    with (
        patch("code_puppy.messaging.emit_info") as mock_info,
        patch("code_puppy.messaging.emit_error") as mock_error,
        patch("code_puppy.messaging.emit_warning") as mock_warning,
        patch("code_puppy.messaging.emit_success") as mock_success,
    ):
        yield {
            "info": mock_info,
            "error": mock_error,
            "warning": mock_warning,
            "success": mock_success,
        }


@pytest.fixture
def mock_subprocess():
    """Fixture to mock subprocess.Popen."""
    with patch("subprocess.Popen") as mock:
        process = MagicMock()
        process.returncode = 0
        process.poll.return_value = 0
        process.stdout = iter([])
        process.communicate.return_value = ("", "")
        mock.return_value = process
        yield mock, process
