"""Tests for code_puppy.messaging.spinner.console_spinner."""

import time
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner


@pytest.fixture
def console():
    return Console(file=StringIO(), force_terminal=False, width=120)


@pytest.fixture(autouse=True)
def reset_user_input():
    """Ensure awaiting_user_input is reset."""
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=False,
    ):
        yield


def test_init(console):
    spinner = ConsoleSpinner(console=console)
    assert not spinner.is_spinning
    assert spinner._thread is None


def test_start_stop(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    assert spinner.is_spinning
    time.sleep(0.15)
    spinner.stop()
    assert not spinner.is_spinning
    assert spinner._thread is None
    assert spinner._live is None


def test_stop_when_not_spinning(console):
    spinner = ConsoleSpinner(console=console)
    spinner.stop()  # Should not raise


def test_start_twice_no_double_thread(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    thread1 = spinner._thread
    spinner.start()  # Should not start another thread
    assert spinner._thread is thread1
    spinner.stop()


def test_context_manager(console):
    spinner = ConsoleSpinner(console=console)
    with spinner:
        assert spinner.is_spinning
    assert not spinner.is_spinning


def test_update_frame(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    spinner.update_frame()
    spinner.stop()


def test_generate_spinner_panel(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    panel = spinner._generate_spinner_panel()
    assert panel is not None
    spinner.stop()


def test_generate_spinner_panel_paused(console):
    spinner = ConsoleSpinner(console=console)
    spinner._paused = True

    panel = spinner._generate_spinner_panel()
    assert str(panel) == ""


def test_generate_spinner_panel_with_context(console):
    from code_puppy.messaging.spinner.spinner_base import SpinnerBase

    SpinnerBase.set_context_info("test context")
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    panel = spinner._generate_spinner_panel()
    assert "test context" in str(panel)
    spinner.stop()
    SpinnerBase.clear_context_info()


def test_pause_resume(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    time.sleep(0.05)

    spinner.pause()
    assert spinner._paused
    assert spinner._live is None

    spinner.resume()
    assert not spinner._paused
    time.sleep(0.05)

    spinner.stop()


def test_resume_when_not_paused(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    spinner.resume()  # Not paused, should be no-op
    spinner.stop()


def test_resume_when_awaiting_user_input(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    spinner._paused = True
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=True,
    ):
        spinner.resume()
    assert spinner._paused  # Should stay paused
    spinner.stop()


def test_resume_with_existing_live(console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    time.sleep(0.05)
    spinner._paused = True
    # Don't destroy _live
    spinner._paused = True
    # Now resume with _live still existing
    live_mock = MagicMock()
    spinner._live = live_mock
    spinner.resume()
    spinner.stop()


@patch("platform.system", return_value="Windows")
def test_stop_windows_cleanup(mock_sys, console):
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    time.sleep(0.05)
    spinner.stop()
    assert not spinner.is_spinning


def test_spinner_thread_error_handling(console):
    """Test that spinner thread handles exceptions gracefully."""
    spinner = ConsoleSpinner(console=console)
    spinner.start()
    # Force an error in the update loop
    spinner._live = MagicMock()
    spinner._live.update.side_effect = Exception("render fail")
    time.sleep(0.15)
    # The thread should handle the error
    spinner.stop()


def test_generate_spinner_panel_awaiting_input(console):
    spinner = ConsoleSpinner(console=console)
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=True,
    ):
        panel = spinner._generate_spinner_panel()
        assert str(panel) == ""


def test_pause_cleanup_exception(console):
    """pause() catches exceptions during Live cleanup."""
    spinner = ConsoleSpinner(console=console)
    spinner._is_spinning = True
    spinner._live = MagicMock()
    spinner._live.stop.side_effect = RuntimeError("cleanup fail")
    spinner.pause()  # Should not raise
    assert spinner._paused


def test_resume_live_start_exception(console):
    """resume() catches exceptions during Live creation."""
    spinner = ConsoleSpinner(console=console)
    spinner._is_spinning = True
    spinner._paused = True
    spinner._live = None
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=False,
    ):
        with patch(
            "code_puppy.messaging.spinner.console_spinner.Live",
            side_effect=RuntimeError("live fail"),
        ):
            spinner.resume()  # Should not raise


def test_resume_live_update_exception(console):
    """resume() catches exceptions during Live update/refresh."""
    spinner = ConsoleSpinner(console=console)
    spinner._is_spinning = True
    spinner._paused = True
    spinner._live = MagicMock()
    spinner._live.update.side_effect = RuntimeError("update fail")
    with patch(
        "code_puppy.tools.command_runner.is_awaiting_user_input",
        return_value=False,
    ):
        spinner.resume()  # Should not raise
