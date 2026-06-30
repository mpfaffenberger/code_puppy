from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from code_puppy.api.session_context import SessionContext, session_manager

from .session_runtime import SessionRuntime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RuntimeCleanupResult:
    removed_session_ids: tuple[str, ...]


class SessionRuntimeManager:
    """Registry for :class:`~code_puppy.api.ws.runtime.SessionRuntime`.

    This is designed for the multiplexed chat websocket, where the
    server keeps multiple sessions "hot" at once.
    """

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._runtimes: dict[str, SessionRuntime] = {}
        self._lock = asyncio.Lock()

    async def get_runtime(self, session_id: str) -> SessionRuntime | None:
        async with self._lock:
            return self._runtimes.get(session_id)

    async def ensure_runtime(
        self,
        session_id: str,
        *,
        agent_name: str = "code-puppy",
        model_name: str | None = None,
        working_directory: str = "",
        load_if_exists: bool = True,
    ) -> SessionRuntime:
        """Get or create a runtime for *session_id*.

        This bridges to the existing :mod:`code_puppy.api.session_context` layer:
        - If an in-memory SessionContext exists, we reuse it.
        - Else, we optionally load from disk via SessionManager.load_session.
        - Else, we create a new SessionContext.

        Args:
            load_if_exists: If True, attempt to load persisted session state.

        Returns:
            SessionRuntime instance.
        """
        async with self._lock:
            existing = self._runtimes.get(session_id)
            if existing is not None:
                existing.last_used_at = self._now()
                return existing

            ctx = await session_manager.get_session(session_id)
            if ctx is None and load_if_exists:
                try:
                    ctx = await session_manager.load_session(session_id)
                except Exception:
                    logger.debug(
                        "Failed to load session %s from disk", session_id, exc_info=True
                    )
                    ctx = None

            if ctx is None:
                ctx = await session_manager.create_session(
                    session_id,
                    agent_name=agent_name,
                    model_name=model_name,
                    working_directory=working_directory,
                )

            rt = SessionRuntime(session_id=session_id, ctx=ctx)
            rt.last_used_at = self._now()
            self._runtimes[session_id] = rt
            return rt

    async def cancel_session(self, session_id: str) -> bool:
        """Cancel the active task for *session_id*.

        Returns:
            True if a runtime existed and cancellation was requested.
        """
        rt = await self.get_runtime(session_id)
        if rt is None:
            return False
        await rt.cancel()
        return True

    async def remove_runtime(self, session_id: str) -> bool:
        """Remove runtime from the manager.

        This does not destroy the underlying SessionContext (that remains in the
        existing SessionManager registry).
        """
        async with self._lock:
            removed = self._runtimes.pop(session_id, None)
        return removed is not None

    async def cleanup_idle(self, *, max_idle: timedelta) -> RuntimeCleanupResult:
        """Remove runtimes that have been idle longer than *max_idle*."""
        now = self._now()
        removed: list[str] = []

        async with self._lock:
            for session_id, rt in list(self._runtimes.items()):
                if now - rt.last_used_at > max_idle:
                    removed.append(session_id)
                    self._runtimes.pop(session_id, None)

        if removed:
            logger.info("Cleaned up %d idle runtimes", len(removed))

        return RuntimeCleanupResult(removed_session_ids=tuple(removed))

    async def get_session_context(self, session_id: str) -> SessionContext | None:
        rt = await self.get_runtime(session_id)
        return rt.ctx if rt else None

    async def active_task_count(self) -> int:
        """Count runtimes with active tasks (for debugging/tests)."""
        async with self._lock:
            rts = list(self._runtimes.values())

        count = 0
        for rt in rts:
            task = await rt.get_active_task()
            if task is not None and not task.done():
                count += 1
        return count


_manager_instance: SessionRuntimeManager | None = None


def get_runtime_manager() -> SessionRuntimeManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SessionRuntimeManager()
    return _manager_instance
