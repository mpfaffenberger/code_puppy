"""Import production call boundaries directly; no reconstructed runtime source."""

import asyncio
import socket
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.exceptions import ModelHTTPError, RunCancelled
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from code_puppy.agents import run_invocation
from code_puppy.agents.retry_checkpoint import resumable_call
from code_puppy.agents.run_invocation import ModelCall, run_with_exception_retry


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in invocation tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture
def case(monkeypatch):
    agent = SimpleNamespace(
        _message_history=[], name="synthetic", get_model_name=lambda: "synthetic"
    )
    state = SimpleNamespace(agent=agent, calls=[], events=[])
    monkeypatch.setattr(
        run_invocation, "on_agent_exception", AsyncMock(return_value=[])
    )

    def client(outcome):
        async def run(prompt, **kwargs):
            state.calls.append((model, prompt, kwargs))
            if prompt is not None:
                kwargs["message_history"].append(
                    ModelRequest(parts=[UserPromptPart(prompt)])
                )
            return await outcome()

        model = SimpleNamespace(run=run)
        return model

    @asynccontextmanager
    async def context(current):
        state.events.append(("enter", current))
        try:
            yield
        finally:
            state.events.append(("exit", current))

    state.client = client
    state.invocation = ModelCall(
        lambda: agent.current, lambda current: [context(current)]
    )
    return state


async def test_physical_retries_resolve_live_client_and_forward_current_history(case):
    state = case
    replacement = state.client(AsyncMock(return_value="done"))
    old_history = state.agent._message_history

    async def fail():
        state.agent.current = replacement
        state.agent._message_history = list(old_history)
        raise ConnectionError("transient")

    original = state.client(fail)
    state.agent.current = original
    limits, handler, extra = object(), object(), object()
    call = resumable_call(
        state.agent,
        state.invocation,
        "continue",
        usage_limits=limits,
        event_stream_handler=handler,
        extra=extra,
    )
    with pytest.raises(ConnectionError):
        await call()
    assert await call() == "done"
    assert [(model, prompt) for model, prompt, _ in state.calls] == [
        (original, "continue"),
        (replacement, None),
    ]
    assert state.calls[0][2]["message_history"] is old_history
    assert state.calls[1][2]["message_history"] is state.agent._message_history
    for _, _, options in state.calls:
        assert options["usage_limits"] is limits
        assert options["event_stream_handler"] is handler
        assert options["extra"] is extra
    assert state.events == [
        ("enter", original),
        ("exit", original),
        ("enter", replacement),
        ("exit", replacement),
    ]
    assert len(state.agent._message_history) == 1


async def test_identical_follow_up_gets_fresh_checkpoint_and_recovery(
    case, monkeypatch
):
    state = case
    replacement = state.client(AsyncMock(return_value="recovered"))
    calls = 0

    async def outcome():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("synthetic replacement required")
        return "initial"

    original = state.client(outcome)
    state.agent.current = original

    async def recover(error, **metadata):
        assert isinstance(error, PermissionError)
        assert metadata["agent"] is state.agent
        state.agent.current = replacement
        return [{"retry": True, "delay": 0.25}]

    callback = AsyncMock(side_effect=recover)
    sleep = AsyncMock()
    monkeypatch.setattr(run_invocation, "on_agent_exception", callback)
    monkeypatch.setattr(run_invocation.asyncio, "sleep", sleep)
    for expected in ["initial", "recovered"]:
        call = resumable_call(state.agent, state.invocation, "continue")
        assert await run_with_exception_retry(call, agent=state.agent) == expected
    assert [prompt for _, prompt, _ in state.calls] == ["continue", "continue", None]
    assert len(state.agent._message_history) == 2
    callback.assert_awaited_once()
    sleep.assert_awaited_once_with(0.25)
    assert [event for event, _ in state.events] == ["enter", "exit"] * 3


