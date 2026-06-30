"""Event emitter for frontend integration.

Provides a global event queue that WebSocket handlers can subscribe to.
Events are JSON-serializable dicts with type, timestamp, data, and an
optional ``session_id`` channel for multi-tenant routing.

Session-channel model
---------------------
- Producers may attach a ``session_id`` to an event in two ways:
    1. Explicit kwarg:  ``emit_event(type, data, session_id="abc")``
    2. ContextVar:      set ``code_puppy.plugins.frontend_emitter.session_context.current_emitter_session_id``
                        before calling ``emit_event``; the value is
                        picked up automatically.
  The explicit kwarg always wins over the ContextVar.

- Consumers may subscribe in two ways:
    1. ``subscribe()``                        -> wildcard (all events)
    2. ``subscribe(session_id="abc")``        -> only events whose
                                                  ``session_id`` matches
                                                  ``"abc"``.
  Wildcard subscribers also receive session-tagged events. Session
  subscribers only receive events whose ``session_id`` exactly matches
  their filter (events with ``session_id is None`` are NOT delivered
  to session subscribers).

This design is fully backward compatible: existing 2-arg callers of
``emit_event`` and bare ``subscribe()`` calls behave identically to
before -- they just see ``session_id: None`` on emitted events.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from code_puppy.config import (
    get_frontend_emitter_enabled,
    get_frontend_emitter_max_recent_events,
    get_frontend_emitter_queue_size,
)
from code_puppy.plugins.frontend_emitter.session_context import (
    current_emitter_session_id,
)

logger = logging.getLogger(__name__)


# Sentinel used for "no explicit kwarg was passed".  We can't use ``None``
# because ``None`` is a meaningful explicit value meaning "this event has
# no session context, even if a ContextVar is set".  This lets a caller
# opt OUT of the ContextVar fallback by explicitly passing ``session_id=None``.
class _Unset:
    def __repr__(self) -> str:
        return "<unset>"


_UNSET: Any = _Unset()


@dataclass(eq=False)
class _Subscriber:
    """A subscription handle. Wraps an asyncio.Queue plus an optional filter."""

    queue: "asyncio.Queue[Dict[str, Any]]"
    session_id: Optional[str] = None  # None == wildcard (all events)


# Global state for event distribution.
#
# We keep two parallel data structures:
#   * ``_subscribers``: the legacy "set of queues" used by callers that
#     have a raw queue reference (back-compat for unsubscribe(queue)).
#   * ``_subscriber_records``: the richer set with filter metadata,
#     iterated during fan-out.
#
# Both are kept in sync by ``subscribe`` / ``unsubscribe``.
_subscribers: Set["asyncio.Queue[Dict[str, Any]]"] = set()
_subscriber_records: Set[_Subscriber] = set()
_recent_events: List[Dict[str, Any]] = []  # Keep last N events for new subscribers


def _resolve_session_id(explicit: Any) -> Optional[str]:
    """Resolve the effective session_id for an emit call.

    Precedence: explicit kwarg > ContextVar > None.

    Passing ``session_id=None`` *explicitly* opts out of the ContextVar
    fallback (the resolved value is ``None``).  Only the ``_UNSET``
    sentinel triggers the ContextVar lookup.
    """
    if explicit is _UNSET:
        try:
            return current_emitter_session_id.get()
        except LookupError:
            return None
    return explicit


def emit_event(
    event_type: str,
    data: Any = None,
    session_id: Any = _UNSET,
) -> None:
    """Emit an event to all matching subscribers.

    Creates a structured event dict with unique ID, type, timestamp,
    data, and ``session_id`` channel, then broadcasts it to all active
    subscribers whose filter matches.

    Args:
        event_type: Type of event (e.g., "tool_call_start", "stream_token").
        data: Event data payload - should be JSON-serializable.
        session_id: Optional session identifier. If omitted, the value of
            the ``code_puppy.plugins.frontend_emitter.session_context.current_emitter_session_id`` ContextVar is
            used (or ``None`` if no ContextVar is set). Pass
            ``session_id=None`` explicitly to bypass the ContextVar
            fallback.

    Routing rules:
        - A wildcard subscriber (``subscribe()`` with no filter) receives
          ALL events regardless of their ``session_id``.
        - A session-filtered subscriber (``subscribe(session_id="x")``)
          receives ONLY events whose resolved ``session_id == "x"``.
          Events with ``session_id is None`` are NOT delivered to
          session-filtered subscribers.
    """
    # Early return if emitter is disabled
    if not get_frontend_emitter_enabled():
        return

    resolved_sid = _resolve_session_id(session_id)

    event: Dict[str, Any] = {
        "id": str(uuid4()),
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": resolved_sid,
        "data": data or {},
    }

    # Store in recent events for replay to new subscribers
    max_recent = get_frontend_emitter_max_recent_events()
    _recent_events.append(event)
    if len(_recent_events) > max_recent:
        _recent_events.pop(0)

    # Build the set of queues that are managed via the public subscribe()
    # API.  Anything in the legacy ``_subscribers`` set that is NOT here is
    # an "orphan" -- a queue someone added directly, which we still want
    # to honour as a wildcard subscriber for back-compat.
    managed_qids = {id(sub.queue) for sub in _subscriber_records}

    # 1. Deliver to filter-matching managed subscribers.
    for sub in list(_subscriber_records):
        # Filter logic:
        #   - sub.session_id is None  -> wildcard, deliver everything
        #   - sub.session_id == sid   -> exact match
        #   - otherwise               -> skip
        if sub.session_id is not None and sub.session_id != resolved_sid:
            continue
        try:
            sub.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Subscriber queue full, dropping event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to emit event to subscriber: {e}")

    # 2. Back-compat: deliver to any queue someone added DIRECTLY to the
    # legacy ``_subscribers`` set without going through ``subscribe()``.
    # These orphan queues are treated as unconditional wildcards.  Queues
    # owned by ``subscribe()`` are excluded here so they don't double-fire
    # and so session filtering above is respected.
    for orphan_q in list(_subscribers):
        if id(orphan_q) in managed_qids:
            continue
        try:
            orphan_q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"Subscriber queue full, dropping event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to emit event to subscriber: {e}")


def subscribe(
    session_id: Optional[str] = None,
) -> "asyncio.Queue[Dict[str, Any]]":
    """Subscribe to events.

    Creates and returns a new async queue that will receive future events.
    The queue has a configurable max size (via frontend_emitter_queue_size)
    to prevent unbounded memory growth if the subscriber is slow.

    Args:
        session_id: If provided, the queue will ONLY receive events whose
            ``session_id`` exactly matches this value.  If omitted (or
            ``None``), the queue acts as a wildcard and receives every
            emitted event.

    Returns:
        An ``asyncio.Queue`` that will receive matching event dictionaries.
    """
    queue_size = get_frontend_emitter_queue_size()
    queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=queue_size)
    _subscribers.add(queue)
    _subscriber_records.add(_Subscriber(queue=queue, session_id=session_id))
    logger.debug(
        f"New subscriber added (session_id={session_id!r}), "
        f"total subscribers: {len(_subscriber_records)}"
    )
    return queue


def unsubscribe(queue: "asyncio.Queue[Dict[str, Any]]") -> None:
    """Unsubscribe from events.

    Removes the queue from the subscriber set. Safe to call even if the
    queue was never subscribed or already unsubscribed.

    Args:
        queue: The queue returned from ``subscribe()``.
    """
    _subscribers.discard(queue)
    # Drop matching record(s) from the rich set as well.  We compare by
    # queue identity since the same queue object can only correspond to
    # one _Subscriber record (subscribe always allocates a fresh queue).
    to_drop = {sub for sub in _subscriber_records if sub.queue is queue}
    _subscriber_records.difference_update(to_drop)
    logger.debug(
        f"Subscriber removed, remaining subscribers: {len(_subscriber_records)}"
    )


def get_recent_events(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get recent events for new subscribers.

    Args:
        session_id: Optional session filter. If provided, only events whose
            ``event["session_id"] == session_id`` are returned.

    Returns:
        A list of recent event dictionaries.
    """
    events = _recent_events.copy()
    if session_id is None:
        return events
    return [e for e in events if e.get("session_id") == session_id]


def get_subscriber_count() -> int:
    """Get the current number of active subscribers.

    Returns:
        Number of active subscriber queues.
    """
    return len(_subscriber_records)


def clear_recent_events() -> None:
    """Clear the recent events buffer.

    Useful for testing or resetting state.
    """
    _recent_events.clear()
    logger.debug("Recent events cleared")
