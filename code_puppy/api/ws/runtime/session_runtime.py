from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from code_puppy.api.session_context import SessionContext


@dataclass(slots=True)
class SessionRuntime:
    """Async runtime state for a single session.

    This complements :class:`~code_puppy.api.session_context.SessionContext`.

    SessionContext stores durable-ish session state (agent, history, metadata).
    SessionRuntime stores ephemeral runtime state (active stream task,
    cancellation token/event, etc.).

    NOTE: This is scaffolding for chat mux and is not yet integrated into
    websocket handlers.
    """

    session_id: str
    ctx: SessionContext

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # When set, any active streaming loop should stop ASAP.
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)

    # Track at most one active streaming task at a time for now.
    _active_task: asyncio.Task[Any] | None = None

    # Serialise runtime-level mutations.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def set_active_task(self, task: asyncio.Task[Any] | None) -> None:
        """Set (or clear) the active streaming task for this session."""
        async with self._lock:
            self._active_task = task
            self.last_used_at = datetime.now(timezone.utc)

    async def get_active_task(self) -> asyncio.Task[Any] | None:
        async with self._lock:
            return self._active_task

    async def cancel(self) -> None:
        """Cancel the active streaming task (if any) and set cancel_event."""
        self.cancel_event.set()
        async with self._lock:
            task = self._active_task

        if task and not task.done():
            task.cancel()

    async def reset_cancel(self) -> None:
        """Clear cancel state for the next turn."""
        # asyncio.Event has no clear() in older Python; but 3.11+ has.
        # This project supports 3.11+, so use clear().
        self.cancel_event.clear()

    async def touch(self) -> None:
        """Update last_used_at."""
        async with self._lock:
            self.last_used_at = datetime.now(timezone.utc)
