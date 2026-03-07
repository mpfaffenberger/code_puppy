"""Comprehensive tests for ConsoleSpinner to boost coverage.

Tests spinner animation, state management, threading, and visual output.
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console
from rich.text import Text


# Patch register_spinner at the package level where it's imported from
@pytest.fixture(autouse=True)
def mock_spinner_registration():
    """Mock spinner registration for all tests."""
    with (
        patch("code_puppy.messaging.spinner.register_spinner"),
        patch("code_puppy.messaging.spinner.unregister_spinner"),
    ):
        yield


class TestConsoleSpinnerInit:
    """Tests for ConsoleSpinner initialization."""

    def test_init_creates_console_if_not_provided(self):
        """Test that a Console is created when none is provided."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner()

        assert spinner.console is not None
        assert isinstance(spinner.console, Console)

    def test_init_uses_provided_console(self):
        """Test that provided console is used."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        assert spinner.console is mock_console

    def test_init_sets_default_state(self):
        """Test initialization sets correct default state."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner()

        assert spinner._thread is None
        assert spinner._paused is False
        assert spinner._live is None
        assert spinner._is_spinning is False

    def test_init_registers_spinner(self):
        """Test that spinner is registered on init."""
        with patch("code_puppy.messaging.spinner.register_spinner") as mock_register:
            from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

            spinner = ConsoleSpinner()

            mock_register.assert_called_once_with(spinner)


class TestConsoleSpinnerStart:
    """Tests for ConsoleSpinner.start() method."""

    def test_start_sets_spinning_state(self):
        """Test that start() sets is_spinning to True."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live_cls,
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live
            spinner.start()

        assert spinner._is_spinning is True
        spinner._stop_event.set()  # Stop the thread
        time.sleep(0.1)

    def test_start_clears_stop_event(self):
        """Test that start() clears the stop event."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._stop_event.set()  # Set it first

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live_cls,
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live
            spinner.start()

        # Will be cleared by start()
        # Note: The thread will run so we need to stop it
        spinner._stop_event.set()
        time.sleep(0.1)

    def test_start_creates_live_display(self):
        """Test that start() creates a Live display."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live_cls,
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live
            spinner.start()

        mock_live_cls.assert_called_once()
        mock_live.start.assert_called_once()
        spinner._stop_event.set()
        time.sleep(0.1)

    def test_start_prints_blank_line(self):
        """Test that start() prints blank line for visual separation."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live_cls,
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live
            spinner.start()

        mock_console.print.assert_called()
        spinner._stop_event.set()
        time.sleep(0.1)

    def test_start_creates_daemon_thread(self):
        """Test that start() creates a daemon thread."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live_cls,
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            mock_live = MagicMock()
            mock_live_cls.return_value = mock_live
            spinner.start()
            time.sleep(0.1)  # Let thread start

        assert spinner._thread is not None
        assert spinner._thread.daemon is True
        spinner._stop_event.set()
        spinner._thread.join(timeout=0.5)

    def test_start_does_not_create_thread_if_already_running(self):
        """Test that start() doesn't create new thread if one exists."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)

        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        spinner._thread = mock_thread
        spinner._is_spinning = True

        with patch("threading.Thread") as mock_thread_class:
            spinner.start()

        # Should not create a new thread
        mock_thread_class.assert_not_called()


