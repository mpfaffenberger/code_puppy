"""Physical retries and context entry must respect consumed cancellation."""

import asyncio
import os
import signal
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from code_puppy.agents import _runtime, retry_profiles
from code_puppy.agents.run_invocation import ModelCall
from code_puppy.callbacks import register_callback
from tests.agents.test_runtime_cancellation import (  # noqa: F401
    DummyAgent,
    isolated_runtime,
)
from tests.agents.test_runtime_consumed_cancellation import (  # noqa: F401
    RecordingAgent,
    Result,
    assert_cancelled_once,
    register_run_outcomes,
    repl_guard,
)


@pytest.fixture
def streaming_backoff(monkeypatch):
    state = SimpleNamespace(delays=[], warning=Mock(), log=Mock(), diagnostics=Mock())
    original_sleep = asyncio.sleep

    async def observed_sleep(delay, *args, **kwargs):
        if delay == 10.0:
            state.delays.append((delay, asyncio.current_task().cancelling()))
            return
        return await original_sleep(delay, *args, **kwargs)

    monkeypatch.setattr(_runtime.asyncio, "sleep", observed_sleep)
    monkeypatch.setattr(_runtime, "emit_warning", state.warning)
    monkeypatch.setattr(_runtime, "emit_exception_diagnostics", state.diagnostics)
    monkeypatch.setattr("code_puppy.error_logging.log_error", state.log)
    monkeypatch.setattr(
        retry_profiles,
        "make_streaming_retry",
        lambda *a, **k: _runtime.streaming_retry(max_attempts=2, delays=[10.0]),
    )
    return state


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGINT integration")
@pytest.mark.parametrize(
    "case",
    [
        "provider_translates",
        "exception_hook_consumes",
        "exception_hook_declines_retry",
        "streaming_translates",
    ],
)
@pytest.mark.usefixtures("repl_guard")
async def test_no_physical_retry_after_cancel(streaming_backoff, case):
    cancel_in_hook = case in {
        "exception_hook_consumes",
        "exception_hook_declines_retry",
    }
    ready = asyncio.Event()
    calls = []
    recovery_calls = []
    cancel_ids, statuses = register_run_outcomes()

    class RetryAgent:
        async def run(self, prompt, **kwargs):
            calls.append(prompt)
            if len(calls) == 1:
                if not cancel_in_hook:
                    ready.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        if case == "streaming_translates":
                            raise httpx.ReadTimeout("translated cancellation") from None
                        raise RuntimeError("translated cancellation") from None
                raise RuntimeError("ordinary model error")
            return Result("unexpected-retry")

    async def retry_hook(*args, **kwargs):
        recovery_calls.append(args)
        if cancel_in_hook:
            ready.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                pass
        if case == "exception_hook_declines_retry":
            return None
        return {"retry": True, "delay": 10.0}

    register_callback("agent_exception", retry_hook)
    agent = DummyAgent(RetryAgent())
    original_history = list(agent._message_history)
    task = asyncio.create_task(_runtime.run_with_mcp(agent, "hello"))
    try:
        await asyncio.wait_for(ready.wait(), 5)
        os.kill(os.getpid(), signal.SIGINT)
        result = await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert calls == ["hello"]
    assert len(recovery_calls) == int(cancel_in_hook)
    assert agent._message_history == original_history
    assert_cancelled_once(result, cancel_ids, statuses)
    assert streaming_backoff.delays == []
    streaming_backoff.warning.assert_not_called()
    streaming_backoff.log.assert_not_called()
    streaming_backoff.diagnostics.assert_not_called()


async def test_context_exit_translation_skips_streaming_backoff(streaming_backoff):
    ready = asyncio.Event()
    events = []
    calls = []

    @asynccontextmanager
    async def context(name):
        events.append(("enter", name))
        try:
            yield
        except asyncio.CancelledError:
            if name == "inner":
                raise httpx.ReadTimeout("translated context cancellation") from None
            raise
        finally:
            events.append(("exit", name))

    async def provider(prompt):
        calls.append(prompt)
        ready.set()
        await asyncio.Event().wait()

    call = ModelCall(
        lambda: SimpleNamespace(run=provider),
        lambda _: [context("outer"), context("inner")],
    )
    retry = _runtime.streaming_retry(max_attempts=2, delays=[10.0])(
        lambda: call.run("hello")
    )
    task = asyncio.create_task(retry())
    try:
        await asyncio.wait_for(ready.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert task.cancelling() == 1
    assert calls == ["hello"]
    assert events == [
        ("enter", "outer"),
        ("enter", "inner"),
        ("exit", "inner"),
        ("exit", "outer"),
    ]
    assert streaming_backoff.delays == []
    streaming_backoff.warning.assert_not_called()
    streaming_backoff.log.assert_not_called()


async def test_uncancelled_streaming_timeout_still_retries(streaming_backoff):
    model = SimpleNamespace(
        run=AsyncMock(side_effect=[httpx.ReadTimeout("transient"), "recovered"])
    )
    call = ModelCall(lambda: model, lambda _: [])
    retry = _runtime.streaming_retry(max_attempts=2, delays=[10.0])(
        lambda: call.run("hello")
    )
    task = asyncio.create_task(retry())
    assert await asyncio.wait_for(task, 5) == "recovered"
    assert model.run.await_count == 2
    assert streaming_backoff.delays == [(10.0, 0)]
    streaming_backoff.warning.assert_called_once()
    streaming_backoff.log.assert_called_once()


@pytest.mark.skipif(os.name == "nt", reason="POSIX SIGINT integration")
@pytest.mark.usefixtures("repl_guard")
async def test_consumed_attempt_context_cannot_start_provider():
    ready = asyncio.Event()
    implementation = RecordingAgent()
    cancel_ids, statuses = register_run_outcomes()

    @asynccontextmanager
    async def physical_context():
        ready.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            pass
        yield

    register_callback("agent_run_context", lambda *a, **k: physical_context())
    task = asyncio.create_task(
        _runtime.run_with_mcp(DummyAgent(implementation), "hello")
    )
    try:
        await asyncio.wait_for(ready.wait(), 5)
        os.kill(os.getpid(), signal.SIGINT)
        result = await asyncio.wait_for(task, 5)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert implementation.calls == []
    assert_cancelled_once(result, cancel_ids, statuses)


@pytest.mark.parametrize("cancel_at", ["before_resolution", "first_context"])
async def test_attempt_stops_before_next_side_effect(cancel_at):
    events = []
    model = SimpleNamespace(run=AsyncMock())
    resolve = Mock(return_value=model)

    async def consume_cancel():
        asyncio.current_task().cancel()
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass

    @asynccontextmanager
    async def context(name):
        events.append(("enter", name))
        if name == "first":
            await consume_cancel()
        try:
            yield
        finally:
            events.append(("exit", name))

    async def run():
        if cancel_at == "before_resolution":
            await consume_cancel()
        call = ModelCall(resolve, lambda _: [context("first"), context("second")])
        return await call.run("hello")

    task = asyncio.create_task(run())
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelling() == 1
    model.run.assert_not_awaited()
    if cancel_at == "before_resolution":
        resolve.assert_not_called()
        assert events == []
    else:
        assert events == [("enter", "first"), ("exit", "first")]
