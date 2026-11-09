"""Cancellation requests remain authoritative when providers or hooks swallow them."""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Any

import pytest
from pydantic_ai.exceptions import UsageLimitExceeded

from code_puppy import agent_completion_inbox
from code_puppy.agents import _run_signals, _runtime
from code_puppy.callbacks import register_callback
from code_puppy.interactive_support import _interactive_sigint_guard
from code_puppy.messaging.pause_controller import get_pause_controller
from tests.agents.test_runtime_cancellation import (  # noqa: F401
    DummyAgent,
    isolated_runtime,
)


class Result:
    usage = None

    def __init__(self, tag: str = "result") -> None:
        self.output = tag
        self.tag = tag

    def all_messages(self) -> list[Any]:
        return [f"history-from-{self.tag}"]


@pytest.fixture
def repl_guard():
    previous = signal.signal(signal.SIGINT, _interactive_sigint_guard)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def register_run_outcomes() -> tuple[list[str], list[bool]]:
    cancel_ids: list[str] = []
    statuses: list[bool] = []
    register_callback("agent_run_cancel", lambda run_id: cancel_ids.append(run_id))
    register_callback("agent_run_end", lambda *args: statuses.append(args[3]))
    return cancel_ids, statuses


def assert_cancelled_once(
    result: Any, cancel_ids: list[str], statuses: list[bool]
) -> None:
    assert result is None
    assert len(cancel_ids) == 1
    assert statuses == [False]
    assert not get_pause_controller().has_pending_steer()
    assert signal.getsignal(signal.SIGINT) is _interactive_sigint_guard


