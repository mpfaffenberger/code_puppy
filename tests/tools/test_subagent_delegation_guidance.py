"""Model-facing delegation guidance must allow parallel fan-out without loops.

Pins the semantics (not the exact prose) of every place that tells a model how
to use sub-agents: the two tool descriptions, the child identity prompt and the
GPT-5.6+ system-prompt guard.
"""

from unittest.mock import patch

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

import code_puppy.tools.agent_tools  # noqa: F401  (import order: breaks a circular import)
from code_puppy.agents._builder import _build_gpt_5_6_invoke_agent_guard_text
from code_puppy.tools import subagent_invocation as si


def _normalized(text: str) -> str:
    return " ".join(text.split())


@pytest.fixture(scope="module")
def tool_descriptions() -> dict[str, str]:
    agent = Agent(TestModel())
    si.register_invoke_agent(agent)
    si.register_invoke_agent_with_model(agent)
    return {
        name: _normalized(tool.description)
        for name, tool in agent._function_toolset.tools.items()
    }


@pytest.mark.parametrize("tool_name", ["invoke_agent", "invoke_agent_with_model"])
@pytest.mark.parametrize(
    "phrase",
    [
        "multiple sub-agents concurrently in one batch",
        "rather than one at a time",
        "tightly scoped",
        "direct children only",
        "without delegating further",
        "instead of starting follow-up chains",
        "recursion guard",
    ],
)
def test_tool_description_allows_parallel_batch_and_forbids_loops(
    tool_descriptions, tool_name, phrase
):
    assert phrase in tool_descriptions[tool_name]


@pytest.mark.parametrize("tool_name", ["invoke_agent", "invoke_agent_with_model"])
def test_tool_description_does_not_ban_same_named_agents(tool_descriptions, tool_name):
    description = tool_descriptions[tool_name].lower()

    assert "invoke yourself" not in description
    assert "already in the invocation chain" not in description


@pytest.fixture
def identity_prompt() -> str:
    with (
        patch.object(si, "get_subagent_depth", return_value=1),
        patch.object(si, "get_subagent_chain", return_value=("planner",)),
        patch.object(si, "get_subagent_recursion_limit", return_value=4),
    ):
        return _normalized(si._subagent_identity_prompt("helper"))


def test_identity_prompt_defaults_to_no_delegation_and_forbids_chains(identity_prompt):
    assert "main agent -> planner -> helper" in identity_prompt
    assert (
        "Do not delegate further unless your caller explicitly asks" in identity_prompt
    )
    assert "one concurrent batch of direct children" in identity_prompt
    assert "do not chain follow-up sub-agent calls" in identity_prompt
    assert "(max 4)" in identity_prompt


def test_identity_prompt_does_not_ban_same_named_agents(identity_prompt):
    prompt = identity_prompt.lower()

    assert "invoke yourself" not in prompt
    assert "already in the invocation chain" not in prompt


def test_gpt_5_6_guard_permits_parallel_batch_and_keeps_safety_rules():
    with patch(
        "code_puppy.config.get_subagent_recursion_limit_gpt_5_6", return_value=7
    ):
        guard = _normalized(_build_gpt_5_6_invoke_agent_guard_text())

    assert "concurrently in one batch" in guard
    assert "rather than one at a time" in guard
    assert "tightly scoped" in guard
    assert "direct child" in guard
    assert "repeated follow-up delegation chains" in guard
    assert "Never invoke `planning-agent`" in guard
    assert "at or below 7" in guard
