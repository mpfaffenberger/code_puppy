"""Phase-2 integration tests: pause/steer wiring across the runtime,
event_stream_handler, and _do_run steering injection.
"""

from __future__ import annotations

import asyncio
import contextlib
from io import StringIO
from typing import Any, List
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import PartStartEvent, RunContext
from pydantic_ai.messages import TextPart
from rich.console import Console

from code_puppy.agents import _runtime
from code_puppy.agents.event_stream_handler import (
    event_stream_handler,
    set_streaming_console,
)
from code_puppy.callbacks import _callbacks, clear_callbacks
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


# =============================================================================
# Shared fixtures
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


# =============================================================================
# Test A: event_stream_handler pause gating
# =============================================================================


class _PauseTriggerEvent:
    """Sentinel: when this 'event' shows up in the stream, we pause the
    controller and schedule a resume on the event loop after a delay.
    """

    def __init__(self, delay: float = 0.1) -> None:
        self.delay = delay


async def _scripted_event_stream(events: List[Any], pause_after: int) -> Any:
    """Yields events; after ``pause_after`` real events, pauses the controller
    and schedules a resume.
    """
    for i, ev in enumerate(events):
        if i == pause_after:
            pc = get_pause_controller()
            pc.pause()

            async def _resume_soon() -> None:
                await asyncio.sleep(0.1)
                pc.resume()

            asyncio.create_task(_resume_soon())
        yield ev


@pytest.mark.asyncio
async def test_event_stream_handler_pause_gates_rendering_and_resumes():
    """The handler must block when paused, then continue rendering once
    resumed. No exceptions should escape.
    """
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=80)
    set_streaming_console(console)
    ctx = MagicMock(spec=RunContext)

    # Two text parts; pause AFTER the first PartStartEvent is processed.
    ev1 = PartStartEvent(index=0, part=TextPart(content="hello"))
    ev2 = PartStartEvent(index=1, part=TextPart(content="world"))

    with contextlib.nullcontext():
        with contextlib.nullcontext():
            with patch(
                "code_puppy.agents.event_stream_handler.get_banner_color",
                return_value="blue",
            ):
                with patch("termflow.Parser"):
                    with patch("termflow.Renderer"):
                        await event_stream_handler(
                            ctx, _scripted_event_stream([ev1, ev2], pause_after=1)
                        )

    # After resume, controller should be back to not-paused.
    assert get_pause_controller().is_paused() is False
    # The handler should have rendered SOMETHING (the first part's banner
    # was emitted before pause; the second one after resume).
    assert buf.getvalue() != ""


# =============================================================================
# Test C: pause timeout auto-resumes and emits warning
# =============================================================================


@pytest.mark.asyncio
async def test_pause_timeout_auto_resumes_and_warns(monkeypatch):
    """If a pause exceeds max_pause_seconds, the handler force-resumes and
    emits a warning.
    """
    warnings: List[str] = []

    def _capture(msg: str, *_a, **_k) -> None:
        warnings.append(msg)

    # Patch the lazily-imported emit_warning the handler resolves.
    monkeypatch.setattr("code_puppy.messaging.emit_warning", _capture)
    # Force a tiny max-pause via the config getter the handler uses.
    monkeypatch.setattr(
        "code_puppy.config.get_value",
        lambda key, default=None: "0.1" if key == "max_pause_seconds" else default,
    )

    console = Console(file=StringIO(), force_terminal=False, width=80)
    set_streaming_console(console)
    ctx = MagicMock(spec=RunContext)

    ev = PartStartEvent(index=0, part=TextPart(content="hi"))

    async def _one_event_stream():
        # Pause BEFORE yielding so the gate fires on first iteration.
        get_pause_controller().pause()
        yield ev

    with contextlib.nullcontext():
        with contextlib.nullcontext():
            with patch(
                "code_puppy.agents.event_stream_handler.get_banner_color",
                return_value="blue",
            ):
                with patch("termflow.Parser"):
                    with patch("termflow.Renderer"):
                        # Should complete quickly via the timeout path.
                        await asyncio.wait_for(
                            event_stream_handler(ctx, _one_event_stream()),
                            timeout=2.0,
                        )

    # Controller force-resumed; warning fired.
    assert get_pause_controller().is_paused() is False
    assert any("auto-resuming" in w for w in warnings), (
        f"expected auto-resume warning, got: {warnings!r}"
    )