@pytest.mark.parametrize(
    "error",
    [
        ValueError("fatal"),
        asyncio.CancelledError(),
        RunCancelled("explicit cancellation"),
    ],
)
async def test_fatal_and_cancel_cleanup_without_recovery(case, error):
    state = case
    state.agent.current = state.client(AsyncMock(side_effect=error))
    call = resumable_call(state.agent, state.invocation, "continue")
    with pytest.raises(type(error)):
        await run_with_exception_retry(call, agent=state.agent)
    assert len(state.calls) == 1
    assert [event for event, _ in state.events] == ["enter", "exit"]
    assert run_invocation.on_agent_exception.await_count == (
        0 if isinstance(error, (asyncio.CancelledError, RunCancelled)) else 1
    )


async def test_recovery_is_bounded_to_one_retry(case, monkeypatch):
    state = case
    state.agent.current = state.client(AsyncMock(side_effect=ConnectionError))
    monkeypatch.setattr(
        run_invocation, "on_agent_exception", AsyncMock(return_value=[{"retry": True}])
    )
    with pytest.raises(ConnectionError):
        await run_with_exception_retry(
            resumable_call(state.agent, state.invocation, "continue"), agent=state.agent
        )
    assert [prompt for _, prompt, _ in state.calls] == ["continue", None]
    run_invocation.on_agent_exception.assert_awaited_once()
    assert [event for event, _ in state.events] == ["enter", "exit"] * 2


async def test_partial_context_entry_unwinds_before_model_call():
    events = []

    @asynccontextmanager
    async def first():
        events.append("enter")
        try:
            yield
        finally:
            events.append("exit")

    @asynccontextmanager
    async def broken():
        raise ValueError("context setup failed")
        yield  # pragma: no cover

    model = SimpleNamespace(run=AsyncMock())
    invocation = ModelCall(lambda: model, lambda _: [first(), broken()])
    with pytest.raises(ValueError, match="context setup failed"):
        await invocation.run("continue")
    assert events == ["enter", "exit"]
    model.run.assert_not_awaited()


async def test_nested_logical_calls_do_not_share_checkpoint_or_context(case):
    state = case
    inner_agent = SimpleNamespace(_message_history=[])
    inner_prompts = []

    async def inner_run(prompt, **kwargs):
        inner_prompts.append(prompt)
        kwargs["message_history"].append(ModelRequest(parts=[UserPromptPart(prompt)]))
        return "nested"

    inner_model = SimpleNamespace(run=inner_run)
    inner = ModelCall(lambda: inner_model, lambda _: [])

    async def outer_run():
        return await resumable_call(inner_agent, inner, "continue")()

    state.agent.current = state.client(outer_run)
    assert await resumable_call(state.agent, state.invocation, "continue")() == "nested"
    assert inner_prompts == ["continue"]
    assert len(inner_agent._message_history) == len(state.agent._message_history) == 1
    assert [event for event, _ in state.events] == ["enter", "exit"]


async def test_real_pydantic_checkpoint_survives_model_replacement(case):
    state = case

    async def persist_history(messages):
        state.agent._message_history = list(messages)
        return messages

    replacement = Agent(
        FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("done")])),
        capabilities=[ProcessHistory(persist_history)],
    )

    async def fail(messages, info):
        state.agent.current = replacement
        raise ModelHTTPError(500, "synthetic", "before response")

    original = Agent(
        FunctionModel(fail), capabilities=[ProcessHistory(persist_history)]
    )
    state.agent.current = original
    call = resumable_call(state.agent, state.invocation, "continue")
    with pytest.raises(ModelHTTPError):
        await call()
    assert (await call()).output == "done"
    assert (
        sum(
            isinstance(part, UserPromptPart)
            for message in state.agent._message_history
            for part in message.parts
        )
        == 1
    )
    assert state.events == [
        ("enter", original),
        ("exit", original),
        ("enter", replacement),
        ("exit", replacement),
    ]