class RecordingAgent:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def run(self, prompt: Any, **_kwargs: Any) -> Result:
        self.calls.append(prompt)
        return Result()


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_result_hook_consumed_cancel_stops_retry(repl_guard):
    hook_started = asyncio.Event()

    async def swallow_then_retry(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        hook_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return {"retry": True, "prompt": "must not run", "delay": 0}

    implementation = RecordingAgent()
    cancel_ids, statuses = register_run_outcomes()
    register_callback("agent_run_result", swallow_then_retry)
    task = asyncio.create_task(
        _runtime.run_with_mcp(DummyAgent(implementation), "hello")
    )
    await asyncio.wait_for(hook_started.wait(), timeout=5)

    os.kill(os.getpid(), signal.SIGINT)
    result = await asyncio.wait_for(task, timeout=5)

    assert implementation.calls == ["hello"]
    assert_cancelled_once(result, cancel_ids, statuses)


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_result_hook_consumed_cancel_cleans_before_return(repl_guard):
    hook_started = asyncio.Event()

    async def swallow(*_args: Any, **_kwargs: Any) -> None:
        hook_started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return None

    implementation = RecordingAgent()
    cancel_ids, statuses = register_run_outcomes()
    register_callback("agent_run_result", swallow)
    task = asyncio.create_task(
        _runtime.run_with_mcp(DummyAgent(implementation), "hello")
    )
    await asyncio.wait_for(hook_started.wait(), timeout=5)
    get_pause_controller().request_steer("discard me", mode="queue")

    os.kill(os.getpid(), signal.SIGINT)
    result = await asyncio.wait_for(task, timeout=5)

    assert implementation.calls == ["hello"]
    assert_cancelled_once(result, cancel_ids, statuses)


class FollowUpAgent:
    def __init__(self) -> None:
        self.follow_up_started = asyncio.Event()
        self.calls: list[Any] = []

    async def run(self, prompt: Any, **_kwargs: Any) -> Result:
        self.calls.append(prompt)
        call_number = len(self.calls)
        if call_number == 2:
            self.follow_up_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return Result("cancelled-follow-up")
        return Result(f"call-{call_number}")


@pytest.mark.parametrize("pending_work", ["second_steer", "completion", "result_hook"])
@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_consumed_follow_up_cancel_has_no_later_side_effects(
    repl_guard, monkeypatch: pytest.MonkeyPatch, pending_work: str
):
    implementation = FollowUpAgent()
    agent = DummyAgent(implementation)
    hook_calls: list[str] = []
    cleanup_calls: list[str] = []
    original_cleanup = _runtime.drain_pause_state_on_cancel

    def count_cleanup() -> None:
        cleanup_calls.append("drained")
        original_cleanup()

    async def capture_result(result: Result, *_args: Any, **_kwargs: Any) -> None:
        hook_calls.append(result.tag)

    monkeypatch.setattr(_runtime, "drain_pause_state_on_cancel", count_cleanup)
    cancel_ids, statuses = register_run_outcomes()
    pause_controller = get_pause_controller()
    pause_controller.request_steer("steer one", mode="queue")
    task = asyncio.create_task(_runtime.run_with_mcp(agent, "hello"))
    await asyncio.wait_for(implementation.follow_up_started.wait(), timeout=5)

    if pending_work == "second_steer":
        pause_controller.request_steer("steer two", mode="queue")
    elif pending_work == "completion":
        agent_completion_inbox.deliver_completion(agent, "completion must survive")
    else:
        register_callback("agent_run_result", capture_result)

    os.kill(os.getpid(), signal.SIGINT)
    result = await asyncio.wait_for(task, timeout=5)
    completion = agent_completion_inbox.pop_completion(agent)

    assert implementation.calls == ["hello", "steer one"]
    assert "history-from-cancelled-follow-up" not in agent._message_history
    assert hook_calls == []
    assert cleanup_calls == ["drained"]
    if pending_work == "completion":
        assert completion is not None
    assert_cancelled_once(result, cancel_ids, statuses)


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_cancel_translated_to_handled_error_still_cleans_up(repl_guard):
    class TranslatingAgent:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def run(self, prompt: Any, **_kwargs: Any) -> Result:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                raise UsageLimitExceeded("translated cancellation") from None

    implementation = TranslatingAgent()
    cancel_ids, statuses = register_run_outcomes()
    task = asyncio.create_task(
        _runtime.run_with_mcp(DummyAgent(implementation), "hello")
    )
    await asyncio.wait_for(implementation.started.wait(), timeout=5)
    get_pause_controller().request_steer("discard me", mode="queue")

    os.kill(os.getpid(), signal.SIGINT)
    result = await asyncio.wait_for(task, timeout=5)

    assert_cancelled_once(result, cancel_ids, statuses)


def test_detach_escalation_resends_cancel(monkeypatch: pytest.MonkeyPatch):
    class FakeTask:
        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            return None

    class Loop:
        def __init__(self) -> None:
            self.calls: list[Any] = []

        def call_soon_threadsafe(self, callback: Any, *args: Any) -> None:
            self.calls.append((callback, args))

    loop = Loop()
    task = FakeTask()
    times = iter([0.0, _run_signals.CANCEL_ESCALATE_AFTER_S + 1])
    monkeypatch.setattr(_run_signals.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(_run_signals, "emit_warning", lambda *_a, **_kw: None)
    cancel = _run_signals.make_schedule_cancel(task, loop)  # type: ignore[arg-type]

    cancel(force=True)
    cancel(force=True)

    assert [callback for callback, _args in loop.calls] == [
        task.cancel,
        task.cancel,
        _run_signals.request_run_detach,
    ]


class QuickAgent:
    async def run(self, prompt: Any, **_kwargs: Any) -> Result:
        return Result()


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_sigint_interrupts_prompt_submit_before_model_start(repl_guard):
    started = asyncio.Event()
    interrupted = asyncio.Event()
    cancel_ids, _statuses = register_run_outcomes()

    async def slow_prompt_scan(_prompt: str, _run_id: str) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            interrupted.set()
            raise

    register_callback("user_prompt_submit", slow_prompt_scan)
    task = asyncio.create_task(_runtime.run_with_mcp(DummyAgent(QuickAgent()), "hello"))
    await asyncio.wait_for(started.wait(), timeout=5)
    get_pause_controller().request_steer("discard me", mode="queue")

    os.kill(os.getpid(), signal.SIGINT)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert interrupted.is_set()
    assert len(cancel_ids) == 1
    assert not get_pause_controller().has_pending_steer()
    assert signal.getsignal(signal.SIGINT) is _interactive_sigint_guard
    assert _runtime._active_run_depth == 0


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_sigint_during_start_hook_balances_terminal_lifecycle(repl_guard):
    started = asyncio.Event()
    lifecycle_depth = 0
    statuses: list[bool] = []
    cancel_ids: list[str] = []

    async def count_start(*_args: Any, **_kwargs: Any) -> None:
        nonlocal lifecycle_depth
        lifecycle_depth += 1

    async def slow_start(*_args: Any, **_kwargs: Any) -> None:
        started.set()
        await asyncio.Event().wait()

    async def count_end(*args: Any) -> None:
        nonlocal lifecycle_depth
        lifecycle_depth -= 1
        statuses.append(args[3])

    register_callback("agent_run_start", count_start)
    register_callback("agent_run_start", slow_start)
    register_callback("agent_run_end", count_end)
    register_callback("agent_run_cancel", lambda run_id: cancel_ids.append(run_id))
    task = asyncio.create_task(_runtime.run_with_mcp(DummyAgent(QuickAgent()), "hello"))
    await asyncio.wait_for(started.wait(), timeout=5)

    os.kill(os.getpid(), signal.SIGINT)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert lifecycle_depth == 0
    assert statuses == [False]
    assert len(cancel_ids) == 1
    assert signal.getsignal(signal.SIGINT) is _interactive_sigint_guard
    assert _runtime._active_run_depth == 0


@pytest.mark.skipif(not hasattr(signal, "SIGINT"), reason="SIGINT unavailable")
async def test_sigint_during_mcp_wait_balances_terminal_lifecycle(
    repl_guard, monkeypatch: pytest.MonkeyPatch
):
    from code_puppy.mcp_ import manager as mcp_manager

    class SlowManager:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.interrupted = False

        async def wait_for_pending_starts(self) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.interrupted = True
                raise

    manager = SlowManager()
    statuses: list[bool] = []
    register_callback("agent_run_end", lambda *args: statuses.append(args[3]))
    monkeypatch.setattr(mcp_manager, "_manager_instance", manager)
    task = asyncio.create_task(_runtime.run_with_mcp(DummyAgent(QuickAgent()), "hello"))
    await asyncio.wait_for(manager.started.wait(), timeout=5)

    os.kill(os.getpid(), signal.SIGINT)
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)

    assert manager.interrupted
    assert statuses == [False]
    assert signal.getsignal(signal.SIGINT) is _interactive_sigint_guard
    assert _runtime._active_run_depth == 0
