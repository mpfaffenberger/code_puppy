"""Helpers for WebSocket stream-drain lifecycle management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(slots=True)
class StreamDrainHandle:
    """Runtime state for one active frontend-emitter drain subscription."""

    event_queue: Any
    task: asyncio.Task
    unsubscribe: Callable[[Any], None]


async def start_stream_drain(
    *,
    session_id: str,
    drain_coro_factory: Callable[[Any, asyncio.Event], Awaitable[None]],
    logger: Any,
) -> StreamDrainHandle | None:
    """Subscribe to the frontend emitter and start the drain task."""
    try:
        from code_puppy.plugins.frontend_emitter.emitter import (
            subscribe,
            unsubscribe,
        )
    except ImportError:
        logger.warning("Frontend emitter not available")
        return None

    event_queue = subscribe(session_id=session_id)
    logger.debug("Subscribed to frontend emitter for streaming")

    drain_ready = asyncio.Event()

    async def drain_events_with_signal() -> None:
        await drain_coro_factory(event_queue, drain_ready)

    drain_task = asyncio.create_task(drain_events_with_signal())
    await drain_ready.wait()
    return StreamDrainHandle(
        event_queue=event_queue,
        task=drain_task,
        unsubscribe=unsubscribe,
    )


async def stop_stream_drain(
    *,
    handle: StreamDrainHandle | None,
    stop_draining: asyncio.Event,
    logger: Any,
) -> None:
    """Stop and unsubscribe one active stream-drain lifecycle."""
    if handle is None:
        return

    stop_draining.set()
    try:
        await asyncio.wait_for(handle.task, timeout=2.0)
    except asyncio.TimeoutError:
        handle.task.cancel()
        try:
            await handle.task
        except asyncio.CancelledError:
            pass

    handle.unsubscribe(handle.event_queue)
    logger.debug("Unsubscribed from frontend emitter")


async def cancel_active_streaming(
    *,
    active_drain_task: asyncio.Task | None,
    stop_draining: asyncio.Event,
    logger: Any,
    log_message: str | None = None,
) -> None:
    """Cancel the current drain task and reset stop state for reuse."""
    if not active_drain_task or active_drain_task.done():
        return

    stop_draining.set()
    active_drain_task.cancel()
    try:
        await active_drain_task
    except asyncio.CancelledError:
        pass
    stop_draining.clear()
    if log_message:
        logger.debug(log_message)
