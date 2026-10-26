"""Invocation output contracts are available to generic lifecycle hooks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from code_puppy import callbacks
from code_puppy.agent_execution_context import (
    get_executing_agent,
    get_execution_output_type,
)
from code_puppy.agents import _runtime, base_agent
from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class StructuredOutput:
    pass


class StopBeforeTask(BaseException):
    """Stop after real callbacks, without scheduling a model task."""


@pytest.fixture
def runtime_contract(monkeypatch):
    agent = CodePuppyAgent()
    monkeypatch.setattr(agent, "get_model_name", lambda: "offline-model")
    monkeypatch.setattr(_runtime, "reset_pause_state_at_run_start", Mock())
    monkeypatch.setattr(_runtime, "inject_interrupted_subagent_notes", Mock())
    monkeypatch.setattr(_runtime, "on_user_prompt_submit", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "code_puppy.model_switching.resolve_run_model_selection", Mock()
    )
    monkeypatch.setattr(_runtime, "_should_prepend_system_prompt", lambda _, p: p)
    builds, calls, starts, ends = [], [], [], []

    def build(target, *, output_type=str, **kwargs):
        builds.append(output_type)

        async def run(prompt, **options):
            calls.append((get_executing_agent(), get_execution_output_type()))
            return SimpleNamespace(data="ok", all_messages=lambda: [])

        target._code_generation_agent = SimpleNamespace(run=run)
        return target._code_generation_agent

    monkeypatch.setattr(_runtime, "build_pydantic_agent", build)
    monkeypatch.setattr(base_agent, "build_pydantic_agent", build)
    callbacks.clear_callbacks("agent_run_start")
    callbacks.clear_callbacks("agent_run_end")
    callbacks.register_callback(
        "agent_run_start",
        lambda *a, **kw: starts.append(
            (get_executing_agent(), get_execution_output_type())
        ),
    )
    callbacks.register_callback(
        "agent_run_end",
        lambda *a, **kw: ends.append(
            (get_executing_agent(), get_execution_output_type())
        ),
    )
    yield SimpleNamespace(
        agent=agent, builds=builds, calls=calls, starts=starts, ends=ends
    )
    assert get_executing_agent() is None
    assert get_execution_output_type() is str


@pytest.mark.parametrize("output_type", [StructuredOutput, None])
async def test_start_hook_can_forward_invocation_contract(
    runtime_contract, output_type
):
    env = runtime_contract

    def reload(*args, **kwargs):
        get_executing_agent().reload_code_generation_agent(
            output_type=get_execution_output_type()
        )
        raise StopBeforeTask()

    callbacks.register_callback("agent_run_start", reload)
    with pytest.raises(StopBeforeTask):
        await env.agent.run_with_mcp("offline", output_type=output_type)

    expected = str if output_type is None else output_type
    # Preserve upstream's initial default build before its structured build.
    assert env.builds == ([str, expected, expected] if output_type else [str, str])
    assert env.starts == [(env.agent, expected)]


@pytest.mark.parametrize("output_type", [StructuredOutput, None])
async def test_contract_visible_at_start_task_and_end(
    runtime_contract, monkeypatch, output_type
):
    env = runtime_contract
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *a, **kw: False)
    await env.agent.run_with_mcp("offline", output_type=output_type)
    expected = (env.agent, str if output_type is None else output_type)
    assert env.starts == env.calls == env.ends == [expected]


def test_reload_preserves_positional_group_and_default_contract(
    runtime_contract, monkeypatch
):
    build = Mock(return_value="rebuilt")
    monkeypatch.setattr(base_agent, "build_pydantic_agent", build)
    agent = runtime_contract.agent
    assert agent.reload_code_generation_agent("group") == "rebuilt"
    build.assert_called_once_with(agent, output_type=str, message_group="group")
    build.reset_mock()
    assert (
        agent.reload_code_generation_agent("group", output_type=StructuredOutput)
        == "rebuilt"
    )
    build.assert_called_once_with(
        agent, output_type=StructuredOutput, message_group="group"
    )
