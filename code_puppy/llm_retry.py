"""
LLM API retry engine with exponential backoff, jitter, and gateway awareness.

Wraps pydantic_ai agent.run() calls with retry logic for transient API
failures (429, 529, 5xx, network errors).

Usage:
    from code_puppy.llm_retry import llm_run_with_retry, LLMRetryConfig

    result = await llm_run_with_retry(
        lambda: pydantic_agent.run(prompt, message_history=history, ...),
        config=LLMRetryConfig(),
    )
"""

import asyncio
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_MAX_RETRIES = 10
_BASE_DELAY_MS = 500
_MAX_DELAY_MS = 32_000
_MAX_CONSECUTIVE_OVERLOADS = 3


# ---------------------------------------------------------------------------
# Config & errors
# ---------------------------------------------------------------------------
def _resolve_max_retries() -> int:
    env = os.environ.get("PUPPY_MAX_LLM_RETRIES")
    if env is not None:
        try:
            value = int(env)
            if value < 0:
                logger.warning(
                    "PUPPY_MAX_LLM_RETRIES=%r must be >= 0, using default %d",
                    env,
                    _DEFAULT_MAX_RETRIES,
                )
                return _DEFAULT_MAX_RETRIES
            return value
        except ValueError:
            logger.warning(
                "PUPPY_MAX_LLM_RETRIES=%r is not a valid integer, using default %d",
                env,
                _DEFAULT_MAX_RETRIES,
            )
    return _DEFAULT_MAX_RETRIES


@dataclass
class LLMRetryConfig:
    """Configuration for the LLM retry engine."""

    max_retries: int = field(default_factory=_resolve_max_retries)
    cancel_event: Optional[asyncio.Event] = None


class RetryExhaustedError(Exception):
    """All retry attempts failed."""

    def __init__(self, message: str, original_error: Exception):
        super().__init__(message)
        self.original_error = original_error


# ---------------------------------------------------------------------------
# Error introspection helpers
# ---------------------------------------------------------------------------
def _get_status_code(error: Exception) -> Optional[int]:
    """Extract HTTP status code from various error types."""
    # anthropic SDK / pydantic_ai errors
    if hasattr(error, "status_code"):
        return error.status_code
    # Some errors wrap an HTTP response
    resp = getattr(error, "response", None)
    if resp is not None and hasattr(resp, "status_code"):
        return resp.status_code
    return None


def _get_retry_after(error: Exception) -> Optional[float]:
    """Extract Retry-After header value in seconds, or None."""
    # Try direct headers attribute (anthropic SDK errors)
    headers = getattr(error, "headers", None)
    # Fall back to response headers
    if headers is None:
        resp = getattr(error, "response", None)
        headers = getattr(resp, "headers", None)
    if not headers:
        return None

    val = None
    if hasattr(headers, "get"):
        val = headers.get("retry-after") or headers.get("Retry-After")
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _get_x_should_retry(error: Exception) -> Optional[bool]:
    """Check x-should-retry header. Returns True, False, or None if absent."""
    headers = getattr(error, "headers", None)
    if headers is None:
        resp = getattr(error, "response", None)
        headers = getattr(resp, "headers", None)
    if not headers or not hasattr(headers, "get"):
        return None
    val = headers.get("x-should-retry")
    if val == "true":
        return True
    if val == "false":
        return False
    return None


def _is_overloaded(error: Exception) -> bool:
    """True for 529 or body-level overloaded_error."""
    if _get_status_code(error) == 529:
        return True
    return "overloaded_error" in str(error).lower()


# ---------------------------------------------------------------------------
# Retryability decision
# ---------------------------------------------------------------------------
def is_retryable(error: Exception) -> bool:
    """Determine whether an LLM API error should be retried.

    Returns:
        True if the error is transient and the request should be retried.
    """
    # Never retry cancellation
    if isinstance(error, (asyncio.CancelledError, KeyboardInterrupt)):
        return False

    # x-should-retry header is authoritative when present
    hint = _get_x_should_retry(error)
    if hint is False:
        return False
    if hint is True:
        return True

    # Overloaded errors (529 or body-level)
    if _is_overloaded(error):
        return True

    # Network-level errors are always retryable — check the error itself and
    # walk the full __cause__/__context__ chain.  The real chain in production is:
    #   pydantic_ai ModelAPIError → SDK APIConnectionError → httpx ConnectError → OSError
    # None of the intermediate types inherit from Python's ConnectionError, so we
    # must walk all the way down to find the stdlib error at the root.
    _network_types = (asyncio.TimeoutError, ConnectionError, OSError)
    if isinstance(error, _network_types):
        return True
    exc: BaseException | None = error
    for _ in range(10):  # bounded walk to prevent infinite loops
        exc = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        if exc is None:
            break
        if isinstance(exc, _network_types):
            return True

    # Streaming errors from pydantic_ai — only retry the specific transient
    # message that pydantic_ai raises when a streamed response terminates early.
    error_msg = str(error).lower()
    if "streamed response ended" in error_msg:
        return True
    # Schema/validation errors are always fatal — never retry
    if "schema" in error_msg or "validation" in error_msg:
        return False

    status = _get_status_code(error)
    if status is None:
        # No status code and not a recognized transient pattern — don't retry
        # blindly.  Only specifically-identified patterns above are retried.
        return False

    if status == 408:
        return True  # Request Timeout
    if status == 409:
        return True  # Conflict
    if status == 429:
        return True  # Rate Limit
    if status == 401:
        return True  # Unauthorized (token may need refresh)
    if status >= 500:
        return True  # Server errors

    # 400 (non-overflow), 402, 403, 404, 422, etc. — fatal
    return False


