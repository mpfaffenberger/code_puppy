"""Output quiescence tracking for pause+steer UI coordination."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class OutputQuiescenceTracker:
    """Tracks active output streams to determine when output is quiescent.

    This is used to coordinate pause operations - we want to wait until
    all active output streams are complete before displaying pause UI.
    """

    _instance: Optional["OutputQuiescenceTracker"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "OutputQuiescenceTracker":
        """Singleton pattern - ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize the tracker (only runs once due to singleton)."""
        if getattr(self, "_initialized", False):
            return

        self._active_count = 0
        self._count_lock = threading.Lock()
        self._quiescent_event = threading.Event()
        self._quiescent_event.set()
        self._async_quiescent_event: Optional[asyncio.Event] = None
        self._callbacks: list[Callable[[bool], None]] = []

        self._initialized = True
        logger.debug("OutputQuiescenceTracker initialized")

    def start_stream(self) -> None:
        """Signal that an output stream has started."""
        with self._count_lock:
            self._active_count += 1
            if self._active_count == 1:
                self._quiescent_event.clear()
                self._notify_callbacks(is_quiescent=False)
            logger.debug("Stream started, active count: %s", self._active_count)

    def end_stream(self) -> None:
        """Signal that an output stream has ended."""
        with self._count_lock:
            if self._active_count > 0:
                self._active_count -= 1
            else:
                logger.warning("end_stream called with no active streams")

            if self._active_count == 0:
                self._quiescent_event.set()
                self._notify_callbacks(is_quiescent=True)
                if self._async_quiescent_event is not None:
                    try:
                        self._async_quiescent_event.set()
                    except Exception:
                        pass

            logger.debug("Stream ended, active count: %s", self._active_count)

    def is_quiescent(self) -> bool:
        """Check if output is currently quiescent (no active streams)."""
        with self._count_lock:
            return self._active_count == 0

    def active_stream_count(self) -> int:
        """Get the current number of active streams."""
        with self._count_lock:
            return self._active_count

    def wait_for_quiescence(self, timeout: Optional[float] = None) -> bool:
        """Block until output becomes quiescent or timeout."""
        return self._quiescent_event.wait(timeout=timeout)

    async def async_wait_for_quiescence(self, timeout: Optional[float] = None) -> bool:
        """Async version of wait_for_quiescence."""
        if self.is_quiescent():
            return True

        if self._async_quiescent_event is None:
            self._async_quiescent_event = asyncio.Event()
            if self.is_quiescent():
                self._async_quiescent_event.set()

        try:
            if timeout is not None:
                await asyncio.wait_for(
                    self._async_quiescent_event.wait(), timeout=timeout
                )
            else:
                await self._async_quiescent_event.wait()
            return True
        except asyncio.TimeoutError:
            return False

    def add_callback(self, callback: Callable[[bool], None]) -> None:
        """Add a callback for quiescence state changes."""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[bool], None]) -> bool:
        """Remove a quiescence callback."""
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False

    def _notify_callbacks(self, is_quiescent: bool) -> None:
        for callback in self._callbacks:
            try:
                callback(is_quiescent)
            except Exception as exc:
                logger.error("Quiescence callback error: %s", exc)

    def reset(self) -> None:
        """Reset the tracker state (for testing)."""
        with self._count_lock:
            self._active_count = 0
            self._quiescent_event.set()
            self._async_quiescent_event = None
            self._callbacks.clear()
            logger.debug("OutputQuiescenceTracker reset")


_quiescence_tracker: Optional[OutputQuiescenceTracker] = None
_quiescence_lock = threading.Lock()


def get_output_quiescence_tracker() -> OutputQuiescenceTracker:
    """Get the singleton OutputQuiescenceTracker instance."""
    global _quiescence_tracker
    if _quiescence_tracker is None:
        with _quiescence_lock:
            if _quiescence_tracker is None:
                _quiescence_tracker = OutputQuiescenceTracker()
    return _quiescence_tracker


def reset_output_quiescence_tracker() -> None:
    """Reset the global OutputQuiescenceTracker (for testing)."""
    global _quiescence_tracker
    if _quiescence_tracker is not None:
        _quiescence_tracker.reset()


__all__ = [
    "OutputQuiescenceTracker",
    "get_output_quiescence_tracker",
    "reset_output_quiescence_tracker",
]
