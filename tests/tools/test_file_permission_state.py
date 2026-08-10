"""Tests for the core-side file-permission UX state provider API.

The approval *decision* flows through the ``file_permission`` hook; this
module's state (diff-already-shown flag, last user feedback) is reached
through ``code_puppy.tools.file_permission_state`` so core never imports
the file-permission plugin.
"""

from __future__ import annotations

import pytest

from code_puppy.tools import file_permission_state as fps


@pytest.fixture(autouse=True)
def _isolate_provider():
    """Start each test with no provider and restore the previous one after.

    Other test files may already have registered the real plugin provider in
    the same process (plugin modules cache in ``sys.modules``), so fallback
    tests must actively clear it to stay deterministic -- while teardown
    restores whatever was registered before, so nothing leaks out.
    """
    saved = {
        "_diff_shown_setter": fps._diff_shown_setter,
        "_diff_shown_getter": fps._diff_shown_getter,
        "_diff_shown_clearer": fps._diff_shown_clearer,
        "_feedback_getter": fps._feedback_getter,
        "_feedback_clearer": fps._feedback_clearer,
    }
    fps._diff_shown_setter = None
    fps._diff_shown_getter = None
    fps._diff_shown_clearer = None
    fps._feedback_getter = None
    fps._feedback_clearer = None
    yield
    for name, value in saved.items():
        setattr(fps, name, value)


def _install_provider() -> dict:
    """Install dummy accessors backed by a shared dict; returns that dict."""
    state: dict = {"diff_shown": False, "feedback": None}

    def set_diff_shown(shown: bool = True) -> None:
        state["diff_shown"] = shown

    def was_diff_shown() -> bool:
        return state["diff_shown"]

    def clear_diff_shown() -> None:
        state["diff_shown"] = False

    def get_feedback():
        return state["feedback"]

    def clear_feedback() -> None:
        state["feedback"] = None

    fps.register_file_permission_state_provider(
        set_diff_already_shown=set_diff_shown,
        was_diff_already_shown=was_diff_shown,
        clear_diff_shown_flag=clear_diff_shown,
        get_last_user_feedback=get_feedback,
        clear_user_feedback=clear_feedback,
    )
    return state


class TestFallbackDefaults:
    def test_no_provider_returns_false_for_diff_shown(self):
        assert fps.was_diff_already_shown() is False

    def test_no_provider_returns_none_for_feedback(self):
        assert fps.get_last_user_feedback() is None

    def test_no_provider_set_clear_are_noops(self):
        fps.set_diff_already_shown(True)
        fps.clear_diff_shown_flag()
        fps.clear_user_feedback()
        assert fps.was_diff_already_shown() is False
        assert fps.get_last_user_feedback() is None


class TestProviderDelegation:
    def test_diff_shown_flag_round_trips(self):
        state = _install_provider()
        fps.set_diff_already_shown(True)
        assert fps.was_diff_already_shown() is True
        assert state["diff_shown"] is True
        fps.clear_diff_shown_flag()
        assert state["diff_shown"] is False
        assert fps.was_diff_already_shown() is False

    def test_feedback_round_trips(self):
        state = _install_provider()
        state["feedback"] = "fix the message"
        assert fps.get_last_user_feedback() == "fix the message"
        fps.clear_user_feedback()
        assert fps.get_last_user_feedback() is None

    def test_reregister_replaces_provider(self):
        first = _install_provider()
        first["feedback"] = "from first"
        second = _install_provider()
        # The second registration fully replaces the accessors.
        assert fps.get_last_user_feedback() is None
        second["feedback"] = "from second"
        assert fps.get_last_user_feedback() == "from second"

    def test_default_flag_arg_sets_true(self):
        _install_provider()
        fps.set_diff_already_shown()
        assert fps.was_diff_already_shown() is True
