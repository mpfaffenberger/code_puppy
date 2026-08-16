"""Cancellation behavior of ``run_with_mcp`` (Phase B.2 instrumentation).

Covers:
- A cancelled run terminates cleanly: no cancel-scope ``RuntimeError``
  propagates to the caller (pydantic-ai 1.92+ fixed stream teardown on
  cancel upstream, #5313).
- The cancel-scope-corruption suppression path is instrumented: when it
  fires it logs a WARNING and bumps a module-level counter. That counter
  is the Phase C proof-of-death gate for deleting the suppression.

The manual Ctrl+C matrix (terminal-level SIGINT during streaming, during
tool runs, during MCP startup) remains a human task.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import _callbacks, clear_callbacks

LOGGER_NAME = "code_puppy.agents._runtime"


class HangingPydanticAgent:
    """Pydantic-agent stand-in whose run() hangs until cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        self.started.set()
        try:
            await asyncio.Event().wait()  # hang forever
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class ScriptedPydanticAgent:
    """Pydantic-agent stand-in that raises a scripted exception."""

    def __init__(self, outcome: BaseException) -> None:
        self._outcome = outcome

    async def run(self, prompt: Any, **kwargs: Any) -> Any:
        raise self._outcome


class DummyAgent:
    """Runtime-compatible agent shell; no actual model/provider involved."""

    name = "dummy-agent"

    def __init__(self, pydantic_agent: Any) -> None:
        self._code_generation_agent = pydantic_agent
        self._message_history = ["already-started"]
        self._mcp_servers: list[Any] = []

    def get_model_name(self) -> str:
        return "dummy-model"

    def get_full_system_prompt(self) -> str:
        return "unused because message history is non-empty"


@pytest.fixture(autouse=True)
def isolated_runtime(monkeypatch: pytest.MonkeyPatch):
    """Keep global callback/interactive state out of these tests."""
    snapshot = {phase: list(callbacks) for phase, callbacks in _callbacks.items()}
    clear_callbacks()
    monkeypatch.setattr(_runtime, "sigint_fallback_cancels", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)

    yield

    clear_callbacks()
    for phase, callbacks in snapshot.items():
        _callbacks[phase].extend(callbacks)


# ---------------------------------------------------------------------------
# Cancellation terminates cleanly.
# ---------------------------------------------------------------------------


async def test_cancelled_run_terminates_without_cancel_scope_error():
    """Cancelling a run must terminate it; no cancel-scope RuntimeError."""
    pydantic_agent = HangingPydanticAgent()
    agent = DummyAgent(pydantic_agent)
    baseline = _runtime.get_cancel_scope_suppression_count()

    task = asyncio.create_task(_runtime.run_with_mcp(agent, "hello"))
    await asyncio.wait_for(pydantic_agent.started.wait(), timeout=5)

    task.cancel()
    done, _ = await asyncio.wait([task], timeout=5)
    assert task in done, "cancelled run failed to terminate"

    # The runtime swallows the outer CancelledError after cancelling the
    # inner agent task; either outcome is acceptable, but a RuntimeError
    # (cancel-scope corruption) is not.
    if not task.cancelled():
        assert task.exception() is None

    # Let the inner agent task finish unwinding its cancellation.
    await asyncio.sleep(0)
    assert pydantic_agent.cancelled, "inner agent task was not cancelled"

    # The suppression path must NOT have fired for a plain cancellation.
    assert _runtime.get_cancel_scope_suppression_count() == baseline


# ---------------------------------------------------------------------------
# Suppression instrumentation (Phase C proof-of-death gate).
# ---------------------------------------------------------------------------


def test_record_cancel_scope_suppression_warns_and_counts(caplog):
    exc = RuntimeError(
        "Attempted to exit a cancel scope that isn't the current "
        "task's current cancel scope"
    )
    baseline = _runtime.get_cancel_scope_suppression_count()

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        _runtime._record_cancel_scope_suppression(exc)

    assert _runtime.get_cancel_scope_suppression_count() == baseline + 1
    warnings = [
        r
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert "cancel-scope corruption suppressed" in message
    assert "expected extinct after pydantic-ai 1.92+" in message
    assert "cancel scope" in message  # the repr of the suppressed exception


async def test_scope_noise_suppression_path_increments_counter(caplog):
    """End-to-end: an ExceptionGroup of cancel-scope noise is suppressed,
    logged at WARNING, counted, and does NOT propagate to the caller."""
    noise = RuntimeError(
        "Attempted to exit cancel scope in a different task than it was entered in"
    )
    pydantic_agent = ScriptedPydanticAgent(ExceptionGroup("teardown", [noise]))
    agent = DummyAgent(pydantic_agent)
    baseline = _runtime.get_cancel_scope_suppression_count()

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        result = await _runtime.run_with_mcp(agent, "hello")

    assert result is None  # suppressed, not raised
    assert _runtime.get_cancel_scope_suppression_count() == baseline + 1
    messages = [
        r.getMessage()
        for r in caplog.records
        if r.name == LOGGER_NAME and r.levelno == logging.WARNING
    ]
    assert any("cancel-scope corruption suppressed" in m for m in messages)
