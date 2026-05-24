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
    monkeypatch.setattr(_runtime, "cancel_agent_uses_signal", lambda: True)
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

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is None
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

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is None
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

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is None
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
