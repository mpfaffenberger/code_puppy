"""Regression tests for malformed provider SSE retry recovery.

A malformed SSE ``data:`` payload can raise ``json.JSONDecodeError`` from the
OpenAI or Anthropic SDK. The runtime must recognize that exception through an
``ExceptionGroup`` and retry the turn from its last completed step.
"""

from __future__ import annotations

import importlib
import json

import pytest

from code_puppy.agents._runtime import (
    _is_retryable_one,
    should_retry_streaming,
    streaming_retry,
)


def _malformed_sse_json_decode_error() -> json.JSONDecodeError:
    """Same exception shape as a concatenated SSE ``data:`` payload."""
    doc = '{"ok": 1}{"oops": 2}'
    try:
        json.loads(doc)
    except json.JSONDecodeError as exc:
        return exc
    raise AssertionError("expected json.loads to raise JSONDecodeError")


def test_is_retryable_one_recognizes_json_decode_error() -> None:
    exc = _malformed_sse_json_decode_error()

    assert _is_retryable_one(exc) is True


def test_should_retry_streaming_reaches_json_decode_error_inside_group() -> None:
    """Must unwrap the BaseExceptionGroup pydantic-ai raises in practice."""
    exc = _malformed_sse_json_decode_error()
    group = BaseExceptionGroup("stream failed", [exc])

    assert should_retry_streaming(group) is True


def test_is_retryable_one_does_not_widen_to_unrelated_value_errors() -> None:
    """Guard against over-widening: unrelated ValueErrors stay non-retryable."""
    assert _is_retryable_one(ValueError("nope")) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "streaming_module_path,event_name",
    [
        ("openai._streaming", "response.output_item.added"),
        ("anthropic._streaming", "content_block_delta"),
    ],
)
async def test_streaming_retry_recovers_from_provider_sse_extra_data(
    monkeypatch: pytest.MonkeyPatch,
    streaming_module_path: str,
    event_name: str,
) -> None:
    """Exercise each SDK's real SSE exception through the real retry loop."""
    streaming = importlib.import_module(streaming_module_path)
    malformed_event = streaming.ServerSentEvent(
        event=event_name,
        data='{"ok": 1}{"oops": 2}',
    )
    attempts = 0

    async def run_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            malformed_event.json()
        return "recovered"

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("code_puppy.agents._runtime.emit_warning", lambda *args: None)

    run_with_retry = streaming_retry(max_attempts=2, delays=(0,))(run_once)

    assert await run_with_retry() == "recovered"
    assert attempts == 2
