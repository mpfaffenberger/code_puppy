"""Tests for transient streaming retry behavior.

These stay intentionally focused on the retry classifier and retry loop so
we don't need to spin up the entire BaseAgent circus just to verify whether
network gremlins get another chance.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import httpcore
import httpx
import pytest
from pydantic_ai import UnexpectedModelBehavior

from code_puppy.agents.base_agent import should_retry_streaming_exception

try:
    from openai import APIError
except ImportError:  # pragma: no cover - optional dependency in some test envs
    APIError = None

MAX_STREAMING_RETRIES = 3
STREAMING_RETRY_DELAYS = [1, 2, 4]


async def _run_with_streaming_retry(run_coro_factory):
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
                    "Service unavailable, please retry.",
                    body={
                        "message": "Service unavailable, please retry.",
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


# Each of these snippets is either an explicit provider "please retry" hint or
# an SSE framing artifact that reliably succeeds on retry. They were added as
# part of issue #294. Keep this list aligned with ``_RETRYABLE_SNIPPETS``.
_NEW_RETRYABLE_SNIPPETS = [
    "malformed streamed SSE event",
    "extra JSON data in SSE payload",
    "Too Many Requests",
    "rate limited",
    "server had an error processing your request",
    "please retry your request",
    "internal server error",
    # Generic "stream ... ended" fallback — covers wording we don't yet know.
    "stream connection ended unexpectedly",
    "stream ended early",
]


class TestExpandedRetryClassifier:
    """Coverage for the expanded retry snippet list (issue #294)."""

    @pytest.mark.parametrize("snippet", _NEW_RETRYABLE_SNIPPETS)
    def test_unexpected_model_behavior_snippet_is_retryable(self, snippet):
        assert should_retry_streaming_exception(UnexpectedModelBehavior(snippet))

    @pytest.mark.parametrize("snippet", _NEW_RETRYABLE_SNIPPETS)
    def test_openai_api_error_body_snippet_is_retryable(self, snippet):
        err = _make_openai_api_error(
            snippet,
            body={"message": snippet, "type": "server_error"},
        )
        assert should_retry_streaming_exception(err)

    def test_classifier_still_rejects_unrelated_errors(self):
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("your prompt is malformed")
        )
        assert not should_retry_streaming_exception(
            UnexpectedModelBehavior("stream opened but no body")
        )  # matches 'stream' but not 'ended'

    def test_generic_stream_ended_fallback(self):
        # Different phrasings, all transient.
        for phrasing in (
            "the stream ended prematurely",
            "stream connection ended mid-chunk",
            "upstream stream ended unexpectedly",
        ):
            assert should_retry_streaming_exception(UnexpectedModelBehavior(phrasing))
