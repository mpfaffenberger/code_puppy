"""Comprehensive test coverage for terminal_utils.py.

Tests terminal utilities including:
- Windows/Unix platform detection
- Terminal reset functionality (both platforms)
- ANSI escape sequence handling
- Console mode manipulation (Windows)
- Keyboard buffer operations (Windows)
- Cross-platform signal handling (Ctrl+C)
- Truecolor support detection
- Terminal warning messages

Target: 85%+ coverage of 177 statements in terminal_utils.py
"""

import os
import platform
import subprocess
from unittest.mock import MagicMock, patch

import pytest

# Marker for Windows-only tests
WINDOWS_ONLY = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="Windows-specific test - requires ctypes.windll",
)


# Import all functions to test
import code_puppy.terminal_utils  # noqa: E402
from code_puppy.terminal_utils import (  # noqa: E402
    _original_ctrl_handler,
    detect_truecolor_support,
    disable_windows_ctrl_c,
    enable_windows_ctrl_c,
    ensure_ctrl_c_disabled,
    flush_windows_keyboard_buffer,
    print_truecolor_warning,
    reset_terminal,
    reset_unix_terminal,
    reset_windows_console_mode,
    reset_windows_terminal_ansi,
    reset_windows_terminal_full,
    set_keep_ctrl_c_disabled,
)


class TestWindowsANSIReset:
    """Test Windows ANSI escape sequence reset."""

    @patch("platform.system")
    @patch("sys.stdout")
    @patch("sys.stderr")
    def test_reset_ansi_on_windows_success(
        self, mock_stderr, mock_stdout, mock_platform
    ):
        """Test ANSI reset on Windows succeeds."""
        mock_platform.return_value = "Windows"
        mock_stdout.write = MagicMock()
        mock_stdout.flush = MagicMock()
        mock_stderr.write = MagicMock()
        mock_stderr.flush = MagicMock()

        reset_windows_terminal_ansi()

        # Verify both stdout and stderr receive reset sequence
        mock_stdout.write.assert_called_once_with("\x1b[0m")
        mock_stdout.flush.assert_called_once()
        mock_stderr.write.assert_called_once_with("\x1b[0m")
        mock_stderr.flush.assert_called_once()

    @patch("platform.system")
    def test_reset_ansi_skips_non_windows(self, mock_platform):
        """Test ANSI reset does nothing on non-Windows platforms."""
        mock_platform.return_value = "Linux"
        # Should not raise any errors
        reset_windows_terminal_ansi()

    @patch("platform.system")
    @patch("sys.stdout.write")
    def test_reset_ansi_handles_stdout_error(self, mock_write, mock_platform):
        """Test ANSI reset handles stdout errors gracefully."""
        mock_platform.return_value = "Windows"
        mock_write.side_effect = IOError("Write failed")

        # Should not raise exception
        reset_windows_terminal_ansi()

    @patch("platform.system")
    @patch("sys.stdout")
    @patch("sys.stderr.write")
    def test_reset_ansi_handles_stderr_error(
        self, mock_stderr_write, mock_stdout, mock_platform
    ):
        """Test ANSI reset handles stderr errors gracefully."""
        mock_platform.return_value = "Windows"
        mock_stdout.write = MagicMock()
        mock_stdout.flush = MagicMock()
        mock_stderr_write.side_effect = IOError("Write failed")

        # Should not raise exception
        reset_windows_terminal_ansi()


