"""Tests for agent_exception retry semantics in the runtime."""

from __future__ import annotations

from typing import Any

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import _callbacks, clear_callbacks, register_callback


class DummyResult:
    """Tiny result object with the bits runtime code cares about."""

    def __init__(self, data: str) -> None:
        self.data = data

    def all_messages(self) -> list[Any]:
        return []


class ScriptedPydanticAgent:
    """Pydantic-agent stand-in that returns/raises scripted outcomes."""

    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        history = kwargs.get("message_history")
        self.calls.append(
            {
                "prompt": prompt,
                "message_history": list(history)
                if isinstance(history, list)
                else history,
            }
        )
        if not self._outcomes:
            raise AssertionError("Unexpected extra pydantic_agent.run() call")

        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class DummyAgent:
    """Runtime-compatible agent shell; no actual model/provider involved."""

    name = "dummy-agent"

    def __init__(self, pydantic_agent: ScriptedPydanticAgent) -> None:
        self._code_generation_agent = pydantic_agent
        self._message_history = ["already-started"]
        self._mcp_servers: list[Any] = []

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused because message history is non-empty"


@pytest.fixture(autouse=True)
def isolated_runtime_callbacks(monkeypatch: pytest.MonkeyPatch):
    """Keep global callback state from leaking into or out of these tests."""
    snapshot = {phase: list(callbacks) for phase, callbacks in _callbacks.items()}
    clear_callbacks()
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)

    yield

    clear_callbacks()
    for phase, callbacks in snapshot.items():
        _callbacks[phase].extend(callbacks)


@pytest.fixture
def diagnostics(monkeypatch: pytest.MonkeyPatch) -> list[BaseException]:
    seen: list[BaseException] = []

    def spy(exc: BaseException, *, group_id: str | None = None) -> None:
        del group_id
        seen.append(exc)

    monkeypatch.setattr(_runtime, "emit_exception_diagnostics", spy)
    return seen


async def test_no_callbacks_preserves_baseline_exception_path(
    diagnostics: list[BaseException],
) -> None:
    original = RuntimeError("boom")
    pydantic_agent = ScriptedPydanticAgent(original)
    agent = DummyAgent(pydantic_agent)

    # Exceptions now propagate to the caller (no longer silently swallowed)
    with pytest.raises(RuntimeError, match="boom"):
        await _runtime.run_with_mcp(agent, "hello")

    assert len(pydantic_agent.calls) == 1
    assert diagnostics == [original]


async def test_agent_exception_callback_fires_without_retry(
    diagnostics: list[BaseException],
) -> None:
    original = RuntimeError("observe me")
    seen: list[dict[str, Any]] = []

    def observe(exception: Exception, **kwargs: Any) -> None:
        seen.append({"exception": exception, **kwargs})

    register_callback("agent_exception", observe)
    pydantic_agent = ScriptedPydanticAgent(original)
    agent = DummyAgent(pydantic_agent)
    # Exception propagates even when a callback fires (callbacks don't suppress it)
    with pytest.raises(RuntimeError, match="observe me"):
        await _runtime.run_with_mcp(agent, "hello")

    assert len(pydantic_agent.calls) == 1
    assert diagnostics == [original]
    assert seen == [
        {
            "exception": original,
            "agent": agent,
            "agent_name": "dummy-agent",
            "model_name": "dummy-model",
        }
    ]


async def test_agent_exception_retry_then_success_honors_delay(
    monkeypatch: pytest.MonkeyPatch,
    diagnostics: list[BaseException],
) -> None:
    original = RuntimeError("recoverable")
    success = DummyResult("ok")
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def recover(exception: Exception, *, agent: DummyAgent, **_: Any) -> dict[str, Any]:
        assert exception is original
        agent._message_history.append("fixed")
        return {"retry": True, "delay": 0.25}

    monkeypatch.setattr(_runtime.asyncio, "sleep", fake_sleep)
    register_callback("agent_exception", recover)
    pydantic_agent = ScriptedPydanticAgent(original, success)
    agent = DummyAgent(pydantic_agent)

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is success
    assert diagnostics == []
    assert sleeps == [0.25]
    assert pydantic_agent.calls == [
        {"prompt": "hello", "message_history": ["already-started"]},
        {"prompt": "hello", "message_history": ["already-started", "fixed"]},
    ]


