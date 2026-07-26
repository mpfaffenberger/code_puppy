"""Tests for the global nested sub-agent recursion limit."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.config import (
    DEFAULT_SUBAGENT_RECURSION_LIMIT,
    get_config_keys,
    get_subagent_recursion_limit,
)
from code_puppy.tools.agent_tools import AgentInvokeOutput
from code_puppy.tools.subagent_context import subagent_context
from code_puppy.tools.subagent_invocation import (
    _subagent_identity_prompt,
    _subagent_recursion_blocked,
    register_invoke_agent,
    register_invoke_agent_with_model,
)


@pytest.mark.parametrize("configured", [None, "", "not-a-number", "-1"])
def test_recursion_limit_defaults_for_missing_or_invalid_values(configured):
    with patch("code_puppy.config.get_value", return_value=configured):
        assert get_subagent_recursion_limit() == DEFAULT_SUBAGENT_RECURSION_LIMIT == 4


@pytest.mark.parametrize(("configured", "expected"), [("0", 0), ("7", 7)])
def test_recursion_limit_uses_configured_nonnegative_integer(configured, expected):
    with patch("code_puppy.config.get_value", return_value=configured):
        assert get_subagent_recursion_limit() == expected


def test_recursion_limit_is_discoverable_by_config_commands():
    assert "subagent_recursion_limit" in get_config_keys()


def test_recursion_guard_allows_calls_below_limit_and_blocks_at_limit():
    with patch(
        "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
        return_value=2,
    ):
        assert not _subagent_recursion_blocked()
        with subagent_context("first"):
            assert not _subagent_recursion_blocked()
            with subagent_context("second"):
                assert _subagent_recursion_blocked()


def test_identity_prompt_exposes_child_depth_chain_and_delegation_rules():
    with (
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
            return_value=4,
        ),
        subagent_context("parent"),
    ):
        prompt = _subagent_identity_prompt("child")

    normalized_prompt = " ".join(prompt.split())
    assert "You are the sub-agent `child`, not the main agent" in normalized_prompt
    assert "nesting depth is 2" in normalized_prompt
    assert "main agent -> parent -> child" in normalized_prompt
    assert "2 deeper level(s) remain" in normalized_prompt
    assert "NEVER invoke yourself" in normalized_prompt
    assert "at most one child level" in normalized_prompt


def test_invocation_tool_docs_warn_against_recursive_delegation():
    for register_tool in (register_invoke_agent, register_invoke_agent_with_model):
        doc = _capture_tool(register_tool).__doc__
        assert "never invoke yourself" in doc.lower()
        assert "at most one level deeper" in doc.lower()
        assert "recursive" in doc.lower()


def _capture_tool(register_tool):
    agent = MagicMock()
    captured = {}
    agent.tool.side_effect = lambda func: captured.setdefault("tool", func)
    register_tool(agent)
    return captured["tool"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("register_tool", "extra_kwargs"),
    [
        (register_invoke_agent, {}),
        (register_invoke_agent_with_model, {"model_name": "test-model"}),
    ],
)
async def test_invocation_tools_stop_before_loading_agent_at_limit(
    register_tool, extra_kwargs
):
    tool = _capture_tool(register_tool)

    with (
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
            return_value=1,
        ),
        patch("code_puppy.tools.subagent_invocation.emit_error") as emit_error,
        patch("code_puppy.agents.agent_manager.load_agent") as load_agent,
        subagent_context("parent"),
    ):
        result = await tool(
            MagicMock(),
            agent_name="child",
            prompt="delegate this",
            **extra_kwargs,
        )

    assert isinstance(result, AgentInvokeOutput)
    assert result.response is None
    assert result.error == (
        "Sub-agent recursion limit (1) reached; cannot invoke 'child'."
    )
    emit_error.assert_called_once()
    load_agent.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("register_tool", "extra_kwargs"),
    [
        (register_invoke_agent, {}),
        (register_invoke_agent_with_model, {"model_name": "test-model"}),
    ],
)
async def test_invocation_tools_preserve_gpt_5_6_single_level_cap(
    register_tool, extra_kwargs
):
    tool = _capture_tool(register_tool)

    with (
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
            return_value=4,
        ),
        patch("code_puppy.tools.subagent_invocation.emit_error"),
        patch("code_puppy.agents.agent_manager.load_agent") as load_agent,
        subagent_context("parent", "gpt-5.6-sol"),
    ):
        result = await tool(
            MagicMock(),
            agent_name="child",
            prompt="delegate this",
            **extra_kwargs,
        )

    assert result.error == "GPT-5.6 sub-agents cannot invoke 'child'."
    load_agent.assert_not_called()