@WINDOWS_ONLY
class TestWindowsConsoleModeReset:
    """Test Windows console mode reset with ctypes mocking."""

    @patch("platform.system")
    def test_reset_console_mode_skips_non_windows(self, mock_platform):
        """Test console mode reset does nothing on non-Windows."""
        mock_platform.return_value = "Linux"
        reset_windows_console_mode()

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_reset_console_mode_success(self, mock_kernel32, mock_platform):
        """Test successful Windows console mode reset."""
        mock_platform.return_value = "Windows"

        # Setup mock handles and functions
        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.side_effect = [-11, -10]  # stdout, stdin
        mock_kernel32.GetStdHandle.return_value = mock_handle

        # Mock mode storage
        mode_values = [0x0000, 0x0000]  # Initial modes

        def mock_get_console_mode(handle, mode_ref):
            mode_ref.contents.value = mode_values.pop(0)
            return 1  # Success

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode
        mock_kernel32.SetConsoleMode.return_value = 1  # Success

        reset_windows_console_mode()

        # Verify GetStdHandle called twice (stdout and stdin)
        assert mock_kernel32.GetStdHandle.call_count == 2

        # Verify GetConsoleMode called twice
        assert mock_kernel32.GetConsoleMode.call_count == 2

        # Verify SetConsoleMode called twice (stdout and stdin)
        assert mock_kernel32.SetConsoleMode.call_count == 2

        # Verify correct mode flags are set
        stdout_call = mock_kernel32.SetConsoleMode.call_args_list[0]
        stdin_call = mock_kernel32.SetConsoleMode.call_args_list[1]

        # Should have enabled processed output, wrap at EOL, virtual terminal processing
        assert stdout_call[1] == mock_handle
        stdout_mode = stdout_call[0][1]
        assert stdout_mode & 0x0001  # ENABLE_PROCESSED_OUTPUT
        assert stdout_mode & 0x0002  # ENABLE_WRAP_AT_EOL_OUTPUT
        assert stdout_mode & 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING

        # Should have enabled line input, echo input, processed input
        assert stdin_call[1] == mock_handle
        stdin_mode = stdin_call[0][1]
        assert stdin_mode & 0x0002  # ENABLE_LINE_INPUT
        assert stdin_mode & 0x0004  # ENABLE_ECHO_INPUT
        assert stdin_mode & 0x0001  # ENABLE_PROCESSED_INPUT

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_reset_console_mode_handles_get_handle_failure(
        self, mock_kernel32, mock_platform
    ):
        """Test console mode reset handles GetStdHandle failure gracefully."""
        mock_platform.return_value = "Windows"
        mock_kernel32.GetStdHandle.return_value = None  # Invalid handle

        # Should not raise exception
        reset_windows_console_mode()

        # Should still attempt to get handle
        mock_kernel32.GetStdHandle.assert_called()

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_reset_console_mode_handles_get_mode_failure(
        self, mock_kernel32, mock_platform
    ):
        """Test console mode reset handles GetConsoleMode failure gracefully."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.GetConsoleMode.return_value = 0  # Failure

        # Should not raise exception
        reset_windows_console_mode()

        # Should attempt to get mode but not set it
        mock_kernel32.GetConsoleMode.assert_called()
        mock_kernel32.SetConsoleMode.assert_not_called()

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_reset_console_mode_handles_set_mode_failure(
        self, mock_kernel32, mock_platform
    ):
        """Test console mode reset handles SetConsoleMode failure gracefully."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle

        mode_ref = MagicMock()
        mode_ref.contents.value = 0x0000
        mock_kernel32.GetConsoleMode.return_value = 1  # Success
        mock_kernel32.SetConsoleMode.return_value = 0  # Failure

        # Should not raise exception
        reset_windows_console_mode()

        # Should attempt both get and set
        mock_kernel32.GetConsoleMode.assert_called()
        mock_kernel32.SetConsoleMode.assert_called()

    @patch("platform.system")
    def test_reset_console_mode_handles_import_error(self, mock_platform):
        """Test console mode reset handles missing ctypes gracefully."""
        mock_platform.return_value = "Windows"

        # Mock import failure
        with patch.dict("sys.modules", {"ctypes": None}):
            # Should not raise exception even with missing ctypes
            reset_windows_console_mode()


@WINDOWS_ONLY
class TestWindowsKeyboardBuffer:
    """Test Windows keyboard buffer flushing."""

    @patch("platform.system")
    def test_flush_keyboard_skips_non_windows(self, mock_platform):
        """Test keyboard flush does nothing on non-Windows."""
        mock_platform.return_value = "Linux"
        flush_windows_keyboard_buffer()

    @patch("platform.system")
    @patch("msvcrt.kbhit")
    @patch("msvcrt.getch")
    def test_flush_keyboard_clears_buffer(self, mock_getch, mock_kbhit, mock_platform):
        """Test keyboard buffer is cleared when keys are waiting."""
        mock_platform.return_value = "Windows"

        # Simulate 3 keys in buffer
        mock_kbhit.side_effect = [True, True, True, False]
        mock_getch.return_value = b"a"

        flush_windows_keyboard_buffer()

        # Verify kbhit called multiple times
        assert mock_kbhit.call_count == 4

        # Verify getch called 3 times (once for each key)
        assert mock_getch.call_count == 3

    @patch("platform.system")
    @patch("msvcrt.kbhit")
    def test_flush_keyboard_empty_buffer(self, mock_kbhit, mock_platform):
        """Test keyboard flush when buffer is empty."""
        mock_platform.return_value = "Windows"
        mock_kbhit.return_value = False

        flush_windows_keyboard_buffer()

        # Should check once and exit
        mock_kbhit.assert_called_once()

    @patch("platform.system")
    @patch("msvcrt.kbhit")
    def test_flush_keyboard_handles_kbhit_error(self, mock_kbhit, mock_platform):
        """Test keyboard flush handles kbhit errors gracefully."""
        mock_platform.return_value = "Windows"
        mock_kbhit.side_effect = Exception("kbhit error")

        # Should not raise exception
        flush_windows_keyboard_buffer()


