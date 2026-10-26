"""Tests for the core-side file-permission UX state provider API."""

from __future__ import annotations

from typing import Any

import pytest

from code_puppy.tools import file_permission_state as fps


@pytest.fixture(autouse=True)
def _isolate_provider():
    """Start each test provider-free and restore the previous registration."""
    saved = fps._provider
    fps._provider = None
    yield
    fps._provider = saved


def _install_provider(
    *, owner: str | None = None
) -> tuple[dict[str, Any], fps.FilePermissionStateProvider]:
    """Install dummy accessors backed by shared state."""
    state: dict[str, Any] = {"diff_shown": False, "feedback": None}

    def set_diff_shown(shown: bool = True) -> None:
        state["diff_shown"] = shown

    def was_diff_shown() -> bool:
        return state["diff_shown"]

    def clear_diff_shown() -> None:
        state["diff_shown"] = False

    def get_feedback() -> str | None:
        return state["feedback"]

    def clear_feedback() -> None:
        state["feedback"] = None

    token = fps.register_file_permission_state_provider(
        set_diff_already_shown=set_diff_shown,
        was_diff_already_shown=was_diff_shown,
        clear_diff_shown_flag=clear_diff_shown,
        get_last_user_feedback=get_feedback,
        clear_user_feedback=clear_feedback,
        owner=owner,
    )
    return state, token


class TestFallbackDefaults:
    def test_no_provider_returns_defaults(self):
        assert fps.was_diff_already_shown() is False
        assert fps.get_last_user_feedback() is None

    def test_no_provider_mutations_are_noops(self):
        fps.set_diff_already_shown(True)
        fps.clear_diff_shown_flag()
        fps.clear_user_feedback()
        assert fps.was_diff_already_shown() is False
        assert fps.get_last_user_feedback() is None


class TestProviderDelegation:
    def test_diff_shown_flag_round_trips(self):
        state, _ = _install_provider()
        fps.set_diff_already_shown()
        assert fps.was_diff_already_shown() is True
        assert state["diff_shown"] is True
        fps.clear_diff_shown_flag()
        assert fps.was_diff_already_shown() is False

    def test_feedback_round_trips(self):
        state, _ = _install_provider()
        state["feedback"] = "fix the message"
        assert fps.get_last_user_feedback() == "fix the message"
        fps.clear_user_feedback()
        assert fps.get_last_user_feedback() is None

    def test_registration_captures_plugin_loading_owner(self):
        from code_puppy.callbacks import clear_loading_context, set_loading_context

        set_loading_context("permission-plugin")
        try:
            _, token = _install_provider()
        finally:
            clear_loading_context()
        assert token.owner == "permission-plugin"


class TestProviderLifecycle:
    def test_disabled_owner_uses_fallback_without_calling_provider(self, monkeypatch):
        state, token = _install_provider(owner="permission-plugin")
        state["diff_shown"] = True
        state["feedback"] = "stale feedback"
        monkeypatch.setattr(
            "code_puppy.plugins.config.get_disabled_plugins",
            lambda: {"permission-plugin"},
        )

        assert token.owner == "permission-plugin"
        assert fps.was_diff_already_shown() is False
        assert fps.get_last_user_feedback() is None
        fps.set_diff_already_shown(False)
        fps.clear_diff_shown_flag()
        fps.clear_user_feedback()
        assert state == {"diff_shown": True, "feedback": "stale feedback"}

    def test_unregister_restores_no_provider_fallback(self):
        state, token = _install_provider()
        state["diff_shown"] = True
        state["feedback"] = "feedback"

        assert fps.unregister_file_permission_state_provider(token) is True
        assert fps.was_diff_already_shown() is False
        assert fps.get_last_user_feedback() is None
        assert fps.unregister_file_permission_state_provider(token) is False

    def test_reload_replaces_provider_and_stale_unregister_is_safe(self):
        first_state, first_token = _install_provider()
        first_state["feedback"] = "old"
        second_state, second_token = _install_provider()
        second_state["feedback"] = "new"

        assert fps.get_last_user_feedback() == "new"
        assert fps.unregister_file_permission_state_provider(first_token) is False
        assert fps.get_last_user_feedback() == "new"
        assert fps.unregister_file_permission_state_provider(second_token) is True
        assert fps.get_last_user_feedback() is None