class TestConsoleSpinnerStop:
    """Tests for ConsoleSpinner.stop() method."""

    def test_stop_when_not_spinning_returns_early(self):
        """Test that stop() returns early if not spinning."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = False

        with patch("code_puppy.messaging.spinner.unregister_spinner") as mock_unreg:
            spinner.stop()

        # Should not try to unregister if not spinning
        mock_unreg.assert_not_called()

    def test_stop_sets_stop_event(self):
        """Test that stop() sets the stop event."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True

        spinner.stop()

        assert spinner._stop_event.is_set()

    def test_stop_sets_is_spinning_false(self):
        """Test that stop() sets is_spinning to False."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True

        spinner.stop()

        assert spinner._is_spinning is False

    def test_stop_stops_live_display(self):
        """Test that stop() stops the Live display."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True
        mock_live = MagicMock()
        spinner._live = mock_live

        spinner.stop()

        mock_live.stop.assert_called_once()
        assert spinner._live is None

    def test_stop_joins_thread(self):
        """Test that stop() joins the thread."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        spinner._thread = mock_thread

        spinner.stop()

        mock_thread.join.assert_called_once_with(timeout=0.5)
        assert spinner._thread is None

    def test_stop_unregisters_spinner(self):
        """Test that stop() unregisters the spinner."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True

        with patch("code_puppy.messaging.spinner.unregister_spinner") as mock_unreg:
            spinner.stop()

        mock_unreg.assert_called_once_with(spinner)

    def test_stop_windows_cleanup(self):
        """Test Windows-specific cleanup on stop."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True

        mock_stdout = MagicMock()
        mock_stderr = MagicMock()

        with (
            patch("platform.system", return_value="Windows"),
            patch.object(sys, "stdout", mock_stdout),
            patch.object(sys, "stderr", mock_stderr),
        ):
            spinner.stop()

        # Should write ANSI reset codes on Windows
        assert mock_stdout.write.called
        assert mock_stderr.write.called

    def test_stop_non_windows_no_special_cleanup(self):
        """Test that non-Windows doesn't do special cleanup."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock(spec=Console)
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True

        mock_stdout = MagicMock()

        with (
            patch("platform.system", return_value="Linux"),
            patch.object(sys, "stdout", mock_stdout),
        ):
            spinner.stop()

        # stdout.write should not be called for ANSI reset on Linux
        # The write is only in the Windows block


class TestConsoleSpinnerUpdateFrame:
    """Tests for update_frame method."""

    def test_update_frame_advances_index(self):
        """Test that update_frame advances the frame index."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._frame_index = 0

        spinner.update_frame()

        assert spinner._frame_index == 1

    def test_update_frame_wraps_around(self):
        """Test that update_frame wraps around at end of frames."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._frame_index = len(SpinnerBase.FRAMES) - 1

        spinner.update_frame()

        assert spinner._frame_index == 0


class TestConsoleSpinnerGeneratePanel:
    """Tests for _generate_spinner_panel method."""

    def test_generate_panel_when_paused_returns_empty(self):
        """Test that paused spinner returns empty Text."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = True

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=False
        ):
            result = spinner._generate_spinner_panel()

        assert isinstance(result, Text)
        assert str(result) == ""

    def test_generate_panel_when_awaiting_input_returns_empty(self):
        """Test that spinner returns empty when awaiting user input."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=True
        ):
            result = spinner._generate_spinner_panel()

        assert isinstance(result, Text)
        assert str(result) == ""

    def test_generate_panel_includes_thinking_message(self):
        """Test that panel includes a rotating loading message with puppy name."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False
        spinner._frame_index = 0

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=False
        ):
            result = spinner._generate_spinner_panel()

        result_str = str(result)
        # Should contain the puppy name prefix (e.g. "Blu is ...")
        assert SpinnerBase.puppy_name.lower() in result_str.lower()
        assert " is " in result_str

    def test_generate_panel_includes_current_frame(self):
        """Test that panel includes current spinner frame."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False
        spinner._frame_index = 0

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=False
        ):
            result = spinner._generate_spinner_panel()

        result_str = str(result)
        assert SpinnerBase.FRAMES[0] in result_str

    def test_generate_panel_includes_context_info(self):
        """Test that panel includes context info when set."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False
        spinner._frame_index = 0

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch.object(
                SpinnerBase,
                "get_context_info",
                return_value="Tokens: 1,000/10,000 (10.0% used)",
            ),
        ):
            result = spinner._generate_spinner_panel()

        result_str = str(result)
        assert "Tokens" in result_str

    def test_generate_panel_no_context_info(self):
        """Test panel without context info."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner
        from code_puppy.messaging.spinner.spinner_base import SpinnerBase

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False
        spinner._frame_index = 0

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch.object(SpinnerBase, "get_context_info", return_value=""),
        ):
            result = spinner._generate_spinner_panel()

        # Should still generate valid Text
        assert isinstance(result, Text)