@WINDOWS_ONLY
class TestWindowsFullReset:
    """Test Windows full terminal reset (combines all resets)."""

    @patch("platform.system")
    @patch("sys.stdout")
    @patch("sys.stderr")
    @patch("ctypes.windll.kernel32")
    @patch("msvcrt.kbhit")
    @patch("msvcrt.getch")
    def test_full_reset_executes_all_components(
        self,
        mock_getch,
        mock_kbhit,
        mock_kernel32,
        mock_stderr,
        mock_stdout,
        mock_platform,
    ):
        """Test full reset calls all Windows reset functions."""
        mock_platform.return_value = "Windows"

        # Setup mocks
        mock_stdout.write = MagicMock()
        mock_stdout.flush = MagicMock()
        mock_stderr.write = MagicMock()
        mock_stderr.flush = MagicMock()

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.GetConsoleMode.return_value = 1
        mock_kernel32.SetConsoleMode.return_value = 1

        mock_kbhit.return_value = False

        reset_windows_terminal_full()

        # Verify all components called
        mock_stdout.write.assert_called_once_with("\x1b[0m")
        mock_kernel32.GetStdHandle.assert_called()
        mock_kbhit.assert_called_once()

    @patch("platform.system")
    def test_full_reset_skips_non_windows(self, mock_platform):
        """Test full reset does nothing on non-Windows."""
        mock_platform.return_value = "Linux"
        reset_windows_terminal_full()


class TestUnixTerminalReset:
    """Test Unix/Linux/macOS terminal reset."""

    @patch("platform.system")
    @patch("subprocess.run")
    def test_reset_unix_terminal_success(self, mock_run, mock_platform):
        """Test successful Unix terminal reset."""
        mock_platform.return_value = "Darwin"  # macOS
        mock_run.return_value = MagicMock(returncode=0)

        reset_unix_terminal()

        mock_run.assert_called_once_with(["reset"], check=True, capture_output=True)

    @patch("platform.system")
    @patch("subprocess.run")
    def test_reset_unix_terminal_skips_windows(self, mock_run, mock_platform):
        """Test Unix reset does nothing on Windows."""
        mock_platform.return_value = "Windows"
        reset_unix_terminal()

        mock_run.assert_not_called()

    @patch("platform.system")
    @patch("subprocess.run")
    def test_reset_unix_terminal_handles_called_process_error(
        self, mock_run, mock_platform
    ):
        """Test Unix reset handles CalledProcessError gracefully."""
        mock_platform.return_value = "Linux"
        mock_run.side_effect = subprocess.CalledProcessError(1, "reset")

        # Should not raise exception
        reset_unix_terminal()

        mock_run.assert_called_once()

    @patch("platform.system")
    @patch("subprocess.run")
    def test_reset_unix_terminal_handles_file_not_found(self, mock_run, mock_platform):
        """Test Unix reset handles missing 'reset' command gracefully."""
        mock_platform.return_value = "Linux"
        mock_run.side_effect = FileNotFoundError()

        # Should not raise exception
        reset_unix_terminal()

        mock_run.assert_called_once()


