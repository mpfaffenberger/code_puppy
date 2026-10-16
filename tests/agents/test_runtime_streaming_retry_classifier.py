"""Regression tests for transient provider-stream failure classification.

Malformed SSE and raw TLS record failures can escape provider transport
wrappers. Both must be retried without widening the policy to unrelated parse,
certificate, or protocol errors.
"""

from __future__ import annotations

import importlib
import json
import ssl

import httpcore2
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


# httpx2 / httpcore2 exceptions are a separate hierarchy from httpx / httpcore.
# Streams from the OAuth clients and pydantic-ai provider clients raise them.
_HTTPX2_TRANSIENT = [
    pytest.param(lambda: httpx2.ReadTimeout("stream stalled"), id="httpx2-ReadTimeout"),
    pytest.param(lambda: httpx2.ConnectTimeout("slow"), id="httpx2-ConnectTimeout"),
    pytest.param(lambda: httpx2.ReadError("reset"), id="httpx2-ReadError"),
    pytest.param(
        lambda: httpx2.RemoteProtocolError("peer closed"),
        id="httpx2-RemoteProtocolError",
    ),
    pytest.param(
        lambda: httpcore2.ReadTimeout("stream stalled"), id="httpcore2-ReadTimeout"
    ),
    pytest.param(lambda: httpcore2.ReadError("reset"), id="httpcore2-ReadError"),
    pytest.param(
        lambda: httpcore2.RemoteProtocolError("peer closed"),
        id="httpcore2-RemoteProtocolError",
    ),
]


@pytest.mark.parametrize("make_exc", _HTTPX2_TRANSIENT)
def test_is_retryable_one_recognizes_httpx2_transport_errors(make_exc) -> None:
    assert _is_retryable_one(make_exc()) is True


@pytest.mark.parametrize("make_exc", _HTTPX2_TRANSIENT)
def test_should_retry_streaming_reaches_httpx2_error_inside_group(make_exc) -> None:
    group = BaseExceptionGroup("stream failed", [make_exc()])

    assert should_retry_streaming(group) is True


def test_should_retry_streaming_reaches_httpx2_error_through_cause_chain() -> None:
    """SDKs wrap the transport error; the real one sits on ``__cause__``."""
    try:
        try:
            raise httpx2.ReadTimeout("stream stalled")
        except httpx2.ReadTimeout as inner:
            raise RuntimeError("provider wrapper") from inner
    except RuntimeError as wrapped:
        assert should_retry_streaming(wrapped) is True


def test_httpx2_http_status_error_is_not_retryable() -> None:
    """A 401 is a client error: surviving it is fine, retrying it is not."""
    request = httpx2.Request("GET", "https://example.test/v1/stream")
    response = httpx2.Response(401, request=request)
    exc = httpx2.HTTPStatusError("unauthorized", request=request, response=response)

    assert _is_retryable_one(exc) is False


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_httpx2_read_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The reported failure: ReadTimeout while consuming an established stream."""
    attempts = 0

    async def run_once() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx2.ReadTimeout("stream stalled")
        return "recovered"

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", lambda *args, **kwargs: None
    )
    monkeypatch.setattr("code_puppy.agents._runtime.emit_warning", lambda *args: None)

    run_with_retry = streaming_retry(max_attempts=2, delays=(0,))(run_once)

    assert await run_with_retry() == "recovered"
    assert attempts == 2
