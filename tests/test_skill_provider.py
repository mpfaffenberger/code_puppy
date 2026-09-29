"""Tests for the optional skills provider callback seam."""

from unittest.mock import MagicMock, patch

from code_puppy.callbacks import (
    clear_callbacks,
    clear_loading_context,
    register_callback,
    set_loading_context,
)
from code_puppy.skill_provider import get_skill_provider


def setup_function():
    clear_callbacks("register_skills")


def teardown_function():
    clear_loading_context()
    clear_callbacks("register_skills")


def test_no_plugin_returns_none():
    assert get_skill_provider() is None


def test_first_provider_wins_deterministically():
    first = MagicMock(name="first")
    second = MagicMock(name="second")
    register_callback("register_skills", lambda: [{"provider": first}])
    register_callback("register_skills", lambda: [{"provider": second}])

    assert get_skill_provider() is first


def test_resolution_is_repeated_not_cached():
    provider = MagicMock()
    calls = []

    def provide_skills():
        calls.append(True)
        return [{"provider": provider}]

    register_callback("register_skills", provide_skills)

    assert get_skill_provider() is provider
    assert get_skill_provider() is provider
    assert len(calls) == 2


def test_disabled_plugin_provider_is_filtered():
    provider = MagicMock()

    set_loading_context("agent_skills")
    register_callback("register_skills", lambda: [{"provider": provider}])
    clear_loading_context()

    with patch(
        "code_puppy.callbacks._get_disabled_plugins", return_value={"agent_skills"}
    ):
        assert get_skill_provider() is None


def test_skill_entries_and_invalid_results_are_ignored():
    provider = MagicMock()
    register_callback(
        "register_skills",
        lambda: [
            {"name": "ordinary-skill", "skill_md": "# body"},
            "not-a-dict",
            {"provider": provider},
        ],
    )

    assert get_skill_provider() is provider
