"""Tests for shell pass-through feature.

The `!` prefix allows users to run shell commands directly from the
Code Puppy prompt without any agent processing.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import code_puppy.command_line.shell_passthrough as shell_passthrough_module
from code_puppy.command_line.shell_passthrough import (
    _AMBIGUOUS_CLI_COMMANDS,
    _BANNER_NAME,
    _PS_CMDLET_RE,
    _SHELL_INTENT_RE,
    KNOWN_CLI_COMMANDS,
    SHELL_PASSTHROUGH_PREFIX,
    _format_banner,
    _get_platform_shell,
    execute_shell_passthrough,
    extract_command,
    is_known_cli_command,
    is_powershell_cmdlet,
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


class TestIsKnownCliCommand:
    """Test auto-detection of well-known CLI commands.

    Users should be able to type ``ls -la`` or ``git status`` directly and
    have Code Puppy route the input to the shell without touching the AI agent
    (zero tokens consumed).

    The detection uses a three-stage filter:
      1. First word must be in KNOWN_CLI_COMMANDS.
      2. Executable must exist on PATH (shutil.which).
      3. Ambiguous English words (find, open, …) require shell-intent evidence.
    """

    # ── Positive cases ────────────────────────────────────────────────────

    def test_ls_alone(self):
        """Bare `ls` is a known CLI command."""
        with patch("shutil.which", return_value="/bin/ls"):
            assert is_known_cli_command("ls") is True

    def test_ls_with_flags(self):
        """`ls -la` is auto-detected."""
        with patch("shutil.which", return_value="/bin/ls"):
            assert is_known_cli_command("ls -la") is True

    def test_ls_pipe_grep(self):
        """`ls | grep test` is auto-detected — pipe is shell-intent evidence."""
        with patch("shutil.which", return_value="/bin/ls"):
            assert is_known_cli_command("ls | grep test") is True

    def test_git_status(self):
        """`git status` is auto-detected."""
        with patch("shutil.which", return_value="/usr/bin/git"):
            assert is_known_cli_command("git status") is True

    def test_grep_pattern_with_flag(self):
        """`grep -r foo .` is auto-detected (has a flag)."""
        with patch("shutil.which", return_value="/bin/grep"):
            assert is_known_cli_command("grep -r foo .") is True

    def test_pwd_single_word(self):
        """Single-word known command is accepted without shell-intent check."""
        with patch("shutil.which", return_value="/bin/pwd"):
            assert is_known_cli_command("pwd") is True

    def test_leading_whitespace(self):
        """Leading whitespace before a known command is tolerated."""
        with patch("shutil.which", return_value="/bin/ls"):
            assert is_known_cli_command("  ls -la") is True

    def test_case_insensitive_first_word(self):
        """First-word check is case-insensitive (LS → ls)."""
        with patch("shutil.which", return_value="/bin/ls"):
            assert is_known_cli_command("LS -la") is True

    def test_known_commands_set_non_empty(self):
        """KNOWN_CLI_COMMANDS must contain at least the basics."""
        for cmd in ("ls", "git", "grep", "cat", "pwd", "find"):
            assert cmd in KNOWN_CLI_COMMANDS

    def test_find_with_flag_passes_ambiguity_guard(self):
        """`find . -name foo` has a flag → passes ambiguity guard."""
        with patch("shutil.which", return_value="/usr/bin/find"):
            assert is_known_cli_command("find . -name foo") is True

    def test_find_with_path_passes_ambiguity_guard(self):
        """`find ./src` has a path → passes ambiguity guard."""
        with patch("shutil.which", return_value="/usr/bin/find"):
            assert is_known_cli_command("find ./src") is True

    def test_find_with_pipe_passes_ambiguity_guard(self):
        """`find . | head` has a pipe → passes ambiguity guard."""
        with patch("shutil.which", return_value="/usr/bin/find"):
            assert is_known_cli_command("find . | head") is True

    # ── Negative cases ────────────────────────────────────────────────────

    def test_natural_language_not_detected(self):
        """Natural language prompts must NOT be auto-detected as CLI commands."""
        assert is_known_cli_command("write me a python script") is False

    def test_slash_command_excluded(self):
        """`/help` is a Code Puppy command, not a shell command."""
        assert is_known_cli_command("/help") is False

    def test_bang_prefix_excluded(self):
        """`!ls` is already handled by `is_shell_passthrough`; skip here."""
        assert is_known_cli_command("!ls") is False

    def test_unknown_command(self):
        """An unknown first word is not auto-detected."""
        assert is_known_cli_command("frobnicator --foo") is False

    def test_empty_string(self):
        """Empty input is not a CLI command."""
        assert is_known_cli_command("") is False

    def test_whitespace_only(self):
        """Whitespace-only input is not a CLI command."""
        assert is_known_cli_command("   ") is False

    def test_command_not_on_path_rejected(self):
        """Known command name is rejected when not installed on PATH."""
        with patch("shutil.which", return_value=None):
            assert is_known_cli_command("kubectl get pods") is False

    # ── Ambiguity guard (stage 3) ─────────────────────────────────────────

    def test_find_natural_language_blocked(self):
        """`find memory leak in parser` looks like NL — blocked by ambiguity guard."""
        with patch("shutil.which", return_value="/usr/bin/find"):
            assert is_known_cli_command("find memory leak in parser") is False

    def test_open_natural_language_blocked(self):
        """`open the config file` looks like NL — blocked."""
        with patch("shutil.which", return_value="/usr/bin/open"):
            assert is_known_cli_command("open the config file") is False

    def test_date_natural_language_blocked(self):
        """`date of the last release` looks like NL — blocked."""
        with patch("shutil.which", return_value="/bin/date"):
            assert is_known_cli_command("date of the last release") is False

    def test_type_natural_language_blocked(self):
        """`type the password` looks like NL — blocked."""
        with patch("shutil.which", return_value="/usr/bin/type"):
            assert is_known_cli_command("type the password") is False

    def test_ambiguous_set_contains_expected_words(self):
        """_AMBIGUOUS_CLI_COMMANDS must include the risky English words."""
        for word in ("find", "open", "date", "type", "history", "who"):
            assert word in _AMBIGUOUS_CLI_COMMANDS

    def test_shell_intent_re_matches_flag(self):
        """_SHELL_INTENT_RE detects a CLI flag."""
        assert _SHELL_INTENT_RE.search("find . -name foo") is not None

    def test_shell_intent_re_matches_pipe(self):
        """_SHELL_INTENT_RE detects a pipe operator."""
        assert _SHELL_INTENT_RE.search("find . | head") is not None

    def test_shell_intent_re_matches_relative_path(self):
        """_SHELL_INTENT_RE detects a relative path."""
        assert _SHELL_INTENT_RE.search("find ./src") is not None

    def test_shell_intent_re_no_match_on_natural_language(self):
        """_SHELL_INTENT_RE does NOT match plain English prose."""
        assert _SHELL_INTENT_RE.search("memory leak in parser") is None

    # ── Windows path detection (shell intent regex) ───────────────────────

    def test_shell_intent_re_matches_windows_backslash_relative(self):
        r"""_SHELL_INTENT_RE detects Windows relative path ``.\src``."""
        assert _SHELL_INTENT_RE.search(r"find .\src") is not None

    def test_shell_intent_re_matches_windows_parent_path(self):
        r"""_SHELL_INTENT_RE detects Windows parent path ``..\config``."""
        assert _SHELL_INTENT_RE.search(r"find ..\config") is not None

    def test_shell_intent_re_matches_windows_drive_letter(self):
        r"""_SHELL_INTENT_RE detects Windows absolute path ``C:\Users``."""
        assert _SHELL_INTENT_RE.search(r"find C:\Users") is not None


class TestIsPowershellCmdlet:
    """Test auto-detection of PowerShell Verb-Noun cmdlets.

    PowerShell Core (pwsh) runs on Windows, macOS, AND Linux.
    Detection is gated by ``pwsh``/``powershell`` being on PATH — not by
    platform.  The PATH check is cached, so we reset the cache in each test.
    """

    def _reset_ps_cache(self):
        """Reset the cached PowerShell availability before each test."""
        shell_passthrough_module._powershell_available = None

    # ── Positive cases (pwsh on PATH) ─────────────────────────────────────

    def test_get_childitem_detected(self):
        """Get-ChildItem is a valid PowerShell cmdlet."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Get-ChildItem") is True

    def test_set_location_detected(self):
        """Set-Location C:\\projects is detected."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Set-Location C:\\projects") is True

    def test_invoke_webrequest_detected(self):
        """Invoke-WebRequest is detected."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Invoke-WebRequest https://example.com") is True

    def test_select_string_detected(self):
        """Select-String is detected (PowerShell grep equivalent)."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Select-String -Pattern foo") is True

    def test_works_on_macos_with_pwsh(self):
        """PowerShell cmdlets work on macOS when pwsh is installed."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Get-ChildItem") is True

    def test_works_on_linux_with_pwsh(self):
        """PowerShell cmdlets work on Linux when pwsh is installed."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/bin/pwsh"):
            assert is_powershell_cmdlet("Get-ChildItem") is True

    # ── Negative cases ────────────────────────────────────────────────────

    def test_natural_language_not_detected(self):
        """'Get some coffee' does NOT match Verb-Noun pattern."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("Get some coffee") is False

    def test_no_powershell_on_path_rejected(self):
        """Even valid cmdlets are rejected if pwsh/powershell not on PATH."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value=None):
            assert is_powershell_cmdlet("Get-ChildItem") is False

    def test_bang_prefix_excluded(self):
        """!Get-ChildItem is handled by is_shell_passthrough."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("!Get-ChildItem") is False

    def test_slash_prefix_excluded(self):
        """/Get-ChildItem is a Code Puppy command."""
        self._reset_ps_cache()
        with patch("shutil.which", return_value="/usr/local/bin/pwsh"):
            assert is_powershell_cmdlet("/Get-ChildItem") is False

    def test_ps_cmdlet_regex_pattern(self):
        """_PS_CMDLET_RE matches the Verb-Noun pattern."""
        assert _PS_CMDLET_RE.match("Get-ChildItem") is not None
        assert _PS_CMDLET_RE.match("Set-Location") is not None
        assert _PS_CMDLET_RE.match("Invoke-WebRequest") is not None
        assert _PS_CMDLET_RE.match("ConvertFrom-Json") is not None
        assert _PS_CMDLET_RE.match("Get some coffee") is None
        assert _PS_CMDLET_RE.match("ls -la") is None


