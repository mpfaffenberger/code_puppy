"""Shared rate limiter for Confluence API requests using SQLite.

This module provides a process-safe rate limiter that works across multiple
Code Puppy instances using SQLite for robust concurrent access.
"""

import sqlite3
import time
from pathlib import Path
from typing import Any

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_warning


class SharedRateLimiter:
    """A process-safe rate limiter using SQLite for storage.

    Uses a sliding window algorithm to track requests across all Code Puppy instances.
    SQLite provides ACID transactions and WAL mode for excellent concurrent access.

    Example:
        limiter = SharedRateLimiter(
            name="confluence",
            max_requests=20,
            time_window=60
        )

        # Will block/wait if rate limit is exceeded
        limiter.wait_if_needed()

        # Or check without waiting
        if limiter.can_proceed():
            make_request()
    """

    def __init__(
        self,
        name: str,
        max_requests: int = 20,
        time_window: int = 60,
        config_dir: Path | None = None,
    ):
        """Initialize the rate limiter.

        Args:
            name: Identifier for this rate limiter (e.g., "confluence")
            max_requests: Maximum number of requests allowed in the time window
            time_window: Time window in seconds (default: 60)
            config_dir: Directory to store rate limit data (default: ~/.code_puppy/)
        """
        self.name = name
        self.max_requests = max_requests
        self.time_window = time_window

        # Store rate limit data in config directory
        base_dir = config_dir or Path(CONFIG_DIR)
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = base_dir / f"rate_limit_{name}.db"

        # Initialize the database
        self._init_database()

    def _init_database(self) -> None:
        """Initialize the SQLite database with proper schema and settings."""
        with sqlite3.connect(self.db_path) as conn:
            # Enable WAL mode for better concurrent access
            conn.execute("PRAGMA journal_mode=WAL")

            # Create table if it doesn't exist
            conn.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for efficient timestamp queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON requests(timestamp)
            """)

            conn.commit()

    def _clean_old_requests(self, conn: sqlite3.Connection) -> None:
        """Remove request records older than the time window.

        Args:
            conn: SQLite connection (must be in a transaction)
        """
        cutoff_time = time.time() - self.time_window
        conn.execute("DELETE FROM requests WHERE timestamp < ?", (cutoff_time,))

    def can_proceed(self) -> bool:
        """Check if a request can be made without exceeding the rate limit.

        Returns:
            True if request can proceed, False if rate limit would be exceeded.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean old requests first
                self._clean_old_requests(conn)

                # Count current requests in the window
                result = conn.execute(
                    "SELECT COUNT(*) FROM requests WHERE timestamp > ?",
                    (time.time() - self.time_window,),
                ).fetchone()

                current_count = result[0] if result else 0
                return current_count < self.max_requests

        except Exception:
            # If database fails, allow the request (fail open)
            return True

    def record_request(self) -> None:
        """Record that a request was made.

        This should be called AFTER successfully making a request.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean old requests and add new one in a single transaction
                self._clean_old_requests(conn)

                conn.execute(
                    "INSERT INTO requests (timestamp) VALUES (?)", (time.time(),)
                )

                conn.commit()

        except Exception:
            # If database fails, silently continue (fail open)
            pass

    def wait_if_needed(self, max_wait: float = 60.0) -> None:
        """Wait until a request can be made without exceeding the rate limit.

        Args:
            max_wait: Maximum time to wait in seconds (default: 60)

        Raises:
            TimeoutError: If max_wait is exceeded.
        """
        start_time = time.time()
        warning_emitted = False

        while not self.can_proceed():
            elapsed = time.time() - start_time
            if elapsed >= max_wait:
                raise TimeoutError(
                    f"Rate limit wait timeout after {max_wait}s. "
                    f"Limit: {self.max_requests} requests per {self.time_window}s"
                )

            # Calculate wait time based on oldest request
            try:
                with sqlite3.connect(self.db_path) as conn:
                    result = conn.execute(
                        "SELECT MIN(timestamp) FROM requests WHERE timestamp > ?",
                        (time.time() - self.time_window,),
                    ).fetchone()

                    if result and result[0]:
                        # Wait until the oldest request expires
                        oldest_timestamp = result[0]
                        wait_until = oldest_timestamp + self.time_window
                        wait_time = max(0.1, wait_until - time.time())
                    else:
                        wait_time = 0.1

            except Exception:
                wait_time = 0.1

            # Emit warning on first wait
            if not warning_emitted:
                emit_warning(
                    f"Rate limit reached ({self.max_requests} requests/{self.time_window}s). "
                    f"Waiting {wait_time:.1f}s..."
                )
                warning_emitted = True

            # Sleep and check again
            time.sleep(min(wait_time, 1.0))

    def get_current_usage(self) -> dict[str, Any]:
        """Get current rate limit usage statistics.

        Returns:
            Dictionary with usage information.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Clean old requests first
                self._clean_old_requests(conn)

                # Get current count
                result = conn.execute(
                    "SELECT COUNT(*) FROM requests WHERE timestamp > ?",
                    (time.time() - self.time_window,),
                ).fetchone()

                current_count = result[0] if result else 0

                # Get oldest request time in window
                oldest_result = conn.execute(
                    "SELECT MIN(timestamp) FROM requests WHERE timestamp > ?",
                    (time.time() - self.time_window,),
                ).fetchone()

                oldest_timestamp = (
                    oldest_result[0] if oldest_result and oldest_result[0] else None
                )

                return {
                    "current_requests": current_count,
                    "max_requests": self.max_requests,
                    "time_window": self.time_window,
                    "requests_remaining": max(0, self.max_requests - current_count),
                    "oldest_request_age": time.time() - oldest_timestamp
                    if oldest_timestamp
                    else None,
                    "can_proceed": current_count < self.max_requests,
                }

        except Exception:
            return {
                "current_requests": 0,
                "max_requests": self.max_requests,
                "time_window": self.time_window,
                "requests_remaining": self.max_requests,
                "oldest_request_age": None,
                "can_proceed": True,
                "error": "Database unavailable",
            }
