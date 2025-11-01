"""Global cancellation token system for interruptible operations."""

import asyncio
import threading


class CancellationToken:
    """Global cancellation token that can be checked by any operation."""

    def __init__(self):
        self._cancelled = False
        self._lock = threading.RLock()
        self._event = asyncio.Event()

    def cancel(self) -> None:
        """Cancel the token."""
        with self._lock:
            self._cancelled = True
            # Set the asyncio event for async waiters
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._event.set)
            except RuntimeError:
                # No running loop, set directly
                self._event.set()

    def is_cancelled(self) -> bool:
        """Check if the token is cancelled."""
        with self._lock:
            return self._cancelled

    def reset(self) -> None:
        """Reset the token to uncancelled state."""
        with self._lock:
            self._cancelled = False
            self._event.clear()

    def raise_if_cancelled(self, message: str = "Operation was cancelled") -> None:
        """Raise an exception if the token is cancelled."""
        if self.is_cancelled():
            raise asyncio.CancelledError(message)

    async def wait_for_cancel(self) -> None:
        """Wait until the token is cancelled."""
        await self._event.wait()

    def __bool__(self) -> bool:
        """Boolean context - True if not cancelled."""
        return not self.is_cancelled()


# Global cancellation token instance
_global_cancellation_token = CancellationToken()


def get_global_cancellation_token() -> CancellationToken:
    """Get the global cancellation token."""
    return _global_cancellation_token


def cancel_all_operations() -> None:
    """Cancel all operations using the global token."""
    _global_cancellation_token.cancel()


def reset_cancellation_token() -> None:
    """Reset the global cancellation token."""
    _global_cancellation_token.reset()


def check_cancellation() -> bool:
    """Check if cancellation is requested."""
    return _global_cancellation_token.is_cancelled()


def raise_if_cancelled(message: str = "Operation was cancelled") -> None:
    """Raise an exception if cancellation is requested."""
    _global_cancellation_token.raise_if_cancelled(message)
