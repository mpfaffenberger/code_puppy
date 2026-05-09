"""Tests for agent run lifecycle callbacks (P1-02)."""

from __future__ import annotations

import asyncio
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
def run_end_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def spy(**kwargs: Any) -> None:
        seen.append(kwargs)

    monkeypatch.setattr(_runtime, "on_agent_run_end", spy)
    return seen


# ---- Tests ------------------------------------------------------------------


async def test_success_only_when_result_returned(
    run_end_calls: list[dict[str, Any]],
) -> None:
    success = DummyResult("ok")
    pydantic_agent = ScriptedPydanticAgent(success)
    agent = DummyAgent(pydantic_agent)

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is success
    assert len(run_end_calls) == 1
    assert run_end_calls[0]["success"] is True
    assert run_end_calls[0]["response_text"] == "ok"


async def test_run_with_mcp_model_exception_reports_failure(
    run_end_calls: list[dict[str, Any]],
) -> None:
    original = RuntimeError("model died")
    pydantic_agent = ScriptedPydanticAgent(original)
    agent = DummyAgent(pydantic_agent)

    with pytest.raises(BaseExceptionGroup):
        await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_calls) == 1
    assert run_end_calls[0]["success"] is False
    assert run_end_calls[0]["error"] is not None


async def test_run_with_mcp_usage_limit_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    run_end_calls: list[dict[str, Any]],
) -> None:
    from pydantic_ai import UsageLimitExceeded

    original = UsageLimitExceeded("limit hit")
    pydantic_agent = ScriptedPydanticAgent(original)
    agent = DummyAgent(pydantic_agent)

    with pytest.raises(BaseExceptionGroup):
        await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_calls) == 1
    assert run_end_calls[0]["success"] is False
    assert run_end_calls[0]["error"] is not None


async def test_run_with_mcp_cancel_reports_failure(
    monkeypatch: pytest.MonkeyPatch,
    run_end_calls: list[dict[str, Any]],
) -> None:
    """CancelledError from inside _do_run should propagate and report failure."""
    cancel = asyncio.CancelledError("task cancelled")
    pydantic_agent = ScriptedPydanticAgent(cancel)
    agent = DummyAgent(pydantic_agent)

    with pytest.raises(asyncio.CancelledError) as exc_info:
        await _runtime.run_with_mcp(agent, "hello")

    assert len(run_end_calls) == 1
    assert run_end_calls[0]["success"] is False
    assert run_end_calls[0]["error"] is exc_info.value


async def test_event_stream_handler_restored_on_model_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When non-streaming is used and a model exception occurs, handler is restored."""
    original = RuntimeError("model died")
    pydantic_agent = ScriptedPydanticAgent(original)
    agent = DummyAgent(pydantic_agent)

    # Pre-set a fake handler
    fake_handler = object()
    pydantic_agent._event_stream_handler = fake_handler

    with pytest.raises(BaseExceptionGroup):
        await _runtime.run_with_mcp(agent, "hello")

    # Should be restored even after exception
    assert pydantic_agent._event_stream_handler is fake_handler


async def test_event_stream_handler_restored_on_retry_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handler is restored when exception occurs during a retry call."""
    first = RuntimeError("recoverable")
    second = RuntimeError("still broken")

    def recover(exception: Exception, **_: Any) -> dict[str, bool]:
        return {"retry": True}

    register_callback("agent_exception", recover)
    pydantic_agent = ScriptedPydanticAgent(first, second)
    agent = DummyAgent(pydantic_agent)

    fake_handler = object()
    pydantic_agent._event_stream_handler = fake_handler

    with pytest.raises(BaseExceptionGroup):
        await _runtime.run_with_mcp(agent, "hello")

    assert pydantic_agent._event_stream_handler is fake_handler
