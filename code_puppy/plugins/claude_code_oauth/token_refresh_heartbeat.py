"""Token refresh heartbeat for long-running Claude Code OAuth sessions.

This module provides a background task that periodically checks and refreshes
Claude Code OAuth tokens during long-running agentic operations. This ensures
that tokens don't expire during extended streaming responses or tool processing.

Usage:
    async with token_refresh_heartbeat_context():
        # Long running agent operation
        await agent.run(...)
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger(__name__)

# Heartbeat interval in seconds - check token every 2 minutes
# This is frequent enough to catch expiring tokens before they cause issues
# but not so frequent as to spam the token endpoint
HEARTBEAT_INTERVAL_SECONDS = 120

# Minimum time between refresh attempts to avoid hammering the endpoint
MIN_REFRESH_INTERVAL_SECONDS = 60

# Global tracking of last refresh time to coordinate across heartbeats
_last_refresh_time: float = 0.0


class TokenRefreshHeartbeat:
    """Background task that periodically refreshes Claude Code OAuth tokens.

    This runs as an asyncio task during agent operations and checks if the
    token needs refreshing at regular intervals.
    """

    def __init__(
        self,
        interval: float = HEARTBEAT_INTERVAL_SECONDS,
        min_refresh_interval: float = MIN_REFRESH_INTERVAL_SECONDS,
    ):
        self._interval = interval
        self._min_refresh_interval = min_refresh_interval
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._refresh_count = 0

    async def start(self) -> None:
        """Start the heartbeat background task."""
        if self._task is not None:
            logger.debug("Heartbeat already running")
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._heartbeat_loop())
        logger.debug("Token refresh heartbeat started")

    async def stop(self) -> None:
        """Stop the heartbeat background task."""
        if self._task is None:
            return

        self._stop_event.set()
        self._task.cancel()

        try:
            await self._task
        except asyncio.CancelledError:
            pass

        self._task = None
        logger.debug(
            "Token refresh heartbeat stopped (refreshed %d times)",
            self._refresh_count,
        )

    async def _heartbeat_loop(self) -> None:
        """Main heartbeat loop that periodically checks token status."""
        global _last_refresh_time

        while not self._stop_event.is_set():
            try:
                # Wait for the interval or until stopped
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=self._interval
                    )
                    # If we got here, stop event was set
                    break
                except asyncio.TimeoutError:
                    # Normal timeout - time to check token
                    pass

                # Check if we should attempt refresh
                async with self._lock:
                    now = time.time()
                    if now - _last_refresh_time < self._min_refresh_interval:
                        logger.debug(
                            "Skipping refresh - last refresh was %.1f seconds ago",
                            now - _last_refresh_time,
                        )
                        continue

                    # Attempt the refresh
                    refreshed = await self._attempt_refresh()
                    if refreshed:
                        _last_refresh_time = now
                        self._refresh_count += 1

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Error in heartbeat loop: %s", exc)
                # Continue running - don't let errors kill the heartbeat
                await asyncio.sleep(5)  # Brief pause before retrying

    async def _attempt_refresh(self) -> bool:
        """Attempt to refresh the token if needed.

        Returns:
            True if a refresh was performed, False otherwise.
        """
        try:
            # Import here to avoid circular imports
            from .utils import (
                is_token_expired,
                load_stored_tokens,
                refresh_access_token,
            )

            tokens = await asyncio.to_thread(load_stored_tokens)
            if not tokens:
                logger.debug("No stored tokens found")
                return False

            if not is_token_expired(tokens):
                logger.debug("Token not yet expired, skipping refresh")
                return False

            # Token is expiring soon, refresh it
            logger.info("Heartbeat: Token expiring soon, refreshing proactively")
            refreshed_token = await asyncio.to_thread(refresh_access_token, force=False)

            if refreshed_token:
                logger.info("Heartbeat: Successfully refreshed token")
                return True
            else:
                logger.warning("Heartbeat: Token refresh returned None")
                return False

        except Exception as exc:
            logger.error("Heartbeat: Error during token refresh: %s", exc)
            return False

    @property
    def refresh_count(self) -> int:
        """Get the number of successful refreshes performed by this heartbeat."""
        return self._refresh_count

    @property
    def is_running(self) -> bool:
        """Check if the heartbeat is currently running."""
        return self._task is not None and not self._task.done()


# Global heartbeat instance for the current session
_current_heartbeat: Optional[TokenRefreshHeartbeat] = None


@asynccontextmanager
async def token_refresh_heartbeat_context(
    interval: float = HEARTBEAT_INTERVAL_SECONDS,
):
    """Context manager that runs token refresh heartbeat during its scope.

    Use this around long-running agent operations to ensure tokens stay fresh.

    Args:
        interval: Seconds between heartbeat checks. Default is 2 minutes.

    Example:
        async with token_refresh_heartbeat_context():
            result = await agent.run(prompt)
    """
    global _current_heartbeat

    heartbeat = TokenRefreshHeartbeat(interval=interval)

    try:
        await heartbeat.start()
        _current_heartbeat = heartbeat
        yield heartbeat
    finally:
        await heartbeat.stop()
        _current_heartbeat = None


def is_heartbeat_running() -> bool:
    """Check if a token refresh heartbeat is currently active."""
    return _current_heartbeat is not None and _current_heartbeat.is_running


def get_current_heartbeat() -> Optional[TokenRefreshHeartbeat]:
    """Get the currently running heartbeat instance, if any."""
    return _current_heartbeat


async def force_token_refresh() -> bool:
    """Force an immediate token refresh.

    This can be called from anywhere to trigger a token refresh,
    regardless of whether a heartbeat is running.

    Returns:
        True if refresh was successful, False otherwise.
    """
    global _last_refresh_time

    try:
        from .utils import refresh_access_token

        logger.info("Forcing token refresh")
        refreshed_token = refresh_access_token(force=True)

        if refreshed_token:
            _last_refresh_time = time.time()
            logger.info("Force refresh successful")
            return True
        else:
            logger.warning("Force refresh returned None")
            return False

    except Exception as exc:
        logger.error("Force refresh error: %s", exc)
        return False
