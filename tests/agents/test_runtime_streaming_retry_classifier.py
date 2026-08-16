"""Regression tests: bare JSONDecodeError must be classified as retryable.

A malformed SSE line raises ``json.JSONDecodeError``, which used to escape
``_is_retryable_one`` and crash the session.
"""

from __future__ import annotations

import json

from code_puppy.agents._runtime import _is_retryable_one, should_retry_streaming


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