class TestGetPlatformShell:
    """Test platform-aware shell resolution.

    _get_platform_shell() caches its result per session, so each test must
    reset the cache to exercise different branches.
    """

    def _reset_shell_cache(self):
        """Reset the cached platform shell before each test."""
        shell_passthrough_module._cached_platform_shell = None

    def test_unix_uses_shell_env(self):
        """On Unix, _get_platform_shell uses $SHELL."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch.dict(os.environ, {"SHELL": "/bin/zsh"}),
        ):
            mock_sys.platform = "linux"
            assert _get_platform_shell() == ["/bin/zsh", "-c"]

    def test_unix_fallback_to_sh(self):
        """On Unix without $SHELL, fallback to /bin/sh."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_sys.platform = "linux"
            assert _get_platform_shell() == ["/bin/sh", "-c"]

    def test_windows_prefers_pwsh(self):
        """On Windows, prefer pwsh over powershell."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch("shutil.which", side_effect=lambda x: "C:\\pwsh.exe" if x == "pwsh" else None),
        ):
            mock_sys.platform = "win32"
            assert _get_platform_shell() == ["pwsh", "-Command"]

    def test_windows_falls_back_to_powershell(self):
        """On Windows without pwsh, fall back to powershell."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch(
                "shutil.which",
                side_effect=lambda x: "C:\\powershell.exe" if x == "powershell" else None,
            ),
        ):
            mock_sys.platform = "win32"
            assert _get_platform_shell() == ["powershell", "-Command"]

    def test_windows_falls_back_to_cmd(self):
        """On Windows without pwsh or powershell, fall back to cmd."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch("shutil.which", return_value=None),
        ):
            mock_sys.platform = "win32"
            assert _get_platform_shell() == ["cmd", "/c"]

    def test_result_is_cached(self):
        """Second call returns cached result without re-querying shutil.which."""
        self._reset_shell_cache()
        with (
            patch("code_puppy.command_line.shell_passthrough.sys") as mock_sys,
            patch.dict(os.environ, {"SHELL": "/bin/bash"}),
        ):
            mock_sys.platform = "linux"
            first = _get_platform_shell()
            assert first == ["/bin/bash", "-c"]

        # Second call should return cached value even without the patch
        second = _get_platform_shell()
        assert second == ["/bin/bash", "-c"]


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

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_successful_command(self, mock_get_console, mock_run, mock_shell):
        """Successful commands show a success message."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)
        mock_shell.return_value = ["/bin/sh", "-c"]

        execute_shell_passthrough("!echo hello")

        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs[1]["shell"] is False
        # Command is passed as [*shell_args, command]
        assert call_kwargs[0][0] == ["/bin/sh", "-c", "echo hello"]

        # Should have printed banner, context line, and success
        assert console.print.call_count == 3
        last_call = str(console.print.call_args_list[-1])
        assert "Done" in last_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_failed_command_shows_exit_code(self, mock_get_console, mock_run, _):
        """Non-zero exit codes show the exit code."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=1)

        execute_shell_passthrough("!false")

        last_call = str(console.print.call_args_list[-1])
        assert "Exit code 1" in last_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_exit_code_127(self, mock_get_console, mock_run, _):
        """Exit code 127 (command not found) is reported properly."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=127)

        execute_shell_passthrough("!nonexistentcommand")

        last_call = str(console.print.call_args_list[-1])
        assert "127" in last_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_keyboard_interrupt(self, mock_get_console, mock_run, _):
        """Ctrl+C during execution shows interrupted message."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.side_effect = KeyboardInterrupt()

        execute_shell_passthrough("!sleep 999")

        last_call = str(console.print.call_args_list[-1])
        assert "Interrupted" in last_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_generic_exception(self, mock_get_console, mock_run, _):
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

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_inherits_stdio(self, mock_get_console, mock_run, _):
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

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.os.getcwd", return_value="/tmp")
    def test_uses_current_working_directory(self, mock_cwd, mock_get_console, mock_run, _):
        """Command should run in the current working directory."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!ls")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == "/tmp"

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_banner_shown_before_command(self, mock_get_console, mock_run, _):
        """The banner should display with SHELL PASSTHROUGH label."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!git status")

        first_call = str(console.print.call_args_list[0])
        assert "SHELL PASSTHROUGH" in first_call
        assert "git status" in first_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_context_hint_shown(self, mock_get_console, mock_run, _):
        """A context line should clarify this bypasses the AI."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo hi")

        second_call = str(console.print.call_args_list[1])
        assert "Bypassing AI" in second_call

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_rich_markup_escaped_in_command(self, mock_get_console, mock_run, _):
        """Commands with Rich markup chars should be escaped to prevent injection."""
        console = self._mock_console()
        mock_get_console.return_value = console
        mock_run.return_value = MagicMock(returncode=0)

        execute_shell_passthrough("!echo [bold red]oops[/bold red]")

        # Command is the last element of [*shell_args, command]
        assert mock_run.call_args[0][0][-1] == "echo [bold red]oops[/bold red]"

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    def test_rich_markup_escaped_in_error(self, mock_get_console, mock_run, _):
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

    Also covers interactive_mode(initial_command=...) as a separate
    entry point that must honour the same passthrough guarantee.
    """

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_interactive_mode_initial_command_calls_passthrough(
        self, mock_run, mock_get_console, _
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
            patch("code_puppy.command_line.motd.print_motd"),
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
            # Command is last element: ["/bin/sh", "-c", "ls -la"]
            assert mock_run.call_args[0][0][-1] == "ls -la"
            # Agent processing must NOT have been triggered
            mock_run_prompt.assert_not_called()

    @patch("code_puppy.command_line.shell_passthrough._get_platform_shell", return_value=["/bin/sh", "-c"])
    @patch("code_puppy.command_line.shell_passthrough._get_console")
    @patch("code_puppy.command_line.shell_passthrough.subprocess.run")
    def test_execute_single_prompt_calls_passthrough(self, mock_run, mock_console, _):
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
            # Command is last element: ["/bin/sh", "-c", "ls -la"]
            assert mock_run.call_args[0][0][-1] == "ls -la"
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
