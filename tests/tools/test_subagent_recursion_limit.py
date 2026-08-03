"""Tests for the global nested sub-agent recursion limit."""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.config import (
    DEFAULT_SUBAGENT_RECURSION_LIMIT,
    DEFAULT_SUBAGENT_RECURSION_LIMIT_GPT_5_6,
    get_config_keys,
    get_subagent_recursion_limit,
    get_subagent_recursion_limit_gpt_5_6,
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
    assert "subagent_recursion_limit_gpt_5_6" in get_config_keys()


@pytest.mark.parametrize("configured", [None, "", "not-a-number", "-1"])
def test_gpt_5_6_recursion_limit_defaults_for_missing_or_invalid_values(configured):
    with patch("code_puppy.config.get_value", return_value=configured):
        assert (
            get_subagent_recursion_limit_gpt_5_6()
            == DEFAULT_SUBAGENT_RECURSION_LIMIT_GPT_5_6
            == 2
        )


@pytest.mark.parametrize(("configured", "expected"), [("0", 0), ("1", 1), ("5", 5)])
def test_gpt_5_6_recursion_limit_uses_configured_nonnegative_integer(
    configured, expected
):
    with patch("code_puppy.config.get_value", return_value=configured):
        assert get_subagent_recursion_limit_gpt_5_6() == expected


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
async def test_invocation_tools_preserve_gpt_5_6_two_level_cap(
    register_tool, extra_kwargs
):
    tool = _capture_tool(register_tool)

    # Nest two GPT-5.6 sub-agent contexts so the third invocation would push
    # chain depth to 3, exceeding the (default) GPT-5.6 cap of 2.
    with (
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
            return_value=4,
        ),
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit_gpt_5_6",
            return_value=2,
        ),
        patch("code_puppy.tools.subagent_invocation.emit_error"),
        patch("code_puppy.agents.agent_manager.load_agent") as load_agent,
        subagent_context("outer", "gpt-5.6-sol"),
        subagent_context("inner", "gpt-5.6-sol"),
    ):
        result = await tool(
            MagicMock(),
            agent_name="child",
            prompt="delegate this",
            **extra_kwargs,
        )

    assert result.error == (
        "Cannot invoke 'child' at sub-agent depth 3: "
        "GPT-5.6 callers are limited to depth 2."
    )
    load_agent.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("register_tool", "extra_kwargs"),
    [
        (register_invoke_agent, {}),
        (register_invoke_agent_with_model, {"model_name": "test-model"}),
    ],
)
async def test_invocation_tools_allow_gpt_5_6_up_to_two_levels(
    register_tool, extra_kwargs
):
    """A GPT-5.6 sub-agent at depth 1 must still be allowed to invoke a
    depth-2 child -- the cap is 2, not 1. Locks down the depth-1 vs depth-2
    boundary so a future ``tighten it back down`` edit trips a test.
    """
    tool = _capture_tool(register_tool)

    with (
        patch(
            "code_puppy.tools.subagent_invocation.get_subagent_recursion_limit",
            return_value=4,
        ),
        patch("code_puppy.tools.subagent_invocation.emit_error"),
        # Stop before the sub-agent actually runs -- we just want to prove
        # the recursion guard let us past load_agent().
        patch(
            "code_puppy.agents.agent_manager.load_agent",
            side_effect=RuntimeError("stop-here"),
        ) as load_agent,
        subagent_context("outer", "gpt-5.6-sol"),
    ):
        result = await tool(
            MagicMock(),
            agent_name="child",
            prompt="delegate this",
            **extra_kwargs,
        )

    # Guard did not fire; execution reached load_agent() and only failed there.
    load_agent.assert_called_once()
    assert result.response is None
    assert result.error is not None
    assert "GPT-5.6" not in result.error
