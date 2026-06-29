"""End-to-end test: the retry decorator survives wrapper exceptions.

These tests exercise the real ``streaming_retry`` decorator (not just the
classifier predicate) with the exact wrapper shapes the Anthropic SDK +
pydantic-ai surface in production. They are deterministic (no network) but
prove the full retry-and-recover path works for the wrapper types that used
to escape the classifier.
"""

import httpx
import pytest

from code_puppy.agents._runtime import streaming_retry


def _make_model_api_error_with_cause() -> Exception:
    """Tushar's exact traceback shape: ModelAPIError wrapping httpx.ConnectError."""
    from pydantic_ai.exceptions import ModelAPIError

    wrapper = ModelAPIError(model_name="claude-x", message="Connection error.")
    wrapper.__cause__ = httpx.ConnectError("failed to establish connection")
    return wrapper


def _make_anthropic_upstream_idle_timeout() -> Exception:
    """Mid-stream gateway stall: anthropic.APIStatusError with type=api_error."""
    from anthropic import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 502
    err.body = {
        "error": {
            "message": "upstream_idle_timeout (rid=abc): no data for 60s",
            "type": "api_error",
        }
    }
    err.message = "upstream_idle_timeout (rid=abc): no data for 60s"
    return err


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_model_api_error():
    """Two failed attempts (wrapper exception), then a success on attempt 3.

    The decorator must classify the wrapper as retryable via the cause-chain
    walk, retry, and eventually return the success value -- not re-raise.
    """
    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _make_model_api_error_with_cause()
        return "streamed-result"

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    result = await runner()

    assert result == "streamed-result"
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_streaming_retry_recovers_from_anthropic_upstream_idle_timeout():
    """Same shape, different wrapper: APIStatusError mid-stream stall."""
    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise _make_anthropic_upstream_idle_timeout()
        return "streamed-result"

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    result = await runner()

    assert result == "streamed-result"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_streaming_retry_gives_up_after_max_attempts_with_wrapper():
    """If every attempt fails, the ORIGINAL wrapper is re-raised intact.

    The retry loop must hand the renderer the SAME wrapper exception it
    received -- so the renderer can ask the classifier whether to show the
    friendly one-liner or the full traceback. Losing the wrapper here would
    silently turn a recognisable transient into something neither layer
    knows how to format.
    """
    from pydantic_ai.exceptions import ModelAPIError

    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        raise _make_model_api_error_with_cause()

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    with pytest.raises(ModelAPIError, match="Connection error"):
        await runner()

    assert call_count["n"] == 3  # all three attempts consumed


@pytest.mark.asyncio
async def test_streaming_retry_does_not_retry_genuine_bugs():
    """Belt-and-braces: a true non-transient still fails fast (no retries)."""
    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        raise ValueError("genuine programming bug")

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    with pytest.raises(ValueError, match="genuine programming bug"):
        await runner()

    assert call_count["n"] == 1  # NO retries -- single attempt and done


# --- Real reports from the field. These bodies are copy-pasted from user
# --- Teams messages so any future regression that breaks classification of
# --- the actual shapes seen in production gets caught.

def _real_world_geoff_upstream_idle_timeout() -> Exception:
    """Verbatim from Geoff Allen 1:06 PM: upstream_idle_timeout, no data for 60s."""
    from anthropic import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 502
    err.body = {
        "error": {
            "message": "upstream_idle_timeout (rid=915221f2): no data for 60s",
            "type": "api_error",
        },
        "request_id": "915221f2",
        "type": "error",
    }
    err.message = "upstream_idle_timeout (rid=915221f2): no data for 60s"
    return err


def _real_world_tripuresh_upstream_stream_error() -> Exception:
    """Verbatim from Tripuresh Pandey 1:10 PM: upstream_stream_error, error decoding response body."""
    from anthropic import APIStatusError

    err = APIStatusError.__new__(APIStatusError)
    err.status_code = 502
    err.body = {
        "error": {
            "message": "upstream_stream_error (rid=d697750e): error decoding response body",
            "type": "api_error",
        },
        "request_id": "d697750e",
        "type": "error",
    }
    err.message = "upstream_stream_error (rid=d697750e): error decoding response body"
    return err


@pytest.mark.asyncio
async def test_field_report_geoff_upstream_idle_timeout_recovers():
    """Geoff Allen's exact error: the retry decorator must retry and recover."""
    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise _real_world_geoff_upstream_idle_timeout()
        return "streamed-result"

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    result = await runner()

    assert result == "streamed-result"
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_field_report_tripuresh_upstream_stream_error_recovers():
    """Tripuresh Pandey's exact error: the retry decorator must retry and recover."""
    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise _real_world_tripuresh_upstream_stream_error()
        return "streamed-result"

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    result = await runner()

    assert result == "streamed-result"
    assert call_count["n"] == 2


# --- On-disk error logging: SRE / support need to be able to see upstream
# --- blips even though the user only sees the friendly UI. These tests prove
# --- log_error fires on every retry attempt and on exhaustion.

@pytest.mark.asyncio
async def test_streaming_retry_logs_each_transient_attempt_to_error_log(monkeypatch):
    """Every retry attempt MUST be persisted to errors.log, not just shown in the UI."""
    captured = []

    def fake_log_error(exc, context=None, include_traceback=True):
        captured.append((exc, context))

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", fake_log_error
    )

    call_count = {"n": 0}

    async def factory():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _real_world_geoff_upstream_idle_timeout()
        return "streamed-result"

    runner = streaming_retry(max_attempts=5, delays=(0, 0, 0, 0, 0))(factory)
    result = await runner()

    assert result == "streamed-result"
    # 2 transient attempts (1 and 2) failed, attempt 3 succeeded -> 2 log calls.
    attempt_logs = [c for c in captured if "attempt" in c[1]]
    assert len(attempt_logs) == 2
    assert "attempt 1/5" in attempt_logs[0][1]
    assert "attempt 2/5" in attempt_logs[1][1]
    # Verify it's the actual exception object, not just a stringified copy.
    assert type(attempt_logs[0][0]).__name__ == "APIStatusError"


@pytest.mark.asyncio
async def test_streaming_retry_logs_exhaustion_to_error_log(monkeypatch):
    """When all retries are exhausted, a distinct exhaustion entry MUST hit the log."""
    captured = []

    def fake_log_error(exc, context=None, include_traceback=True):
        captured.append((exc, context))

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", fake_log_error
    )

    async def factory():
        raise _real_world_tripuresh_upstream_stream_error()

    runner = streaming_retry(max_attempts=2, delays=(0, 0))(factory)
    with pytest.raises(Exception):
        await runner()

    exhaustion_logs = [c for c in captured if "exhausted" in c[1]]
    assert len(exhaustion_logs) == 1
    assert "exhausted all 2 attempts" in exhaustion_logs[0][1]


@pytest.mark.asyncio
async def test_streaming_retry_does_not_log_non_transient(monkeypatch):
    """Genuine bugs are re-raised without being recorded as retry attempts.

    They will still be logged by ``_render_turn_exception`` upstream (covered
    in test_cli_runner_turn_exception), but the retry decorator should not
    pollute the log with non-transient errors it never tried to retry.
    """
    captured = []

    def fake_log_error(exc, context=None, include_traceback=True):
        captured.append((exc, context))

    monkeypatch.setattr(
        "code_puppy.error_logging.log_error", fake_log_error
    )

    async def factory():
        raise ValueError("genuine programming bug")

    runner = streaming_retry(max_attempts=3, delays=(0, 0, 0))(factory)
    with pytest.raises(ValueError):
        await runner()

    assert captured == []
