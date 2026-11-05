"""Regression tests for transient provider-stream failure classification.

Malformed SSE and raw TLS record failures can escape provider transport
wrappers. Both must be retried without widening the policy to unrelated parse,
certificate, or protocol errors.
"""

from __future__ import annotations

import importlib
import json
import ssl

import httpcore
import httpcore2
import httpx
import httpx2
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


def _tls_record_error() -> ssl.SSLError:
    """Match the reported message-only shape; constructed errors lack .reason."""
    return ssl.SSLError(
        ssl.SSL_ERROR_SSL,
        "[SSL: DECRYPTION_FAILED_OR_BAD_RECORD_MAC] "
        "decryption failed or bad record mac (_ssl.c:2648)",
    )


def test_is_retryable_one_recognizes_tls_record_error() -> None:
    assert _is_retryable_one(_tls_record_error()) is True


def test_is_retryable_one_uses_structured_tls_reason() -> None:
    """Real OpenSSL errors populate .reason; constructed ones do not."""
    exc = ssl.SSLError(ssl.SSL_ERROR_SSL, "decryption failed or bad record mac")
    exc.reason = "DECRYPTION_FAILED_OR_BAD_RECORD_MAC"

    assert _is_retryable_one(exc) is True


def test_should_retry_streaming_reaches_tls_record_error_inside_group() -> None:
    group = BaseExceptionGroup("stream failed", [_tls_record_error()])

    assert should_retry_streaming(group) is True


def test_certificate_verification_error_is_not_retryable() -> None:
    exc = ssl.SSLCertVerificationError(
        ssl.SSL_ERROR_SSL,
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed",
    )

    assert _is_retryable_one(exc) is False


def test_tls_protocol_error_is_not_retryable() -> None:
    exc = ssl.SSLError(
        ssl.SSL_ERROR_SSL,
        "[SSL: WRONG_VERSION_NUMBER] wrong version number",
    )

    assert _is_retryable_one(exc) is False


def test_structured_tls_reason_is_not_overridden_by_message_fallback() -> None:
    exc = _tls_record_error()
    exc.reason = "WRONG_VERSION_NUMBER"

    assert _is_retryable_one(exc) is False


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_tls_record_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def run_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _tls_record_error()
        return "recovered"

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("code_puppy.agents._runtime.emit_warning", lambda *args: None)

    run_with_retry = streaming_retry(max_attempts=2, delays=(0,))(run_once)

    assert await run_with_retry() == "recovered"
    assert attempts == 2


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


_INCOMPLETE_CHUNKED_READ = (
    "peer closed connection without sending complete message body "
    "(incomplete chunked read)"
)

_RETRYABLE_TRANSPORT_ERRORS = [
    httpx.RemoteProtocolError,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpcore.RemoteProtocolError,
    httpcore.ReadError,
    httpcore.ReadTimeout,
    httpx2.RemoteProtocolError,
    httpx2.NetworkError,
    httpx2.ReadError,
    httpx2.WriteError,
    httpx2.ConnectError,
    httpx2.TimeoutException,
    httpx2.ReadTimeout,
    httpx2.ConnectTimeout,
    httpx2.PoolTimeout,
    httpcore2.RemoteProtocolError,
    httpcore2.NetworkError,
    httpcore2.ReadError,
    httpcore2.ConnectError,
    httpcore2.TimeoutException,
    httpcore2.ReadTimeout,
    httpcore2.PoolTimeout,
]


def _ids(error_classes: list[type[Exception]]) -> list[str]:
    return [f"{cls.__module__}.{cls.__name__}" for cls in error_classes]


@pytest.mark.parametrize(
    "error_class", _RETRYABLE_TRANSPORT_ERRORS, ids=_ids(_RETRYABLE_TRANSPORT_ERRORS)
)
def test_is_retryable_one_recognizes_transport_errors(
    error_class: type[Exception],
) -> None:
    assert _is_retryable_one(error_class(_INCOMPLETE_CHUNKED_READ)) is True


def _httpx2_incomplete_chunked_read() -> httpx2.RemoteProtocolError:
    """Same shape as the real failure: httpx2 error chained from httpcore2."""
    try:
        try:
            raise httpcore2.RemoteProtocolError(_INCOMPLETE_CHUNKED_READ)
        except httpcore2.RemoteProtocolError as cause:
            raise httpx2.RemoteProtocolError(_INCOMPLETE_CHUNKED_READ) from cause
    except httpx2.RemoteProtocolError as exc:
        return exc


def test_should_retry_streaming_recognizes_httpx2_incomplete_chunked_read() -> None:
    assert should_retry_streaming(_httpx2_incomplete_chunked_read()) is True


def test_should_retry_streaming_follows_cause_to_httpcore2_error() -> None:
    wrapper = RuntimeError("provider wrapper")
    wrapper.__cause__ = httpcore2.RemoteProtocolError(_INCOMPLETE_CHUNKED_READ)

    assert should_retry_streaming(wrapper) is True


def test_should_retry_streaming_reaches_httpx2_error_inside_group() -> None:
    group = BaseExceptionGroup("stream failed", [_httpx2_incomplete_chunked_read()])

    assert should_retry_streaming(group) is True


@pytest.mark.parametrize("status_code", [401, 404])
def test_httpx2_status_error_is_not_retryable(status_code: int) -> None:
    request = httpx2.Request("POST", "https://example.invalid/v1/messages")
    response = httpx2.Response(status_code, request=request)
    exc = httpx2.HTTPStatusError("client error", request=request, response=response)

    assert _is_retryable_one(exc) is False


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_httpx2_incomplete_chunked_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def run_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _httpx2_incomplete_chunked_read()
        return "recovered"

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("code_puppy.agents._runtime.emit_warning", lambda *args: None)

    run_with_retry = streaming_retry(max_attempts=2, delays=(0,))(run_once)

    assert await run_with_retry() == "recovered"
    assert attempts == 2