@pytest.mark.asyncio
async def test_pause_timeout_rearms_while_slash_drain_active(monkeypatch):
    """Phase 6: while the slash-command consumer owns the pause window,
    an expired wait must RE-ARM the pause and keep waiting — no misleading
    auto-resume warning, no streaming under an open /command menu. Once
    the drain ends (is_draining False), the normal timeout path applies.
    """
    warnings: List[str] = []

    def _capture(msg: str, *_a, **_k) -> None:
        warnings.append(msg)

    monkeypatch.setattr("code_puppy.messaging.emit_warning", _capture)
    monkeypatch.setattr(
        "code_puppy.config.get_value",
        lambda key, default=None: "0.05" if key == "max_pause_seconds" else default,
    )

    # Drain "active" for the first two timeouts, then idle.
    calls = {"n": 0}

    def fake_is_draining():
        calls["n"] += 1
        return calls["n"] <= 2

    monkeypatch.setattr("code_puppy.messaging.run_ui.is_draining", fake_is_draining)

    console = Console(file=StringIO(), force_terminal=False, width=80)
    set_streaming_console(console)
    ctx = MagicMock(spec=RunContext)

    ev = PartStartEvent(index=0, part=TextPart(content="hi"))

    async def _one_event_stream():
        get_pause_controller().pause()
        yield ev

    with patch(
        "code_puppy.agents.event_stream_handler.get_banner_color",
        return_value="blue",
    ):
        with patch("termflow.Parser"):
            with patch("termflow.Renderer"):
                await asyncio.wait_for(
                    event_stream_handler(ctx, _one_event_stream()),
                    timeout=5.0,
                )

    # Two re-arms (draining), then the third timeout took the normal path.
    assert calls["n"] == 3
    assert len([w for w in warnings if "auto-resuming" in w]) == 1
    assert get_pause_controller().is_paused() is False


# =============================================================================
# Test D: steering injection in _do_run
# =============================================================================


class _DummyResult:
    def __init__(self, data: str) -> None:
        self.data = data

    def all_messages(self) -> list[Any]:
        return []


class _ScriptedPydanticAgent:
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
    """Mirror test_agent_exception_recovery.py's isolation."""
    monkeypatch.setattr(_runtime, "cancel_agent_uses_signal", lambda: True)
    monkeypatch.setattr(_runtime, "get_enable_streaming", lambda: False)
    monkeypatch.setattr(_runtime, "should_render_fallback", lambda *_, **__: False)


# NOTE: tests that verified the OLD ``_do_run`` between-turns steering
# injection (test_steering_message_injected_between_turns,
# test_multiple_steering_messages_concatenated_into_one_turn) have been
# deleted. Steering is now injected by ``make_steer_history_processor``
# which fires before EVERY model call (including between tool calls
# within a single ``agent.run()``). Mocked pydantic_agent.run() doesn't
# invoke history processors, so those scaffold-style tests can't exercise
# the new behaviour. The processor is comprehensively unit-tested in
# ``tests/agents/test_steer_history_processor.py``.


@pytest.mark.asyncio
async def test_no_steering_means_runtime_behaves_exactly_as_before(
    _isolated_runtime,
):
    """Regression guard: empty steer queue must not change the call count."""
    only = _DummyResult("solo")
    pydantic_agent = _ScriptedPydanticAgent(only)
    agent = _DummyAgent(pydantic_agent)

    result = await _runtime.run_with_mcp(agent, "hello")

    assert result is only
    assert len(pydantic_agent.calls) == 1
