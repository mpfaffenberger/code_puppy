"""Capability that tracks active model-request tasks for cancellation.

pydantic-ai >= 1.80 wraps model requests in independent ``asyncio.Task``s via
a cooperative hand-off protocol (``wrap_model_request``).  External
``task.cancel()`` on the parent agent task no longer closes the HTTP stream
because the ``wrap_task`` holding the stream is an independent task.

This capability captures references to those inner tasks by recording
``asyncio.current_task()`` inside ``wrap_model_request``, and registers a
``done_callback`` that retrieves the task's exception so it doesn't surface
as an "Unhandled exception in event loop" when pydantic-ai's cleanup race
leaves the exception unretrieved.

Additionally, ``install_cancellation_exception_handler`` installs a targeted
asyncio exception handler that suppresses "Task was destroyed but it is
pending" warnings from pydantic-ai's internal ``Event.wait()`` tasks that
get garbage-collected during cancellation before the event loop can process
their cancellation.

On pydantic-ai < 1.80 the capability API doesn't exist, so this module
gracefully degrades to a no-op (``HAS_CAPABILITIES = False``).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Set

logger = logging.getLogger(__name__)

# ── Global task registry ────────────────────────────────────────────────────

_active_model_request_tasks: Set[asyncio.Task[Any]] = set()


def _retrieve_exception(task: asyncio.Task[Any]) -> None:
    """Done-callback: retrieve the task exception to prevent asyncio warnings.

    When ``cancel_active_model_requests`` cancels a ``wrap_task``, a race in
    pydantic-ai's ``stream()`` cleanup can leave the task's exception
    unretrieved.  asyncio then logs "Unhandled exception in event loop" when
    the task is garbage-collected.  Calling ``task.exception()`` here marks
    it as retrieved.
    """
    if task.cancelled():
        return
    try:
        task.exception()
    except (asyncio.CancelledError, asyncio.InvalidStateError):
        pass
    except Exception:
        # Exception was retrieved — that's the point.  Swallow it.
        pass


def cancel_active_model_requests(loop: asyncio.AbstractEventLoop) -> int:
    """Cancel every tracked model-request task (thread-safe).

    Returns the number of tasks that were cancelled.
    """
    cancelled = 0
    for task in list(_active_model_request_tasks):
        if not task.done():
            loop.call_soon_threadsafe(task.cancel)
            cancelled += 1
    if cancelled:
        logger.debug("Cancelled %d active model-request task(s)", cancelled)
    return cancelled


# ── Asyncio exception handler ──────────────────────────────────────────────

_default_handler: Any = None


def install_cancellation_exception_handler(loop: asyncio.AbstractEventLoop) -> None:
    """Install a custom exception handler that suppresses cancellation noise.

    pydantic-ai's ``stream()`` creates internal ``Event.wait()`` tasks
    (e.g. ``ready_waiter``) that can be garbage-collected while still pending
    when external cancellation causes ``CancelledError`` to propagate out
    before the event loop processes their cancellation.  This produces:

        Task was destroyed but it is pending!
        task: <Task pending coro=<Event.wait() ...>>

    This handler suppresses that specific warning and delegates everything
    else to the default handler.
    """
    global _default_handler
    _default_handler = loop.get_exception_handler()

    def _handler(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        message = context.get("message", "")

        # Suppress "Task was destroyed but it is pending" for Event.wait() tasks.
        # These are pydantic-ai's internal ready_waiter / stream_done waiter tasks
        # that get GC'd during cancellation before the event loop can finalize them.
        if "Task was destroyed but it is pending" in message:
            task = context.get("task") or context.get("future")
            if task is not None:
                coro = getattr(task, "get_coro", lambda: None)()
                coro_name = getattr(coro, "__qualname__", "") if coro else ""
                if "Event.wait" in coro_name:
                    logger.debug(
                        "Suppressed 'Task destroyed but pending' for %s", coro_name
                    )
                    return

        # Delegate to the original handler (or asyncio's default).
        if _default_handler is not None:
            _default_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)


# ── Capability (only available on pydantic-ai >= 1.80) ──────────────────────

HAS_CAPABILITIES = False
CancellationCapability: Any = None  # replaced below if available

try:
    from dataclasses import dataclass

    from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
    from pydantic_ai.messages import ModelResponse
    from pydantic_ai.models import ModelRequestContext
    from pydantic_ai.tools import RunContext

    @dataclass
    class _CancellationCapability(AbstractCapability[Any]):
        """Tracks the ``asyncio.Task`` running each model request.

        ``wrap_model_request`` runs *inside* the ``wrap_task`` that
        pydantic-ai creates in ``ModelRequestNode.stream()``.  So
        ``asyncio.current_task()`` gives us a direct handle to the task
        that owns the HTTP connection.

        A ``done_callback`` is registered on each tracked task so that
        its exception is always retrieved — even when pydantic-ai's
        cleanup race skips the ``await wrap_task``.
        """

        async def wrap_model_request(
            self,
            ctx: RunContext[Any],
            *,
            request_context: ModelRequestContext,
            handler: WrapModelRequestHandler,
        ) -> ModelResponse:
            task = asyncio.current_task()
            if task is not None:
                _active_model_request_tasks.add(task)
                task.add_done_callback(_retrieve_exception)
            try:
                return await handler(request_context)
            finally:
                if task is not None:
                    _active_model_request_tasks.discard(task)

    CancellationCapability = _CancellationCapability
    HAS_CAPABILITIES = True

except ImportError:
    pass


def _cancellation_capabilities():
    """Return capabilities list with CancellationCapability if available."""
    if HAS_CAPABILITIES and CancellationCapability is not None:
        return [CancellationCapability()]
    return []
