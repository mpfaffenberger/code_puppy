"""Tests for the /tutorial command flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.core_commands import handle_tutorial_command


def _mock_tutorial_result(mock_executor_class: Any, result: str) -> None:
    mock_future = MagicMock()
    mock_future.result.return_value = result

    mock_executor = MagicMock()
    mock_executor.submit.return_value = mock_future

    mock_executor_class.return_value.__enter__.return_value = mock_executor


def test_tutorial_chatgpt_flow() -> None:
    """Test tutorial triggers ChatGPT OAuth and model switch."""
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
        _mock_tutorial_result(mock_executor_class, "chatgpt")

        with patch(
            "code_puppy.command_line.onboarding_wizard.reset_onboarding"
        ) as mock_reset:
            with patch(
                "code_puppy.plugins.chatgpt_oauth.oauth_flow.run_oauth_flow"
            ) as mock_oauth:
                with patch(
                    "code_puppy.model_switching.set_model_and_reload_agent"
                ) as mock_set_model:
                    with patch("code_puppy.command_line.core_commands.emit_info"):
                        result = handle_tutorial_command("/tutorial")

    assert result is True
    mock_reset.assert_called_once()
    mock_oauth.assert_called_once()
    mock_set_model.assert_called_once_with("chatgpt-gpt-5.3-codex")


def test_tutorial_claude_flow() -> None:
    """Test tutorial triggers Claude Code OAuth and model switch."""
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
        _mock_tutorial_result(mock_executor_class, "claude")

        with patch(
            "code_puppy.command_line.onboarding_wizard.reset_onboarding"
        ) as mock_reset:
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
            ) as mock_auth:
                with patch(
                    "code_puppy.model_switching.set_model_and_reload_agent"
                ) as mock_set_model:
                    with patch("code_puppy.command_line.core_commands.emit_info"):
                        result = handle_tutorial_command("/tutorial")

    assert result is True
    mock_reset.assert_called_once()
    mock_auth.assert_called_once()
    mock_set_model.assert_called_once_with("claude-code-claude-opus-4-6")


@pytest.mark.parametrize(
    ("wizard_result", "expected_message"),
    [
        ("completed", "Tutorial complete"),
        ("skipped", "Tutorial skipped"),
    ],
)
def test_tutorial_terminal_paths(wizard_result: str, expected_message: str) -> None:
    """Test tutorial completion and skip paths."""
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor_class:
        _mock_tutorial_result(mock_executor_class, wizard_result)

        with patch(
            "code_puppy.command_line.onboarding_wizard.reset_onboarding"
        ) as mock_reset:
            with patch(
                "code_puppy.plugins.chatgpt_oauth.oauth_flow.run_oauth_flow"
            ) as mock_oauth:
                with patch(
                    "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
                ) as mock_auth:
                    with patch(
                        "code_puppy.model_switching.set_model_and_reload_agent"
                    ) as mock_set_model:
                        with patch(
                            "code_puppy.command_line.core_commands.emit_info"
                        ) as mock_emit_info:
                            result = handle_tutorial_command("/tutorial")

    assert result is True
    mock_reset.assert_called_once()
    mock_oauth.assert_not_called()
    mock_auth.assert_not_called()
    mock_set_model.assert_not_called()

    emitted_messages = [call.args[0] for call in mock_emit_info.call_args_list]
    assert any(expected_message in message for message in emitted_messages)
