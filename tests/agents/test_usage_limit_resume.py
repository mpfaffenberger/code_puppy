"""Tests for opt-in auto-resume after a "try again in N minutes" usage cap."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from code_puppy.agents import usage_limit_resume as ulr
from code_puppy.agents._runtime import streaming_retry


class _StatusError(Exception):
    """Duck-types SDK status errors (``status_code`` + ``body``)."""

    def __init__(self, message: str, status_code: int = 429, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _anthropic_style(msg: str) -> _StatusError:
    body = {"type": "error", "error": {"type": "rate_limit_error", "message": msg}}
    return _StatusError(f"Error code: 429 - {json.dumps(body)}", body=body)


# ---- parse_wait_seconds -----------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Try again in 47 minutes.", 47 * 60),
        ("try again in 1 minute", 60),
        ("Please try again in 2 hours", 7200),
        ("Try again in 1h 30m", 5400),
        ("Try again in 1h30m", 5400),
        ("try again in 2 hours and 5 minutes", 7500),
        ("Try again in 1 hour, 10 minutes", 4200),
        ("Try again in 4.5 minutes", 270),
        ("try again in 90 seconds", 90),
        ("Try again after about 10 mins", 600),
        ("Your limit resets in 3 hrs", 10800),
        ("TRY AGAIN IN 5 MINUTES", 300),
    ],
)
def test_parse_wait_seconds_formats(text, expected):
    assert ulr.parse_wait_seconds(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    ["", "rate limited", "try again later", "try again in a moment", "in 5 months"],
)
def test_parse_wait_seconds_none(text):
    assert ulr.parse_wait_seconds(text) is None


# ---- usage_limit_wait_seconds -----------------------------------------------


def test_detects_anthropic_style_error():
    exc = _anthropic_style("You have hit your usage limit. Try again in 47 minutes.")
    assert ulr.usage_limit_wait_seconds(exc) == 47 * 60


def test_detects_different_json_shape_same_string():
    body = {"detail": {"code": "quota", "msg": "Try again in 12 minutes"}}
    exc = _StatusError(str(body), status_code=429, body=body)
    assert ulr.usage_limit_wait_seconds(exc) == 12 * 60


def test_detects_rate_limit_text_without_status():
    exc = RuntimeError('{"type":"rate_limit_error","message":"Try again in 5 minutes"}')
    assert ulr.usage_limit_wait_seconds(exc) == 300


def test_detects_through_cause_chain_and_group():
    inner = _anthropic_style("Try again in 20 minutes")
    try:
        try:
            raise inner
        except _StatusError as e:
            raise RuntimeError("model request failed") from e
    except RuntimeError as wrapped:
        group = BaseExceptionGroup("stream failed", [wrapped])
    assert ulr.usage_limit_wait_seconds(group) == 20 * 60


def test_ignores_phrase_without_rate_limit_signal():
    exc = _StatusError("Server busy. Try again in 5 minutes", status_code=503)
    assert ulr.usage_limit_wait_seconds(exc) is None


def test_ignores_short_waits_left_to_normal_backoff():
    exc = _anthropic_style("Rate limit. Try again in 20 seconds")
    assert ulr.usage_limit_wait_seconds(exc) is None


def test_long_retry_after_header_without_phrase():
    class _Resp:
        status_code = 429
        headers = {"retry-after": "1800"}
        text = "{}"

    exc = _StatusError("Error code: 429")
    exc.response = _Resp()
    assert ulr.usage_limit_wait_seconds(exc) == 1800


def test_unrelated_error_is_none():
    assert ulr.usage_limit_wait_seconds(ValueError("boom")) is None


# ---- settings ---------------------------------------------------------------


def test_settings_defaults_and_parsing():
    with patch("code_puppy.config.get_value", return_value=None):
        assert ulr.is_enabled() is False
        assert ulr.get_max_wait_minutes() == ulr.DEFAULT_MAX_WAIT_MINUTES
        assert ulr.get_max_resumes() == ulr.DEFAULT_MAX_RESUMES
    with patch("code_puppy.config.get_value", return_value="garbage"):
        assert ulr.get_max_wait_minutes() == ulr.DEFAULT_MAX_WAIT_MINUTES
    with patch("code_puppy.config.get_value", return_value="true"):
        assert ulr.is_enabled() is True


# ---- streaming_retry integration --------------------------------------------


def _flaky(exc: Exception, failures: int):
    calls = {"n": 0}

    async def factory():
        calls["n"] += 1
        if calls["n"] <= failures:
            raise exc
        return "ok"

    return factory, calls


@pytest.fixture
def no_sleep():
    with (
        patch.object(ulr, "wait_for_reset", new=AsyncMock()) as wait,
        patch("code_puppy.agents._runtime.asyncio.sleep", new=AsyncMock()),
        patch("code_puppy.error_logging.log_error"),
    ):
        yield wait


def _settings(enabled=True, max_wait=300, max_resumes=3):
    return (
        patch.object(ulr, "is_enabled", return_value=enabled),
        patch.object(ulr, "get_max_wait_minutes", return_value=max_wait),
        patch.object(ulr, "get_max_resumes", return_value=max_resumes),
    )


def test_streaming_retry_waits_and_resumes_when_enabled(no_sleep):
    exc = _anthropic_style("Try again in 47 minutes")
    factory, calls = _flaky(exc, failures=1)
    a, b, c = _settings()
    with a, b, c:
        result = asyncio.run(streaming_retry(max_attempts=1)(factory)())
    assert result == "ok"
    assert calls["n"] == 2
    no_sleep.assert_awaited_once()
    assert no_sleep.await_args.args[0] == 47 * 60


def test_streaming_retry_unchanged_when_disabled(no_sleep):
    exc = _anthropic_style("Try again in 47 minutes")
    factory, calls = _flaky(exc, failures=5)
    a, b, c = _settings(enabled=False)
    with a, b, c, patch("code_puppy.agents._runtime.emit_error"):
        with pytest.raises(_StatusError):
            asyncio.run(streaming_retry(max_attempts=1)(factory)())
    no_sleep.assert_not_awaited()


def test_streaming_retry_refuses_wait_beyond_cap(no_sleep):
    exc = _anthropic_style("Try again in 10 hours")
    factory, calls = _flaky(exc, failures=1)
    a, b, c = _settings(max_wait=60)
    with a, b, c, patch("code_puppy.agents._runtime.emit_warning"):
        with pytest.raises(_StatusError):
            asyncio.run(streaming_retry(max_attempts=3)(factory)())
    assert calls["n"] == 1
    no_sleep.assert_not_awaited()


def test_streaming_retry_caps_back_to_back_resumes(no_sleep):
    exc = _anthropic_style("Try again in 5 minutes")
    factory, calls = _flaky(exc, failures=100)
    a, b, c = _settings(max_resumes=2)
    with (
        a,
        b,
        c,
        patch("code_puppy.agents._runtime.emit_error"),
        patch("code_puppy.agents._runtime.emit_warning"),
    ):
        with pytest.raises(_StatusError):
            asyncio.run(streaming_retry(max_attempts=1)(factory)())
    assert no_sleep.await_count == 2


def test_wait_for_reset_is_cancellable():
    async def run():
        with patch("code_puppy.messaging.emit_warning"):
            task = asyncio.create_task(ulr.wait_for_reset(3600, 1, 3))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())


def test_wait_for_reset_uses_wall_clock():
    """A wall-clock jump (laptop sleep) ends the wait without more sleeping."""
    clock = {"now": 1000.0}

    async def fake_sleep(seconds):
        clock["now"] += 10_000  # machine "slept" well past the deadline

    with (
        patch("code_puppy.agents.usage_limit_resume.time.time", lambda: clock["now"]),
        patch("code_puppy.agents.usage_limit_resume.asyncio.sleep", fake_sleep),
        patch("code_puppy.messaging.emit_warning") as warn,
    ):
        asyncio.run(ulr.wait_for_reset(3600, 1, 3))
    assert warn.call_count == 2


# ---- HTTP short-circuit -----------------------------------------------------


class _FakeResponse:
    def __init__(self, status=429, body=b"", headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    async def aread(self):
        return self._body


@pytest.mark.parametrize(
    ("resp", "enabled", "expected"),
    [
        (_FakeResponse(body=b'{"message":"Try again in 30 minutes"}'), True, True),
        (_FakeResponse(body=b'{"message":"Try again in 30 minutes"}'), False, False),
        (_FakeResponse(body=b'{"message":"slow down"}'), True, False),
        (_FakeResponse(headers={"retry-after": "900"}), True, True),
        (_FakeResponse(status=503, body=b"Try again in 30 minutes"), True, False),
    ],
)
def test_response_is_usage_limit(resp, enabled, expected):
    with patch.object(ulr, "is_enabled", return_value=enabled):
        assert asyncio.run(ulr.response_is_usage_limit(resp)) is expected
