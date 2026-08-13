"""Regression coverage for streaming transport recovery and terminal status."""

import httpx
from pydantic_ai import UnexpectedModelBehavior

from code_puppy.agents._runtime import (
    _retry_status_message,
    should_fallback_to_non_streaming,
)


def test_malformed_sse_uses_non_streaming_fallback() -> None:
    error = UnexpectedModelBehavior(
        "Malformed streamed SSE event: extra JSON data in SSE payload"
    )

    assert should_fallback_to_non_streaming(error)


def test_remote_protocol_error_uses_non_streaming_fallback() -> None:
    assert should_fallback_to_non_streaming(
        httpx.RemoteProtocolError("peer closed connection")
    )


def test_rate_limit_status_shows_real_error_not_false_resume_claim() -> None:
    error = RuntimeError(
        "Your requests to gpt-5.4 for gpt-5.4 in eastus2 have exceeded rate limit."
    )

    message = _retry_status_message(error, 5, 1, 1, 5)

    assert message.startswith("Model provider rate limit:")
    assert "gpt-5.4 in eastus2" in message
    assert "Retrying in 5s" in message
    assert "Turn interrupted mid-stream" not in message
    assert "last completed step" not in message


def test_protocol_status_shows_real_error_not_false_resume_claim() -> None:
    error = UnexpectedModelBehavior(
        "Malformed streamed SSE event: extra JSON data in SSE payload"
    )

    message = _retry_status_message(error, 15, 2, 2, 5)

    assert message.startswith("Streaming protocol error:")
    assert "Malformed streamed SSE event" in message
    assert "Retrying in 15s" in message
    assert "Turn interrupted mid-stream" not in message