async def test_agent_exception_retry_then_failure_does_not_loop(
    diagnostics: list[BaseException],
) -> None:
    first = RuntimeError("recoverable")
    second = RuntimeError("still broken")
    seen: list[Exception] = []

    def recover(exception: Exception, **_: Any) -> dict[str, bool]:
        seen.append(exception)
        return {"retry": True}

    register_callback("agent_exception", recover)
    pydantic_agent = ScriptedPydanticAgent(first, second)
    agent = DummyAgent(pydantic_agent)

    # After retry fails, exception propagates (no silent None return)
    with pytest.raises(RuntimeError, match="still broken"):
        await _runtime.run_with_mcp(agent, "hello")
    assert len(pydantic_agent.calls) == 2
    assert seen == [first]
    assert diagnostics == [second]


async def test_multiple_agent_exception_callbacks_first_retry_wins(
    monkeypatch: pytest.MonkeyPatch,
    diagnostics: list[BaseException],
) -> None:
    original = RuntimeError("pick a retry")
    success = DummyResult("ok")
    order: list[str] = []
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    def observer(exception: Exception, **_: Any) -> None:
        assert exception is original
        order.append("observer")

    def first_retry(exception: Exception, **_: Any) -> dict[str, Any]:
        assert exception is original
        order.append("first_retry")
        return {"retry": True, "delay": 0.1}

    def second_retry(exception: Exception, **_: Any) -> dict[str, Any]:
        assert exception is original
        order.append("second_retry")
        return {"retry": True, "delay": 99.0}

    monkeypatch.setattr(_runtime.asyncio, "sleep", fake_sleep)
    register_callback("agent_exception", observer)
    register_callback("agent_exception", first_retry)
    register_callback("agent_exception", second_retry)
    pydantic_agent = ScriptedPydanticAgent(original, success)
    agent = DummyAgent(pydantic_agent)

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is success
    assert diagnostics == []
    assert len(pydantic_agent.calls) == 2
    assert order == ["observer", "first_retry", "second_retry"]
    assert sleeps == [0.1]


@pytest.mark.parametrize("follow_up", ["hook", "queue"])
async def test_explicit_follow_up_cancel_never_enters_recovery(
    monkeypatch: pytest.MonkeyPatch, follow_up: str
) -> None:
    from pydantic_ai.exceptions import RunCancelled

    success = DummyResult("initial")
    client = ScriptedPydanticAgent(
        success, RunCancelled("explicit cancellation"), DummyResult("wrong retry")
    )
    agent = DummyAgent(client)
    recovered = []
    cancelled = []

    def recover(exception, **kwargs):
        recovered.append(exception)
        return {"retry": True}

    register_callback("agent_exception", recover)
    monkeypatch.setattr(_runtime, "_checkpoint_cancelled_history", lambda *args: None)
    monkeypatch.setattr(
        _runtime, "emit_info", lambda message, **kwargs: cancelled.append(message)
    )
    if follow_up == "hook":
        register_callback(
            "agent_run_result",
            lambda *args, **kwargs: {"retry": True, "prompt": "follow-up", "delay": 0},
        )
    else:
        monkeypatch.setattr(
            _runtime, "prepare_queued_steer_injection", lambda *args: "follow-up"
        )

    assert await _runtime.run_with_mcp(agent, "initial") is None
    assert [call["prompt"] for call in client.calls] == ["initial", "follow-up"]
    assert recovered == []
    assert "\nCancelled" in cancelled


