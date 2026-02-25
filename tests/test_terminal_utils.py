"""Comprehensive test coverage for terminal_utils.py."""

import subprocess
import sys
from unittest.mock import MagicMock

from code_puppy import terminal_utils

# ── reset_windows_terminal_ansi ──


class TestResetWindowsTerminalAnsi:
    def test_noop_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        stdout = MagicMock()
        monkeypatch.setattr(terminal_utils.sys, "stdout", stdout)
        terminal_utils.reset_windows_terminal_ansi()
        stdout.write.assert_not_called()

    def test_writes_reset_on_windows(self, monkeypatch):
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

    def test_exception_silenced(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        stdout = MagicMock()
        stdout.write.side_effect = OSError("broken")
        monkeypatch.setattr(terminal_utils.sys, "stdout", stdout)
        terminal_utils.reset_windows_terminal_ansi()  # should not raise


# ── reset_windows_console_mode ──


class TestResetWindowsConsoleMode:
    def test_noop_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        terminal_utils.reset_windows_console_mode()

    def test_calls_ctypes_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0
        mock_ctypes.c_ulong.return_value = mock_mode
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        terminal_utils.reset_windows_console_mode()
        assert mock_ctypes.windll.kernel32.GetStdHandle.call_count == 2
        assert mock_ctypes.windll.kernel32.SetConsoleMode.call_count == 2

    def test_exception_silenced(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        monkeypatch.setitem(sys.modules, "ctypes", None)  # force ImportError
        terminal_utils.reset_windows_console_mode()  # should not raise


# ── flush_windows_keyboard_buffer ──


class TestFlushWindowsKeyboardBuffer:
    def test_noop_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        terminal_utils.flush_windows_keyboard_buffer()

    def test_flushes_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_msvcrt = MagicMock()
        mock_msvcrt.kbhit.side_effect = [True, True, False]
        monkeypatch.setitem(sys.modules, "msvcrt", mock_msvcrt)
        terminal_utils.flush_windows_keyboard_buffer()
        assert mock_msvcrt.getch.call_count == 2

    def test_exception_silenced(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        monkeypatch.setitem(sys.modules, "msvcrt", None)
        terminal_utils.flush_windows_keyboard_buffer()


# ── reset_windows_terminal_full ──


class TestResetWindowsTerminalFull:
    def test_noop_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        ansi = MagicMock()
        monkeypatch.setattr(terminal_utils, "reset_windows_terminal_ansi", ansi)
        terminal_utils.reset_windows_terminal_full()
        ansi.assert_not_called()

    def test_calls_all_three_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        ansi = MagicMock()
        console = MagicMock()
        keyboard = MagicMock()
        monkeypatch.setattr(terminal_utils, "reset_windows_terminal_ansi", ansi)
        monkeypatch.setattr(terminal_utils, "reset_windows_console_mode", console)
        monkeypatch.setattr(terminal_utils, "flush_windows_keyboard_buffer", keyboard)
        terminal_utils.reset_windows_terminal_full()
        ansi.assert_called_once()
        console.assert_called_once()
        keyboard.assert_called_once()


# ── reset_unix_terminal ──


class TestResetUnixTerminal:
    def test_noop_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        run = MagicMock()
        monkeypatch.setattr(terminal_utils.subprocess, "run", run)
        terminal_utils.reset_unix_terminal()
        run.assert_not_called()

    def test_runs_reset_on_unix(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        run = MagicMock()
        monkeypatch.setattr(terminal_utils.subprocess, "run", run)
        terminal_utils.reset_unix_terminal()
        run.assert_called_once_with(["reset"], check=True, capture_output=True)

    def test_handles_called_process_error(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        monkeypatch.setattr(
            terminal_utils.subprocess,
            "run",
            MagicMock(side_effect=subprocess.CalledProcessError(1, "reset")),
        )
        terminal_utils.reset_unix_terminal()

    def test_handles_file_not_found(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        monkeypatch.setattr(
            terminal_utils.subprocess, "run", MagicMock(side_effect=FileNotFoundError)
        )
        terminal_utils.reset_unix_terminal()


# ── reset_terminal ──


class TestResetTerminal:
    def test_routes_to_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        full = MagicMock()
        monkeypatch.setattr(terminal_utils, "reset_windows_terminal_full", full)
        terminal_utils.reset_terminal()
        full.assert_called_once()

    def test_routes_to_unix(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        unix = MagicMock()
        monkeypatch.setattr(terminal_utils, "reset_unix_terminal", unix)
        terminal_utils.reset_terminal()
        unix.assert_called_once()


# ── disable_windows_ctrl_c ──


class TestDisableWindowsCtrlC:
    def test_returns_false_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        assert terminal_utils.disable_windows_ctrl_c() is False

    def test_success_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0x0007
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = True
        mock_ctypes.windll.kernel32.SetConsoleMode.return_value = True
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        terminal_utils._original_ctrl_handler = None
        assert terminal_utils.disable_windows_ctrl_c() is True
        assert terminal_utils._original_ctrl_handler == 0x0007

    def test_get_console_mode_fails(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0x0007
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = False
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.disable_windows_ctrl_c() is False

    def test_set_console_mode_fails(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0x0007
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = True
        mock_ctypes.windll.kernel32.SetConsoleMode.return_value = False
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.disable_windows_ctrl_c() is False

    def test_exception_returns_false(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        monkeypatch.setitem(sys.modules, "ctypes", None)
        assert terminal_utils.disable_windows_ctrl_c() is False


# ── enable_windows_ctrl_c ──


class TestEnableWindowsCtrlC:
    def test_returns_false_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        assert terminal_utils.enable_windows_ctrl_c() is False

    def test_returns_true_if_nothing_to_restore(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        terminal_utils._original_ctrl_handler = None
        assert terminal_utils.enable_windows_ctrl_c() is True

    def test_restores_on_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        terminal_utils._original_ctrl_handler = 0x0007
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.SetConsoleMode.return_value = True
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.enable_windows_ctrl_c() is True
        assert terminal_utils._original_ctrl_handler is None

    def test_set_console_mode_fails(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        terminal_utils._original_ctrl_handler = 0x0007
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.SetConsoleMode.return_value = False
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.enable_windows_ctrl_c() is False

    def test_exception_returns_false(self, monkeypatch):
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        terminal_utils._original_ctrl_handler = 0x0007
        monkeypatch.setitem(sys.modules, "ctypes", None)
        assert terminal_utils.enable_windows_ctrl_c() is False


# ── set_keep_ctrl_c_disabled / ensure_ctrl_c_disabled ──


class TestKeepCtrlCDisabled:
    def test_set_keep_ctrl_c_disabled(self):
        terminal_utils.set_keep_ctrl_c_disabled(True)
        assert terminal_utils._keep_ctrl_c_disabled is True
        terminal_utils.set_keep_ctrl_c_disabled(False)
        assert terminal_utils._keep_ctrl_c_disabled is False


class TestEnsureCtrlCDisabled:
    def test_returns_true_when_not_keeping(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", False)
        assert terminal_utils.ensure_ctrl_c_disabled() is True

    def test_returns_true_on_non_windows(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", True)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Linux")
        assert terminal_utils.ensure_ctrl_c_disabled() is True

    def test_already_disabled(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", True)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0x0000  # ENABLE_PROCESSED_INPUT not set
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = True
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.ensure_ctrl_c_disabled() is True

    def test_disables_when_enabled(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", True)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_mode.value = 0x0001  # ENABLE_PROCESSED_INPUT is set
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = True
        mock_ctypes.windll.kernel32.SetConsoleMode.return_value = True
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.ensure_ctrl_c_disabled() is True

    def test_get_console_mode_fails(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", True)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        mock_ctypes = MagicMock()
        mock_mode = MagicMock()
        mock_ctypes.c_ulong.return_value = mock_mode
        mock_ctypes.windll.kernel32.GetConsoleMode.return_value = False
        monkeypatch.setitem(sys.modules, "ctypes", mock_ctypes)
        assert terminal_utils.ensure_ctrl_c_disabled() is False

    def test_exception_returns_false(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "_keep_ctrl_c_disabled", True)
        monkeypatch.setattr(terminal_utils.platform, "system", lambda: "Windows")
        monkeypatch.setitem(sys.modules, "ctypes", None)
        assert terminal_utils.ensure_ctrl_c_disabled() is False


# ── detect_truecolor_support ──


class TestDetectTruecolorSupport:
    def test_colorterm_truecolor(self, monkeypatch):
        monkeypatch.setenv("COLORTERM", "truecolor")
        assert terminal_utils.detect_truecolor_support() is True

    def test_colorterm_24bit(self, monkeypatch):
        monkeypatch.setenv("COLORTERM", "24bit")
        assert terminal_utils.detect_truecolor_support() is True

    def test_term_xterm_direct(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-direct")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("ALACRITTY_SOCKET", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        assert terminal_utils.detect_truecolor_support() is True

    def test_iterm_session(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("ITERM_SESSION_ID", "abc")
        assert terminal_utils.detect_truecolor_support() is True

    def test_kitty_window(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.setenv("KITTY_WINDOW_ID", "1")
        assert terminal_utils.detect_truecolor_support() is True

    def test_alacritty(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.setenv("ALACRITTY_SOCKET", "/tmp/sock")
        assert terminal_utils.detect_truecolor_support() is True

    def test_windows_terminal(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("ALACRITTY_SOCKET", raising=False)
        monkeypatch.setenv("WT_SESSION", "abc")
        assert terminal_utils.detect_truecolor_support() is True

    def test_rich_fallback_truecolor(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("ALACRITTY_SOCKET", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        mock_console_cls = MagicMock()
        mock_console_cls.return_value.color_system = "truecolor"
        monkeypatch.setattr(
            "code_puppy.terminal_utils.Console", mock_console_cls, raising=False
        )
        # We need to mock the import inside the function
        import rich.console

        monkeypatch.setattr(rich.console, "Console", mock_console_cls)
        assert terminal_utils.detect_truecolor_support() is True

    def test_rich_fallback_not_truecolor(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("ALACRITTY_SOCKET", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        import rich.console

        mock_console_cls = MagicMock()
        mock_console_cls.return_value.color_system = "256"
        monkeypatch.setattr(rich.console, "Console", mock_console_cls)
        assert terminal_utils.detect_truecolor_support() is False

    def test_rich_import_error(self, monkeypatch):
        monkeypatch.delenv("COLORTERM", raising=False)
        monkeypatch.setenv("TERM", "dumb")
        monkeypatch.delenv("ITERM_SESSION_ID", raising=False)
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
        monkeypatch.delenv("ALACRITTY_SOCKET", raising=False)
        monkeypatch.delenv("WT_SESSION", raising=False)
        import rich.console

        monkeypatch.setattr(
            rich.console, "Console", MagicMock(side_effect=Exception("fail"))
        )
        assert terminal_utils.detect_truecolor_support() is False


# ── print_truecolor_warning ──


class TestPrintTruecolorWarning:
    def test_no_warning_when_truecolor_supported(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: True)
        mock_console = MagicMock()
        terminal_utils.print_truecolor_warning(console=mock_console)
        mock_console.print.assert_not_called()

    def test_rich_console_warning(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        mock_console = MagicMock()
        mock_console.color_system = "256"
        terminal_utils.print_truecolor_warning(console=mock_console)
        assert mock_console.print.call_count > 10

    def test_creates_console_when_none(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        mock_console = MagicMock()
        mock_console.color_system = "standard"
        import rich.console

        monkeypatch.setattr(rich.console, "Console", lambda: mock_console)
        terminal_utils.print_truecolor_warning(console=None)
        assert mock_console.print.call_count > 10

    def test_fallback_to_plain_print(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        # Make the import of rich.console.Console raise ImportError
        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "rich.console":
                raise ImportError("no rich")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        printed = []
        monkeypatch.setattr(builtins, "print", lambda *a, **kw: printed.append(a))
        terminal_utils.print_truecolor_warning(console=None)
        assert len(printed) > 5

    def test_console_color_system_none(self, monkeypatch):
        monkeypatch.setattr(terminal_utils, "detect_truecolor_support", lambda: False)
        mock_console = MagicMock()
        mock_console.color_system = None
        terminal_utils.print_truecolor_warning(console=mock_console)
        # Should use "unknown" for color_system
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("unknown" in c for c in calls)
