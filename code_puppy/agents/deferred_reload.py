"""Queue agent rebuilds for the live CLI event loop."""

import logging
import threading
from collections.abc import Callable

from code_puppy.i18n import t
from code_puppy.messaging import emit_warning

logger = logging.getLogger(__name__)
MAX_RELOAD_ATTEMPTS = 3


class DeferredReloadQueue:
    """Thread-safe queue that applies agent rebuilds on the main loop.

    Requests are keyed by agent name and only ever applied while an agent
    with that name is the active one. Each request carries a generation that
    changes whenever it is re-requested, so work that started before a newer
    request can neither clear it nor spend its retry budget.
    """

    def __init__(self) -> None:
        self._generations: dict[str, int] = {}
        self._lock = threading.Lock()

    def request(self, agent_name: str) -> None:
        """Request a reload; a repeat request supersedes any in-flight rebuild."""
        with self._lock:
            self._generations[agent_name] = self._generations.get(agent_name, 0) + 1

    def clear(self) -> None:
        """Clear queued requests; intended for deterministic test cleanup."""
        with self._lock:
            self._generations.clear()

    def apply(self, get_current_agent: Callable[[], object]) -> None:
        """Rebuild the active agent if it has a pending request.

        The agent and its name are read once, up front: ``refresh_config`` may
        rewrite an agent's configuration, so nothing after it is trusted to
        identify the request. Failed rebuilds are retried right here, up to
        ``MAX_RELOAD_ATTEMPTS`` times, stopping early if a newer request for
        the same agent arrives (that request starts again from scratch on the
        next drain).
        """
        try:
            current = get_current_agent()
            name = current.name
        except Exception:
            logger.exception("Could not inspect the active agent for deferred reload")
            return
        if not isinstance(name, str) or not name:
            logger.warning("Skipping deferred reload: unusable agent name %r", name)
            return

        with self._lock:
            generation = self._generations.get(name)
        if generation is None:
            return

        error: Exception | None = None
        for attempt in range(1, MAX_RELOAD_ATTEMPTS + 1):
            if not self._is_current(name, generation):
                return  # admission: never start a rebuild for a stale request
            try:
                current.refresh_config()
                current.reload_code_generation_agent()
            except Exception as exc:
                error = exc
                logger.exception(
                    "Deferred reload attempt %d/%d failed for agent %r",
                    attempt,
                    MAX_RELOAD_ATTEMPTS,
                    name,
                )
                if not self._is_current(name, generation):
                    return
            else:
                self._finish(name, generation)
                return

        if self._finish(name, generation):
            emit_warning(
                t(
                    "agent_reload.gave_up",
                    agent=name,
                    attempts=MAX_RELOAD_ATTEMPTS,
                    error=error,
                )
            )

    def _is_current(self, name: str, generation: int) -> bool:
        """True while the request this drain was selected by is still pending."""
        with self._lock:
            return self._generations.get(name) == generation

    def _finish(self, name: str, generation: int) -> bool:
        """Drop the request unless a newer one replaced it; True if dropped."""
        with self._lock:
            if self._generations.get(name) != generation:
                return False
            del self._generations[name]
            return True


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
