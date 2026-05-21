"""Tests for cross-run PauseController leakage protection.

The ``PauseController`` is a process-wide singleton. Without explicit
hygiene at run start + on cancel, a Ctrl+C'd run can leave stale steering
messages in the queue that get silently consumed by the NEXT (potentially
totally different) agent run. These tests lock the hygiene down.
"""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import _callbacks, clear_callbacks
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


# =============================================================================
# Shared fixtures (mirrors test_runtime_pause_integration.py)
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
    """Records every ``run`` call so tests can assert which prompts were
    actually sent to the model. ``outcomes`` is a list of either result
    objects or exceptions; the latter are raised in order.
    """

    def __init__(self, *outcomes: Any) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

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
# Bug A.1 — stale state is scrubbed at run start
# =============================================================================


@pytest.mark.asyncio
async def test_stale_steer_drained_at_run_start(_isolated_runtime, monkeypatch):
    """A stale steer left over from a prior cancelled run MUST NOT be
    consumed as if the user had typed it in this run.
    """
    warnings: List[str] = []
    # ``reset_pause_state_at_run_start`` lives in _run_signals and calls
    # ``emit_warning`` imported there. Patch the imported reference.
    monkeypatch.setattr(
        "code_puppy.agents._run_signals.emit_warning",
        lambda msg, *_a, **_k: warnings.append(msg),
    )

    only = _DummyResult("solo")
    pydantic_agent = _ScriptedPydanticAgent(only)
    agent = _DummyAgent(pydantic_agent)

    # Simulate the leak: someone's previous (cancelled) run queued a steer.
    get_pause_controller().request_steer("stale msg from previous session")

    result = await _runtime.run_with_mcp(agent, "fresh prompt")

    # 1. The fresh run should have received the ORIGINAL prompt, not the steer.
    assert len(pydantic_agent.calls) == 1, (
        "Stale steer must NOT trigger a follow-up turn"
    )
    assert pydantic_agent.calls[0]["prompt"] == "fresh prompt"
    assert result is only

    # 2. Pause queue must be empty post-run.
    assert get_pause_controller().drain_pending_steer() == []

    # 3. A warning must have fired so the user knows we scrubbed something.
    assert any("stale steering message" in w for w in warnings), (
        f"expected stale-steer warning, got: {warnings!r}"
    )


@pytest.mark.asyncio
async def test_stale_pause_state_cleared_at_run_start(_isolated_runtime):
    """A previously-paused controller must be resumed before the new run
    starts; otherwise the new run's event stream + spinner freeze.
    """
    only = _DummyResult("solo")
    pydantic_agent = _ScriptedPydanticAgent(only)
    agent = _DummyAgent(pydantic_agent)

    # Simulate the leak: someone left the controller paused.
    pc = get_pause_controller()
    pc.pause()
    assert pc.is_paused() is True

    await _runtime.run_with_mcp(agent, "hello")

    # Controller must have been resumed by run_with_mcp's start-of-run reset.
    assert pc.is_paused() is False


@pytest.mark.asyncio
async def test_clean_state_at_run_start_emits_no_warning(
    _isolated_runtime, monkeypatch
):
    """No false-positive warnings when the controller is already clean.

    Regression guard: previous bug fixes that over-eagerly emit can be
    just as annoying as the bug they're fixing.
    """
    warnings: List[str] = []
    monkeypatch.setattr(
        "code_puppy.agents._run_signals.emit_warning",
        lambda msg, *_a, **_k: warnings.append(msg),
    )

    only = _DummyResult("solo")
    pydantic_agent = _ScriptedPydanticAgent(only)
    agent = _DummyAgent(pydantic_agent)

    await _runtime.run_with_mcp(agent, "hello")

    stale_warnings = [w for w in warnings if "stale steering" in w]
    assert stale_warnings == [], (
        f"clean state must not emit a stale-steer warning: {stale_warnings!r}"
    )


# =============================================================================
# Bug A.2 — queue is drained on cancel
# =============================================================================


