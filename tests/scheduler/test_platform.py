"""Tests for scheduler platform modules - platform.py, platform_unix.py, platform_win.py."""

import os
import signal
import sys
from unittest.mock import MagicMock, patch


class TestPlatformUnix:
    """Test platform_unix.py functions directly."""

    def test_is_process_running_true(self):
        from code_puppy.scheduler.platform_unix import is_process_running

        # Current process is always running
        assert is_process_running(os.getpid()) is True

    def test_is_process_running_false(self):
        from code_puppy.scheduler.platform_unix import is_process_running

        # PID 999999999 almost certainly doesn't exist
        assert is_process_running(999999999) is False

    def test_is_process_running_permission_error(self):
        from code_puppy.scheduler.platform_unix import is_process_running

        with patch("os.kill", side_effect=PermissionError):
            assert is_process_running(1) is False

    def test_terminate_process_success(self):
        from code_puppy.scheduler.platform_unix import terminate_process

        with patch("os.kill") as mock_kill:
            assert terminate_process(1234) is True
            mock_kill.assert_called_once_with(1234, signal.SIGTERM)

    def test_terminate_process_not_found(self):
        from code_puppy.scheduler.platform_unix import terminate_process

        with patch("os.kill", side_effect=ProcessLookupError):
            assert terminate_process(999999) is False

    def test_terminate_process_permission_error(self):
        from code_puppy.scheduler.platform_unix import terminate_process

        with patch("os.kill", side_effect=PermissionError):
            assert terminate_process(1) is False


class TestPlatformWin:
    """Test platform_win.py functions with mocked ctypes.windll."""

    def test_is_process_running_true(self):
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 123  # non-zero = valid handle
        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        with patch.dict(sys.modules, {"ctypes": MagicMock(windll=mock_windll)}):
            # Re-import to pick up mocked ctypes

            import code_puppy.scheduler.platform_win as pw

            # Directly patch ctypes in the module
            with patch.object(pw, "ctypes", MagicMock(windll=mock_windll)):
                result = pw.is_process_running(1234)
                assert result is True

    def test_is_process_running_false(self):
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 0  # 0 = invalid
        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        import code_puppy.scheduler.platform_win as pw

        with patch.object(pw, "ctypes", MagicMock(windll=mock_windll)):
            result = pw.is_process_running(1234)
            assert result is False

    def test_is_process_running_exception(self):
        import code_puppy.scheduler.platform_win as pw

        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.OpenProcess.side_effect = Exception("fail")
        with patch.object(pw, "ctypes", mock_ctypes):
            assert pw.is_process_running(1) is False

    def test_terminate_process_true(self):
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 42
        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        import code_puppy.scheduler.platform_win as pw

        with patch.object(pw, "ctypes", MagicMock(windll=mock_windll)):
            result = pw.terminate_process(1234)
            assert result is True
            mock_kernel32.TerminateProcess.assert_called_once_with(42, 0)
            mock_kernel32.CloseHandle.assert_called_once_with(42)

    def test_terminate_process_no_handle(self):
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 0
        mock_windll = MagicMock()
        mock_windll.kernel32 = mock_kernel32

        import code_puppy.scheduler.platform_win as pw

        with patch.object(pw, "ctypes", MagicMock(windll=mock_windll)):
            result = pw.terminate_process(1234)
            assert result is False

    def test_terminate_process_exception(self):
        import code_puppy.scheduler.platform_win as pw

        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.OpenProcess.side_effect = Exception("fail")
        with patch.object(pw, "ctypes", mock_ctypes):
            assert pw.terminate_process(1) is False


class TestPlatformImports:
    """Test that platform.py exports the correct functions."""

    def test_exports_exist(self):
        from code_puppy.scheduler.platform import is_process_running, terminate_process

        assert callable(is_process_running)
        assert callable(terminate_process)


class TestSchedulerMain:
    """Test __main__.py."""

    def test_main_module_importable(self):
        """Test that the module can be imported without executing."""
        import code_puppy.scheduler.__main__ as main_mod

        assert hasattr(main_mod, "start_daemon")

    def test_start_daemon_callable(self):
        """Test start_daemon is importable and callable."""
        from code_puppy.scheduler.__main__ import start_daemon

        assert callable(start_daemon)
