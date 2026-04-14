"""Tests for streaming retry transient error handling.

Verifies that transient streaming, transport, and OpenAI SDK rate-limit-ish
errors are retried with exponential backoff, while non-retryable errors
propagate immediately.

Covers: https://github.com/mpfaffenberger/code_puppy/issues/199
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpcore
import httpx
import pytest
from openai import APIError

from code_puppy.agents.base_agent import should_retry_streaming_exception


# ---- Helpers to build the retry function in isolation ----
# We still exercise the real classifier so tests stay aligned with production.

MAX_STREAMING_RETRIES = 3
STREAMING_RETRY_DELAYS = [1, 2, 4]


async def _run_with_streaming_retry(run_coro_factory):
    """Mirror of the retry loop in base_agent.py for isolated testing."""
    last_error = None
    for attempt in range(MAX_STREAMING_RETRIES):
        try:
            return await run_coro_factory()
        except Exception as e:
            if not should_retry_streaming_exception(e):
                raise
            last_error = e
            if attempt < MAX_STREAMING_RETRIES - 1:
                delay = STREAMING_RETRY_DELAYS[attempt]
                await asyncio.sleep(delay)
    raise last_error


# ---- Tests ----


class TestStreamingRetry:
    """Tests for transient HTTP error retry logic."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """No retries needed when the call succeeds immediately."""
        factory = AsyncMock(return_value="ok")

        result = await _run_with_streaming_retry(factory)

        assert result == "ok"
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_httpx_remote_protocol_error(self):
        """Retries when httpx.RemoteProtocolError is raised."""
        factory = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError(
                    "peer closed connection without sending complete message body"
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpx_read_timeout(self):
        """Retries when httpx.ReadTimeout is raised."""
        factory = AsyncMock(
            side_effect=[
                httpx.ReadTimeout("read timed out"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpcore_remote_protocol_error(self):
        """Retries when httpcore.RemoteProtocolError is raised."""
        factory = AsyncMock(
            side_effect=[
                httpcore.RemoteProtocolError(
                    "peer closed connection without sending complete message body"
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_exhausts_retries_then_raises(self):
        """Raises the last error after all retries are exhausted."""
        error = httpx.RemoteProtocolError("persistent failure")
        factory = AsyncMock(side_effect=error)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.RemoteProtocolError, match="persistent failure"):
                await _run_with_streaming_retry(factory)

        assert factory.await_count == MAX_STREAMING_RETRIES

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self):
        """Non-retryable exceptions are NOT caught — they propagate immediately."""
        factory = AsyncMock(side_effect=ValueError("not a network error"))

        with pytest.raises(ValueError, match="not a network error"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1  # No retry attempted

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Verifies exponential backoff delay values between retries."""
        error = httpx.RemoteProtocolError("keep failing")
        factory = AsyncMock(side_effect=error)
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(httpx.RemoteProtocolError):
                await _run_with_streaming_retry(factory)

        # Only 2 sleeps happen (between attempt 1→2 and 2→3; no sleep after last failure)
        assert sleep_calls == [1, 2]

    @pytest.mark.asyncio
    async def test_recovery_on_last_attempt(self):
        """Succeeds on the final retry attempt."""
        factory = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError("fail 1"),
                httpx.ReadTimeout("fail 2"),
                "finally worked",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "finally worked"
        assert factory.await_count == 3

    @pytest.mark.asyncio
    async def test_mixed_retryable_errors(self):
        """Handles different retryable error types across attempts."""
        factory = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError("peer closed"),
                httpcore.RemoteProtocolError("peer closed again"),
                "success",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "success"
        assert factory.await_count == 3

    @pytest.mark.asyncio
    async def test_retries_on_openai_api_error_too_many_requests(self):
        """Retries when the OpenAI SDK raises stream-time APIError for 429-ish events."""
        request = httpx.Request("POST", "https://example.test/responses")
        factory = AsyncMock(
            side_effect=[
                APIError(
                    "Too Many Requests",
                    request=request,
                    body={"message": "Too Many Requests", "type": "api_error"},
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_openai_api_error_server_processing_message(self):
        """Retries Azure/OpenAI stream-time server errors that explicitly say retry."""
        request = httpx.Request("POST", "https://example.test/responses")
        error_message = (
            "The server had an error processing your request. Sorry about that! "
            "You can retry your request. (Please include the request ID cb059d60-af56-424f-a320-773824872552.)"
        )
        factory = AsyncMock(
            side_effect=[
                APIError(
                    error_message,
                    request=request,
                    body={"message": error_message, "type": "api_error"},
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_openai_api_error_propagates(self):
        """OpenAI API errors that are not transient should not be retried."""
        request = httpx.Request("POST", "https://example.test/responses")
        factory = AsyncMock(
            side_effect=APIError(
                "Invalid tool schema",
                request=request,
                body={"message": "Invalid tool schema", "type": "invalid_request_error"},
            )
        )

        with pytest.raises(APIError, match="Invalid tool schema"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1
