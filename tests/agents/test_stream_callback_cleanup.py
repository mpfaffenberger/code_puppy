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


async def test_registered_plugin_callback_gets_the_raw_part(monkeypatch):
    """The plugin seam end to end: a real ``stream_event`` registration gets
    the very part object core streamed (filters like emoji_filter mutate it)."""
    from pydantic_ai.messages import TextPartDelta

    from code_puppy import callbacks

    seen = []
    finished = asyncio.Event()

    def plugin(event_type, event_data, agent_session_id=None):
        seen.append((event_type, event_data["delta"]))
        finished.set()

    monkeypatch.setitem(callbacks._callbacks, "stream_event", [])
    callbacks.register_callback("stream_event", plugin)
    delta = TextPartDelta(content_delta="stream me")
    _fire_stream_event("part_delta", {"index": 0, "delta": delta})
    await asyncio.wait_for(finished.wait(), 1)
    assert seen == [("part_delta", delta)]
    assert seen[0][1] is delta
