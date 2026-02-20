"""
Tests for CircuitBreaker HALF_OPEN race condition fix (code_puppy-y10).

Verifies that only one test call is allowed through at a time when the
circuit breaker is in HALF_OPEN state.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from code_puppy.mcp_.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)


class TestHalfOpenRaceCondition:
    """Test that concurrent HALF_OPEN calls are properly serialized."""

    @pytest.mark.asyncio
    async def test_concurrent_half_open_calls_rejected(self):
        """Only one call should pass through in HALF_OPEN; others get CircuitOpenError."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout=0)

        # Move to OPEN then HALF_OPEN
        cb.record_failure()
        # timeout=0 means get_state() immediately transitions to HALF_OPEN
        assert cb.get_state() == CircuitState.HALF_OPEN

        # Create a slow function that holds the "in-flight" slot
        gate = asyncio.Event()

        async def slow_func():
            await gate.wait()
            return "ok"

        # Start first call (will hold in-flight)
        task1 = asyncio.create_task(cb.call(slow_func))
        await asyncio.sleep(0.01)  # Let task1 acquire the lock and release it

        # Second concurrent call should be rejected
        with pytest.raises(CircuitOpenError, match="in flight"):
            await cb.call(AsyncMock(return_value="ignored"))

        # Let first call complete
        gate.set()
        result = await task1
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_half_open_in_flight_cleared_on_success(self):
        """After a successful half-open call, the next call should be allowed."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout=0)
        cb.record_failure()
        await asyncio.sleep(0.01)

        # First call succeeds -> transitions to CLOSED
        result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.get_state() == CircuitState.CLOSED

        # Next call should work fine (CLOSED state)
        result2 = await cb.call(AsyncMock(return_value="ok2"))
        assert result2 == "ok2"

    @pytest.mark.asyncio
    async def test_half_open_in_flight_cleared_on_failure(self):
        """After a failed half-open call, the flag resets (circuit goes OPEN)."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout=60)
        cb.record_failure()
        # Manually set to HALF_OPEN to avoid auto-transition with timeout=0
        cb._state = CircuitState.HALF_OPEN
        cb._success_count = 0

        # Half-open call fails -> back to OPEN
        with pytest.raises(RuntimeError):
            await cb.call(AsyncMock(side_effect=RuntimeError("boom")))

        assert cb._state == CircuitState.OPEN
        assert cb._half_open_in_flight is False

    @pytest.mark.asyncio
    async def test_many_concurrent_half_open_only_one_passes(self):
        """Of N concurrent half-open calls, exactly 1 passes and N-1 are rejected."""
        cb = CircuitBreaker(failure_threshold=1, success_threshold=1, timeout=0)
        cb.record_failure()
        await asyncio.sleep(0.01)

        gate = asyncio.Event()
        results = {"passed": 0, "rejected": 0}

        async def attempt():
            try:
                await cb.call(gate.wait)
                results["passed"] += 1
            except CircuitOpenError:
                results["rejected"] += 1

        tasks = [asyncio.create_task(attempt()) for _ in range(5)]
        await asyncio.sleep(0.05)  # Let all tasks try
        gate.set()
        await asyncio.gather(*tasks)

        assert results["passed"] == 1
        assert results["rejected"] == 4
