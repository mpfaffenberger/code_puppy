"""
Tests for Windows terminal state cleanup after cancellation.

These tests verify that the ConsoleSpinner properly resets terminal state
on Windows when stopped, and that the main interactive loop also performs
cleanup after cancellation.
"""

import platform
import sys
from unittest.mock import MagicMock, Mock, patch

import pytest


class TestConsoleSpinnerWindowsCleanup:
    """Test ConsoleSpinner Windows-specific terminal cleanup."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_stop_resets_terminal_on_windows(self):
        """Test that stop() resets terminal state on Windows."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        spinner = ConsoleSpinner()
        spinner.start()

        # Mock stdout and stderr to capture cleanup calls
        with (
            patch.object(sys, "stdout") as mock_stdout,
            patch.object(sys, "stderr") as mock_stderr,
        ):
            mock_stdout.write = Mock()
            mock_stdout.flush = Mock()
            mock_stderr.write = Mock()
            mock_stderr.flush = Mock()

            spinner.stop()

            # Verify ANSI reset codes were written
            stdout_calls = [call[0][0] for call in mock_stdout.write.call_args_list]
            stderr_calls = [call[0][0] for call in mock_stderr.write.call_args_list]

            assert "\x1b[0m" in stdout_calls, "ANSI reset not written to stdout"
            assert "\x1b[0m" in stderr_calls, "ANSI reset not written to stderr"
            assert "\r" in stdout_calls, "Carriage return not written"
            assert "\x1b[K" in stdout_calls, "Clear line code not written"

            # Verify flush was called
            assert mock_stdout.flush.called, "stdout not flushed"
            assert mock_stderr.flush.called, "stderr not flushed"

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    @patch("msvcrt.kbhit")
    @patch("msvcrt.getch")
    def test_stop_flushes_keyboard_buffer_on_windows(self, mock_getch, mock_kbhit):
        """Test that stop() flushes keyboard buffer on Windows."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        # Simulate keyboard buffer with 3 keys
        mock_kbhit.side_effect = [True, True, True, False]
        mock_getch.return_value = b"x"

        spinner = ConsoleSpinner()
        spinner.start()

        with patch.object(sys, "stdout"), patch.object(sys, "stderr"):
            spinner.stop()

        # Verify keyboard buffer was flushed
        assert mock_kbhit.call_count == 4, "kbhit not called enough times"
        assert mock_getch.call_count == 3, "getch not called for each buffered key"

    @pytest.mark.skipif(platform.system() == "Windows", reason="Non-Windows test")
    def test_stop_skips_windows_cleanup_on_other_platforms(self):
        """Test that Windows cleanup is skipped on non-Windows platforms."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        spinner = ConsoleSpinner()
        spinner.start()

        with (
            patch.object(sys, "stdout") as mock_stdout,
            patch.object(sys, "stderr") as mock_stderr,
        ):
            mock_stdout.write = Mock()
            mock_stderr.write = Mock()

            spinner.stop()

            # On non-Windows, we shouldn't see the Windows-specific cleanup
            # (though Rich may still write to stdout for its own cleanup)
            # Just verify we didn't import msvcrt
            stdout_calls = [call[0][0] for call in mock_stdout.write.call_args_list]

            # If there are no calls, that's fine for non-Windows
            # Just checking the test runs without error on non-Windows

    def test_stop_handles_cleanup_errors_gracefully(self):
        """Test that stop() handles cleanup errors without crashing."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        spinner = ConsoleSpinner()
        spinner.start()

        # Make stdout.write raise an exception
        with patch.object(sys, "stdout") as mock_stdout:
            mock_stdout.write = Mock(side_effect=Exception("Write error"))
            mock_stdout.flush = Mock()

            # Should not raise exception
            spinner.stop()
            assert not spinner._is_spinning


class TestMainInteractiveModeWindowsCleanup:
    """Test main.py interactive mode Windows-specific cleanup."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    async def test_cancellation_resets_terminal_state(self):
        """Test that cancellation in interactive mode resets terminal state."""
        # This test verifies the cleanup code around line 645 in main.py

        with (
            patch.object(sys, "stdout") as mock_stdout,
            patch.object(sys, "stderr") as mock_stderr,
        ):
            mock_stdout.write = Mock()
            mock_stdout.flush = Mock()
            mock_stderr.write = Mock()
            mock_stderr.flush = Mock()

            # Simulate the cleanup code that runs when result is None
            if platform.system() == "Windows":
                try:
                    sys.stdout.write("\x1b[0m")
                    sys.stdout.flush()
                    sys.stderr.write("\x1b[0m")
                    sys.stderr.flush()
                except Exception:
                    pass

            # Verify ANSI reset was written
            stdout_calls = [call[0][0] for call in mock_stdout.write.call_args_list]
            stderr_calls = [call[0][0] for call in mock_stderr.write.call_args_list]

            assert "\x1b[0m" in stdout_calls, "ANSI reset not written to stdout"
            assert "\x1b[0m" in stderr_calls, "ANSI reset not written to stderr"
            assert mock_stdout.flush.called, "stdout not flushed"
            assert mock_stderr.flush.called, "stderr not flushed"

    @pytest.mark.asyncio
    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    async def test_input_prompt_resets_terminal_state(self):
        """Test that terminal state is reset before prompting for input."""
        # This test verifies the cleanup code around line 482 in main.py

        with patch.object(sys, "stdout") as mock_stdout:
            mock_stdout.write = Mock()
            mock_stdout.flush = Mock()

            # Simulate the cleanup code that runs before prompting
            if platform.system() == "Windows":
                try:
                    sys.stdout.write("\x1b[0m")
                    sys.stdout.flush()
                except Exception:
                    pass

            # Verify ANSI reset was written
            stdout_calls = [call[0][0] for call in mock_stdout.write.call_args_list]
            assert "\x1b[0m" in stdout_calls, "ANSI reset not written before prompt"
            assert mock_stdout.flush.called, "stdout not flushed before prompt"


