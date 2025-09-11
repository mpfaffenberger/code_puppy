"""
Retry manager for MCP server communication with various backoff strategies.

This module provides retry logic for handling transient failures in MCP server
communication with intelligent backoff strategies to prevent overwhelming failed servers.
"""

import asyncio
import logging
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RetryStats:
    """Statistics for retry operations per server."""

    total_retries: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    average_attempts: float = 0.0
    last_retry: Optional[datetime] = None

    def calculate_average(self, new_attempts: int) -> None:
        """Update the average attempts calculation."""
        if self.total_retries == 0:
            self.average_attempts = float(new_attempts)
        else:
            # Calculate new average: (old_average * old_count + new_value) / new_count
            total_attempts = (self.average_attempts * self.total_retries) + new_attempts
            self.average_attempts = total_attempts / (self.total_retries + 1)


class RetryManager:
    """
    Manages retry logic for MCP server operations with various backoff strategies.

    Supports different backoff strategies and intelligent retry decisions based on
    error types. Tracks retry statistics per server for monitoring.
    """

    def __init__(self):
        """Initialize the retry manager."""
        self._stats: Dict[str, RetryStats] = defaultdict(RetryStats)
        self._lock = asyncio.Lock()

    async def retry_with_backoff(
        self,
        func: Callable,
        max_attempts: int = 3,
        strategy: str = "exponential",
        server_id: str = "unknown",
    ) -> Any:
        """
        Execute a function with retry logic and backoff strategy.

        Args:
            func: The async function to execute
            max_attempts: Maximum number of retry attempts
            strategy: Backoff strategy ('fixed', 'linear', 'exponential', 'exponential_jitter')
            server_id: ID of the server for tracking stats

        Returns:
            The result of the function call

        Raises:
            The last exception encountered if all retries fail
        """
        last_exception = None

        for attempt in range(max_attempts):
            try:
                result = await func()

                # Record successful retry if this wasn't the first attempt
                if attempt > 0:
                    await self.record_retry(server_id, attempt + 1, success=True)

                return result

            except Exception as e:
                last_exception = e

                # Check if this error is retryable
                if not self.should_retry(e):
                    logger.info(
                        f"Non-retryable error for server {server_id}: {type(e).__name__}: {e}"
                    )
                    await self.record_retry(server_id, attempt + 1, success=False)
                    raise e

                # If this is the last attempt, don't wait
                if attempt == max_attempts - 1:
                    await self.record_retry(server_id, max_attempts, success=False)
                    break

                # Calculate backoff delay
                delay = self.calculate_backoff(attempt + 1, strategy)

                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed for server {server_id}: "
                    f"{type(e).__name__}: {e}. Retrying in {delay:.2f}s"
                )

                # Wait before retrying
                await asyncio.sleep(delay)

        # All attempts failed
        logger.error(
            f"All {max_attempts} attempts failed for server {server_id}. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )
        raise last_exception

    def calculate_backoff(self, attempt: int, strategy: str) -> float:
        """
        Calculate backoff delay based on attempt number and strategy.

        Args:
            attempt: The current attempt number (1-based)
            strategy: The backoff strategy to use

        Returns:
            Delay in seconds
        """
        if strategy == "fixed":
            return 1.0

        elif strategy == "linear":
            return float(attempt)

        elif strategy == "exponential":
            return 2.0 ** (attempt - 1)

        elif strategy == "exponential_jitter":
            base_delay = 2.0 ** (attempt - 1)
            jitter = random.uniform(-0.25, 0.25)  # ±25% jitter
            return max(0.1, base_delay * (1 + jitter))

        else:
            logger.warning(f"Unknown backoff strategy: {strategy}, using exponential")
            return 2.0 ** (attempt - 1)

    def should_retry(self, error: Exception) -> bool:
        """
        Determine if an error is retryable.

        Args:
            error: The exception to evaluate

        Returns:
            True if the error is retryable, False otherwise
        """
        # Network timeouts and connection errors are retryable
        if isinstance(error, (asyncio.TimeoutError, ConnectionError, OSError)):
            return True

        # HTTP errors
        if isinstance(error, httpx.HTTPError):
            if isinstance(error, httpx.TimeoutException):
                return True
            elif isinstance(error, httpx.ConnectError):
                return True
            elif isinstance(error, httpx.ReadError):
                return True
            elif hasattr(error, "response") and error.response is not None:
                status_code = error.response.status_code
                # 5xx server errors are retryable
                if 500 <= status_code < 600:
                    return True
                # Rate limit errors are retryable (with longer backoff)
                if status_code == 429:
                    return True
                # 4xx client errors are generally not retryable
                # except for specific cases like 408 (timeout)
                if status_code == 408:
                    return True
                return False

        # JSON decode errors might be transient
        if isinstance(error, ValueError) and "json" in str(error).lower():
            return True

        # Authentication and authorization errors are not retryable
        error_str = str(error).lower()
        if any(
            term in error_str
            for term in ["unauthorized", "forbidden", "authentication", "permission"]
        ):
            return False

        # Schema validation errors are not retryable
        if "schema" in error_str or "validation" in error_str:
            return False

        # By default, consider other errors as potentially retryable
        # This is conservative but helps handle unknown transient issues
        return True

    async def record_retry(self, server_id: str, attempts: int, success: bool) -> None:
        """
        Record retry statistics for a server.

        Args:
            server_id: ID of the server
            attempts: Number of attempts made
            success: Whether the retry was successful
        """
        async with self._lock:
            stats = self._stats[server_id]
            stats.last_retry = datetime.now()

            if success:
                stats.successful_retries += 1
            else:
                stats.failed_retries += 1

            stats.calculate_average(attempts)
            stats.total_retries += 1

    async def get_retry_stats(self, server_id: str) -> RetryStats:
        """
        Get retry statistics for a server.

        Args:
            server_id: ID of the server

        Returns:
            RetryStats object with current statistics
        """
        async with self._lock:
            # Return a copy to avoid external modification
            stats = self._stats[server_id]
            return RetryStats(
                total_retries=stats.total_retries,
                successful_retries=stats.successful_retries,
                failed_retries=stats.failed_retries,
                average_attempts=stats.average_attempts,
                last_retry=stats.last_retry,
            )

    async def get_all_stats(self) -> Dict[str, RetryStats]:
        """
        Get retry statistics for all servers.

        Returns:
            Dictionary mapping server IDs to their retry statistics
        """
        async with self._lock:
            return {
                server_id: RetryStats(
                    total_retries=stats.total_retries,
                    successful_retries=stats.successful_retries,
                    failed_retries=stats.failed_retries,
                    average_attempts=stats.average_attempts,
                    last_retry=stats.last_retry,
                )
                for server_id, stats in self._stats.items()
            }

    async def clear_stats(self, server_id: str) -> None:
        """
        Clear retry statistics for a server.

        Args:
            server_id: ID of the server
        """
        async with self._lock:
            if server_id in self._stats:
                del self._stats[server_id]

    async def clear_all_stats(self) -> None:
        """Clear retry statistics for all servers."""
        async with self._lock:
            self._stats.clear()


# Global retry manager instance
_retry_manager_instance: Optional[RetryManager] = None


def get_retry_manager() -> RetryManager:
    """
    Get the global retry manager instance (singleton pattern).

    Returns:
        The global RetryManager instance
    """
    global _retry_manager_instance
    if _retry_manager_instance is None:
        _retry_manager_instance = RetryManager()
    return _retry_manager_instance


# Convenience function for common retry patterns
async def retry_mcp_call(
    func: Callable,
    server_id: str,
    max_attempts: int = 3,
    strategy: str = "exponential_jitter",
) -> Any:
    """
    Convenience function for retrying MCP calls with sensible defaults.

    Args:
        func: The async function to execute
        server_id: ID of the server for tracking
        max_attempts: Maximum retry attempts
        strategy: Backoff strategy

    Returns:
        The result of the function call
    """
    retry_manager = get_retry_manager()
    return await retry_manager.retry_with_backoff(
        func=func, max_attempts=max_attempts, strategy=strategy, server_id=server_id
    )
