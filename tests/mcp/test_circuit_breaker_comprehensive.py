"""
Comprehensive tests for CircuitBreaker state machine and behavior.

This module tests all state transitions and edge cases for the circuit breaker
pattern implementation used to protect against cascading failures in MCP servers.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest

from code_puppy.mcp_.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerInitialization:
    """Test circuit breaker initialization and state."""

    def test_initialization_default_values(self):
        """Test that circuit breaker initializes with default values."""
        cb = CircuitBreaker()
        assert cb.failure_threshold == 5
        assert cb.success_threshold == 2
        assert cb.timeout == 60
        assert cb.get_state() == CircuitState.CLOSED
        assert cb.is_closed()
        assert not cb.is_open()
        assert not cb.is_half_open()

    def test_initialization_custom_values(self):
        """Test circuit breaker with custom thresholds."""
        cb = CircuitBreaker(failure_threshold=3, success_threshold=1, timeout=10)
        assert cb.failure_threshold == 3
        assert cb.success_threshold == 1
        assert cb.timeout == 10

    def test_initial_state_is_closed(self):
        """Test that the initial state is always CLOSED."""
        for _ in range(5):
            cb = CircuitBreaker()
            assert cb.get_state() == CircuitState.CLOSED
            assert cb.is_closed()


class TestCircuitBreakerStateMethods:
    """Test state checking methods."""

    def test_is_closed_method(self):
        """Test is_closed() returns True only in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=1, timeout=1)
        assert cb.is_closed()
        cb.force_open()
        assert not cb.is_closed()
        cb.force_close()
        assert cb.is_closed()

    def test_is_open_method(self):
        """Test is_open() returns True only in OPEN state."""
        cb = CircuitBreaker()
        assert not cb.is_open()
        cb.force_open()
        assert cb.is_open()
        cb.force_close()
        assert not cb.is_open()

    def test_is_half_open_method(self):
        """Test is_half_open() returns True only in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, timeout=1)
        assert not cb.is_half_open()
        cb.force_open()
        assert not cb.is_half_open()
        # Wait for timeout to allow OPEN->HALF_OPEN transition
        time.sleep(1.1)
        assert cb.is_half_open()

    def test_get_state_method(self):
        """Test get_state() returns the correct state."""
        cb = CircuitBreaker()
        assert cb.get_state() == CircuitState.CLOSED
        cb.force_open()
        assert cb.get_state() == CircuitState.OPEN


class TestCircuitBreakerClosedToOpenTransition:
    """Test CLOSED → OPEN state transition."""

    @pytest.mark.asyncio
    async def test_closed_to_open_on_failure_threshold(self):
        """Test circuit opens after reaching failure threshold."""
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2)
        assert cb.is_closed()

        # Record failures below threshold
        await cb._on_failure()
        assert cb.is_closed()
        await cb._on_failure()
        assert cb.is_closed()

        # Reach threshold - should transition to OPEN
        await cb._on_failure()
        assert cb.is_open()
        assert cb._last_failure_time is not None

    @pytest.mark.asyncio
    async def test_closed_state_resets_failure_count_on_success(self):
        """Test that failures are forgiven by success in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2)

        # Accumulate some failures
        await cb._on_failure()
        await cb._on_failure()
        assert cb._failure_count == 2

        # Success in CLOSED state resets the failure count
        await cb._on_success()
        assert cb._failure_count == 0
        assert cb.is_closed()

    @pytest.mark.asyncio
    async def test_failure_threshold_exact_match(self):
        """Test that circuit opens on exact failure threshold match."""
        threshold = 5
        cb = CircuitBreaker(failure_threshold=threshold, success_threshold=2)

        # Record exactly threshold-1 failures
        for _ in range(threshold - 1):
            await cb._on_failure()
            assert cb.is_closed()

        # One more failure should open it
        await cb._on_failure()
        assert cb.is_open()


class TestCircuitBreakerOpenToHalfOpenTransition:
    """Test OPEN → HALF_OPEN state transition."""

    def test_open_to_half_open_after_timeout(self):
        """Test circuit transitions to HALF_OPEN after timeout."""
        timeout = 1
        cb = CircuitBreaker(failure_threshold=1, timeout=timeout)
        cb.force_open()
        assert cb.is_open()

        # Before timeout, should still be OPEN
        time.sleep(0.5)
        assert cb.is_open()

        # After timeout, should transition to HALF_OPEN
        time.sleep(0.6)  # Total 1.1 seconds
        assert cb.is_half_open()

    def test_timeout_zero_allows_immediate_recovery(self):
        """Test that timeout of 0 allows immediate recovery."""
        cb = CircuitBreaker(failure_threshold=1, timeout=0)
        cb.force_open()

        # Timeout of 0 allows immediate transition to HALF_OPEN when state is checked
        # because any elapsed time (>= 0) satisfies the timeout condition
        assert cb.is_half_open()

    def test_large_timeout_delays_recovery(self):
        """Test that large timeout delays recovery."""
        timeout = 100
        cb = CircuitBreaker(failure_threshold=1, timeout=timeout)
        cb.force_open()
        assert cb.is_open()

        # Even after 1 second, with 100s timeout, should still be OPEN
        time.sleep(1)
        assert cb.is_open()

    def test_multiple_get_state_calls_idempotent(self):
        """Test that multiple get_state() calls with timeout don't change state prematurely."""
        timeout = 2
        cb = CircuitBreaker(failure_threshold=1, timeout=timeout)
        cb.force_open()

        # Call get_state multiple times before timeout
        for _ in range(5):
            assert cb.get_state() == CircuitState.OPEN
            time.sleep(0.2)

        # After timeout, should transition
        time.sleep(1.2)
        assert cb.get_state() == CircuitState.HALF_OPEN


