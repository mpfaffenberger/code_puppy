"""Queue agent rebuilds for the live CLI event loop."""

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

from code_puppy.i18n import t
from code_puppy.messaging import emit_warning

logger = logging.getLogger(__name__)
MAX_RELOAD_ATTEMPTS = 3


@dataclass
class _Request:
    """A pending reload; ``generation`` changes whenever it is re-requested."""

    generation: int = 0
    attempts: int = 0


class DeferredReloadQueue:
    """Thread-safe queue that applies agent rebuilds on the main loop."""

    def __init__(self) -> None:
        self._pending: dict[str, _Request] = {}
        self._lock = threading.Lock()

    def request(self, agent_name: str) -> None:
        """Request a reload; a repeat request supersedes any in-flight rebuild.

        A fresh request means the configuration changed again, so it gets a
        full set of attempts and cannot be cleared by a rebuild that started
        before it arrived.
        """
        with self._lock:
            pending = self._pending.get(agent_name)
            if pending is None:
                self._pending[agent_name] = _Request()
            else:
                pending.generation += 1
                pending.attempts = 0

    def clear(self) -> None:
        """Clear queued requests; intended for deterministic test cleanup."""
        with self._lock:
            self._pending.clear()

    def apply(self, get_current_agent: Callable[[], object]) -> None:
        """Apply the active agent's request from the main event loop."""
        try:
            current = get_current_agent()
        except Exception:
            logger.exception("Could not inspect the active agent for deferred reload")
            return

        with self._lock:
            pending = self._pending.get(current.name)
            if pending is None:
                return
            generation = pending.generation

        try:
            current.refresh_config()
            current.reload_code_generation_agent()
        except Exception as exc:
            logger.exception("Deferred reload failed for agent %r", current.name)
            self._record_failure(current.name, generation, exc)
            return

        with self._lock:
            pending = self._pending.get(current.name)
            # A newer request arrived mid-rebuild; keep it for the next drain.
            if pending is not None and pending.generation == generation:
                del self._pending[current.name]

    def _record_failure(self, agent_name: str, generation: int, exc: Exception) -> None:
        """Count a failed attempt; evict and warn the user once attempts run out."""
        with self._lock:
            pending = self._pending.get(agent_name)
            if pending is None or pending.generation != generation:
                return  # superseded: the newer request starts from scratch
            pending.attempts += 1
            if pending.attempts < MAX_RELOAD_ATTEMPTS:
                return
            del self._pending[agent_name]
            attempts = pending.attempts

        emit_warning(
            t(
                "agent_reload.gave_up",
                agent=agent_name,
                attempts=attempts,
                error=exc,
            )
        )


_queue = DeferredReloadQueue()


def request_agent_reload(agent_name: str) -> None:
    """Request a main-loop reload for *agent_name* after its config changes."""
    _queue.request(agent_name)


def apply_agent_reloads(get_current_agent: Callable[[], object]) -> None:
    """Apply queued reloads for the active agent on the main event loop."""
    _queue.apply(get_current_agent)


def clear_pending_agent_reloads() -> None:
    """Clear queued reloads, primarily for test isolation."""
    _queue.clear()
