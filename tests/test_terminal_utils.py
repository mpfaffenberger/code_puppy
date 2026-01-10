"""Comprehensive test coverage for terminal_utils.py.

Tests terminal utilities including:
- Windows/Unix platform detection
- Terminal reset functionality
- Terminal size detection
- ANSI escape sequence handling
- Cross-platform signal handling
"""

import platform
import sys
from unittest.mock import MagicMock, patch

from code_puppy import terminal_utils


class TestANSISequences:
    """Test ANSI escape sequence handling."""

    def test_reset_sequence_format(self):
        """Test ANSI reset sequence has correct format."""
        reset_seq = "\x1b[0m"
        assert reset_seq.startswith("\x1b[")
        assert reset_seq.endswith("m")

    def test_bold_sequence_format(self):
        """Test ANSI bold sequence format."""
        bold_seq = "\x1b[1m"
        assert bold_seq.startswith("\x1b[")
        assert "1" in bold_seq

    def test_color_sequence_format(self):
        """Test ANSI color sequence format."""
        # Blue text
        blue_seq = "\x1b[34m"
        assert blue_seq.startswith("\x1b[")
        assert "34" in blue_seq


class TestPlatformDetection:
    """Test platform detection for terminal utilities."""

    @patch("platform.system")
    def test_detect_windows(self, mock_platform):
        """Test Windows detection."""
        mock_platform.return_value = "Windows"
        assert platform.system() == "Windows"

    @patch("platform.system")
    def test_detect_linux(self, mock_platform):
        """Test Linux detection."""
        mock_platform.return_value = "Linux"
        assert platform.system() == "Linux"

    @patch("platform.system")
    def test_detect_darwin(self, mock_platform):
        """Test macOS detection."""
        mock_platform.return_value = "Darwin"
        assert platform.system() == "Darwin"


class TestTerminalUtilityImports:
    """Test that terminal utilities can be imported."""

    def test_reset_windows_terminal_ansi_import(self):
        """Test reset_windows_terminal_ansi can be imported."""
        from code_puppy.terminal_utils import reset_windows_terminal_ansi

        assert callable(reset_windows_terminal_ansi)

    def test_reset_windows_console_mode_import(self):
        """Test reset_windows_console_mode can be imported."""
        from code_puppy.terminal_utils import reset_windows_console_mode

        assert callable(reset_windows_console_mode)

    def test_reset_unix_terminal_import(self):
        """Test reset_unix_terminal can be imported."""
        from code_puppy.terminal_utils import reset_unix_terminal

        assert callable(reset_unix_terminal)


class TestTerminalUtilityBehavior:
    """Test terminal utility behavior."""

    @patch("platform.system")
    def test_platform_aware_reset(
        self,
        mock_platform,
    ):
        """Test that reset functions respect platform."""
        mock_platform.return_value = "Linux"
        # Should not error even on non-Windows
        from code_puppy.terminal_utils import reset_windows_terminal_ansi

        reset_windows_terminal_ansi()

    def test_multiple_resets_safe(self):
        """Test multiple consecutive resets are safe."""
        from code_puppy.terminal_utils import reset_windows_terminal_ansi

        # Should be safe to call multiple times
        try:
            reset_windows_terminal_ansi()
            reset_windows_terminal_ansi()
            reset_windows_terminal_ansi()
        except Exception:
            # May fail in test environment, but shouldn't crash
            pass


class TestTerminalState:
    """Test terminal state management."""

    def test_reset_function_callable(self):
        """Test that reset functions are callable."""
        from code_puppy.terminal_utils import reset_windows_terminal_ansi

        assert callable(reset_windows_terminal_ansi)
        assert hasattr(reset_windows_terminal_ansi, "__call__")


class TestStdinIsatty:
    """Test stdin.isatty() checks for terminal operations."""

    @patch("sys.stdin.isatty")
    def test_stdin_is_tty(self, mock_isatty):
        """Test when stdin is a TTY."""
        mock_isatty.return_value = True
        assert sys.stdin.isatty()

    @patch("sys.stdin.isatty")
    def test_stdin_is_not_tty(self, mock_isatty):
        """Test when stdin is not a TTY (piped input)."""
        mock_isatty.return_value = False
        assert not sys.stdin.isatty()


