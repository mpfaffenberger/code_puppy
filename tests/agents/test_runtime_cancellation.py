"""Cancellation behavior of ``run_with_mcp`` (pydantic-ai v2).

Covers:
- A cancelled run terminates cleanly: no cancel-scope ``RuntimeError``
  propagates to the caller (pydantic-ai 1.92+ fixed stream teardown on
  cancel upstream, #5313; the Phase C proof-of-death gate then deleted
  code_puppy's cancel-scope suppression entirely).
- Cancel-scope ``RuntimeError``s now propagate like any other error —
  no silent suppression.
- A cancelled run's partial work is preserved: pydantic-ai v2 attaches a
  ``RunCancelled`` snapshot to the ``CancelledError`` and the runtime
  checkpoints it into ``agent._message_history``.

The manual Ctrl+C matrix (terminal-level SIGINT during streaming, during
tool runs, during MCP startup) remains a human task.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from code_puppy.agents import _runtime
from code_puppy.callbacks import _callbacks, clear_callbacks


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


# ---------------------------------------------------------------------------
# Cancel-scope noise is no longer suppressed (Phase C gate passed).
# ---------------------------------------------------------------------------


async def test_scope_noise_propagates_like_any_other_error():
    """The v1-era suppression is deleted: cancel-scope RuntimeErrors from an
    ExceptionGroup now surface to the caller instead of being swallowed."""
    noise = RuntimeError(
        "Attempted to exit cancel scope in a different task than it was entered in"
    )
    pydantic_agent = ScriptedPydanticAgent(ExceptionGroup("teardown", [noise]))
    agent = DummyAgent(pydantic_agent)

    with pytest.raises(RuntimeError, match="cancel scope"):
        await _runtime.run_with_mcp(agent, "hello")


# ---------------------------------------------------------------------------
# Cancelled-run history preservation (pydantic-ai v2 RunCancelled snapshot).
# ---------------------------------------------------------------------------


async def test_cancelled_run_checkpoints_partial_history():
    """A CancelledError carrying a RunCancelled snapshot must checkpoint the
    snapshot's messages into agent._message_history."""
    from pydantic_ai.exceptions import RunCancelled
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    snapshot_messages = [
        ModelRequest(parts=[UserPromptPart(content="already-started")]),
        ModelRequest(parts=[UserPromptPart(content="partial-progress")]),
    ]

    class CancelledWithSnapshot(HangingPydanticAgent):
        async def run(self, prompt: Any, **kwargs: Any) -> Any:
            self.started.set()
            cancel_exc = asyncio.CancelledError()
            RunCancelled("cancelled mid-run", messages=snapshot_messages)._attach_to(
                cancel_exc
            )
            raise cancel_exc

    pydantic_agent = CancelledWithSnapshot()
    agent = DummyAgent(pydantic_agent)
    agent._message_history = [snapshot_messages[0]]

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is None  # cancelled, not a successful run
    # The snapshot (2 messages) is longer than the checkpoint (1) — taken.
    assert len(agent._message_history) == 2
