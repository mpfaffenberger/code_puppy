"""A coroutine belongs either to a scheduled task or to the failure cleanup."""

import asyncio
import inspect
from unittest.mock import Mock

import pytest

from code_puppy.agents.event_stream_handler import _fire_stream_event


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("no loop"), ImportError("unavailable"), asyncio.CancelledError()],
)
def test_failed_submission_closes_coroutine(monkeypatch, failure):
    async def callback():
        pass

    coroutine = callback()
    monkeypatch.setattr(
        "code_puppy.callbacks.on_stream_event", Mock(return_value=coroutine)
    )
    monkeypatch.setattr(
        "code_puppy.agents.event_stream_handler.asyncio.create_task",
        Mock(side_effect=failure),
    )
    try:
        if isinstance(failure, asyncio.CancelledError):
            with pytest.raises(asyncio.CancelledError):
                _fire_stream_event("delta", {})
        else:
            _fire_stream_event("delta", {})
        assert inspect.getcoroutinestate(coroutine) == inspect.CORO_CLOSED
    finally:
        coroutine.close()  # keep control runs warning-free, after the assertion


async def test_successful_submission_runs_callback(monkeypatch):
    seen = []
    finished = asyncio.Event()

    async def callback(kind, data, session):
        seen.append((kind, data, session))
        finished.set()

    monkeypatch.setattr("code_puppy.callbacks.on_stream_event", callback)
    monkeypatch.setattr("code_puppy.messaging.get_session_context", lambda: "session")
    _fire_stream_event("delta", {"text": "hello"})
    await asyncio.wait_for(finished.wait(), 1)
    assert seen == [("delta", {"text": "hello"}, "session")]