@pytest.mark.parametrize("follow_up", ["hook", "queue"])
async def test_follow_up_recovery_resolves_rebuilt_client_and_attempt_context(
    monkeypatch: pytest.MonkeyPatch, follow_up: str
) -> None:
    from contextlib import asynccontextmanager

    from pydantic_ai.messages import ModelRequest, UserPromptPart

    events = []
    prompts = []
    result = DummyResult("done")
    result.all_messages = lambda: agent._message_history
    attempts = 0

    class Client:
        def __bool__(self):
            return False  # A live replacement must not be mistaken for a cache miss.

        async def run(self, prompt, **kwargs):
            nonlocal attempts
            attempts += 1
            prompts.append((self, prompt))
            if prompt is not None:
                kwargs["message_history"].append(
                    ModelRequest(parts=[UserPromptPart(prompt)])
                )
            if attempts == 2:
                raise RuntimeError("replace on follow-up")
            return result

    original, replacement = Client(), Client()
    agent = DummyAgent(original)

    @asynccontextmanager
    async def context(current):
        events.append(("enter", current))
        try:
            yield
        finally:
            events.append(("exit", current))

    register_callback("agent_run_context", lambda _, current, *args: context(current))

    def recover(exception, **kwargs):
        assert str(exception) == "replace on follow-up"
        agent._code_generation_agent = replacement
        return {"retry": True}

    register_callback("agent_exception", recover)
    if follow_up == "hook":
        register_callback(
            "agent_run_result",
            lambda *args, **kwargs: (
                {"retry": True, "prompt": "hello", "delay": 0}
                if attempts == 1
                else None
            ),
        )
    else:
        queued = iter(["hello", None])
        monkeypatch.setattr(
            _runtime, "prepare_queued_steer_injection", lambda *args: next(queued)
        )

    assert await _runtime.run_with_mcp(agent, "hello") is result
    assert prompts == [(original, "hello"), (original, "hello"), (replacement, None)]
    assert events == [
        ("enter", original),
        ("exit", original),
        ("enter", original),
        ("exit", original),
        ("enter", replacement),
        ("exit", replacement),
    ]
    assert (
        sum(
            isinstance(part, UserPromptPart)
            for message in agent._message_history
            if isinstance(message, ModelRequest)
            for part in message.parts
        )
        == 2
    )


@pytest.mark.parametrize("follow_up", ["hook", "queue"])
@pytest.mark.parametrize("invalidate_at", ["result", "recovery"])
async def test_real_mcp_invalidation_keeps_built_client_for_in_flight_run(
    monkeypatch: pytest.MonkeyPatch, follow_up: str, invalidate_at: str
) -> None:
    from contextlib import asynccontextmanager
    from unittest.mock import Mock

    from code_puppy.agents import agent_manager
    from code_puppy.mcp_.agent_bindings import invalidate_agent_mcp_cache

    initial, bridge, final = (
        DummyResult("initial"),
        DummyResult("bridge"),
        DummyResult("done"),
    )
    original_error = RuntimeError("invalidate during recovery")
    outcomes = [initial]
    if invalidate_at == "recovery":
        outcomes.append(original_error)
    if follow_up == "queue":
        outcomes.append(bridge)
    outcomes.append(final)
    client = ScriptedPydanticAgent(*outcomes)
    agent = DummyAgent(client)
    agent.pydantic_agent = client
    agent._mcp_servers = [object()]
    monkeypatch.setattr(agent_manager, "_CURRENT_AGENT", agent)
    build = Mock(side_effect=AssertionError("Do not rebuild an in-flight client"))
    monkeypatch.setattr(_runtime, "build_pydantic_agent", build)
    events, recovered = [], []
    queued = False

    def invalidate():
        invalidate_agent_mcp_cache(agent.name)
        assert agent._code_generation_agent is None
        assert agent.pydantic_agent is None
        assert agent._mcp_servers == []

    @asynccontextmanager
    async def context(current):
        events.append(("enter", current))
        try:
            yield
        finally:
            events.append(("exit", current))

    register_callback("agent_run_context", lambda _, current, *args: context(current))

    def recover(exception, **kwargs):
        recovered.append(exception)
        assert exception is original_error
        invalidate()
        return {"retry": True}

    register_callback("agent_exception", recover)

    def result_hook(result, *args, **kwargs):
        nonlocal queued
        if result is not initial:
            return None
        if invalidate_at == "result":
            invalidate()
        queued = follow_up == "queue"
        # A hook retry lets the loop revisit its queue after this result hook.
        return {"retry": True, "prompt": "hook-follow-up", "delay": 0}

    register_callback("agent_run_result", result_hook)

    def drain_queue(*args):
        nonlocal queued
        if queued:
            queued = False
            return "queued-follow-up"
        return None

    monkeypatch.setattr(_runtime, "prepare_queued_steer_injection", drain_queue)
    assert await _runtime.run_with_mcp(agent, "hello") is final
    prompts = ["hello", "hook-follow-up"]
    if invalidate_at == "recovery":
        prompts.append("hook-follow-up")
    if follow_up == "queue":
        prompts.append("queued-follow-up")
    assert [call["prompt"] for call in client.calls] == prompts
    assert events == [(event, client) for _ in prompts for event in ("enter", "exit")]
    assert recovered == ([original_error] if invalidate_at == "recovery" else [])
    build.assert_not_called()
    assert agent._code_generation_agent is None
