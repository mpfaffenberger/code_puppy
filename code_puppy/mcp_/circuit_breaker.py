"""
Circuit breaker implementation for MCP servers to prevent cascading failures.

This module implements the circuit breaker pattern to protect against cascading
failures when MCP servers become unhealthy. The circuit breaker has three states:
- CLOSED: Normal operation, calls pass through
- OPEN: Calls are blocked and fail fast
- HALF_OPEN: Limited calls allowed to test recovery
"""

import asyncio
import logging
import threading
import time
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking calls
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitOpenError(Exception):
    """Raised when circuit breaker is in OPEN state."""

    pass


class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures in MCP servers.

    The circuit breaker monitors the success/failure rate of operations and
    transitions between states to protect the system from unhealthy dependencies.

    States:
    - CLOSED: Normal operation, all calls allowed
    - OPEN: Circuit is open, all calls fail fast with CircuitOpenError
    - HALF_OPEN: Testing recovery, limited calls allowed

    State Transitions:
    - CLOSED → OPEN: After failure_threshold consecutive failures
    - OPEN → HALF_OPEN: After timeout seconds
    - HALF_OPEN → CLOSED: After success_threshold consecutive successes
    - HALF_OPEN → OPEN: After any failure
    """

    def __init__(
        self, failure_threshold: int = 5, success_threshold: int = 2, timeout: int = 60
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
            success_threshold: Number of consecutive successes needed to close circuit from half-open
            timeout: Seconds to wait before transitioning from OPEN to HALF_OPEN
        """
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
        # NOTE: We use threading.Lock (not asyncio.Lock) because this lock is shared
        # between synchronous callers (record_success/record_failure) and async callers
        # (_on_success/_on_failure called from call()). This is safe because the critical
        # sections are very short and CPU-bound only (counter increments, state transitions)
        # — no I/O or awaits occur while the lock is held, so event loop blocking is negligible.
        self._sync_lock = threading.Lock()
        self._half_open_in_flight = False

        logger.info(
            f"Circuit breaker initialized: failure_threshold={failure_threshold}, "
            f"success_threshold={success_threshold}, timeout={timeout}s"
        )

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function

        Returns:
            Result of the function call

        Raises:
            CircuitOpenError: If circuit is in OPEN state
            Exception: Any exception raised by the wrapped function
        """
        with self._sync_lock:
            current_state = self._get_current_state()

            if current_state == CircuitState.OPEN:
                logger.warning("Circuit breaker is OPEN, failing fast")
                raise CircuitOpenError("Circuit breaker is open")

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_in_flight:
                    logger.warning(
                        "Circuit breaker HALF_OPEN with call already in flight, failing fast"
                    )
                    raise CircuitOpenError(
                        "Circuit breaker half-open test call already in flight"
                    )
                # In half-open state, we're testing recovery
                logger.info("Circuit breaker is HALF_OPEN, allowing test call")
                self._half_open_in_flight = True

            checked_state = current_state

        # Execute the function outside the lock to avoid blocking other calls
        try:
            result = (
                await func(*args, **kwargs)
                if asyncio.iscoroutinefunction(func)
                else func(*args, **kwargs)
            )
            await self._on_success(checked_state=checked_state)
            return result
        except Exception:
            await self._on_failure(checked_state=checked_state)
            raise

    def record_success(self) -> None:
        """Record a successful operation (synchronous)."""
        with self._sync_lock:
            self._on_success_sync()

    def record_failure(self) -> None:
        """Record a failed operation (synchronous)."""
        with self._sync_lock:
            self._on_failure_sync()

    def get_state(self) -> CircuitState:
        """Get current circuit breaker state."""
        with self._sync_lock:
            return self._get_current_state()

    def is_open(self) -> bool:
        """Check if circuit breaker is in OPEN state."""
        with self._sync_lock:
            return self._get_current_state() == CircuitState.OPEN

    def is_half_open(self) -> bool:
        """Check if circuit breaker is in HALF_OPEN state."""
        with self._sync_lock:
            return self._get_current_state() == CircuitState.HALF_OPEN

    def is_closed(self) -> bool:
        """Check if circuit breaker is in CLOSED state."""
        with self._sync_lock:
            return self._get_current_state() == CircuitState.CLOSED

    def reset(self) -> None:
        """Reset circuit breaker to CLOSED state and clear counters."""
        with self._sync_lock:
            logger.info("Resetting circuit breaker to CLOSED state")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_in_flight = False

    def force_open(self) -> None:
        """Force circuit breaker to OPEN state."""
        with self._sync_lock:
            logger.warning("Forcing circuit breaker to OPEN state")
            self._state = CircuitState.OPEN
            self._last_failure_time = time.time()
            self._half_open_in_flight = False

    def force_close(self) -> None:
        """Force circuit breaker to CLOSED state and reset counters."""
        with self._sync_lock:
            logger.info("Forcing circuit breaker to CLOSED state")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._half_open_in_flight = False

    def _get_current_state(self) -> CircuitState:
        """
        Get the current state, handling automatic transitions.

        This method handles the automatic transition from OPEN to HALF_OPEN
        after the timeout period has elapsed.
        """
        if self._state == CircuitState.OPEN and self._should_attempt_reset():
            logger.info("Timeout reached, transitioning from OPEN to HALF_OPEN")
            self._state = CircuitState.HALF_OPEN
            self._success_count = 0  # Reset success counter for half-open testing

        return self._state

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset from OPEN to HALF_OPEN."""
        if self._last_failure_time is None:
            return False

        return time.time() - self._last_failure_time >= self.timeout

    def _on_success_sync(self, checked_state: CircuitState | None = None) -> None:
        """Handle successful operation (synchronous, no lock)."""
        current_state = (
            checked_state if checked_state is not None else self._get_current_state()
        )

        if current_state == CircuitState.CLOSED:
            if self._failure_count > 0:
                logger.debug("Resetting failure count after success")
                self._failure_count = 0

        elif current_state == CircuitState.HALF_OPEN:
            self._success_count += 1
            logger.debug(
                f"Success in HALF_OPEN state: {self._success_count}/{self.success_threshold}"
            )

            self._half_open_in_flight = False

            if self._success_count >= self.success_threshold:
                logger.info(
                    "Success threshold reached, transitioning from HALF_OPEN to CLOSED"
                )
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                self._last_failure_time = None
                self._half_open_in_flight = False

    def _on_failure_sync(self, checked_state: CircuitState | None = None) -> None:
        """Handle failed operation (synchronous, no lock)."""
        current_state = (
            checked_state if checked_state is not None else self._get_current_state()
        )

        if current_state == CircuitState.CLOSED:
            self._failure_count += 1
            logger.debug(
                f"Failure in CLOSED state: {self._failure_count}/{self.failure_threshold}"
            )

            if self._failure_count >= self.failure_threshold:
                logger.warning(
                    "Failure threshold reached, transitioning from CLOSED to OPEN"
                )
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()

        elif current_state == CircuitState.HALF_OPEN:
            logger.warning("Failure in HALF_OPEN state, transitioning back to OPEN")
            self._state = CircuitState.OPEN
            self._success_count = 0
            self._last_failure_time = time.time()
            self._half_open_in_flight = False

    async def _on_success(self, checked_state: CircuitState | None = None) -> None:
        """Handle successful operation.

        This method is async to match the await call-site in call(), but the
        underlying work is purely synchronous. We acquire threading.Lock (not
        asyncio.Lock) because the same state is accessed from sync contexts
        (record_success). The critical section is short and CPU-bound, so
        holding a threading.Lock in an async method does not meaningfully
        block the event loop.
        """
        with self._sync_lock:
            self._on_success_sync(checked_state=checked_state)

    async def _on_failure(self, checked_state: CircuitState | None = None) -> None:
        """Handle failed operation.

        See _on_success docstring for rationale on threading.Lock usage in
        an async method.
        """
        with self._sync_lock:
            self._on_failure_sync(checked_state=checked_state)