# ---------------------------------------------------------------------------
# Backoff formula
# ---------------------------------------------------------------------------
def _compute_backoff(attempt: int, retry_after_secs: Optional[float] = None) -> float:
    """Compute retry delay in seconds.

    Uses exponential backoff with up to 25% jitter.
    Server-provided Retry-After header takes absolute priority.

    Args:
        attempt: 1-based attempt number.
        retry_after_secs: Value from Retry-After header, if present.

    Returns:
        Delay in seconds.
    """
    if retry_after_secs is not None and retry_after_secs > 0:
        return retry_after_secs

    base = min(_BASE_DELAY_MS * (2 ** (attempt - 1)), _MAX_DELAY_MS) / 1000.0
    jitter = random.random() * 0.25 * base
    return base + jitter


# ---------------------------------------------------------------------------
# Abort-aware sleep
# ---------------------------------------------------------------------------
async def _cancellable_sleep(
    seconds: float, cancel_event: Optional[asyncio.Event]
) -> None:
    """Sleep that aborts immediately if cancel_event is set."""
    if cancel_event is None:
        await asyncio.sleep(seconds)
        return

    if cancel_event.is_set():
        raise asyncio.CancelledError("LLM retry sleep interrupted by cancel event")

    try:
        await asyncio.wait_for(cancel_event.wait(), timeout=seconds)
        # If we get here, the event was set during the wait
        raise asyncio.CancelledError("LLM retry sleep interrupted by cancel event")
    except asyncio.TimeoutError:
        pass  # Normal: full duration elapsed without cancellation


# ---------------------------------------------------------------------------
# Main retry loop
# ---------------------------------------------------------------------------
async def llm_run_with_retry(
    coro_factory: Callable[[], Any],
    config: Optional[LLMRetryConfig] = None,
) -> Any:
    """Execute an LLM API call with retry logic.

    Wraps a coroutine factory (typically ``lambda: agent.run(...)``) with
    production-grade retry handling for transient API failures.

    Args:
        coro_factory: Callable that returns a fresh coroutine for each attempt.
            Must create a new coroutine on every call (use a lambda).
        config: Retry configuration. Uses defaults if None.

    Returns:
        The successful result of coro_factory().

    Raises:
        RetryExhaustedError: All retry attempts failed.
        asyncio.CancelledError: If cancelled during retry sleep.
    """
    # Lazy import to avoid circular dependency
    from code_puppy.callbacks import _trigger_callbacks

    if config is None:
        config = LLMRetryConfig()

    max_retries = config.max_retries
    overload_hits = 0
    last_error: Optional[Exception] = None

    # 1 initial attempt + max_retries retries = max_retries + 1 total attempts
    for attempt in range(1, max_retries + 2):
        try:
            result = await coro_factory()

            # If we recovered after retries, fire the callback
            if attempt > 1:
                await _trigger_callbacks(
                    "api_retry_end",
                    total_attempts=attempt,
                )

            return result

        except (asyncio.CancelledError, KeyboardInterrupt):
            raise  # Never swallow cancellation

        except Exception as error:
            last_error = error
            status = _get_status_code(error)

            logger.warning(
                "LLM API error on attempt %d/%d: %s: %s (status=%s)",
                attempt,
                max_retries + 1,
                type(error).__name__,
                error,
                status,
            )

            # Track consecutive overloads — short-circuit early when the
            # model is clearly overloaded rather than burning all retries
            if _is_overloaded(error):
                overload_hits += 1
                if overload_hits >= _MAX_CONSECUTIVE_OVERLOADS:
                    raise RetryExhaustedError(
                        f"API returned {_MAX_CONSECUTIVE_OVERLOADS} consecutive "
                        f"overloaded errors",
                        error,
                    ) from error
            else:
                overload_hits = 0

            # Retries exhausted
            if attempt > max_retries:
                raise RetryExhaustedError(
                    f"LLM API call failed after {max_retries} retries: {error}",
                    error,
                ) from error

            # Non-retryable → fail immediately
            if not is_retryable(error):
                raise

            # Compute delay
            retry_after = _get_retry_after(error)
            delay_secs = _compute_backoff(attempt, retry_after)

            # Notify plugins
            await _trigger_callbacks(
                "api_retry_start",
                error=error,
                attempt=attempt,
                delay_ms=int(delay_secs * 1000),
                max_retries=max_retries,
            )

            logger.info(
                "Retrying LLM API call in %.1fs (attempt %d/%d)",
                delay_secs,
                attempt,
                max_retries + 1,
            )

            await _cancellable_sleep(delay_secs, config.cancel_event)

    # Unreachable, but satisfies type checker
    raise RetryExhaustedError(
        f"LLM API call failed: {last_error}",
        last_error,  # type: ignore[arg-type]
    )
