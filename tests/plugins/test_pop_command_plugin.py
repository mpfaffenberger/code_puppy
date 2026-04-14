"""Tests for the /pop custom-command plugin."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)


def _plugin_module():
    sys.modules.setdefault("dbos", MagicMock())
    return importlib.import_module("code_puppy.plugins.pop_command.register_callbacks")


def _agent_manager_module(agent: MagicMock) -> SimpleNamespace:
    return SimpleNamespace(get_current_agent=lambda: agent)


def test_custom_help_includes_pop():
    entries = dict(_plugin_module()._custom_help())
    assert "pop" in entries


def test_parse_pop_count_defaults_to_one():
    assert _plugin_module()._parse_pop_count("/pop") == 1


def test_parse_pop_count_rejects_invalid_integer():
    module = _plugin_module()
    with patch(
        "code_puppy.plugins.pop_command.register_callbacks.emit_error"
    ) as mock_error:
        assert module._parse_pop_count("/pop nope") is None
    mock_error.assert_called_once()


def test_prune_dangling_tool_fragments_removes_orphan_return_tail():
    system = ModelRequest(parts=[TextPart(content="system")])
    reply = ModelResponse(parts=[TextPart(content="hello")])
    orphan_return = ModelRequest(
        parts=[ToolReturnPart(tool_name="t", content="ok", tool_call_id="tc1")]
    )

    cleaned, extra = _plugin_module()._prune_dangling_tool_fragments(
        [system, reply, orphan_return]
    )

    assert cleaned == [system, reply]
    assert extra == 1


def test_prune_dangling_tool_fragments_removes_orphan_call_then_orphan_return():
    system = ModelRequest(parts=[TextPart(content="system")])
    text_reply = ModelResponse(parts=[TextPart(content="all good")])
    tool_call = ModelResponse(
        parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="tc1")]
    )
    tool_return = ModelRequest(
        parts=[ToolReturnPart(tool_name="t", content="ok", tool_call_id="tc1")]
    )

    cleaned, extra = _plugin_module()._prune_dangling_tool_fragments(
        [system, text_reply, tool_call, tool_return]
    )

    assert cleaned == [system, text_reply]
    assert extra == 2


def test_handle_custom_command_ignores_other_commands():
    assert _plugin_module()._handle_custom_command("/nope", "nope") is None


def test_handle_pop_command_pops_and_prunes_tail_fragments():
    system = ModelRequest(parts=[TextPart(content="system")])
    stable = ModelResponse(parts=[TextPart(content="keep me")])
    tool_call = ModelResponse(
        parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="tc1")]
    )
    tool_return = ModelRequest(
        parts=[ToolReturnPart(tool_name="t", content="ok", tool_call_id="tc1")]
    )
    last_message = ModelResponse(parts=[TextPart(content="latest")])

    agent = MagicMock()
    agent.get_message_history.return_value = [
        system,
        stable,
        tool_call,
        tool_return,
        last_message,
    ]

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.pop_command.register_callbacks.emit_success"
        ) as mock_success,
        patch("code_puppy.plugins.pop_command.register_callbacks.emit_info"),
    ):
        result = _plugin_module()._handle_custom_command("/pop", "pop")

    assert result is True
    agent.set_message_history.assert_called_once_with([system, stable])
    assert "pruned 2 extra incomplete tool-call fragment" in str(mock_success.call_args)


def test_handle_pop_command_preserves_system_prompt_when_count_too_large():
    system = ModelRequest(parts=[TextPart(content="system")])
    message = ModelResponse(parts=[TextPart(content="hello")])

    agent = MagicMock()
    agent.get_message_history.return_value = [system, message]

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.pop_command.register_callbacks.emit_warning"
        ) as mock_warning,
        patch("code_puppy.plugins.pop_command.register_callbacks.emit_success"),
        patch(
            "code_puppy.plugins.pop_command.register_callbacks.emit_info"
        ) as mock_info,
    ):
        result = _plugin_module()._handle_custom_command("/pop 99", "pop")

    assert result is True
    agent.set_message_history.assert_called_once_with([system])
    assert "requested 99 but only 1" in str(mock_warning.call_args)
    assert "History is now empty" in str(mock_info.call_args)


def test_handle_pop_command_reports_system_only_history():
    system = ModelRequest(parts=[TextPart(content="system")])

    agent = MagicMock()
    agent.get_message_history.return_value = [system]

    with (
        patch.dict(
            sys.modules,
            {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
        ),
        patch(
            "code_puppy.plugins.pop_command.register_callbacks.emit_warning"
        ) as mock_warning,
    ):
        result = _plugin_module()._handle_custom_command("/pop", "pop")

    assert result is True
    agent.set_message_history.assert_not_called()
    assert "only the system prompt" in str(mock_warning.call_args)
