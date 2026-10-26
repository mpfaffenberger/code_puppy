"""Tests for disabling only the interactive ask-user tool."""

from unittest.mock import MagicMock, patch

from code_puppy.tools import register_tools_for_agent


def test_disable_ask_user_question_preserves_other_tools(monkeypatch):
    ask_register = MagicMock()
    read_register = MagicMock()
    monkeypatch.setenv("CODE_PUPPY_DISABLE_ASK_USER_QUESTION", "1")

    with patch.dict(
        "code_puppy.tools.TOOL_REGISTRY",
        {
            "ask_user_question": ask_register,
            "read_file": read_register,
        },
        clear=True,
    ):
        agent = MagicMock()
        register_tools_for_agent(agent, ["ask_user_question", "read_file"])

    ask_register.assert_not_called()
    read_register.assert_called_once_with(agent)


def test_ask_user_question_remains_enabled_by_default(monkeypatch):
    ask_register = MagicMock()
    monkeypatch.delenv("CODE_PUPPY_DISABLE_ASK_USER_QUESTION", raising=False)

    with patch.dict(
        "code_puppy.tools.TOOL_REGISTRY",
        {"ask_user_question": ask_register},
        clear=True,
    ):
        agent = MagicMock()
        register_tools_for_agent(agent, ["ask_user_question"])

    ask_register.assert_called_once_with(agent)