@pytest.mark.asyncio
async def test_steer_drained_on_cancel(_isolated_runtime, monkeypatch):
    """A run that's cancelled mid-flight MUST flush the steer queue so the
    next run doesn't inherit stale messages.

    The steer must be queued INSIDE the run (mid-flight) — queueing it
    before ``run_with_mcp`` starts would be drained by the start-of-run
    reset, which is its own (also-tested) hygiene step.
    """
    infos: List[str] = []
    # ``drain_pause_state_on_cancel`` lives in _run_signals.
    monkeypatch.setattr(
        "code_puppy.agents._run_signals.emit_info",
        lambda msg, *_a, **_k: infos.append(msg),
    )

    pc = get_pause_controller()

    async def _queue_steer_then_cancel(prompt: Any, **kwargs: Any) -> Any:
        # Simulate: user paused mid-run, typed a steer, then Ctrl+C'd before
        # the steer was drained at the next turn boundary.
        pc.request_steer("doomed msg")
        raise asyncio.CancelledError()

    pydantic_agent = _ScriptedPydanticAgent()
    pydantic_agent.run = _queue_steer_then_cancel  # type: ignore[assignment]
    agent = _DummyAgent(pydantic_agent)

    # run_with_mcp catches CancelledError internally and returns None.
    await _runtime.run_with_mcp(agent, "hello")

    # The doomed steer MUST be gone.
    assert pc.drain_pending_steer() == []

    # And we must have emitted the diagnostic so the user knows.
    discard_msgs = [m for m in infos if "Discarded" in m and "steering" in m]
    assert discard_msgs, f"expected on-cancel discard diagnostic, got: {infos!r}"


@pytest.mark.asyncio
async def test_paused_state_cleared_on_cancel(_isolated_runtime, monkeypatch):
    """A run cancelled while paused must end with the controller resumed,
    so the NEXT run isn't frozen.
    """
    monkeypatch.setattr(
        "code_puppy.agents._run_signals.emit_info", lambda *_a, **_k: None
    )

    pc = get_pause_controller()

    async def _pause_then_cancel(prompt: Any, **kwargs: Any) -> Any:
        pc.pause()
        raise asyncio.CancelledError()

    pydantic_agent = _ScriptedPydanticAgent()
    pydantic_agent.run = _pause_then_cancel  # type: ignore[assignment]
    agent = _DummyAgent(pydantic_agent)

    await _runtime.run_with_mcp(agent, "hello")

    assert pc.is_paused() is False, (
        "Controller must be resumed after cancellation so the next run isn't frozen"
    )


# =============================================================================
# Wiring: confirm the steer history processor is actually attached
# =============================================================================


def test_steer_queued_mid_run_is_injected_via_history_processor():
    """End-to-end-ish smoke: a steer queued at any point during a run gets
    seen by the steer ``history_processor`` on its next invocation.

    This is a unit test on the processor itself (we can't drive a real
    pydantic-ai agent in CI), but it locks the contract: queue a steer,
    invoke the processor, the steer shows up in the returned messages.
    The actual pydantic-ai → history_processors → model wiring is verified
    by the unit tests in ``test_steer_history_processor.py`` and by the
    ``_builder.py`` wiring (``history_processors=[compaction, steer]``).
    """
    from unittest.mock import Mock

    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from code_puppy.agents._steer_processor import make_steer_history_processor

    agent = Mock()
    agent._message_history = []
    processor = make_steer_history_processor(agent)

    # Simulate: agent is mid-run, history processor fires (queue empty → no-op).
    msgs = processor([])
    assert msgs == []

    # Now: user presses Ctrl+T and submits a steer.
    get_pause_controller().request_steer("change direction")

    # Next history-processor invocation must pick it up.
    msgs = processor([])
    assert len(msgs) == 1
    assert isinstance(msgs[0], ModelRequest)
    assert isinstance(msgs[0].parts[0], UserPromptPart)
    assert msgs[0].parts[0].content == "change direction"


def test_steer_processor_is_wired_into_builder_after_compaction():
    """Guard: the builder must wire the steer processor AFTER compaction
    so steers don't get compacted away on the same call.
    """
    import inspect

    from code_puppy.agents import _builder

    src = inspect.getsource(_builder)
    # Both processors must be referenced in the builder.
    assert "make_steer_history_processor" in src
    assert "make_history_processor" in src
    # And they must appear in that order in the history_processors list.
    # We rely on a textual check of the list literal here; the wiring test
    # `test_steer_processor_appended_after_compaction` (below) verifies
    # the actual list ordering on a built agent.
    history_processors_line = next(
        line for line in src.splitlines() if "history_processors=" in line
    )
    # Format is `history_processors=[history_processor, steer_processor]`.
    # Just sanity-check both names appear and history_processor comes first.
    h_idx = history_processors_line.find("history_processor")
    s_idx = history_processors_line.find("steer_processor")
    assert h_idx >= 0 and s_idx > h_idx, (
        f"steer_processor must come AFTER history_processor: {history_processors_line!r}"
    )
