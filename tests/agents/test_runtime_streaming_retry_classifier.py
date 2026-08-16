"""Regression tests for the streaming-retry classifier's JSONDecodeError branch.

Covers PUP-634: a bare ``json.decoder.JSONDecodeError`` raised inside the
installed ``anthropic`` SDK's ``ServerSentEvent.json()`` (malformed/concatenated
``data:`` line) used to escape ``_is_retryable_one`` entirely -- it isn't an
``httpx``/``httpcore`` transport error, isn't one of the ``isinstance`` types
already checked, and its default message doesn't match the
``_RETRYABLE_SNIPPETS`` substrings. That meant zero retries were attempted and
the exception crashed the whole interactive session via ``run_agent_task``'s
``except* Exception`` re-raise.

These tests pin the fix at the two levels that matter:
1. The leaf classifier (`_is_retryable_one`) recognizes the exception type.
2. The public entry point (`should_retry_streaming`) still reaches that leaf
   when the exception arrives wrapped in a ``BaseExceptionGroup`` -- which is
   how pydantic-ai's anyio TaskGroup actually delivers it in production.

Plus a negative guardrail so the new branch doesn't quietly widen the
classifier into retrying every deterministic parse error under the sun.
"""

from __future__ import annotations

import json

from code_puppy.agents._runtime import _is_retryable_one, should_retry_streaming


def _malformed_sse_json_decode_error() -> json.JSONDecodeError:
    """Build the same exception shape ``json.loads`` raises on a
    concatenated SSE ``data:`` payload (two JSON objects on one line).
    """
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
    """pydantic-ai's anyio TaskGroup wraps stream failures in an
    ExceptionGroup; ``should_retry_streaming`` must descend into it rather
    than only inspecting the top-level exception.
    """
    exc = _malformed_sse_json_decode_error()
    group = BaseExceptionGroup("stream failed", [exc])

    assert should_retry_streaming(group) is True


def test_is_retryable_one_does_not_widen_to_unrelated_value_errors() -> None:
    """Regression guard: the new branch is scoped to JSONDecodeError, not to
    every parse-ish failure. A generic deterministic ValueError must still
    be treated as non-retryable.
    """
    assert _is_retryable_one(ValueError("nope")) is False