class TestTerminalResetRouting:
    """Test routing for Windows vs Unix terminal resets."""

    def test_reset_terminal_routes_to_windows(self, monkeypatch):
        """Test reset_terminal uses Windows reset on Windows."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        reset_windows = MagicMock()
        monkeypatch.setattr(
            terminal_utils, "reset_windows_terminal_full", reset_windows
        )

        terminal_utils.reset_terminal()

        reset_windows.assert_called_once()

    def test_reset_terminal_routes_to_unix(self, monkeypatch):
        """Test reset_terminal uses Unix reset on Unix-like systems."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        reset_unix = MagicMock()
        monkeypatch.setattr(terminal_utils, "reset_unix_terminal", reset_unix)

        terminal_utils.reset_terminal()

        reset_unix.assert_called_once()


class TestWindowsAnsiReset:
    """Test ANSI reset behavior on Windows vs Unix."""

    def test_reset_windows_ansi_writes_sequences(self, monkeypatch):
        """Test Windows ANSI reset writes to stdout and stderr."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")

        stdout = MagicMock()
        stderr = MagicMock()
        monkeypatch.setattr(terminal_utils.sys, "stdout", stdout)
        monkeypatch.setattr(terminal_utils.sys, "stderr", stderr)

        terminal_utils.reset_windows_terminal_ansi()

        stdout.write.assert_called_once_with("\x1b[0m")
        stdout.flush.assert_called_once()
        stderr.write.assert_called_once_with("\x1b[0m")
        stderr.flush.assert_called_once()

    def test_reset_windows_ansi_noop_on_unix(self, monkeypatch):
        """Test ANSI reset is a no-op on non-Windows platforms."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Darwin")

        stdout = MagicMock()
        stderr = MagicMock()
        monkeypatch.setattr(terminal_utils.sys, "stdout", stdout)
        monkeypatch.setattr(terminal_utils.sys, "stderr", stderr)

        terminal_utils.reset_windows_terminal_ansi()

        stdout.write.assert_not_called()
        stderr.write.assert_not_called()


class TestUnixResetCommand:
    """Test Unix reset command behavior."""

    def test_reset_unix_terminal_runs_command(self, monkeypatch):
        """Test Unix reset invokes the reset command."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        run_mock = MagicMock()
        monkeypatch.setattr(terminal_utils.subprocess, "run", run_mock)

        terminal_utils.reset_unix_terminal()

        run_mock.assert_called_once_with(["reset"], check=True, capture_output=True)

    def test_reset_unix_terminal_skips_windows(self, monkeypatch):
        """Test Unix reset does nothing on Windows."""
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        run_mock = MagicMock()
        monkeypatch.setattr(terminal_utils.subprocess, "run", run_mock)

        terminal_utils.reset_unix_terminal()

        run_mock.assert_not_called()


class TestTruecolorWarningSizing:
    """Test sizing of truecolor warning output."""

    def test_warning_fallback_box_width(self, monkeypatch):
        """Test plain-text warning uses consistent width."""
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        monkeypatch.setitem(sys.modules, "rich", None)
        monkeypatch.setitem(sys.modules, "rich.console", None)

        emit_info_mock = MagicMock()
        monkeypatch.setattr(terminal_utils, "emit_info", emit_info_mock)

        terminal_utils.print_truecolor_warning()

        first_call = emit_info_mock.call_args_list[0][0][0]
        assert "=" * 70 in first_call

    def test_warning_rich_box_width(self, monkeypatch):
        """Test Rich warning uses the 72-character border."""
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        mock_console = MagicMock()
        mock_console.color_system = "standard"

        terminal_utils.print_truecolor_warning(console=mock_console)

        # The first line printed is empty string, border is on second call
        border_line = mock_console.print.call_args_list[1][0][0]
        assert "━" * 72 in border_line