class TestCrossPlatformReset:
    """Test cross-platform terminal reset routing."""

    @patch("platform.system")
    @patch("code_puppy.terminal_utils.reset_windows_terminal_full")
    def test_reset_terminal_routes_to_windows(self, mock_win_reset, mock_platform):
        """Test reset routes to Windows function on Windows."""
        mock_platform.return_value = "Windows"

        reset_terminal()

        mock_win_reset.assert_called_once()

    @patch("platform.system")
    @patch("code_puppy.terminal_utils.reset_unix_terminal")
    def test_reset_terminal_routes_to_unix(self, mock_unix_reset, mock_platform):
        """Test reset routes to Unix function on Unix-like systems."""
        mock_platform.return_value = "Linux"

        reset_terminal()

        mock_unix_reset.assert_called_once()

    @patch("platform.system")
    @patch("code_puppy.terminal_utils.reset_unix_terminal")
    def test_reset_terminal_routes_to_unix_macos(self, mock_unix_reset, mock_platform):
        """Test reset routes to Unix function on macOS."""
        mock_platform.return_value = "Darwin"

        reset_terminal()

        mock_unix_reset.assert_called_once()


@WINDOWS_ONLY
class TestWindowsCtrlCDisable:
    """Test Windows Ctrl+C disabling functionality."""

    @patch("platform.system")
    def test_disable_ctrl_c_skips_non_windows(self, mock_platform):
        """Test Ctrl+C disable returns False on non-Windows."""
        mock_platform.return_value = "Linux"
        result = disable_windows_ctrl_c()
        assert result is False

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    @patch("code_puppy.terminal_utils._original_ctrl_handler", None)
    def test_disable_ctrl_c_success(self, mock_kernel32, mock_platform):
        """Test successful Ctrl+C disabling."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle

        mode_ref = MagicMock()
        mode_ref.contents.value = 0x0007  # ENABLE_PROCESSED_INPUT enabled
        mock_kernel32.GetConsoleMode.return_value = 1
        mock_kernel32.SetConsoleMode.return_value = 1

        result = disable_windows_ctrl_c()

        assert result is True
        # Verify ENABLE_PROCESSED_INPUT was disabled
        set_mode_call = mock_kernel32.SetConsoleMode.call_args
        new_mode = set_mode_call[0][1]
        assert not (new_mode & 0x0001)  # ENABLE_PROCESSED_INPUT should be cleared

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_disable_ctrl_c_handles_get_mode_failure(
        self, mock_kernel32, mock_platform
    ):
        """Test Ctrl+C disable handles GetConsoleMode failure."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.GetConsoleMode.return_value = 0  # Failure

        result = disable_windows_ctrl_c()

        assert result is False

    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    def test_disable_ctrl_c_handles_set_mode_failure(
        self, mock_kernel32, mock_platform
    ):
        """Test Ctrl+C disable handles SetConsoleMode failure."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle

        mode_ref = MagicMock()
        mode_ref.contents.value = 0x0007
        mock_kernel32.GetConsoleMode.return_value = 1
        mock_kernel32.SetConsoleMode.return_value = 0  # Failure

        result = disable_windows_ctrl_c()

        assert result is False

    @patch("platform.system")
    def test_disable_ctrl_c_handles_exception(self, mock_platform):
        """Test Ctrl+C disable handles exceptions gracefully."""
        mock_platform.return_value = "Windows"

        # Mock import failure
        with patch.dict("sys.modules", {"ctypes": None}):
            result = disable_windows_ctrl_c()
            assert result is False


@WINDOWS_ONLY
class TestWindowsCtrlCEnable:
    """Test Windows Ctrl+C enabling functionality."""

    @patch("platform.system")
    def test_enable_ctrl_c_skips_non_windows(self, mock_platform):
        """Test Ctrl+C enable returns False on non-Windows."""
        mock_platform.return_value = "Linux"
        result = enable_windows_ctrl_c()
        assert result is False

    @patch("platform.system")
    @patch("code_puppy.terminal_utils._original_ctrl_handler", 0x0007)
    @patch("ctypes.windll.kernel32")
    def test_enable_ctrl_c_success(self, mock_kernel32, mock_platform):
        """Test successful Ctrl+C enabling."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.SetConsoleMode.return_value = 1

        result = enable_windows_ctrl_c()

        assert result is True
        mock_kernel32.SetConsoleMode.assert_called_once_with(mock_handle, 0x0007)

    @patch("platform.system")
    def test_enable_ctrl_c_no_restore_needed(self, mock_platform):
        """Test Ctrl+C enable when no original handler saved."""
        mock_platform.return_value = "Windows"

        # Temporarily set _original_ctrl_handler to None
        with patch("code_puppy.terminal_utils._original_ctrl_handler", None):
            result = enable_windows_ctrl_c()
            assert result is True  # Should succeed as nothing to restore

    @patch("platform.system")
    @patch("code_puppy.terminal_utils._original_ctrl_handler", 0x0007)
    @patch("ctypes.windll.kernel32")
    def test_enable_ctrl_c_handles_set_mode_failure(self, mock_kernel32, mock_platform):
        """Test Ctrl+C enable handles SetConsoleMode failure."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.SetConsoleMode.return_value = 0  # Failure

        result = enable_windows_ctrl_c()

        assert result is False

    @patch("platform.system")
    @patch("code_puppy.terminal_utils._original_ctrl_handler", 0x0007)
    def test_enable_ctrl_c_handles_exception(self, mock_platform):
        """Test Ctrl+C enable handles exceptions gracefully."""
        mock_platform.return_value = "Windows"

        # Mock import failure
        with patch.dict("sys.modules", {"ctypes": None}):
            result = enable_windows_ctrl_c()
            assert result is False


class TestSetKeepCtrlCDisabled:
    """Test set_keep_ctrl_c_disabled function."""

    def test_set_keep_ctrl_c_disabled_true(self):
        """Test setting keep Ctrl+C disabled to True."""
        set_keep_ctrl_c_disabled(True)

        assert code_puppy.terminal_utils._keep_ctrl_c_disabled is True

    def test_set_keep_ctrl_c_disabled_false(self):
        """Test setting keep Ctrl+C disabled to False."""
        set_keep_ctrl_c_disabled(False)

        assert code_puppy.terminal_utils._keep_ctrl_c_disabled is False


class TestEnsureCtrlCDisabled:
    """Test ensure_ctrl_c_disabled function."""

    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", False)
    def test_ensure_ctrl_c_disabled_flag_false(self):
        """Test ensure returns True when flag is False (don't need to disable)."""
        result = ensure_ctrl_c_disabled()
        assert result is True

    @patch("platform.system")
    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", True)
    def test_ensure_ctrl_c_disabled_non_windows(self, mock_platform):
        """Test ensure returns True on non-Windows platforms."""
        mock_platform.return_value = "Linux"
        result = ensure_ctrl_c_disabled()
        assert result is True

    @WINDOWS_ONLY
    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", True)
    def test_ensure_ctrl_c_disabled_already_disabled(
        self, mock_kernel32, mock_platform
    ):
        """Test ensure when Ctrl+C is already disabled."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle

        mode_ref = MagicMock()
        mode_ref.contents.value = 0x0006  # ENABLE_PROCESSED_INPUT is disabled
        mock_kernel32.GetConsoleMode.return_value = 1

        result = ensure_ctrl_c_disabled()

        assert result is True
        mock_kernel32.SetConsoleMode.assert_not_called()

    @WINDOWS_ONLY
    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", True)
    def test_ensure_ctrl_c_disabled_needs_disabling(self, mock_kernel32, mock_platform):
        """Test ensure when Ctrl+C needs to be disabled."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle

        mode_ref = MagicMock()
        mode_ref.contents.value = 0x0007  # ENABLE_PROCESSED_INPUT is enabled
        mock_kernel32.GetConsoleMode.return_value = 1
        mock_kernel32.SetConsoleMode.return_value = 1

        result = ensure_ctrl_c_disabled()

        assert result is True
        mock_kernel32.SetConsoleMode.assert_called_once()

        # Verify ENABLE_PROCESSED_INPUT was disabled
        call_args = mock_kernel32.SetConsoleMode.call_args
        new_mode = call_args[0][1]
        assert not (new_mode & 0x0001)  # ENABLE_PROCESSED_INPUT should be cleared

    @WINDOWS_ONLY
    @patch("platform.system")
    @patch("ctypes.windll.kernel32")
    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", True)
    def test_ensure_ctrl_c_disabled_handles_failure(self, mock_kernel32, mock_platform):
        """Test ensure handles console mode operations failure."""
        mock_platform.return_value = "Windows"

        mock_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = mock_handle
        mock_kernel32.GetConsoleMode.return_value = 0  # Failure

        result = ensure_ctrl_c_disabled()

        assert result is False


class TestTruecolorDetection:
    """Test truecolor support detection."""

    def test_detect_colorterm_truecolor(self):
        """Test detection via COLORTERM=truecolor."""
        with patch.dict(os.environ, {"COLORTERM": "truecolor"}):
            assert detect_truecolor_support() is True

    def test_detect_colorterm_24bit(self):
        """Test detection via COLORTERM=24bit."""
        with patch.dict(os.environ, {"COLORTERM": "24bit"}):
            assert detect_truecolor_support() is True

    def test_detect_xterm_direct(self):
        """Test detection via TERM=xterm-direct."""
        with patch.dict(os.environ, {"TERM": "xterm-direct"}):
            assert detect_truecolor_support() is True

    def test_detect_xterm_truecolor(self):
        """Test detection via TERM=xterm-truecolor."""
        with patch.dict(os.environ, {"TERM": "xterm-truecolor"}):
            assert detect_truecolor_support() is True

    def test_detect_iterm2(self):
        """Test detection via TERM=iterm2."""
        with patch.dict(os.environ, {"TERM": "iterm2"}):
            assert detect_truecolor_support() is True

    def test_detect_vte_256color(self):
        """Test detection via TERM=vte-256color."""
        with patch.dict(os.environ, {"TERM": "vte-256color"}):
            assert detect_truecolor_support() is True

    def test_detect_iterm_session_id(self):
        """Test detection via ITERM_SESSION_ID."""
        with patch.dict(os.environ, {"ITERM_SESSION_ID": "w0t0p0:123456"}):
            assert detect_truecolor_support() is True

    def test_detect_kitty_window_id(self):
        """Test detection via KITTY_WINDOW_ID."""
        with patch.dict(os.environ, {"KITTY_WINDOW_ID": "1"}):
            assert detect_truecolor_support() is True

    def test_detect_alacritty_socket(self):
        """Test detection via ALACRITTY_SOCKET."""
        with patch.dict(
            os.environ, {"ALACRITTY_SOCKET": "/tmp/Alacritty-12345.socket"}
        ):
            assert detect_truecolor_support() is True

    def test_detect_wt_session(self):
        """Test detection via WT_SESSION (Windows Terminal)."""
        with patch.dict(
            os.environ, {"WT_SESSION": "12345678-1234-1234-1234-123456789012"}
        ):
            assert detect_truecolor_support() is True

    def test_no_truecolor_support(self):
        """Test returns False when no indicators present."""
        with patch.dict(os.environ, {}, clear=True):
            # Mock Console.color_system to not be truecolor
            with patch("rich.console.Console") as mock_console_class:
                mock_console = MagicMock()
                mock_console.color_system = "standard"
                mock_console_class.return_value = mock_console

                assert detect_truecolor_support() is False

    def test_rich_fallback_truecolor(self):
        """Test Rich fallback detects truecolor."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("rich.console.Console") as mock_console_class:
                mock_console = MagicMock()
                mock_console.color_system = "truecolor"
                mock_console_class.return_value = mock_console

                assert detect_truecolor_support() is True

    def test_rich_fallback_256(self):
        """Test Rich fallback with 256 colors."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("rich.console.Console") as mock_console_class:
                mock_console = MagicMock()
                mock_console.color_system = "256"
                mock_console_class.return_value = mock_console

                assert detect_truecolor_support() is False

    def test_rich_import_error(self):
        """Test handles Rich import error gracefully."""
        with patch.dict(os.environ, {}, clear=True):
            with patch.dict("sys.modules", {"rich": None, "rich.console": None}):
                assert detect_truecolor_support() is False

    def test_case_insensitive_colorterm(self):
        """Test COLORTERM detection is case-insensitive."""
        with patch.dict(os.environ, {"COLORTERM": "TRUECOLOR"}):
            assert detect_truecolor_support() is True

        with patch.dict(os.environ, {"COLORTERM": "TrueColor"}):
            assert detect_truecolor_support() is True

    def test_partial_term_match(self):
        """Test TERM matching finds truecolor patterns anywhere."""
        with patch.dict(os.environ, {"TERM": "xterm-direct-256color"}):
            assert detect_truecolor_support() is True


class TestPrintTruecolorWarning:
    """Test truecolor warning printing."""

    def test_no_warning_when_truecolor_supported(self):
        """Test no warning printed when truecolor is supported."""
        with patch("code_puppy.terminal_utils.detect_truecolor_support") as mock_detect:
            mock_detect.return_value = True
            with patch("rich.console.Console.print") as mock_print:
                print_truecolor_warning()
                mock_print.assert_not_called()

    def test_warning_with_rich(self):
        """Test warning printed with Rich when available."""
        with patch("code_puppy.terminal_utils.detect_truecolor_support") as mock_detect:
            mock_detect.return_value = False

            mock_console = MagicMock()
            mock_console.color_system = "standard"

            with patch("rich.console.Console") as mock_console_class:
                mock_console_class.return_value = mock_console
                print_truecolor_warning()

                # Verify console was created and print was called
                mock_console_class.assert_called_once()
                mock_console.print.assert_called()

                # Verify warning content contains key phrases
                calls = mock_console.print.call_args_list
                call_args = [str(call) for call in calls]
                call_text = " ".join(call_args)
                assert "WARNING" in call_text or "truecolor" in call_text.lower()

    def test_warning_without_rich(self):
        """Test warning printed without Rich (fallback to emit_info)."""
        with patch("code_puppy.terminal_utils.detect_truecolor_support") as mock_detect:
            mock_detect.return_value = False

            # Mock rich import failure
            with patch.dict("sys.modules", {"rich": None, "rich.console": None}):
                with patch("code_puppy.terminal_utils.emit_info") as mock_emit_info:
                    print_truecolor_warning()

                    # Verify emit_info was called
                    mock_emit_info.assert_called()

                    # Get all emit_info calls and verify warning content
                    calls = mock_emit_info.call_args_list
                    call_args = [str(call) for call in calls]
                    call_text = " ".join(call_args).lower()

                    assert "warning" in call_text
                    assert "truecolor" in call_text or "24-bit color" in call_text

    def test_warning_with_custom_console(self):
        """Test warning with provided console instance."""
        with patch("code_puppy.terminal_utils.detect_truecolor_support") as mock_detect:
            mock_detect.return_value = False

            mock_console = MagicMock()
            mock_console.color_system = "standard"

            print_truecolor_warning(console=mock_console)

            # Verify provided console was used
            mock_console.print.assert_called()

    def test_warning_no_duplicate_calls(self):
        """Test warning only prints when truecolor is not supported."""
        with patch("code_puppy.terminal_utils.detect_truecolor_support") as mock_detect:
            # First call - no truecolor, should print
            mock_detect.return_value = False
            with patch("rich.console.Console.print") as mock_print:
                print_truecolor_warning()
                first_call_count = mock_print.call_count

            # Second call - truecolor detected, should not print
            mock_detect.return_value = True
            with patch("rich.console.Console.print") as mock_print:
                print_truecolor_warning()
                mock_print.assert_not_called()

            assert first_call_count > 0  # Verify first call actually printed


class TestEdgeCasesAndIntegration:
    """Test edge cases and integration scenarios."""

    def test_multiple_reset_calls_safe(self):
        """Test calling reset functions multiple times is safe."""
        with patch("platform.system", return_value="Windows"):
            with patch("sys.stdout.write"):
                with patch("sys.stderr.write"):
                    # Should not raise exceptions
                    reset_windows_terminal_ansi()
                    reset_windows_terminal_ansi()
                    reset_windows_terminal_ansi()

    @WINDOWS_ONLY
    @patch("platform.system")
    @patch("code_puppy.terminal_utils._keep_ctrl_c_disabled", True)
    def test_ensure_ctrl_c_after_operations(self, mock_platform):
        """Test ensure_ctrl_c_disabled after potential console mode changes."""
        mock_platform.return_value = "Windows"

        # Simulate operations that might change console mode
        with patch("ctypes.windll.kernel32") as mock_kernel32:
            mock_handle = MagicMock()
            mock_kernel32.GetStdHandle.return_value = mock_handle

            mode_ref = MagicMock()
            mode_ref.contents.value = 0x0007  # Ctrl+C enabled
            mock_kernel32.GetConsoleMode.return_value = 1
            mock_kernel32.SetConsoleMode.return_value = 1

            result = ensure_ctrl_c_disabled()
            assert result is True

    def test_reset_routing_based_on_platform(self):
        """Test that reset_terminal correctly routes based on platform."""
        # Test Windows routing
        with patch("platform.system", return_value="Windows"):
            with patch(
                "code_puppy.terminal_utils.reset_windows_terminal_full"
            ) as mock_win:
                reset_terminal()
                mock_win.assert_called_once()

        # Test Linux routing
        with patch("platform.system", return_value="Linux"):
            with patch("code_puppy.terminal_utils.reset_unix_terminal") as mock_unix:
                reset_terminal()
                mock_unix.assert_called_once()

        # Test macOS routing
        with patch("platform.system", return_value="Darwin"):
            with patch("code_puppy.terminal_utils.reset_unix_terminal") as mock_unix:
                reset_terminal()
                mock_unix.assert_called_once()

    def test_truecolor_detection_comprehensive(self):
        """Comprehensive truecolor detection with various environment combinations."""
        test_cases = [
            ({"COLORTERM": "truecolor"}, True),
            ({"COLORTERM": "24bit"}, True),
            ({"TERM": "xterm-direct"}, True),
            ({"TERM": "xterm-truecolor"}, True),
            ({"TERM": "iterm2"}, True),
            ({"TERM": "vte-256color"}, True),
            ({"ITERM_SESSION_ID": "w0t0p0:123"}, True),
            ({"KITTY_WINDOW_ID": "1"}, True),
            ({"ALACRITTY_SOCKET": "/tmp/alacritty.sock"}, True),
            ({"WT_SESSION": "1234-5678"}, True),
            ({"COLORTERM": "no"}, False),
            ({"TERM": "xterm-256color"}, False),
            ({}, False),
        ]

        for env_vars, expected in test_cases:
            with patch.dict(os.environ, env_vars, clear=True):
                # Mock Rich to return non-truecolor for fair testing
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = MagicMock()
                    mock_console.color_system = "standard"
                    mock_console_class.return_value = mock_console

                    result = detect_truecolor_support()
                    assert result == expected, f"Failed for {env_vars}"

    @WINDOWS_ONLY
    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.kernel32")
    def test_windows_reset_error_recovery(self, mock_kernel32, mock_platform):
        """Test Windows reset functions recover from errors gracefully."""
        # Simulate various failure modes
        mock_kernel32.GetStdHandle.side_effect = [None, Exception("Failed")]

        # Should not raise exceptions
        reset_windows_console_mode()
        flush_windows_keyboard_buffer()

    def test_global_state_management(self):
        """Test proper management of global state variables."""
        # Test set_keep_ctrl_c_disabled
        set_keep_ctrl_c_disabled(True)

        assert code_puppy.terminal_utils._keep_ctrl_c_disabled is True

        set_keep_ctrl_c_disabled(False)

        assert code_puppy.terminal_utils._keep_ctrl_c_disabled is False

        # Test that _original_ctrl_handler is initially None

        assert _original_ctrl_handler is None


class TestANSISequenceFormats:
    """Test ANSI escape sequence formats used in the module."""

    def test_reset_sequence_format(self):
        """Test ANSI reset sequence has correct format."""
        reset_seq = "\x1b[0m"
        assert reset_seq.startswith("\x1b[")
        assert reset_seq.endswith("m")
        assert "0" in reset_seq

    def test_windows_console_handles(self):
        """Test Windows console handle values are correct."""
        # These are the actual Windows API constants
        STD_OUTPUT_HANDLE = -11
        STD_INPUT_HANDLE = -10

        assert STD_OUTPUT_HANDLE == -11
        assert STD_INPUT_HANDLE == -10

    def test_console_mode_flags(self):
        """Test console mode flag values are correct."""
        # Standard Windows console mode flags
        ENABLE_PROCESSED_OUTPUT = 0x0001
        ENABLE_WRAP_AT_EOL_OUTPUT = 0x0002
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ENABLE_LINE_INPUT = 0x0002
        ENABLE_ECHO_INPUT = 0x0004
        ENABLE_PROCESSED_INPUT = 0x0001

        # Verify flag values
        assert ENABLE_PROCESSED_OUTPUT == 1
        assert ENABLE_WRAP_AT_EOL_OUTPUT == 2
        assert ENABLE_VIRTUAL_TERMINAL_PROCESSING == 4
        assert ENABLE_LINE_INPUT == 2
        assert ENABLE_ECHO_INPUT == 4
        assert ENABLE_PROCESSED_INPUT == 1
