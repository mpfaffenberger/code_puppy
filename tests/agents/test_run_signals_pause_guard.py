"""Tests for the duplicate-keypress guard in make_schedule_pause()."""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

from code_puppy.agents import _run_signals
from code_puppy.messaging.pause_controller import (
    get_pause_controller,
    reset_pause_controller,
)


@pytest.fixture(autouse=True)
def _reset_controller():
    reset_pause_controller()
    yield
    reset_pause_controller()


def _fake_task(done: bool = False) -> Any:
    """Build a minimal duck-typed stand-in for an asyncio.Task."""

    class _T:
        def done(self_inner) -> bool:  # noqa: N805 — duck-type
            return done

    return _T()


def _fake_loop() -> Any:
    """Minimal duck-typed event loop. Real loop not needed — we spy on
    asyncio.run_coroutine_threadsafe directly.
    """

    class _L:
        pass

    return _L()


# =============================================================================
# Guard against re-pausing while already paused
# =============================================================================


def test_schedule_pause_no_ops_when_already_paused(monkeypatch):
    """Pressing the pause key twice MUST NOT fire the callback twice."""
    scheduled_calls: List[Any] = []

    def _spy(coro, loop):
        scheduled_calls.append((coro, loop))

        # Properly close the coroutine to avoid "never awaited" warnings.
        try:
            coro.close()
        except Exception:
            pass

        class _Fut:
            def result(self, timeout=None):
                return None

        return _Fut()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _spy)

    schedule_pause = _run_signals.make_schedule_pause(_fake_task(), _fake_loop())

    # First press: controller not paused → callback scheduled.
    schedule_pause()
    assert len(scheduled_calls) == 1

    # Simulate the pause command actually pausing the controller (as the
    # bus would when PauseAgentCommand fires).
    get_pause_controller().pause()

    # Second press: must be a no-op.
    schedule_pause()
    assert len(scheduled_calls) == 1, (
        "Re-pause while already paused must NOT schedule another callback"
    )


def test_schedule_pause_schedules_when_not_paused(monkeypatch):
    """Baseline: when controller is fresh, schedule_pause does fire."""
    scheduled_calls: List[Any] = []

    def _spy(coro, loop):
        scheduled_calls.append((coro, loop))
        try:
            coro.close()
        except Exception:
            pass

        class _Fut:
            def result(self, timeout=None):
                return None

        return _Fut()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _spy)

    schedule_pause = _run_signals.make_schedule_pause(_fake_task(), _fake_loop())
    schedule_pause()
    assert len(scheduled_calls) == 1


def test_schedule_pause_no_ops_when_task_done(monkeypatch):
    scheduled_calls: List[Any] = []

    monkeypatch.setattr(
        asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: scheduled_calls.append((coro, loop)),
    )

    schedule_pause = _run_signals.make_schedule_pause(
        _fake_task(done=True), _fake_loop()
    )
    schedule_pause()
    assert scheduled_calls == []


def test_schedule_pause_proceeds_when_shell_running(monkeypatch):
    """Pause MUST proceed even while a shell command is in flight.

    Cancel still refuses mid-shell because cancel ends the task and could
    orphan the subprocess; pause is benign — it just queues a steering
    message and lets the agent continue naturally. The renderer buffers
    shell stdout/stderr while paused so the steering prompt is safe.
    """
    scheduled_calls: List[Any] = []

    def _spy(coro, loop):
        scheduled_calls.append((coro, loop))
        try:
            coro.close()
        except Exception:
            pass

        class _Fut:
            def result(self, timeout=None):
                return None

        return _Fut()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _spy)
    # A shell command is in flight — pause must still go through.
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._RUNNING_PROCESSES", {"fake-pid": object()}
    )

    schedule_pause = _run_signals.make_schedule_pause(_fake_task(), _fake_loop())
    schedule_pause()
    assert len(scheduled_calls) == 1, (
        "pause must be scheduled even when a shell command is running"
    )


# =============================================================================
# Cancel hides the sub-agent status panel (mirrors the steer flow)
# =============================================================================


def _fake_loop_recording() -> Any:
    """Loop stand-in that records call_soon_threadsafe scheduling."""

    class _L:
        def __init__(self):
            self.scheduled: List[Any] = []

        def call_soon_threadsafe(self, fn, *args):
            self.scheduled.append((fn, args))

    return _L()


def _fake_cancelable_task(done: bool = False) -> Any:
    """Task stand-in exposing both .done() and .cancel (cancel attr accessed)."""

    class _T:
        def done(self_inner) -> bool:  # noqa: N805 — duck-type
            return done

        def cancel(self_inner) -> None:  # noqa: N805 — duck-type
            pass

    return _T()


def test_schedule_cancel_tears_down_panel_before_banner(monkeypatch):
    """With active sub-agents, cancel must hide the panel so the banner shows."""
    teardown_calls: List[int] = []
    warnings: List[str] = []

    # One active sub-agent task that isn't done yet.
    class _SubTask:
        def done(self):
            return False

        def cancel(self):
            pass

    monkeypatch.setattr(_run_signals, "_active_subagent_tasks", [_SubTask()])
    monkeypatch.setattr(
        _run_signals, "emit_warning", lambda msg, *a, **k: warnings.append(msg)
    )
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._tear_down_live_panels",
        lambda: teardown_calls.append(1),
    )
    # No shells running so force isn't required.
    monkeypatch.setattr("code_puppy.tools.command_runner._RUNNING_PROCESSES", set())

    loop = _fake_loop_recording()
    schedule_cancel = _run_signals.make_schedule_cancel(_fake_cancelable_task(), loop)
    schedule_cancel()

    assert teardown_calls == [1], "panel must be torn down exactly once"
    assert warnings and "Cancelling" in warnings[0]


def test_schedule_cancel_no_panel_teardown_without_subagents(monkeypatch):
    """No active sub-agents → no panel banner, no teardown (just cancel task)."""
    teardown_calls: List[int] = []

    monkeypatch.setattr(_run_signals, "_active_subagent_tasks", [])
    monkeypatch.setattr(
        "code_puppy.tools.command_runner._tear_down_live_panels",
        lambda: teardown_calls.append(1),
    )
    monkeypatch.setattr("code_puppy.tools.command_runner._RUNNING_PROCESSES", set())

    loop = _fake_loop_recording()
    schedule_cancel = _run_signals.make_schedule_cancel(_fake_cancelable_task(), loop)
    schedule_cancel()

    assert teardown_calls == [], "no sub-agent panel to hide → no teardown"
    # The main agent task still gets cancelled.
    assert len(loop.scheduled) == 1
