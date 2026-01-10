"""Event emitter for frontend integration.

Provides a global event queue that WebSocket handlers can subscribe to.
Events are JSON-serializable dicts with type, timestamp, and data.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
from uuid import uuid4

logger = logging.getLogger(__name__)

# Global state for event distribution
_subscribers: Set[asyncio.Queue[Dict[str, Any]]] = set()
_recent_events: List[Dict[str, Any]] = []  # Keep last N events for new subscribers
MAX_RECENT_EVENTS = 100


def emit_event(event_type: str, data: Any = None) -> None:
    """Emit an event to all subscribers.

    Creates a structured event dict with unique ID, type, timestamp, and data,
    then broadcasts it to all active subscriber queues.

    Args:
        event_type: Type of event (e.g., "tool_call_start", "stream_token")
        data: Event data payload - should be JSON-serializable
    """
    event: Dict[str, Any] = {
        "id": str(uuid4()),
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data or {},
    }

    # Store in recent events for replay to new subscribers
    _recent_events.append(event)
    if len(_recent_events) > MAX_RECENT_EVENTS:
        _recent_events.pop(0)

    # Broadcast to all active subscribers
    for subscriber_queue in _subscribers.copy():
        try:
            subscriber_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                f"Subscriber queue full, dropping event: {event_type}"
            )
        except Exception as e:
            logger.error(f"Failed to emit event to subscriber: {e}")


def subscribe() -> asyncio.Queue[Dict[str, Any]]:
    """Subscribe to events.

    Creates and returns a new async queue that will receive all future events.
    The queue has a max size of 100 to prevent unbounded memory growth if
    the subscriber is slow to process events.

    Returns:
        An asyncio.Queue that will receive event dictionaries.
    """
    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)
    _subscribers.add(queue)
    logger.debug(f"New subscriber added, total subscribers: {len(_subscribers)}")
    return queue


def unsubscribe(queue: asyncio.Queue[Dict[str, Any]]) -> None:
    """Unsubscribe from events.

    Removes the queue from the subscriber set. Safe to call even if the queue
    was never subscribed or already unsubscribed.

    Args:
        queue: The queue returned from subscribe()
    """
    _subscribers.discard(queue)
    logger.debug(
        f"Subscriber removed, remaining subscribers: {len(_subscribers)}"
    )


def get_recent_events() -> List[Dict[str, Any]]:
    """Get recent events for new subscribers.

    Returns a copy of the most recent events (up to MAX_RECENT_EVENTS).
    Useful for allowing new WebSocket connections to "catch up" on
    recent activity.

    Returns:
        A list of recent event dictionaries.
    """
    return _recent_events.copy()


def get_subscriber_count() -> int:
    """Get the current number of active subscribers.

    Returns:
        Number of active subscriber queues.
    """
    return len(_subscribers)


def clear_recent_events() -> None:
    """Clear the recent events buffer.

    Useful for testing or resetting state.
    """
    _recent_events.clear()
    logger.debug("Recent events cleared")
