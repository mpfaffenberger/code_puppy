"""Queue agent rebuilds for the live CLI event loop."""

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)
MAX_RELOAD_ATTEMPTS = 3


class DeferredReloadQueue:
    """Thread-safe queue that applies agent rebuilds on the main loop."""

    def __init__(self) -> None:
        self._pending: dict[str, int] = {}
        self._lock = threading.Lock()

    def request(self, agent_name: str) -> None:
        """Request a reload, preserving any existing retry count."""
        with self._lock:
            self._pending.setdefault(agent_name, 0)

    def clear(self) -> None:
        """Clear queued requests; intended for deterministic test cleanup."""
        with self._lock:
            self._pending.clear()

    def apply(self, get_current_agent: Callable[[], object]) -> None:
        """Apply the active request from the main event loop."""
        try:
            current = get_current_agent()
        except Exception:
            logger.exception("Could not inspect the active agent for deferred reload")
            return

        with self._lock:
            pending = dict(self._pending)

        if current.name not in pending:
            return

        try:
            current.refresh_config()
            current.reload_code_generation_agent()
        except Exception:
            with self._lock:
                attempts = self._pending.get(current.name, 0) + 1
                if attempts >= MAX_RELOAD_ATTEMPTS:
                    self._pending.pop(current.name, None)
                    logger.exception(
                        "Giving up after %d failed reload attempts for agent %r",
                        attempts,
                        current.name,
                    )
                else:
                    self._pending[current.name] = attempts
                    logger.exception(
                        "Deferred reload attempt %d/%d failed for agent %r",
                        attempts,
                        MAX_RELOAD_ATTEMPTS,
                        current.name,
                    )
            return

        with self._lock:
            self._pending.pop(current.name, None)


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