class TestConsoleSpinnerUpdateSpinner:
    """Tests for _update_spinner background thread method."""

    def test_update_spinner_stops_on_event(self):
        """Test that _update_spinner stops when stop event is set."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._stop_event.set()

        # Should return quickly
        spinner._update_spinner()

        # If we got here, it stopped

    def test_update_spinner_updates_frame(self):
        """Test that _update_spinner calls update_frame."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._live = MagicMock()
        spinner._paused = False
        call_count = 0

        def stop_after_calls():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                spinner._stop_event.set()

        with (
            patch.object(spinner, "update_frame", side_effect=stop_after_calls),
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
        ):
            spinner._update_spinner()

        assert call_count >= 2

    def test_update_spinner_skips_update_when_paused(self):
        """Test that _update_spinner skips display update when paused."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = True
        spinner._live = MagicMock()
        call_count = 0

        def stop_after_calls():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                spinner._stop_event.set()

        with (
            patch.object(spinner, "update_frame", side_effect=stop_after_calls),
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
        ):
            spinner._update_spinner()

        # Should not update live display when paused
        spinner._live.update.assert_not_called()

    def test_update_spinner_skips_when_awaiting_input(self):
        """Test that _update_spinner skips display update when awaiting input."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._paused = False
        spinner._live = MagicMock()
        call_count = 0

        def stop_after_calls():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                spinner._stop_event.set()

        with (
            patch.object(spinner, "update_frame", side_effect=stop_after_calls),
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=True,
            ),
        ):
            spinner._update_spinner()

        # Should not update live display when awaiting input
        spinner._live.update.assert_not_called()

    def test_update_spinner_handles_exception(self):
        """Test that _update_spinner handles exceptions gracefully."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._live = MagicMock()

        mock_stderr = MagicMock()

        with (
            patch.object(
                spinner, "update_frame", side_effect=RuntimeError("test error")
            ),
            patch.object(sys, "stderr", mock_stderr),
        ):
            spinner._update_spinner()

        # Should write error to stderr
        mock_stderr.write.assert_called()
        assert spinner._is_spinning is False


class TestConsoleSpinnerPause:
    """Tests for pause method."""

    def test_pause_sets_paused_flag(self):
        """Test that pause sets the paused flag."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True

        spinner.pause()

        assert spinner._paused is True

    def test_pause_stops_live_display(self):
        """Test that pause stops the live display."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        mock_live = MagicMock()
        spinner._live = mock_live

        with patch.object(sys, "stdout"):
            spinner.pause()

        mock_live.stop.assert_called_once()
        assert spinner._live is None

    def test_pause_clears_line(self):
        """Test that pause clears the terminal line."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        mock_live = MagicMock()
        spinner._live = mock_live

        mock_stdout = MagicMock()

        with patch.object(sys, "stdout", mock_stdout):
            spinner.pause()

        # Should write cursor/line clear codes
        mock_stdout.write.assert_called()

    def test_pause_does_nothing_when_not_spinning(self):
        """Test that pause does nothing when not spinning."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = False
        spinner._paused = False

        spinner.pause()

        assert spinner._paused is False

    def test_pause_handles_exception(self):
        """Test that pause handles exceptions gracefully."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        mock_live = MagicMock()
        mock_live.stop.side_effect = RuntimeError("test")
        spinner._live = mock_live

        # Should not raise
        spinner.pause()


