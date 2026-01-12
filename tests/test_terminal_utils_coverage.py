"""Additional coverage tests for terminal_utils.py.

These tests specifically target the uncovered Windows code paths
by mocking platform.system() and ctypes to execute the code
regardless of the actual platform we're running on.

Target uncovered lines:
- 44-94: reset_windows_console_mode
- 103-112: flush_windows_keyboard_buffer
- 121-126: reset_windows_terminal_full
- 171-202: disable_windows_ctrl_c
- 215-237: enable_windows_ctrl_c
- 269-295: ensure_ctrl_c_disabled
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


class TestResetWindowsConsoleModeCodePaths:
    """Test reset_windows_console_mode to cover lines 44-94."""

    def test_reset_console_mode_skips_non_windows(self):
        """Test that reset_windows_console_mode is a no-op on non-Windows."""
        with patch("platform.system", return_value="Linux"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            # Should return early without error
            tu.reset_windows_console_mode()
            # If we get here without exception, the early return worked

    def test_reset_console_mode_full_execution_on_windows(self):
        """Execute the full Windows console mode reset code path."""
        # Create mock ctypes module structure
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        # Create a proper c_ulong mock that works with byref
        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong

        # Mock byref to just return the object
        mock_ctypes.byref = lambda x: x

        # Setup GetStdHandle to return mock handles
        stdout_handle = MagicMock()
        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.side_effect = [stdout_handle, stdin_handle]

        # Setup GetConsoleMode to succeed and set mode values
        def mock_get_console_mode(handle, mode_ref):
            mode_ref.value = 0x0000  # Initial mode
            return 1  # Success

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode
        mock_kernel32.SetConsoleMode.return_value = 1  # Success

        # Patch platform and ctypes
        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                # Import fresh to pick up mocks
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                # Call the function
                tu.reset_windows_console_mode()

                # Verify GetStdHandle was called for both stdout and stdin
                assert mock_kernel32.GetStdHandle.call_count == 2
                calls = mock_kernel32.GetStdHandle.call_args_list
                # STD_OUTPUT_HANDLE = -11, STD_INPUT_HANDLE = -10
                assert calls[0][0][0] == -11
                assert calls[1][0][0] == -10

                # Verify SetConsoleMode was called for both
                assert mock_kernel32.SetConsoleMode.call_count == 2

    def test_reset_console_mode_exception_handling(self):
        """Test that exceptions in console mode reset are silently caught."""
        # Mock ctypes to raise exception
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetStdHandle.side_effect = Exception("Test error")

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                # Should not raise - exceptions are silently caught
                tu.reset_windows_console_mode()


class TestFlushWindowsKeyboardBufferCodePaths:
    """Test flush_windows_keyboard_buffer to cover lines 103-112."""

    def test_flush_keyboard_buffer_skips_non_windows(self):
        """Test that flush_windows_keyboard_buffer is a no-op on non-Windows."""
        with patch("platform.system", return_value="Darwin"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            # Should return early without error
            tu.flush_windows_keyboard_buffer()
            # If we get here without exception, the early return worked

    def test_flush_keyboard_buffer_full_execution(self):
        """Execute the full keyboard buffer flush code path."""
        mock_msvcrt = MagicMock()
        # Simulate 2 keys in buffer then empty
        mock_msvcrt.kbhit.side_effect = [True, True, False]
        mock_msvcrt.getch.return_value = b"x"

        with patch.dict(sys.modules, {"msvcrt": mock_msvcrt}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu.flush_windows_keyboard_buffer()

                # Verify kbhit was called to check buffer
                assert mock_msvcrt.kbhit.call_count == 3
                # Verify getch was called to consume keys
                assert mock_msvcrt.getch.call_count == 2

    def test_flush_keyboard_buffer_exception_handling(self):
        """Test that exceptions in keyboard flush are silently caught."""
        mock_msvcrt = MagicMock()
        mock_msvcrt.kbhit.side_effect = Exception("Test error")

        with patch.dict(sys.modules, {"msvcrt": mock_msvcrt}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                # Should not raise - exceptions are silently caught
                tu.flush_windows_keyboard_buffer()


class TestResetWindowsTerminalFullCodePaths:
    """Test reset_windows_terminal_full to cover lines 121-126."""

    def test_full_reset_calls_all_components(self):
        """Test that full reset calls ANSI, console mode, and keyboard flush."""
        with patch("platform.system", return_value="Windows"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            # Mock the three component functions
            with patch.object(tu, "reset_windows_terminal_ansi") as mock_ansi:
                with patch.object(tu, "reset_windows_console_mode") as mock_console:
                    with patch.object(tu, "flush_windows_keyboard_buffer") as mock_kb:
                        tu.reset_windows_terminal_full()

                        mock_ansi.assert_called_once()
                        mock_console.assert_called_once()
                        mock_kb.assert_called_once()

    def test_full_reset_noop_on_non_windows(self):
        """Test that full reset is a no-op on non-Windows."""
        with patch("platform.system", return_value="Linux"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            # Should not call any component functions
            with patch.object(tu, "reset_windows_terminal_ansi") as mock_ansi:
                with patch.object(tu, "reset_windows_console_mode") as mock_console:
                    with patch.object(tu, "flush_windows_keyboard_buffer") as mock_kb:
                        tu.reset_windows_terminal_full()

                        mock_ansi.assert_not_called()
                        mock_console.assert_not_called()
                        mock_kb.assert_not_called()


class TestDisableWindowsCtrlCCodePaths:
    """Test disable_windows_ctrl_c to cover lines 171-202."""

    def test_disable_ctrl_c_full_success_path(self):
        """Execute the full disable Ctrl+C success path."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle

        # GetConsoleMode succeeds and sets value with ENABLE_PROCESSED_INPUT
        def mock_get_console_mode(handle, mode_ref):
            mode_ref.value = 0x0007  # Has ENABLE_PROCESSED_INPUT (0x0001)
            return 1  # Success (non-zero)

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode
        mock_kernel32.SetConsoleMode.return_value = 1  # Success

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                # Reset state
                tu._original_ctrl_handler = None

                result = tu.disable_windows_ctrl_c()

                assert result is True
                # Verify original handler was saved
                assert tu._original_ctrl_handler == 0x0007

                # Verify SetConsoleMode was called with ENABLE_PROCESSED_INPUT cleared
                call_args = mock_kernel32.SetConsoleMode.call_args
                new_mode = call_args[0][1]
                assert not (
                    new_mode & 0x0001
                )  # ENABLE_PROCESSED_INPUT should be cleared

    def test_disable_ctrl_c_get_console_mode_fails(self):
        """Test disable_ctrl_c when GetConsoleMode fails."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle
        mock_kernel32.GetConsoleMode.return_value = 0  # Failure (zero)

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                result = tu.disable_windows_ctrl_c()

                assert result is False

    def test_disable_ctrl_c_set_console_mode_fails(self):
        """Test disable_ctrl_c when SetConsoleMode fails."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle

        def mock_get_console_mode(handle, mode_ref):
            mode_ref.value = 0x0007
            return 1

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode
        mock_kernel32.SetConsoleMode.return_value = 0  # Failure

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                result = tu.disable_windows_ctrl_c()

                assert result is False

    def test_disable_ctrl_c_exception_handling(self):
        """Test disable_ctrl_c handles exceptions gracefully."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetStdHandle.side_effect = Exception("Error")

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                result = tu.disable_windows_ctrl_c()

                assert result is False

    def test_disable_ctrl_c_non_windows(self):
        """Test disable_ctrl_c returns False on non-Windows."""
        with patch("platform.system", return_value="Darwin"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            result = tu.disable_windows_ctrl_c()

            assert result is False


class TestEnableWindowsCtrlCCodePaths:
    """Test enable_windows_ctrl_c to cover lines 215-237."""

    def test_enable_ctrl_c_full_success_path(self):
        """Execute the full enable Ctrl+C success path."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle
        mock_kernel32.SetConsoleMode.return_value = 1  # Success

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                # Set up saved handler
                tu._original_ctrl_handler = 0x0007

                result = tu.enable_windows_ctrl_c()

                assert result is True
                # Verify handler was cleared
                assert tu._original_ctrl_handler is None

                # Verify SetConsoleMode was called with original mode
                mock_kernel32.SetConsoleMode.assert_called_once_with(
                    stdin_handle, 0x0007
                )

    def test_enable_ctrl_c_no_original_handler(self):
        """Test enable_ctrl_c when no original handler was saved."""
        with patch("platform.system", return_value="Windows"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            tu._original_ctrl_handler = None

            result = tu.enable_windows_ctrl_c()

            # Should return True (nothing to restore)
            assert result is True

    def test_enable_ctrl_c_set_console_mode_fails(self):
        """Test enable_ctrl_c when SetConsoleMode fails."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle
        mock_kernel32.SetConsoleMode.return_value = 0  # Failure

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._original_ctrl_handler = 0x0007

                result = tu.enable_windows_ctrl_c()

                assert result is False

    def test_enable_ctrl_c_exception_handling(self):
        """Test enable_ctrl_c handles exceptions gracefully."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetStdHandle.side_effect = Exception("Error")

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._original_ctrl_handler = 0x0007

                result = tu.enable_windows_ctrl_c()

                assert result is False

    def test_enable_ctrl_c_non_windows(self):
        """Test enable_ctrl_c returns False on non-Windows."""
        with patch("platform.system", return_value="Linux"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            result = tu.enable_windows_ctrl_c()

            assert result is False


class TestEnsureCtrlCDisabledCodePaths:
    """Test ensure_ctrl_c_disabled to cover lines 269-295."""

    def test_ensure_already_disabled(self):
        """Test ensure when Ctrl+C is already disabled."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle

        # Mode without ENABLE_PROCESSED_INPUT (already disabled)
        def mock_get_console_mode(handle, mode_ref):
            mode_ref.value = 0x0006  # No ENABLE_PROCESSED_INPUT
            return 1

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._keep_ctrl_c_disabled = True

                result = tu.ensure_ctrl_c_disabled()

                assert result is True
                # SetConsoleMode should NOT be called (already disabled)
                mock_kernel32.SetConsoleMode.assert_not_called()

    def test_ensure_needs_disabling(self):
        """Test ensure when Ctrl+C needs to be disabled."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle

        # Mode with ENABLE_PROCESSED_INPUT (needs disabling)
        def mock_get_console_mode(handle, mode_ref):
            mode_ref.value = 0x0007  # Has ENABLE_PROCESSED_INPUT
            return 1

        mock_kernel32.GetConsoleMode.side_effect = mock_get_console_mode
        mock_kernel32.SetConsoleMode.return_value = 1  # Success

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._keep_ctrl_c_disabled = True

                result = tu.ensure_ctrl_c_disabled()

                assert result is True
                mock_kernel32.SetConsoleMode.assert_called_once()

                # Verify ENABLE_PROCESSED_INPUT was cleared
                call_args = mock_kernel32.SetConsoleMode.call_args
                new_mode = call_args[0][1]
                assert not (new_mode & 0x0001)

    def test_ensure_get_console_mode_fails(self):
        """Test ensure when GetConsoleMode fails."""
        mock_ctypes = MagicMock()
        mock_kernel32 = MagicMock()
        mock_ctypes.windll.kernel32 = mock_kernel32

        class MockCULong:
            def __init__(self, value=0):
                self.value = value

        mock_ctypes.c_ulong = MockCULong
        mock_ctypes.byref = lambda x: x

        stdin_handle = MagicMock()
        mock_kernel32.GetStdHandle.return_value = stdin_handle
        mock_kernel32.GetConsoleMode.return_value = 0  # Failure

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._keep_ctrl_c_disabled = True

                result = tu.ensure_ctrl_c_disabled()

                assert result is False

    def test_ensure_exception_handling(self):
        """Test ensure handles exceptions gracefully."""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.GetStdHandle.side_effect = Exception("Error")

        with patch.dict(sys.modules, {"ctypes": mock_ctypes}):
            with patch("platform.system", return_value="Windows"):
                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                tu._keep_ctrl_c_disabled = True

                result = tu.ensure_ctrl_c_disabled()

                assert result is False

    def test_ensure_flag_false(self):
        """Test ensure when flag is False (don't need to disable)."""
        with patch("platform.system", return_value="Windows"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            tu._keep_ctrl_c_disabled = False

            result = tu.ensure_ctrl_c_disabled()

            assert result is True

    def test_ensure_non_windows(self):
        """Test ensure on non-Windows returns True."""
        with patch("platform.system", return_value="Darwin"):
            import importlib

            import code_puppy.terminal_utils as tu

            importlib.reload(tu)

            tu._keep_ctrl_c_disabled = True

            result = tu.ensure_ctrl_c_disabled()

            assert result is True


class TestWindowsANSIResetCodePaths:
    """Additional tests for reset_windows_terminal_ansi edge cases."""

    def test_ansi_reset_stdout_exception(self):
        """Test ANSI reset handles stdout exception."""
        mock_stdout = MagicMock()
        mock_stdout.write.side_effect = Exception("Write error")

        with patch("platform.system", return_value="Windows"):
            with patch("sys.stdout", mock_stdout):
                with patch("sys.stderr", MagicMock()):
                    import importlib

                    import code_puppy.terminal_utils as tu

                    importlib.reload(tu)

                    # Should not raise
                    tu.reset_windows_terminal_ansi()

    def test_ansi_reset_flush_exception(self):
        """Test ANSI reset handles flush exception."""
        mock_stdout = MagicMock()
        mock_stdout.write.return_value = None
        mock_stdout.flush.side_effect = Exception("Flush error")

        with patch("platform.system", return_value="Windows"):
            with patch("sys.stdout", mock_stdout):
                with patch("sys.stderr", MagicMock()):
                    import importlib

                    import code_puppy.terminal_utils as tu

                    importlib.reload(tu)

                    # Should not raise
                    tu.reset_windows_terminal_ansi()


class TestTruecolorDetectionEdgeCases:
    """Additional edge case tests for truecolor detection."""

    def test_detect_truecolor_rich_exception(self):
        """Test truecolor detection handles Rich exceptions."""
        import os

        with patch.dict(os.environ, {}, clear=True):
            with patch("rich.console.Console") as mock_console_class:
                mock_console_class.side_effect = Exception("Rich error")

                import importlib

                import code_puppy.terminal_utils as tu

                importlib.reload(tu)

                result = tu.detect_truecolor_support()

                # Should return False when Rich fails
                assert result is False

    def test_detect_truecolor_colorterm_case_variations(self):
        """Test COLORTERM with various case variations."""
        import importlib
        import os

        import code_puppy.terminal_utils as tu

        test_cases = [
            ("TRUECOLOR", True),
            ("24BIT", True),
            ("TrueColor", True),
            ("24Bit", True),
            ("other", False),
        ]

        for colorterm, expected in test_cases:
            with patch.dict(os.environ, {"COLORTERM": colorterm}, clear=True):
                with patch("rich.console.Console") as mock_console_class:
                    mock_console = MagicMock()
                    mock_console.color_system = "standard"
                    mock_console_class.return_value = mock_console

                    importlib.reload(tu)
                    result = tu.detect_truecolor_support()
                    assert result == expected, f"Failed for COLORTERM={colorterm}"


class TestPrintTruecolorWarningCodePaths:
    """Additional tests for print_truecolor_warning code paths."""

    def test_warning_with_provided_console(self):
        """Test warning uses provided console instance."""
        import code_puppy.terminal_utils as tu

        mock_console = MagicMock()
        mock_console.color_system = "256"

        # Patch detect_truecolor_support on the already-loaded module
        with patch.object(tu, "detect_truecolor_support", return_value=False):
            tu.print_truecolor_warning(console=mock_console)

            # Console.print should have been called multiple times
            assert mock_console.print.call_count > 0

    def test_warning_creates_console_when_none_provided(self):
        """Test warning creates a console when None is provided."""
        import code_puppy.terminal_utils as tu

        mock_console = MagicMock()
        mock_console.color_system = "standard"
        mock_console_class = MagicMock(return_value=mock_console)

        with patch.object(tu, "detect_truecolor_support", return_value=False):
            # Patch Console class at the point it's imported/used in the function
            with patch.dict(sys.modules):
                import rich.console

                original_console = rich.console.Console
                rich.console.Console = mock_console_class
                try:
                    tu.print_truecolor_warning(console=None)
                finally:
                    rich.console.Console = original_console

            # Verify console was created and print was called
            assert mock_console.print.call_count > 0

    def test_warning_skipped_when_truecolor_supported(self):
        """Test warning is completely skipped when truecolor is supported."""
        import code_puppy.terminal_utils as tu

        mock_console = MagicMock()

        with patch.object(tu, "detect_truecolor_support", return_value=True):
            tu.print_truecolor_warning(console=mock_console)

            # Console.print should NOT be called
            mock_console.print.assert_not_called()

    def test_warning_fallback_to_print_when_rich_fails(self):
        """Test fallback to builtins.print when console creation fails."""
        import rich.console

        import code_puppy.terminal_utils as tu

        printed_output = []

        def capture_print(*args, **kwargs):
            printed_output.extend(args)

        with patch.object(tu, "detect_truecolor_support", return_value=False):
            # Make Console() raise ImportError to trigger fallback path
            original_class = rich.console.Console
            rich.console.Console = MagicMock(side_effect=ImportError("No module"))
            try:
                with patch("builtins.print", capture_print):
                    tu.print_truecolor_warning(console=None)
            finally:
                rich.console.Console = original_class

        # Should have printed something via the fallback
        assert len(printed_output) > 0
        # Verify warning content
        all_text = " ".join(str(o) for o in printed_output).lower()
        assert "warning" in all_text or "truecolor" in all_text or "=" in all_text


# Cleanup fixture to restore module state after tests
@pytest.fixture(autouse=True)
def restore_module_state():
    """Restore terminal_utils module state after each test."""
    yield
    # Reload module to clean state
    import importlib

    import code_puppy.terminal_utils as tu

    try:
        importlib.reload(tu)
    except Exception:
        pass  # Best effort cleanup
