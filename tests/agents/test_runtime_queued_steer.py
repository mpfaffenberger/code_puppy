"""Tests for ``queue``-mode steering injection in ``_runtime._do_run``.

``now``-mode steers are owned by ``make_steer_history_processor`` and
exercised in ``test_steer_history_processor.py``. This file is solely
for the between-``agent.run()``-calls path that drains the queued-mode
queue and re-invokes the agent with the steer as a fresh user turn.
"""

from __future__ import annotations

from typing import Any, List

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import _callbacks, clear_callbacks
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


# =============================================================================
# Shared fixtures — mirror test_runtime_pause_integration.py
# =============================================================================


@pytest.fixture(autouse=True)
def _reset_pause_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


@pytest.fixture(autouse=True)
def _isolated_callbacks():
    snapshot = {phase: list(cbs) for phase, cbs in _callbacks.items()}
    clear_callbacks()
    yield
    clear_callbacks()
    for phase, cbs in snapshot.items():
        _callbacks[phase].extend(cbs)


class _DummyResult:
    def __init__(self, data: str) -> None:
        self.data = data

    def all_messages(self) -> list[Any]:
        return []


class _ScriptedPydanticAgent:
    """Programmable stand-in for ``pydantic_ai.Agent``."""

    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: List[dict[str, Any]] = []

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        if not self._outcomes:
            raise AssertionError("Unexpected extra pydantic_agent.run() call")
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _DummyAgent:
    name = "dummy-agent"

    def __init__(self, pydantic_agent: _ScriptedPydanticAgent) -> None:
        self._code_generation_agent = pydantic_agent
        self._message_history = ["already-started"]
        self._mcp_servers: list[Any] = []

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused"


@pytest.fixture
def _isolated_runtime(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(_runtime, "cancel_agent_uses_signal", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)


# =============================================================================
# Single queued steer → exactly one follow-up turn
# =============================================================================


@pytest.mark.asyncio
async def test_queued_steer_drained_between_turns(_isolated_runtime):
    """A ``queue``-mode steer queued during the first turn must be picked
    up by ``_do_run``'s loop and submitted as a fresh user turn.
    """
    first = _DummyResult("first")
    second = _DummyResult("after-queued-steer")
    pc = get_pause_controller()

    call_count = {"n": 0}
    second_prompt: dict[str, Any] = {}

    async def _run(prompt: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Queue mid-run; the runtime loop drains it AFTER the call returns.
            pc.request_steer("write tests after", mode="queue")
            return first
        second_prompt["value"] = prompt
        return second

    pydantic_agent = _ScriptedPydanticAgent()
    pydantic_agent.run = _run  # type: ignore[assignment]
    agent = _DummyAgent(pydantic_agent)

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is second
    assert call_count["n"] == 2
    assert second_prompt["value"] == "write tests after"
    # Queue empty after drain.
    assert pc.drain_pending_steer_queued() == []


# =============================================================================
# Multiple queued steers → one turn each, in order
# =============================================================================


@pytest.mark.asyncio
async def test_multiple_queued_steers_processed_one_per_iteration(_isolated_runtime):
    """Three ``queue``-mode steers → three follow-up turns, in order.

    The runtime processes one queued steer per loop iteration (cleaner
    turn boundaries for the model than concatenating).
    """
    initial = _DummyResult("initial")
    results = [_DummyResult(f"after-{i}") for i in range(3)]
    pc = get_pause_controller()

    call_count = {"n": 0}
    follow_up_prompts: list[Any] = []

    async def _run(prompt: Any, **kwargs: Any) -> Any:
        call_count["n"] += 1
        if call_count["n"] == 1:
            pc.request_steer("steer one", mode="queue")
            pc.request_steer("steer two", mode="queue")
            pc.request_steer("steer three", mode="queue")
            return initial
        follow_up_prompts.append(prompt)
        return results[call_count["n"] - 2]

    pydantic_agent = _ScriptedPydanticAgent()
    pydantic_agent.run = _run  # type: ignore[assignment]
    agent = _DummyAgent(pydantic_agent)

    await _runtime.run_with_mcp(agent, "hello")

    # 1 initial + 3 follow-ups = 4 calls total.
    assert call_count["n"] == 4
    assert follow_up_prompts == ["steer one", "steer two", "steer three"]
    assert pc.drain_pending_steer_queued() == []


# =============================================================================
# Mode isolation — runtime loop must NOT touch now-mode steers
# =============================================================================


@pytest.mark.asyncio
async def test_now_steer_skipped_by_runtime_loop(_isolated_runtime):
    """``now``-mode steers belong to the history processor exclusively.
    The runtime loop must not drain them or we get double-injection /
    lost-steer bugs.
    """
    only = _DummyResult("solo")
    pc = get_pause_controller()

    async def _run(prompt: Any, **kwargs: Any) -> Any:
        # Queue a now-mode steer mid-run; runtime loop MUST ignore it.
        pc.request_steer("for the history processor", mode="now")
        return only

    pydantic_agent = _ScriptedPydanticAgent()
    pydantic_agent.run = _run  # type: ignore[assignment]
    agent = _DummyAgent(pydantic_agent)

    await _runtime.run_with_mcp(agent, "hello")

    # Now-mode steer untouched by the runtime loop.
    # (In production, the history processor would have drained it on the
    # next model call. With a mocked agent.run, no history processor runs,
    # so it stays put — exactly what we want to assert here.)
    assert pc.drain_pending_steer_now() == ["for the history processor"]
    assert pc.drain_pending_steer_queued() == []


# =============================================================================
# Unit test on prepare_queued_steer_injection helper
# =============================================================================


def test_queued_steer_does_not_double_inject_via_history_processor():
    """Same fact from the opposite angle: invoke the history processor
    directly while a queue-mode steer is pending; it MUST be left alone.
    """
    from unittest.mock import Mock

    from code_puppy.agents._steer_processor import make_steer_history_processor

    agent = Mock()
    agent._message_history = []
    processor = make_steer_history_processor(agent)

    pc = get_pause_controller()
    pc.request_steer("queue-only", mode="queue")

    result = processor([])

    # Processor MUST NOT have drained the queued-mode steer.
    assert result == []
    assert pc.drain_pending_steer_queued() == ["queue-only"]


def test_prepare_queued_steer_injection_returns_none_when_empty(_isolated_runtime):
    """``prepare_queued_steer_injection`` is a no-op when the queue is empty."""
    from unittest.mock import Mock

    from code_puppy.agents._run_signals import prepare_queued_steer_injection

    result = prepare_queued_steer_injection(Mock(), Mock())
    assert result is None


def test_prepare_queued_steer_injection_drains_one_and_requeues_rest():
    """Helper processes exactly ONE steer per call; leftovers are re-queued."""
    from unittest.mock import Mock

    from code_puppy.agents._run_signals import prepare_queued_steer_injection

    pc = get_pause_controller()
    pc.request_steer("one", mode="queue")
    pc.request_steer("two", mode="queue")
    pc.request_steer("three", mode="queue")

    agent = Mock()
    agent._message_history = []
    fake_result = Mock()
    fake_result.all_messages = lambda: ["msg1", "msg2"]

    text = prepare_queued_steer_injection(agent, fake_result)

    assert text == "one"
    # Leftovers re-queued in the same order.
    assert pc.drain_pending_steer_queued() == ["two", "three"]
    # Result's messages were persisted into agent._message_history.
    assert agent._message_history == ["msg1", "msg2"]
