"""Tests for code_puppy/llm_retry.py — LLM API retry engine."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.llm_retry import (
    LLMRetryConfig,
    RetryExhaustedError,
    _cancellable_sleep,
    _compute_backoff,
    _get_retry_after,
    _get_status_code,
    _get_x_should_retry,
    _is_overloaded,
    is_retryable,
    llm_run_with_retry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_api_error(status_code: int, message: str = "error", headers=None):
    """Create a mock API error with a status code and optional headers."""
    err = Exception(message)
    err.status_code = status_code
    err.headers = headers or {}
    return err


def _make_overloaded_error():
    """Create a 529 overloaded error."""
    return _make_api_error(529, '{"type":"overloaded_error"}')


# ---------------------------------------------------------------------------
# _get_status_code
# ---------------------------------------------------------------------------
class TestGetStatusCode:
    def test_direct_attribute(self):
        err = _make_api_error(429)
        assert _get_status_code(err) == 429

    def test_response_attribute(self):
        err = Exception("fail")
        err.response = MagicMock(status_code=503)
        assert _get_status_code(err) == 503

    def test_no_status(self):
        assert _get_status_code(Exception("boom")) is None


# ---------------------------------------------------------------------------
# _get_retry_after
# ---------------------------------------------------------------------------
class TestGetRetryAfter:
    def test_direct_headers(self):
        err = _make_api_error(429, headers={"retry-after": "5"})
        assert _get_retry_after(err) == 5.0

    def test_response_headers(self):
        err = Exception("fail")
        err.headers = None
        err.response = MagicMock(headers={"Retry-After": "10"})
        assert _get_retry_after(err) == 10.0

    def test_none_when_absent(self):
        assert _get_retry_after(Exception("no headers")) is None

    def test_invalid_value(self):
        err = _make_api_error(429, headers={"retry-after": "not-a-number"})
        assert _get_retry_after(err) is None


# ---------------------------------------------------------------------------
# _get_x_should_retry
# ---------------------------------------------------------------------------
class TestGetXShouldRetry:
    def test_true(self):
        err = _make_api_error(500, headers={"x-should-retry": "true"})
        assert _get_x_should_retry(err) is True

    def test_false(self):
        err = _make_api_error(400, headers={"x-should-retry": "false"})
        assert _get_x_should_retry(err) is False

    def test_absent(self):
        err = _make_api_error(500, headers={})
        assert _get_x_should_retry(err) is None


# ---------------------------------------------------------------------------
# _is_overloaded
# ---------------------------------------------------------------------------
class TestIsOverloaded:
    def test_529_status(self):
        assert _is_overloaded(_make_api_error(529)) is True

    def test_overloaded_in_body(self):
        err = Exception('{"type":"overloaded_error","message":"busy"}')
        assert _is_overloaded(err) is True

    def test_not_overloaded(self):
        assert _is_overloaded(_make_api_error(429)) is False


# ---------------------------------------------------------------------------
# _compute_backoff
# ---------------------------------------------------------------------------
class TestComputeBackoff:
    def test_retry_after_takes_priority(self):
        assert _compute_backoff(1, retry_after_secs=5.0) == 5.0

    def test_attempt_1_is_500ms(self):
        # Base is 500ms = 0.5s, jitter adds up to 25%
        delay = _compute_backoff(1)
        assert 0.5 <= delay <= 0.625

    def test_attempt_2_is_1s(self):
        delay = _compute_backoff(2)
        assert 1.0 <= delay <= 1.25

    def test_attempt_7_capped_at_32s(self):
        delay = _compute_backoff(7)
        assert 32.0 <= delay <= 40.0

    def test_attempt_10_still_capped(self):
        delay = _compute_backoff(10)
        assert 32.0 <= delay <= 40.0

    def test_zero_retry_after_ignored(self):
        delay = _compute_backoff(1, retry_after_secs=0.0)
        # 0.0 is not > 0, so falls through to computed backoff
        assert 0.5 <= delay <= 0.625

    def test_negative_retry_after_ignored(self):
        delay = _compute_backoff(1, retry_after_secs=-1.0)
        assert 0.5 <= delay <= 0.625


# ---------------------------------------------------------------------------
# is_retryable
# ---------------------------------------------------------------------------
class TestIsRetryable:
    def test_429_retryable(self):
        assert is_retryable(_make_api_error(429)) is True

    def test_529_retryable(self):
        assert is_retryable(_make_api_error(529)) is True

    def test_503_retryable(self):
        assert is_retryable(_make_api_error(503)) is True

    def test_500_retryable(self):
        assert is_retryable(_make_api_error(500)) is True

    def test_408_retryable(self):
        assert is_retryable(_make_api_error(408)) is True

    def test_409_retryable(self):
        assert is_retryable(_make_api_error(409)) is True

    def test_401_retryable(self):
        assert is_retryable(_make_api_error(401)) is True

    def test_400_not_retryable(self):
        assert is_retryable(_make_api_error(400)) is False

    def test_402_not_retryable(self):
        assert is_retryable(_make_api_error(402)) is False

    def test_404_not_retryable(self):
        assert is_retryable(_make_api_error(404)) is False

    def test_422_not_retryable(self):
        assert is_retryable(_make_api_error(422)) is False

    def test_cancelled_error_not_retryable(self):
        assert is_retryable(asyncio.CancelledError()) is False

    def test_keyboard_interrupt_not_retryable(self):
        assert is_retryable(KeyboardInterrupt()) is False

    def test_timeout_error_retryable(self):
        assert is_retryable(asyncio.TimeoutError()) is True

    def test_connection_error_retryable(self):
        assert is_retryable(ConnectionError("reset")) is True

    def test_os_error_retryable(self):
        assert is_retryable(OSError("network unreachable")) is True

    def test_wrapped_connection_error_retryable(self):
        """pydantic_ai wraps ConnectionError in ModelAPIError (RuntimeError).
        Our engine must detect the __cause__ chain."""
        wrapper = RuntimeError("Connection error.")
        wrapper.__cause__ = ConnectionError("nodename nor servname provided")
        assert is_retryable(wrapper) is True

    def test_wrapped_os_error_retryable(self):
        """Wrapped OSError via __context__ should also be retryable."""
        wrapper = RuntimeError("Network failure")
        wrapper.__context__ = OSError("network unreachable")
        assert is_retryable(wrapper) is True

    def test_deep_chain_connection_error_retryable(self):
        """Real chain: ModelAPIError -> APIConnectionError -> httpx.ConnectError -> OSError.
        Must walk the full chain to find the stdlib OSError at the root."""
        os_error = OSError("nodename nor servname provided")
        httpx_error = Exception("Connect error")  # simulates httpx.ConnectError
        httpx_error.__cause__ = os_error
        sdk_error = Exception("Connection error")  # simulates SDK APIConnectionError
        sdk_error.__cause__ = httpx_error
        model_error = RuntimeError("Connection error.")  # simulates ModelAPIError
        model_error.__cause__ = sdk_error
        assert is_retryable(model_error) is True

    def test_x_should_retry_false_overrides(self):
        err = _make_api_error(500, headers={"x-should-retry": "false"})
        assert is_retryable(err) is False

    def test_x_should_retry_true_overrides(self):
        err = _make_api_error(400, headers={"x-should-retry": "true"})
        assert is_retryable(err) is True

    def test_unknown_error_no_status_not_retryable(self):
        """Unknown errors with no status code are NOT retried."""
        assert is_retryable(Exception("mysterious error")) is False

    def test_streaming_error_retryable(self):
        """Transient streaming errors (pydantic_ai) are retried."""
        err = Exception("Streamed response ended without content")
        assert is_retryable(err) is True
        err2 = Exception("Streamed response ended without content or tool calls")
        assert is_retryable(err2) is True

    def test_validation_error_not_retryable(self):
        """Schema/validation errors are fatal — never retried."""
        assert is_retryable(Exception("Schema validation failed")) is False
        assert is_retryable(Exception("Response validation error")) is False

    def test_overloaded_body_retryable(self):
        err = Exception('{"type":"overloaded_error"}')
        assert is_retryable(err) is True


# ---------------------------------------------------------------------------
# _cancellable_sleep
# ---------------------------------------------------------------------------
class TestCancellableSleep:
    @pytest.mark.asyncio
    async def test_normal_sleep(self):
        """Sleep completes normally without cancel event."""
        await _cancellable_sleep(0.01, cancel_event=None)

    @pytest.mark.asyncio
    async def test_cancel_interrupts(self):
        """Setting the event during sleep raises CancelledError."""
        event = asyncio.Event()

        async def set_after_delay():
            await asyncio.sleep(0.01)
            event.set()

        asyncio.create_task(set_after_delay())
        with pytest.raises(asyncio.CancelledError):
            await _cancellable_sleep(10.0, cancel_event=event)

    @pytest.mark.asyncio
    async def test_already_set_event(self):
        """If event is already set, raises immediately."""
        event = asyncio.Event()
        event.set()
        with pytest.raises(asyncio.CancelledError):
            await _cancellable_sleep(10.0, cancel_event=event)


# ---------------------------------------------------------------------------
# llm_run_with_retry
# ---------------------------------------------------------------------------
class TestLLMRunWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        """Succeeds on first attempt — no retries needed."""
        factory = AsyncMock(return_value="result")
        result = await llm_run_with_retry(factory, config=LLMRetryConfig(max_retries=3))
        assert result == "result"
        assert factory.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_succeed(self):
        """Fails with 429, then succeeds on second attempt."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_api_error(429)
            return "recovered"

        with patch("code_puppy.llm_retry._compute_backoff", return_value=0.001):
            result = await llm_run_with_retry(
                factory, config=LLMRetryConfig(max_retries=3)
            )
        assert result == "recovered"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """All retries fail — raises RetryExhaustedError."""

        async def factory():
            raise _make_api_error(500)

        with patch("code_puppy.llm_retry._compute_backoff", return_value=0.001):
            with pytest.raises(RetryExhaustedError) as exc_info:
                await llm_run_with_retry(factory, config=LLMRetryConfig(max_retries=2))
        assert exc_info.value.original_error.status_code == 500

    @pytest.mark.asyncio
    async def test_fatal_error_not_retried(self):
        """Non-retryable error raises immediately without retry."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            raise _make_api_error(400, "bad request")

        with pytest.raises(Exception, match="bad request"):
            await llm_run_with_retry(factory, config=LLMRetryConfig(max_retries=5))
        assert call_count == 1  # No retry — failed on first attempt

    @pytest.mark.asyncio
    async def test_cancelled_error_propagates(self):
        """CancelledError is never swallowed."""

        async def factory():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await llm_run_with_retry(factory, config=LLMRetryConfig(max_retries=5))

    @pytest.mark.asyncio
    async def test_consecutive_529_exhaustion(self):
        """3 consecutive 529s raises RetryExhaustedError early."""

        async def factory():
            raise _make_overloaded_error()

        with patch("code_puppy.llm_retry._compute_backoff", return_value=0.001):
            with pytest.raises(RetryExhaustedError, match="overloaded"):
                await llm_run_with_retry(
                    factory,
                    config=LLMRetryConfig(max_retries=10),
                )

    @pytest.mark.asyncio
    async def test_overload_counter_resets(self):
        """Non-overload errors reset the consecutive overload counter."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_overloaded_error()  # 2 overloads
            if call_count == 3:
                raise _make_api_error(500)  # resets counter
            if call_count <= 5:
                raise _make_overloaded_error()  # 2 more overloads
            return "ok"

        with patch("code_puppy.llm_retry._compute_backoff", return_value=0.001):
            result = await llm_run_with_retry(
                factory, config=LLMRetryConfig(max_retries=10)
            )
        assert result == "ok"
        assert call_count == 6

    @pytest.mark.asyncio
    async def test_retry_after_header_respected(self):
        """Retry-After header value flows into backoff calculation."""
        call_count = 0

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise _make_api_error(429, headers={"retry-after": "1.5"})
            return "ok"

        with patch(
            "code_puppy.llm_retry._compute_backoff", return_value=0.001
        ) as backoff:
            result = await llm_run_with_retry(
                factory, config=LLMRetryConfig(max_retries=3)
            )
        backoff.assert_called_once_with(1, 1.5)
        assert result == "ok"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_api_retry_callbacks_fired(self):
        """api_retry_start callback is triggered before each retry sleep."""
        call_count = 0
        callback_calls = []

        async def factory():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_api_error(503)
            return "ok"

        async def mock_trigger(phase, **kwargs):
            callback_calls.append((phase, kwargs))
            return []

        with (
            patch("code_puppy.llm_retry._compute_backoff", return_value=0.001),
            patch(
                "code_puppy.callbacks._trigger_callbacks",
                side_effect=mock_trigger,
            ),
        ):
            result = await llm_run_with_retry(
                factory, config=LLMRetryConfig(max_retries=5)
            )

        assert result == "ok"
        # 2 retries → 2 api_retry_start + 1 api_retry_end
        start_calls = [c for c in callback_calls if c[0] == "api_retry_start"]
        end_calls = [c for c in callback_calls if c[0] == "api_retry_end"]
        assert len(start_calls) == 2
        assert len(end_calls) == 1

    @pytest.mark.asyncio
    async def test_config_from_env(self):
        """PUPPY_MAX_LLM_RETRIES env var overrides default."""
        with patch.dict("os.environ", {"PUPPY_MAX_LLM_RETRIES": "2"}):
            config = LLMRetryConfig()
            assert config.max_retries == 2

    @pytest.mark.asyncio
    async def test_config_invalid_env(self):
        """Invalid env var falls back to default."""
        with patch.dict("os.environ", {"PUPPY_MAX_LLM_RETRIES": "not-a-number"}):
            config = LLMRetryConfig()
            assert config.max_retries == 10

    @pytest.mark.asyncio
    async def test_config_negative_env(self):
        """Negative env var falls back to default."""
        with patch.dict("os.environ", {"PUPPY_MAX_LLM_RETRIES": "-3"}):
            config = LLMRetryConfig()
            assert config.max_retries == 10

    @pytest.mark.asyncio
    async def test_default_config(self):
        """Default config uses sensible defaults."""
        config = LLMRetryConfig()
        assert config.max_retries == 10
        assert config.cancel_event is None
