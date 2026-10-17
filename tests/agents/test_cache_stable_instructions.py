"""The system prompt's per-run tail rides as a dynamic instruction part.

pydantic-ai places the Anthropic cache breakpoint after the last *static*
instruction part. The agent ID (and load_prompt fragments) used to be baked into
the static text, so every session and every sub-agent re-wrote the whole system
prompt to the prompt cache: the A/B measured identical cache reads across all
runs, stopping right at the tool definitions.
"""

from unittest.mock import patch

import pytest
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.agents import _builder
from code_puppy.agents.agent_code_puppy import CodePuppyAgent
from code_puppy.model_utils import static_then_runtime


def test_identity_lives_only_in_the_runtime_tail():
    agent = CodePuppyAgent()

    assert agent.get_identity() in agent.get_runtime_system_prompt()
    assert agent.get_identity() not in agent.get_system_prompt()
    assert (
        agent.get_full_system_prompt()
        == agent.get_system_prompt() + agent.get_runtime_system_prompt()
    )


def test_runtime_tail_is_computed_once():
    calls = []

    def runtime() -> str:
        calls.append(1)
        return "tail"

    static, dynamic = static_then_runtime("static", runtime())

    assert (static, dynamic(), dynamic()) == ("static", "tail", "tail")
    assert len(calls) == 1


async def _instruction_parts(agent: CodePuppyAgent) -> list:
    seen: list = []

    async def respond(messages, info: AgentInfo):
        seen.extend(info.model_request_parameters.instruction_parts or [])
        yield "done"

    model = FunctionModel(stream_function=respond)
    with (
        patch.object(
            _builder, "load_model_with_fallback", lambda *a, **k: (model, "test")
        ),
        patch.object(_builder.ModelFactory, "load_config", staticmethod(dict)),
        patch.object(_builder, "load_mcp_servers", lambda **k: []),
        patch.object(_builder, "make_model_settings", lambda *a, **k: None),
    ):
        built = _builder.build_pydantic_agent(agent)
    await built.run("hi")
    return seen


@pytest.mark.asyncio
async def test_builder_sends_identity_as_a_dynamic_part_only():
    first, second = CodePuppyAgent(), CodePuppyAgent()

    parts_a = await _instruction_parts(first)
    parts_b = await _instruction_parts(second)

    static_a = [p.content for p in parts_a if not p.dynamic]
    static_b = [p.content for p in parts_b if not p.dynamic]
    dynamic_a = "".join(p.content for p in parts_a if p.dynamic)
    assert first.get_identity() in dynamic_a
    assert not any(first.get_identity() in text for text in static_a)
    # Two sessions share the cacheable static prefix byte for byte.
    assert static_a == static_b
