"""Tests for the shared TUI menu terminal-ownership session."""

from unittest.mock import patch

from code_puppy.command_line.menu_session import menu_session
from code_puppy.messaging.pause_controller import get_pause_controller


def test_session_pauses_renderer_and_resumes_after():
    pc = get_pause_controller()
    assert not pc.is_paused()
    with menu_session():
        assert pc.is_paused()
    assert not pc.is_paused()


def test_session_is_reentrant_single_pause_cycle():
    pc = get_pause_controller()
    with menu_session():
        assert pc.is_paused()
        with menu_session():
            assert pc.is_paused()
        # Inner exit must NOT resume: the outer session still owns the
        # terminal (nested pin-a-model inside the agent picker).
        assert pc.is_paused()
    assert not pc.is_paused()


def test_session_resumes_on_exception():
    pc = get_pause_controller()
    try:
        with menu_session():
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert not pc.is_paused()


def test_failed_entry_unwinds_cleanly():
    pc = get_pause_controller()
    with patch(
        "code_puppy.messaging.run_ui.suspended_run_ui",
        side_effect=RuntimeError("no ui"),
    ):
        try:
            with menu_session():
                raise AssertionError("should not enter")
        except RuntimeError:
            pass
    assert not pc.is_paused()
    # Depth must be back to zero: a fresh session still works.
    with menu_session():
        assert pc.is_paused()
    assert not pc.is_paused()
