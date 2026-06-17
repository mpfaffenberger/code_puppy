"""Regression tests for ConsoleSpinner teardown races."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from rich.text import Text


def _not_paused():
    controller = MagicMock()
    controller.is_paused.return_value = False
    return controller


def test_update_spinner_uses_live_snapshot_during_teardown_race():
    from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

    spinner = ConsoleSpinner(console=MagicMock())
    spinner._is_spinning = True
    spinner._paused = False
    live = MagicMock()
    spinner._live = live

    def _stop_live_during_update(_panel):
        spinner._live = None

    def _stop_after_refresh():
        spinner._stop_event.set()

    live.update.side_effect = _stop_live_during_update
    live.refresh.side_effect = _stop_after_refresh
    stderr = MagicMock()

    with (
        patch.object(spinner, "update_frame"),
        patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input",
            return_value=False,
        ),
        patch(
            "code_puppy.messaging.pause_controller.get_pause_controller",
            _not_paused,
        ),
        patch("time.sleep", return_value=None),
        patch.object(sys, "stderr", stderr),
    ):
        spinner._update_spinner()

    live.update.assert_called_once()
    live.refresh.assert_called_once()
    stderr.write.assert_not_called()
    assert spinner._is_spinning is True


def test_pause_clears_live_reference_even_when_stop_raises():
    from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

    spinner = ConsoleSpinner(console=MagicMock())
    spinner._is_spinning = True
    live = MagicMock()
    live.stop.side_effect = RuntimeError("already stopped")
    spinner._live = live

    spinner.pause()

    live.stop.assert_called_once()
    assert spinner._live is None
    assert spinner._paused is True


def test_update_spinner_skips_frame_when_live_refresh_is_stopped():
    from code_puppy.messaging.spinner.console_spinner import ConsoleSpinner

    spinner = ConsoleSpinner(console=MagicMock())
    spinner._is_spinning = True
    spinner._paused = False
    live = MagicMock()
    spinner._live = live

    def _raise_stopped_live():
        spinner._stop_event.set()
        raise RuntimeError("Live display is already stopped")

    live.refresh.side_effect = _raise_stopped_live
    stderr = MagicMock()

    with (
        patch.object(spinner, "update_frame"),
        patch.object(spinner, "_generate_spinner_panel", return_value=Text("test")),
        patch(
            "code_puppy.tools.command_runner.is_awaiting_user_input",
            return_value=False,
        ),
        patch(
            "code_puppy.messaging.pause_controller.get_pause_controller",
            _not_paused,
        ),
        patch("time.sleep", return_value=None),
        patch.object(sys, "stderr", stderr),
    ):
        spinner._update_spinner()

    live.update.assert_called_once()
    live.refresh.assert_called_once()
    stderr.write.assert_not_called()
    assert spinner._is_spinning is True
