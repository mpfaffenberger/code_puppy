"""
MCP Error Isolation System

This module provides error isolation for MCP server calls to prevent
server errors from crashing the application. It implements quarantine
logic with exponential backoff for failed servers.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class ErrorStats:
    """Statistics for MCP server errors and quarantine status."""

    total_errors: int = 0
    consecutive_errors: int = 0
    last_error: Optional[datetime] = None
    error_types: Dict[str, int] = field(default_factory=dict)
    quarantine_count: int = 0
    quarantine_until: Optional[datetime] = None


class ErrorCategory(Enum):
    """Categories of errors that can be isolated."""

    NETWORK = "network"
    PROTOCOL = "protocol"
    SERVER = "server"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


class MCPErrorIsolator:
    """
    Isolates MCP server errors to prevent application crashes.

    Features:
    - Quarantine servers after consecutive failures
    - Exponential backoff for quarantine duration
    - Error categorization and tracking
    - Automatic recovery after successful calls
    """

    def __init__(self, quarantine_threshold: int = 5, max_quarantine_minutes: int = 30):
        """
        Initialize the error isolator.

        Args:
            quarantine_threshold: Number of consecutive errors to trigger quarantine
            max_quarantine_minutes: Maximum quarantine duration in minutes
        """
        self.quarantine_threshold = quarantine_threshold
        self.max_quarantine_duration = timedelta(minutes=max_quarantine_minutes)
        self.server_stats: Dict[str, ErrorStats] = {}
        self._lock = asyncio.Lock()

        logger.info(
            f"MCPErrorIsolator initialized with threshold={quarantine_threshold}, "
            f"max_quarantine={max_quarantine_minutes}min"
        )

    async def isolated_call(
        self, server_id: str, func: Callable, *args, **kwargs
    ) -> Any:
        """
        Execute a function call with error isolation.

        Args:
            server_id: ID of the MCP server making the call
            func: Function to execute
            *args: Arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            Exception: If the server is quarantined or the call fails
        """
        async with self._lock:
            # Check if server is quarantined
            if self.is_quarantined(server_id):
                quarantine_until = self.server_stats[server_id].quarantine_until
                raise QuarantinedServerError(
                    f"Server {server_id} is quarantined until {quarantine_until}"
                )

        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            # Record success
            async with self._lock:
                await self._record_success(server_id)

            return result

        except Exception as error:
            # Record and categorize the error
            async with self._lock:
                await self._record_error(server_id, error)

            # Re-raise the error
            raise

    async def quarantine_server(self, server_id: str, duration: int) -> None:
        """
        Manually quarantine a server for a specific duration.

        Args:
            server_id: ID of the server to quarantine
            duration: Quarantine duration in seconds
        """
        async with self._lock:
            stats = self._get_or_create_stats(server_id)
            stats.quarantine_until = datetime.now() + timedelta(seconds=duration)
            stats.quarantine_count += 1

            logger.warning(
                f"Server {server_id} quarantined for {duration}s "
                f"(count: {stats.quarantine_count})"
            )

    def is_quarantined(self, server_id: str) -> bool:
        """
        Check if a server is currently quarantined.

        Args:
            server_id: ID of the server to check

        Returns:
            True if the server is quarantined, False otherwise
        """
        if server_id not in self.server_stats:
            return False

        stats = self.server_stats[server_id]
        if stats.quarantine_until is None:
            return False

        # Check if quarantine has expired
        if datetime.now() >= stats.quarantine_until:
            stats.quarantine_until = None
            return False

        return True

    async def release_quarantine(self, server_id: str) -> None:
        """
        Manually release a server from quarantine.

        Args:
            server_id: ID of the server to release
        """
        async with self._lock:
            if server_id in self.server_stats:
                self.server_stats[server_id].quarantine_until = None
                logger.info(f"Server {server_id} released from quarantine")

    def get_error_stats(self, server_id: str) -> ErrorStats:
        """
        Get error statistics for a server.

        Args:
            server_id: ID of the server

        Returns:
            ErrorStats object with current statistics
        """
        if server_id not in self.server_stats:
            return ErrorStats()

        return self.server_stats[server_id]

    def should_quarantine(self, server_id: str) -> bool:
        """
        Check if a server should be quarantined based on error count.

        Args:
            server_id: ID of the server to check

        Returns:
            True if the server should be quarantined
        """
        if server_id not in self.server_stats:
            return False

        stats = self.server_stats[server_id]
        return stats.consecutive_errors >= self.quarantine_threshold

    def _get_or_create_stats(self, server_id: str) -> ErrorStats:
        """Get or create error stats for a server."""
        if server_id not in self.server_stats:
            self.server_stats[server_id] = ErrorStats()
        return self.server_stats[server_id]

    async def _record_success(self, server_id: str) -> None:
        """Record a successful call and reset consecutive error count."""
        stats = self._get_or_create_stats(server_id)
        stats.consecutive_errors = 0

        logger.debug(
            f"Success recorded for server {server_id}, consecutive errors reset"
        )

    async def _record_error(self, server_id: str, error: Exception) -> None:
        """Record an error and potentially quarantine the server."""
        stats = self._get_or_create_stats(server_id)

        # Update error statistics
        stats.total_errors += 1
        stats.consecutive_errors += 1
        stats.last_error = datetime.now()

        # Categorize the error
        error_category = self._categorize_error(error)
        error_type = error_category.value
        stats.error_types[error_type] = stats.error_types.get(error_type, 0) + 1

        logger.warning(
            f"Error recorded for server {server_id}: {error_type} - {str(error)} "
            f"(consecutive: {stats.consecutive_errors})"
        )

        # Check if quarantine is needed
        if self.should_quarantine(server_id):
            quarantine_duration = self._calculate_quarantine_duration(
                stats.quarantine_count
            )
            stats.quarantine_until = datetime.now() + timedelta(
                seconds=quarantine_duration
            )
            stats.quarantine_count += 1

            logger.error(
                f"Server {server_id} quarantined for {quarantine_duration}s "
                f"after {stats.consecutive_errors} consecutive errors "
                f"(quarantine count: {stats.quarantine_count})"
            )

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """
        Categorize an error based on its type and properties.

        Args:
            error: The exception to categorize

        Returns:
            ErrorCategory enum value
        """
        error_type = type(error).__name__.lower()
        error_message = str(error).lower()

        # Network errors
        if any(
            keyword in error_type
            for keyword in ["connection", "timeout", "network", "socket", "dns", "ssl"]
        ):
            return ErrorCategory.NETWORK

        if any(
            keyword in error_message
            for keyword in [
                "connection",
                "timeout",
                "network",
                "unreachable",
                "refused",
            ]
        ):
            return ErrorCategory.NETWORK

        # Protocol errors
        if any(
            keyword in error_type
            for keyword in [
                "json",
                "decode",
                "parse",
                "schema",
                "validation",
                "protocol",
            ]
        ):
            return ErrorCategory.PROTOCOL

        if any(
            keyword in error_message
            for keyword in ["json", "decode", "parse", "invalid", "malformed", "schema"]
        ):
            return ErrorCategory.PROTOCOL

        # Authentication errors
        if any(
            keyword in error_type
            for keyword in ["auth", "permission", "unauthorized", "forbidden"]
        ):
            return ErrorCategory.AUTHENTICATION

        if any(
            keyword in error_message
            for keyword in [
                "401",
                "403",
                "unauthorized",
                "forbidden",
                "authentication",
                "permission",
            ]
        ):
            return ErrorCategory.AUTHENTICATION

        # Rate limit errors
        if any(keyword in error_type for keyword in ["rate", "limit", "throttle"]):
            return ErrorCategory.RATE_LIMIT

        if any(
            keyword in error_message
            for keyword in ["429", "rate limit", "too many requests", "throttle"]
        ):
            return ErrorCategory.RATE_LIMIT

        # Server errors (5xx responses)
        if any(
            keyword in error_message
            for keyword in [
                "500",
                "501",
                "502",
                "503",
                "504",
                "505",
                "internal server error",
                "bad gateway",
                "service unavailable",
                "gateway timeout",
            ]
        ):
            return ErrorCategory.SERVER

        if any(keyword in error_type for keyword in ["server", "internal"]):
            return ErrorCategory.SERVER

        # Default to unknown
        return ErrorCategory.UNKNOWN

    def _calculate_quarantine_duration(self, quarantine_count: int) -> int:
        """
        Calculate quarantine duration using exponential backoff.

        Args:
            quarantine_count: Number of times this server has been quarantined

        Returns:
            Quarantine duration in seconds
        """
        # Base duration: 30 seconds
        base_duration = 30

        # Exponential backoff: 30s, 60s, 120s, 240s, etc.
        duration = base_duration * (2**quarantine_count)

        # Cap at maximum duration (convert to seconds)
        max_seconds = int(self.max_quarantine_duration.total_seconds())
        duration = min(duration, max_seconds)

        logger.debug(
            f"Calculated quarantine duration: {duration}s "
            f"(count: {quarantine_count}, max: {max_seconds}s)"
        )

        return duration


class QuarantinedServerError(Exception):
    """Raised when attempting to call a quarantined server."""

    pass


# Global isolator instance
_isolator_instance: Optional[MCPErrorIsolator] = None


def get_error_isolator() -> MCPErrorIsolator:
    """
    Get the global MCPErrorIsolator instance.

    Returns:
        MCPErrorIsolator instance
    """
    global _isolator_instance
    if _isolator_instance is None:
        _isolator_instance = MCPErrorIsolator()
    return _isolator_instance