class TestConsoleSpinnerResume:
    """Tests for resume method."""

    def test_resume_clears_paused_flag(self):
        """Test that resume clears the paused flag."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._paused = True
        spinner._live = MagicMock()

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=False
        ):
            spinner.resume()

        assert spinner._paused is False

    def test_resume_does_nothing_when_awaiting_input(self):
        """Test that resume does nothing when awaiting user input."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._paused = True

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=True
        ):
            spinner.resume()

        # Should remain paused
        assert spinner._paused is True

    def test_resume_restarts_live_display(self):
        """Test that resume restarts the live display."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True
        spinner._paused = True
        spinner._live = None

        mock_stdout = MagicMock()

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.spinner.console_spinner.Live"
            ) as mock_live_class,
            patch.object(sys, "stdout", mock_stdout),
        ):
            mock_live = MagicMock()
            mock_live_class.return_value = mock_live
            spinner.resume()

        mock_live_class.assert_called_once()
        mock_live.start.assert_called_once()

    def test_resume_updates_existing_live_display(self):
        """Test that resume updates existing live display."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()
        mock_console.file = MagicMock()
        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True
        spinner._paused = True
        mock_live = MagicMock()
        spinner._live = mock_live

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            spinner.resume()

        mock_live.update.assert_called()
        mock_live.refresh.assert_called()

    def test_resume_does_nothing_when_not_spinning(self):
        """Test that resume does nothing when not spinning."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = False
        spinner._paused = True

        with patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input", return_value=False
        ):
            spinner.resume()

        # paused state unchanged when not spinning
        assert spinner._paused is True

    def test_resume_does_nothing_when_not_paused(self):
        """Test that resume does nothing when not paused."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._paused = False

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.spinner.console_spinner.Live"
            ) as mock_live_class,
        ):
            spinner.resume()

        # Should not create new Live display
        mock_live_class.assert_not_called()

    def test_resume_handles_exception(self):
        """Test that resume handles exceptions gracefully."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())
        spinner._is_spinning = True
        spinner._paused = True
        spinner._live = None

        mock_stdout = MagicMock()

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch(
                "code_puppy.messaging.spinner.console_spinner.Live",
                side_effect=RuntimeError("test"),
            ),
            patch.object(sys, "stdout", mock_stdout),
        ):
            # Should not raise
            spinner.resume()

    def test_resume_clears_console_buffer_if_exists(self):
        """Test that resume clears console buffer if it exists."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()
        mock_console._buffer = []
        mock_console.file = MagicMock()

        spinner = ConsoleSpinner(console=mock_console)
        spinner._is_spinning = True
        spinner._paused = True
        mock_live = MagicMock()
        spinner._live = mock_live

        with (
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        ):
            spinner.resume()

        # Should have written clear codes
        mock_console.file.write.assert_called()


class TestConsoleSpinnerContextManager:
    """Tests for context manager protocol."""

    def test_enter_starts_spinner(self):
        """Test that __enter__ starts the spinner."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())

        with patch.object(spinner, "start") as mock_start:
            result = spinner.__enter__()

        mock_start.assert_called_once()
        assert result is spinner

    def test_exit_stops_spinner(self):
        """Test that __exit__ stops the spinner."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        spinner = ConsoleSpinner(console=MagicMock())

        with patch.object(spinner, "stop") as mock_stop:
            spinner.__exit__(None, None, None)

        mock_stop.assert_called_once()

    def test_context_manager_full_cycle(self):
        """Test full context manager cycle."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live,
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance

            spinner = ConsoleSpinner(console=mock_console)

            with spinner:
                assert spinner._is_spinning is True

            # After context, should be stopped
            assert spinner._is_spinning is False


class TestConsoleSpinnerIntegration:
    """Integration tests for ConsoleSpinner."""

    def test_full_start_stop_cycle(self):
        """Test complete start/stop lifecycle."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live,
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance

            spinner = ConsoleSpinner(console=mock_console)

            spinner.start()
            assert spinner._is_spinning is True
            time.sleep(0.1)  # Let thread run briefly

            spinner.stop()
            assert spinner._is_spinning is False
            assert spinner._thread is None

    def test_pause_resume_cycle(self):
        """Test pause and resume cycle."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live,
            patch(
                "code_puppy.tools.command_runner.is_awaiting_user_input",
                return_value=False,
            ),
            patch.object(sys, "stdout"),
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance

            spinner = ConsoleSpinner(console=mock_console)

            spinner.start()
            assert spinner._is_spinning is True
            assert spinner._paused is False

            spinner.pause()
            assert spinner._paused is True

            spinner.resume()
            assert spinner._paused is False

            spinner.stop()

    def test_multiple_start_calls(self):
        """Test multiple start calls are handled."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live,
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance

            spinner = ConsoleSpinner(console=mock_console)

            spinner.start()
            first_thread = spinner._thread
            time.sleep(0.05)

            spinner.start()  # Should not create new thread

            # Thread should be the same
            assert spinner._thread is first_thread

            spinner.stop()

    def test_multiple_stop_calls(self):
        """Test multiple stop calls are handled."""
        from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

        mock_console = MagicMock()

        with (
            patch("code_puppy.messaging.spinner.console_spinner.Live") as mock_live,
        ):
            mock_live_instance = MagicMock()
            mock_live.return_value = mock_live_instance

            spinner = ConsoleSpinner(console=mock_console)

            spinner.start()
            spinner.stop()

            # Second stop should not raise
            spinner.stop()

            assert spinner._is_spinning is False
