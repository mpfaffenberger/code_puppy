"""Retry behaviour shared by both httpx families.

Code Puppy talks to providers with two different HTTP libraries:

* legacy ``httpx`` -- the MCP SDK and the Anthropic/Google SDK shims still want it,
* ``httpx2`` -- what pydantic-ai's providers now require (see ``httpx2_utils``).

The retry algorithm itself only needs ``status_code``, ``headers`` and ``aclose()`` off
the response object, so it is duck-type compatible with both. The *exception* classes are
separate hierarchies, though, so a subclass declares its own ``retryable_exceptions``.

Keeping this in one place is what stops the rate-limit/backoff logic from drifting between
the two client families.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

try:
    from .messaging import emit_info, emit_warning
except ImportError:  # pragma: no cover - fallback when messaging is unavailable

    def emit_info(content: str, **metadata: Any) -> None:
        pass

    def emit_warning(content: str, **metadata: Any) -> None:
        pass


class RetryingSendMixin:
    """Adds rate-limit handling (429) and retries to an httpx-family ``AsyncClient``.

    This replaces the Tenacity transport with a more direct subclass implementation,
    which plays nicer with proxies and custom transports. Mix in *before* the client
    base class so this ``send`` wins the MRO and cooperates via ``super()``::

        class RetryingAsyncClient(RetryingSendMixin, httpx.AsyncClient):
            retryable_exceptions = (httpx.ConnectError, httpx.ReadTimeout, httpx.PoolTimeout)

    Special handling for Cerebras: their ``Retry-After`` headers are absurdly aggressive
    (often 60s), so we ignore them and use a 3s base backoff instead.
    """

    #: Exception types treated as transient connection failures. Set per HTTP family.
    retryable_exceptions: ClassVar[tuple[type[BaseException], ...]] = ()

    def __init__(
        self,
        retry_status_codes: tuple = (429, 502, 503, 504),
        max_retries: int = 5,
        model_name: str = "",
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.retry_status_codes = retry_status_codes
        self.max_retries = max_retries
        self.model_name = model_name.lower() if model_name else ""
        # Cerebras sends crazy aggressive Retry-After headers (60s), ignore them
        self._ignore_retry_headers = "cerebras" in self.model_name

    async def send(self, request: Any, **kwargs: Any) -> Any:
        """Send request with automatic retries for rate limits and server errors."""
        last_response = None
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await super().send(request, **kwargs)
                last_response = response

                # Check for retryable status
                if response.status_code not in self.retry_status_codes:
                    return response

                # Close response if we're going to retry
                await response.aclose()

                # Determine wait time - Cerebras gets special treatment
                if self._ignore_retry_headers:
                    # Cerebras: 3s base with exponential backoff (3s, 6s, 12s...)
                    wait_time = 3.0 * (2**attempt)
                else:
                    # Default exponential backoff: 1s, 2s, 4s...
                    wait_time = 1.0 * (2**attempt)

                    # Check Retry-After header (only for non-Cerebras)
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            # Try parsing http-date
                            from email.utils import parsedate_to_datetime

                            try:
                                date = parsedate_to_datetime(retry_after)
                                wait_time = date.timestamp() - time.time()
                            except Exception:
                                pass

                # Cap wait time
                wait_time = max(0.5, min(wait_time, 60.0))

                if attempt < self.max_retries:
                    provider_note = (
                        " (ignoring header)" if self._ignore_retry_headers else ""
                    )
                    emit_info(
                        f"HTTP retry: {response.status_code} received{provider_note}. "
                        f"Waiting {wait_time:.1f}s (attempt {attempt + 1}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)

            except self.retryable_exceptions as e:
                last_exception = e
                wait_time = 1.0 * (2**attempt)
                if attempt < self.max_retries:
                    emit_warning(
                        f"HTTP connection error: {e}. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception:
                raise

        # Return last response (even if it's an error status)
        if last_response:
            return last_response

        # Should catch this in loop, but just in case
        if last_exception:
            raise last_exception

        return last_response
