"""/tutorial hands OAuth follow-ups to plugins through hooks, never imports."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from code_puppy.command_line.core_commands import handle_tutorial_command

WIZARD = "code_puppy.command_line.onboarding_wizard"


@pytest.fixture
def run_tutorial():
    """Run /tutorial with the wizard answering ``choice``; return the mocks."""

    def _run(choice, oauth_results=()):
        mocks = {
            "reset": Mock(),
            "require_setup": Mock(),
            "custom_command": Mock(),
            "oauth": Mock(return_value=list(oauth_results)),
            "set_model": Mock(),
        }
        with (
            patch(f"{WIZARD}.run_onboarding_wizard", AsyncMock(return_value=choice)),
            patch(f"{WIZARD}.reset_onboarding", mocks["reset"]),
            patch(f"{WIZARD}.require_model_setup_if_needed", mocks["require_setup"]),
            patch("code_puppy.callbacks.on_custom_command", mocks["custom_command"]),
            patch("code_puppy.callbacks.on_claude_oauth_authenticate", mocks["oauth"]),
            patch(
                "code_puppy.model_switching.set_model_and_reload_agent",
                mocks["set_model"],
            ),
            patch("code_puppy.command_line.core_commands.emit_info"),
        ):
            assert handle_tutorial_command("/tutorial") is True
        mocks["reset"].assert_called_once_with()
        mocks["require_setup"].assert_called_once_with(choice)
        return mocks

    return _run


def test_chatgpt_choice_dispatches_the_plugin_command(run_tutorial):
    mocks = run_tutorial("chatgpt")
    mocks["custom_command"].assert_called_once_with("/chatgpt-auth", "chatgpt-auth")
    mocks["oauth"].assert_not_called()


@pytest.mark.parametrize(
    "results, switches", [([True], True), ([None], False), ([], False)]
)
def test_claude_choice_switches_model_only_after_plugin_auth(
    run_tutorial, results, switches
):
    mocks = run_tutorial("claude", results)
    mocks["oauth"].assert_called_once_with()
    assert mocks["set_model"].called is switches


@pytest.mark.parametrize("choice", ["completed", "skipped"])
def test_plain_endings_touch_no_plugin(run_tutorial, choice):
    mocks = run_tutorial(choice)
    mocks["custom_command"].assert_not_called()
    mocks["oauth"].assert_not_called()
