from __future__ import annotations

import asyncio
import sys
import types

import pytest

from code_puppy.api.ws.ws_stream_drain import (
    StreamDrainHandle,
    cancel_active_streaming,
    start_stream_drain,
    stop_stream_drain,
)


class _Logger:
    def __init__(self):
        self.debug_messages = []
        self.warning_messages = []

    def debug(self, message, *args):
        self.debug_messages.append(message % args if args else message)

    def warning(self, message, *args):
        self.warning_messages.append(message % args if args else message)


@pytest.mark.asyncio
async def test_start_stream_drain_subscribes_and_waits_for_ready(monkeypatch):
    subscribed = []
    queue = asyncio.Queue()
    logger = _Logger()

    emitter_module = types.SimpleNamespace(
        subscribe=lambda *, session_id: subscribed.append(session_id) or queue,
        unsubscribe=lambda event_queue: None,
    )
    monkeypatch.setitem(
        sys.modules,
        "code_puppy.plugins.frontend_emitter.emitter",
        emitter_module,
    )

    async def _drain(event_queue, ready_event: asyncio.Event):
        assert event_queue is queue
        ready_event.set()
        await asyncio.sleep(0)

    handle = await start_stream_drain(
        session_id="session-1",
        drain_coro_factory=_drain,
        logger=logger,
    )
    await handle.task

    assert subscribed == ["session-1"]
    assert handle is not None
    assert handle.event_queue is queue
    assert "Subscribed to frontend emitter for streaming" in logger.debug_messages


@pytest.mark.asyncio
async def test_stop_stream_drain_stops_task_and_unsubscribes():
    unsubscribed = []
    logger = _Logger()
    stop_draining = asyncio.Event()
    ready = asyncio.Event()

    async def _worker():
        ready.set()
        while not stop_draining.is_set():
            await asyncio.sleep(0)

    task = asyncio.create_task(_worker())
    await ready.wait()

    await stop_stream_drain(
        handle=StreamDrainHandle(
            event_queue="queue-1",
            task=task,
            unsubscribe=lambda event_queue: unsubscribed.append(event_queue),
        ),
        stop_draining=stop_draining,
        logger=logger,
    )

    assert stop_draining.is_set()
    assert task.done()
    assert unsubscribed == ["queue-1"]
    assert "Unsubscribed from frontend emitter" in logger.debug_messages


@pytest.mark.asyncio
async def test_cancel_active_streaming_cancels_and_clears_stop_flag():
    logger = _Logger()
    stop_draining = asyncio.Event()
    cancel_seen = []

    async def _worker():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancel_seen.append(True)
            raise

    task = asyncio.create_task(_worker())
    await asyncio.sleep(0)

    await cancel_active_streaming(
        active_drain_task=task,
        stop_draining=stop_draining,
        logger=logger,
        log_message="Active streaming cancelled",
    )

    assert task.done()
    assert cancel_seen == [True]
    assert stop_draining.is_set() is False
    assert "Active streaming cancelled" in logger.debug_messages