class TestCircuitBreakerHalfOpenTClosedTransition:
    """Test HALF_OPEN → CLOSED state transition."""

    @pytest.mark.asyncio
    async def test_half_open_to_closed_on_success_threshold(self):
        """Test circuit closes after success threshold in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=1)
        cb.force_open()
        time.sleep(1.1)
        assert cb.is_half_open()

        # Record successes below threshold
        await cb._on_success()
        assert cb.is_half_open()

        # Reach threshold - should transition to CLOSED
        await cb._on_success()
        assert cb.is_closed()
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None

    @pytest.mark.asyncio
    async def test_half_open_to_closed_success_counter_exact(self):
        """Test exact success threshold match transitions to CLOSED."""
        success_threshold = 3
        cb = CircuitBreaker(
            failure_threshold=1, success_threshold=success_threshold, timeout=1
        )
        cb.force_open()
        time.sleep(1.1)

        # Record exactly threshold-1 successes
        for _ in range(success_threshold - 1):
            await cb._on_success()
            assert cb.is_half_open()

        # One more success should close it
        await cb._on_success()
        assert cb.is_closed()

    @pytest.mark.asyncio
    async def test_half_open_state_resets_success_counter_on_transition(self):
        """Test that success counter resets when entering HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=1)
        cb.force_open()
        time.sleep(1.1)

        assert cb.is_half_open()
        assert cb._success_count == 0


class TestCircuitBreakerHalfOpenToOpenTransition:
    """Test HALF_OPEN → OPEN state transition."""

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_any_failure(self):
        """Test that any failure in HALF_OPEN returns to OPEN."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=1)
        cb.force_open()
        time.sleep(1.1)
        assert cb.is_half_open()

        # Any failure in HALF_OPEN state should transition to OPEN
        await cb._on_failure()
        assert cb.is_open()
        assert cb._success_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_updates_last_failure_time(self):
        """Test that failure in HALF_OPEN updates the failure timestamp."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=1)
        cb.force_open()
        original_time = cb._last_failure_time
        time.sleep(0.2)
        time.sleep(1.1)
        assert cb.is_half_open()

        # Record failure
        await cb._on_failure()
        assert cb.is_open()
        assert cb._last_failure_time > original_time


class TestCircuitBreakerAsyncCall:
    """Test the async call() method."""

    @pytest.mark.asyncio
    async def test_call_succeeds_in_closed_state(self):
        """Test that call() allows execution in CLOSED state."""
        cb = CircuitBreaker()
        mock_func = AsyncMock(return_value="success")

        result = await cb.call(mock_func)
        assert result == "success"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_fails_in_open_state(self):
        """Test that call() raises CircuitOpenError in OPEN state."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.force_open()

        with pytest.raises(CircuitOpenError):
            await cb.call(AsyncMock())

    @pytest.mark.asyncio
    async def test_call_with_sync_function(self):
        """Test that call() handles synchronous functions."""
        cb = CircuitBreaker()
        mock_func = Mock(return_value="sync_result")

        result = await cb.call(mock_func)
        assert result == "sync_result"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_with_arguments(self):
        """Test that call() passes arguments correctly."""
        cb = CircuitBreaker()
        mock_func = AsyncMock(return_value="result")

        await cb.call(mock_func, "arg1", "arg2", key="value")
        mock_func.assert_called_once_with("arg1", "arg2", key="value")

    @pytest.mark.asyncio
    async def test_call_propagates_exceptions(self):
        """Test that exceptions from the function are propagated."""
        cb = CircuitBreaker()
        test_exception = ValueError("Test error")
        mock_func = AsyncMock(side_effect=test_exception)

        with pytest.raises(ValueError, match="Test error"):
            await cb.call(mock_func)

    @pytest.mark.asyncio
    async def test_call_records_failure_on_exception(self):
        """Test that call() records failures when function raises."""
        cb = CircuitBreaker(failure_threshold=2)
        mock_func = AsyncMock(side_effect=Exception("Error"))

        # First call fails
        with pytest.raises(Exception):
            await cb.call(mock_func)
        assert cb.is_closed()
        assert cb._failure_count == 1

        # Second call fails and opens circuit
        with pytest.raises(Exception):
            await cb.call(mock_func)
        assert cb.is_open()

    @pytest.mark.asyncio
    async def test_call_in_half_open_state(self):
        """Test that call() works in HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, timeout=1)
        cb.force_open()
        time.sleep(1.1)

        mock_func = AsyncMock(return_value="recovery")
        result = await cb.call(mock_func)
        assert result == "recovery"
        assert cb._success_count == 1