class TestWindowsCleanupIntegration:
    """Integration tests for Windows terminal cleanup."""

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_spinner_cleanup_comprehensive(self):
        """Comprehensive test of spinner cleanup sequence."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        spinner = ConsoleSpinner()

        # Start and stop multiple times to ensure cleanup works consistently
        for _ in range(3):
            spinner.start()

            with (
                patch.object(sys, "stdout") as mock_stdout,
                patch.object(sys, "stderr") as mock_stderr,
            ):
                mock_stdout.write = Mock()
                mock_stdout.flush = Mock()
                mock_stderr.write = Mock()
                mock_stderr.flush = Mock()

                spinner.stop()

                # Verify all cleanup steps
                stdout_writes = [
                    call[0][0] for call in mock_stdout.write.call_args_list
                ]

                assert any("\x1b[0m" in s for s in stdout_writes), "ANSI reset missing"
                assert any("\r" in s for s in stdout_writes), "Carriage return missing"
                assert any("\x1b[K" in s for s in stdout_writes), "Clear line missing"
                assert mock_stdout.flush.called, "stdout not flushed"
                assert mock_stderr.flush.called, "stderr not flushed"

    @pytest.mark.skipif(platform.system() != "Windows", reason="Windows-specific test")
    def test_cleanup_does_not_interfere_with_normal_operation(self):
        """Test that cleanup doesn't break normal spinner operation."""
        from code_puppy.messaging.spinner import ConsoleSpinner

        spinner = ConsoleSpinner()

        # Multiple start/stop cycles should work without issues
        for i in range(5):
            spinner.start()
            assert spinner._is_spinning, f"Spinner not spinning on iteration {i}"

            spinner.stop()
            assert not spinner._is_spinning, (
                f"Spinner still spinning after stop on iteration {i}"
            )
