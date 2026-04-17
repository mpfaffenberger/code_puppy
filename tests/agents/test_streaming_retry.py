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


def _make_openai_api_error(message: str, *, body=None):
    if APIError is None:
        pytest.skip("openai is not installed in this test environment")
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return APIError(message, request=request, body=body)


class TestStreamingRetry:
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        factory = AsyncMock(return_value="ok")

        result = await _run_with_streaming_retry(factory)

        assert result == "ok"
        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_httpx_remote_protocol_error(self):
        factory = AsyncMock(
            side_effect=[
                httpx.RemoteProtocolError("peer closed connection"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_httpx_read_timeout(self):
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
        factory = AsyncMock(
            side_effect=[
                httpcore.RemoteProtocolError("peer closed connection"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_transient_openai_api_error(self):
        factory = AsyncMock(
            side_effect=[
                _make_openai_api_error(
                    "The server had an error processing your request.",
                    body={
                        "message": "The server had an error processing your request.",
                        "type": "server_error",
                    },
                ),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_unexpected_model_behavior_with_streaming_message(self):
        factory = AsyncMock(
            side_effect=[
                UnexpectedModelBehavior("streamed response ended without content"),
                "recovered",
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_streaming_retry(factory)

        assert result == "recovered"
        assert factory.await_count == 2

    @pytest.mark.asyncio
    async def test_non_retryable_error_propagates_immediately(self):
        factory = AsyncMock(side_effect=ValueError("not a network error"))

        with pytest.raises(ValueError, match="not a network error"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_non_transient_openai_api_error_does_not_retry(self):
        error = _make_openai_api_error(
            "Nope.",
            body={"message": "Nope.", "type": "invalid_request_error"},
        )
        factory = AsyncMock(side_effect=error)

        with pytest.raises(type(error), match="Nope"):
            await _run_with_streaming_retry(factory)

        assert factory.await_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        error = httpx.RemoteProtocolError("keep failing")
        factory = AsyncMock(side_effect=error)
        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(httpx.RemoteProtocolError):
                await _run_with_streaming_retry(factory)

        assert sleep_calls == [1, 2]

    @pytest.mark.asyncio
    async def test_raises_last_retryable_exception_after_exhaustion(self):
        error = httpx.RemoteProtocolError("persistent failure")
        factory = AsyncMock(side_effect=error)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.RemoteProtocolError, match="persistent failure"):
                await _run_with_streaming_retry(factory)

        assert factory.await_count == MAX_STREAMING_RETRIES

    def test_classifier_accepts_retryable_streaming_errors(self):
        assert should_retry_streaming_exception(
            httpx.RemoteProtocolError("peer closed connection")
        )
        assert should_retry_streaming_exception(httpx.ReadTimeout("timed out"))
        assert should_retry_streaming_exception(
            httpcore.RemoteProtocolError("peer closed connection")
        )
        assert should_retry_streaming_exception(
            UnexpectedModelBehavior("streamed response ended without content")
        )

    def test_classifier_rejects_non_retryable_errors(self):
        assert not should_retry_streaming_exception(ValueError("nope"))
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("tool schema validation exploded")
        )

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
            with pytest.raises(httpx.RemoteProtocolError, match="persistent failure"):
                await _run_with_streaming_retry(factory)

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
        assert should_retry_streaming_exception(httpx.ReadTimeout("timed out"))
        assert should_retry_streaming_exception(
            httpcore.RemoteProtocolError("peer closed connection")
        )
        assert should_retry_streaming_exception(
            UnexpectedModelBehavior("streamed response ended without content")
        )

    def test_classifier_rejects_non_retryable_errors(self):
        assert not should_retry_streaming_exception(ValueError("nope"))
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("tool schema validation exploded")
        )

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