class TestCircuitBreakerForceOperations:
    """Test force_open() and force_close() methods."""

    def test_force_open(self):
        """Test force_open() immediately opens the circuit."""
        cb = CircuitBreaker()
        assert cb.is_closed()
        cb.force_open()
        assert cb.is_open()
        assert cb._last_failure_time is not None

    def test_force_close(self):
        """Test force_close() immediately closes the circuit."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.force_open()
        assert cb.is_open()
        cb.force_close()
        assert cb.is_closed()
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None

    def test_force_open_idempotent(self):
        """Test that force_open() is idempotent."""
        cb = CircuitBreaker()
        cb.force_open()
        first_time = cb._last_failure_time
        time.sleep(0.1)
        cb.force_open()
        second_time = cb._last_failure_time
        # Second force_open should update the time
        assert second_time > first_time

    def test_force_close_idempotent(self):
        """Test that force_close() is idempotent."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.force_open()
        cb.force_close()
        assert cb.is_closed()
        cb.force_close()  # Should not raise
        assert cb.is_closed()


class TestCircuitBreakerReset:
    """Test reset() method."""

    @pytest.mark.asyncio
    async def test_reset_from_open_state(self):
        """Test reset() from OPEN state."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.force_open()
        assert cb.is_open()
        cb.reset()
        assert cb.is_closed()
        assert cb._failure_count == 0
        assert cb._success_count == 0
        assert cb._last_failure_time is None

    @pytest.mark.asyncio
    async def test_reset_from_half_open_state(self):
        """Test reset() from HALF_OPEN state."""
        cb = CircuitBreaker(failure_threshold=1, timeout=1)
        cb.force_open()
        time.sleep(1.1)
        assert cb.is_half_open()
        cb.reset()
        assert cb.is_closed()
        assert cb._failure_count == 0
        assert cb._success_count == 0

    @pytest.mark.asyncio
    async def test_reset_clears_all_counters(self):
        """Test that reset() clears all failure and success counters."""
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2)
        await cb._on_failure()
        await cb._on_failure()
        assert cb._failure_count == 2

        cb.reset()
        assert cb._failure_count == 0
        assert cb._success_count == 0


class TestCircuitBreakerRecordMethods:
    """Test record_success() and record_failure() methods."""

    @pytest.mark.asyncio
    async def test_record_success_creates_task(self):
        """Test that record_success() creates an async task."""
        cb = CircuitBreaker()
        cb.record_success()
        # Give the task time to execute
        await asyncio.sleep(0.01)
        # In CLOSED state, success resets failure count
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_record_failure_creates_task(self):
        """Test that record_failure() creates an async task."""
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        # Give the task time to execute
        await asyncio.sleep(0.01)
        assert cb._failure_count == 1

    @pytest.mark.asyncio
    async def test_record_failure_can_open_circuit(self):
        """Test that record_failure() can open the circuit."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        await asyncio.sleep(0.01)
        assert cb._failure_count == 1
        assert cb.is_closed()

        cb.record_failure()
        await asyncio.sleep(0.01)
        assert cb.is_open()


class TestCircuitBreakerEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_calls_in_closed_state(self):
        """Test that multiple concurrent calls are handled safely."""
        cb = CircuitBreaker(failure_threshold=10)
        mock_func = AsyncMock(return_value="result")

        # Run multiple concurrent calls
        tasks = [cb.call(mock_func) for _ in range(5)]
        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        assert all(r == "result" for r in results)

    @pytest.mark.asyncio
    async def test_threshold_of_one(self):
        """Test circuit breaker with threshold of 1."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1)
        mock_func = AsyncMock(side_effect=Exception("Fail"))

        # Single failure should open circuit
        with pytest.raises(Exception):
            await cb.call(mock_func)
        assert cb.is_open()

    @pytest.mark.asyncio
    async def test_alternating_successes_and_failures_in_closed(self):
        """Test alternating successes and failures in CLOSED state."""
        cb = CircuitBreaker(failure_threshold=3, success_threshold=2)

        # Failure, success, failure, success pattern
        await cb._on_failure()
        assert cb._failure_count == 1
        await cb._on_success()
        assert cb._failure_count == 0  # Reset by success
        await cb._on_failure()
        assert cb._failure_count == 1
        await cb._on_success()
        assert cb._failure_count == 0

    @pytest.mark.asyncio
    async def test_lock_prevents_race_conditions(self):
        """Test that async lock prevents race conditions."""
        cb = CircuitBreaker(failure_threshold=2, success_threshold=2)

        # Simulate rapid state changes
        tasks = [
            cb._on_failure(),
            cb._on_failure(),
            cb._on_success(),
        ]
        await asyncio.gather(*tasks)
        # Should complete without deadlock
        assert isinstance(cb.get_state(), CircuitState)

    def test_very_large_thresholds(self):
        """Test with very large threshold values."""
        cb = CircuitBreaker(
            failure_threshold=1000000, success_threshold=1000000, timeout=3600
        )
        assert cb.failure_threshold == 1000000
        assert cb.success_threshold == 1000000
        assert cb.timeout == 3600

    @pytest.mark.asyncio
    async def test_state_transitions_preserve_timestamps(self):
        """Test that state transitions properly manage timestamps."""
        cb = CircuitBreaker(failure_threshold=1, timeout=1)

        # Open the circuit
        await cb._on_failure()
        first_time = cb._last_failure_time
        assert first_time is not None

        # Transition to HALF_OPEN
        time.sleep(1.1)
        assert cb.is_half_open()

        # Failure in HALF_OPEN should update timestamp
        await cb._on_failure()
        assert cb.is_open()
        assert cb._last_failure_time > first_time

    @pytest.mark.asyncio
    async def test_success_in_closed_preserves_closure(self):
        """Test that success in CLOSED state keeps circuit closed."""
        cb = CircuitBreaker(failure_threshold=10, success_threshold=2)

        for _ in range(5):
            await cb._on_success()
            assert cb.is_closed()


class TestCircuitBreakerIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_failure_recovery_cycle(self):
        """Test complete failure and recovery cycle."""
        cb = CircuitBreaker(failure_threshold=2, success_threshold=2, timeout=1)
        failing_func = AsyncMock(side_effect=Exception("Error"))
        passing_func = AsyncMock(return_value="OK")

        # Start in CLOSED state
        assert cb.is_closed()

        # Cause failures to open circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.is_open()

        # Wait for timeout to enter HALF_OPEN
        time.sleep(1.1)
        assert cb.is_half_open()

        # Test recovery with successful calls
        result1 = await cb.call(passing_func)
        assert result1 == "OK"
        assert cb.is_half_open()

        result2 = await cb.call(passing_func)
        assert result2 == "OK"
        assert cb.is_closed()  # Back to CLOSED

    @pytest.mark.asyncio
    async def test_failure_during_recovery_reopens(self):
        """Test that failure during recovery immediately reopens circuit."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=2, timeout=1)
        failing_func = AsyncMock(side_effect=Exception("Error"))

        # Open circuit
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.is_open()

        # Transition to HALF_OPEN
        time.sleep(1.1)
        assert cb.is_half_open()

        # Any failure reopens it
        with pytest.raises(Exception):
            await cb.call(failing_func)
        assert cb.is_open()

    @pytest.mark.asyncio
    async def test_mixed_sync_async_calls(self):
        """Test circuit breaker with both sync and async functions."""
        cb = CircuitBreaker()
        sync_func = Mock(return_value="sync")
        async_func = AsyncMock(return_value="async")

        result1 = await cb.call(sync_func)
        assert result1 == "sync"

        result2 = await cb.call(async_func)
        assert result2 == "async"

        # Both should have been called
        sync_func.assert_called_once()
        async_func.assert_called_once()


class TestCircuitBreakerStateEnum:
    """Test CircuitState enum."""

    def test_circuit_state_values(self):
        """Test that CircuitState has expected values."""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_circuit_state_comparison(self):
        """Test CircuitState enum comparisons."""
        assert CircuitState.CLOSED == CircuitState.CLOSED
        assert CircuitState.CLOSED != CircuitState.OPEN
        assert CircuitState.OPEN != CircuitState.HALF_OPEN


class TestCircuitOpenException:
    """Test CircuitOpenError exception."""

    def test_circuit_open_error_is_exception(self):
        """Test that CircuitOpenError is an Exception."""
        assert issubclass(CircuitOpenError, Exception)

    def test_circuit_open_error_message(self):
        """Test CircuitOpenError can be instantiated with message."""
        error = CircuitOpenError("Custom message")
        assert str(error) == "Custom message"

    def test_circuit_open_error_can_be_caught(self):
        """Test that CircuitOpenError can be caught as Exception."""
        with pytest.raises(Exception):
            raise CircuitOpenError("Test")

        with pytest.raises(CircuitOpenError):
            raise CircuitOpenError("Test")
