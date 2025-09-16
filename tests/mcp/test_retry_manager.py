"""
Tests for the RetryManager class.
"""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from code_puppy.mcp_.retry_manager import (
    RetryManager,
    RetryStats,
    get_retry_manager,
    retry_mcp_call,
)


class TestRetryManager:
    """Test cases for RetryManager class."""

    def setup_method(self):
        """Setup for each test method."""
        self.retry_manager = RetryManager()

    @pytest.mark.asyncio
    async def test_successful_call_no_retry(self):
        """Test that successful calls don't trigger retries."""
        mock_func = AsyncMock(return_value="success")

        result = await self.retry_manager.retry_with_backoff(
            func=mock_func,
            max_attempts=3,
            strategy="exponential",
            server_id="test-server",
        )

        assert result == "success"
        assert mock_func.call_count == 1

        # Check that no retry stats were recorded for successful first attempt
        stats = await self.retry_manager.get_retry_stats("test-server")
        assert stats.total_retries == 0

    @pytest.mark.asyncio
    async def test_retry_with_eventual_success(self):
        """Test that retries work when function eventually succeeds."""
        mock_func = AsyncMock(
            side_effect=[
                ConnectionError("Connection failed"),
                ConnectionError("Still failing"),
                "success",
            ]
        )

        result = await self.retry_manager.retry_with_backoff(
            func=mock_func, max_attempts=3, strategy="fixed", server_id="test-server"
        )

        assert result == "success"
        assert mock_func.call_count == 3

        # Check retry stats - stats are recorded after retries are attempted
        stats = await self.retry_manager.get_retry_stats("test-server")
        assert stats.total_retries == 1
        assert stats.successful_retries == 1
        assert stats.failed_retries == 0
        assert stats.average_attempts == 3.0  # All 3 attempts were made before failure

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test that function raises exception when all retries are exhausted."""
        mock_func = AsyncMock(side_effect=ConnectionError("Always failing"))

        with pytest.raises(ConnectionError):
            await self.retry_manager.retry_with_backoff(
                func=mock_func,
                max_attempts=3,
                strategy="fixed",
                server_id="test-server",
            )

        assert mock_func.call_count == 3

        # Check retry stats - stats are recorded after retries are attempted
        stats = await self.retry_manager.get_retry_stats("test-server")
        assert stats.total_retries == 1
        assert stats.successful_retries == 0
        assert stats.failed_retries == 1
        assert stats.average_attempts == 3.0  # All 3 attempts were made before failure

    @pytest.mark.asyncio
    async def test_non_retryable_error(self):
        """Test that non-retryable errors don't trigger retries."""
        # Create an HTTP 401 error (unauthorized)
        response = Mock()
        response.status_code = 401
        mock_func = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "Unauthorized", request=Mock(), response=response
            )
        )

        with pytest.raises(httpx.HTTPStatusError):
            await self.retry_manager.retry_with_backoff(
                func=mock_func,
                max_attempts=3,
                strategy="exponential",
                server_id="test-server",
            )

        assert mock_func.call_count == 1

        # Check retry stats - stats are recorded after retries are attempted
        stats = await self.retry_manager.get_retry_stats("test-server")
        assert stats.total_retries == 1
        assert stats.successful_retries == 0
        assert stats.failed_retries == 1
        assert stats.average_attempts == 1.0  # Only 1 attempt was made before giving up

    def test_calculate_backoff_fixed(self):
        """Test fixed backoff strategy."""
        assert self.retry_manager.calculate_backoff(1, "fixed") == 1.0
        assert self.retry_manager.calculate_backoff(5, "fixed") == 1.0

    def test_calculate_backoff_linear(self):
        """Test linear backoff strategy."""
        assert self.retry_manager.calculate_backoff(1, "linear") == 1.0
        assert self.retry_manager.calculate_backoff(2, "linear") == 2.0
        assert self.retry_manager.calculate_backoff(3, "linear") == 3.0

    def test_calculate_backoff_exponential(self):
        """Test exponential backoff strategy."""
        assert self.retry_manager.calculate_backoff(1, "exponential") == 1.0
        assert self.retry_manager.calculate_backoff(2, "exponential") == 2.0
        assert self.retry_manager.calculate_backoff(3, "exponential") == 4.0
        assert self.retry_manager.calculate_backoff(4, "exponential") == 8.0

    def test_calculate_backoff_exponential_jitter(self):
        """Test exponential backoff with jitter."""
        # Test multiple times to verify jitter is applied
        delays = [
            self.retry_manager.calculate_backoff(3, "exponential_jitter")
            for _ in range(10)
        ]

        # Base delay for attempt 3 should be 4.0
        # base_delay = 4.0  # Not used in this test

        # All delays should be within jitter range (±25%)
        for delay in delays:
            assert 3.0 <= delay <= 5.0  # 4.0 ± 25%
            assert delay >= 0.1  # Minimum delay

        # Should have some variation (not all the same)
        assert len(set(delays)) > 1

    def test_calculate_backoff_unknown_strategy(self):
        """Test that unknown strategy defaults to exponential."""
        assert self.retry_manager.calculate_backoff(3, "unknown") == 4.0

    def test_should_retry_retryable_errors(self):
        """Test that retryable errors are identified correctly."""
        # Network errors
        assert self.retry_manager.should_retry(ConnectionError("Connection failed"))
        assert self.retry_manager.should_retry(asyncio.TimeoutError("Timeout"))
        assert self.retry_manager.should_retry(OSError("Network error"))

        # HTTP timeout
        assert self.retry_manager.should_retry(httpx.TimeoutException("Timeout"))
        assert self.retry_manager.should_retry(httpx.ConnectError("Connect failed"))
        assert self.retry_manager.should_retry(httpx.ReadError("Read failed"))

        # Server errors (5xx)
        response_500 = Mock()
        response_500.status_code = 500
        http_error_500 = httpx.HTTPStatusError(
            "Server error", request=Mock(), response=response_500
        )
        assert self.retry_manager.should_retry(http_error_500)

        # Rate limit (429)
        response_429 = Mock()
        response_429.status_code = 429
        http_error_429 = httpx.HTTPStatusError(
            "Rate limit", request=Mock(), response=response_429
        )
        assert self.retry_manager.should_retry(http_error_429)

        # Rate limit (429) with JSON error info
        response_429_json = Mock()
        response_429_json.status_code = 429
        response_429_json.json.return_value = {
            "error": {"message": "Rate limit exceeded. Please try again later."}
        }
        http_error_429_json = httpx.HTTPStatusError(
            "Rate limit",
            request=Mock(),
            response=response_429_json,
        )
        assert self.retry_manager.should_retry(http_error_429_json)

        # Timeout (408)
        response_408 = Mock()
        response_408.status_code = 408
        http_error_408 = httpx.HTTPStatusError(
            "Request timeout", request=Mock(), response=response_408
        )
        assert self.retry_manager.should_retry(http_error_408)

        # JSON errors
        assert self.retry_manager.should_retry(ValueError("Invalid JSON format"))

    def test_should_retry_non_retryable_errors(self):
        """Test that non-retryable errors are identified correctly."""
        # Authentication errors
        response_401 = Mock()
        response_401.status_code = 401
        http_error_401 = httpx.HTTPStatusError(
            "Unauthorized", request=Mock(), response=response_401
        )
        assert not self.retry_manager.should_retry(http_error_401)

        response_403 = Mock()
        response_403.status_code = 403
        http_error_403 = httpx.HTTPStatusError(
            "Forbidden", request=Mock(), response=response_403
        )
        assert not self.retry_manager.should_retry(http_error_403)

        # Client errors (4xx except 408)
        response_400 = Mock()
        response_400.status_code = 400
        http_error_400 = httpx.HTTPStatusError(
            "Bad request", request=Mock(), response=response_400
        )
        assert not self.retry_manager.should_retry(http_error_400)

        response_404 = Mock()
        response_404.status_code = 404
        http_error_404 = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=response_404
        )
        assert not self.retry_manager.should_retry(http_error_404)

        # Schema/validation errors
        assert not self.retry_manager.should_retry(
            ValueError("Schema validation failed")
        )
        assert not self.retry_manager.should_retry(ValueError("Validation error"))

        # Authentication-related string errors
        assert not self.retry_manager.should_retry(Exception("Authentication failed"))
        assert not self.retry_manager.should_retry(Exception("Permission denied"))
        assert not self.retry_manager.should_retry(Exception("Unauthorized access"))
        assert not self.retry_manager.should_retry(Exception("Forbidden operation"))

    @pytest.mark.asyncio
    async def test_record_and_get_retry_stats(self):
        """Test recording and retrieving retry statistics."""
        # Record some retry stats
        await self.retry_manager.record_retry("server-1", 2, success=True)
        await self.retry_manager.record_retry("server-1", 3, success=False)
        await self.retry_manager.record_retry("server-2", 1, success=True)

        # Get stats for server-1
        stats = await self.retry_manager.get_retry_stats("server-1")
        assert stats.total_retries == 2
        assert stats.successful_retries == 1
        assert stats.failed_retries == 1
        assert stats.average_attempts == 2.5  # Average of 2 and 3 attempts
        assert stats.last_retry is not None

        # Get stats for server-2
        stats = await self.retry_manager.get_retry_stats("server-2")
        assert stats.total_retries == 1
        assert stats.successful_retries == 1
        assert stats.failed_retries == 0
        assert stats.average_attempts == 1.0

        # Get stats for non-existent server
        stats = await self.retry_manager.get_retry_stats("non-existent")
        assert stats.total_retries == 0

    @pytest.mark.asyncio
    async def test_get_all_stats(self):
        """Test getting all retry statistics."""
        # Record stats for multiple servers
        await self.retry_manager.record_retry("server-1", 2, success=True)
        await self.retry_manager.record_retry("server-2", 1, success=False)

        all_stats = await self.retry_manager.get_all_stats()

        assert len(all_stats) == 2
        assert "server-1" in all_stats
        assert "server-2" in all_stats
        assert all_stats["server-1"].total_retries == 1
        assert all_stats["server-2"].total_retries == 1

    @pytest.mark.asyncio
    async def test_clear_stats(self):
        """Test clearing retry statistics."""
        # Record stats
        await self.retry_manager.record_retry("server-1", 2, success=True)
        await self.retry_manager.record_retry("server-2", 1, success=False)

        # Clear stats for server-1
        await self.retry_manager.clear_stats("server-1")

        stats = await self.retry_manager.get_retry_stats("server-1")
        assert stats.total_retries == 0

        # server-2 stats should remain
        stats = await self.retry_manager.get_retry_stats("server-2")
        assert stats.total_retries == 1

    @pytest.mark.asyncio
    async def test_clear_all_stats(self):
        """Test clearing all retry statistics."""
        # Record stats
        await self.retry_manager.record_retry("server-1", 2, success=True)
        await self.retry_manager.record_retry("server-2", 1, success=False)

        # Clear all stats
        await self.retry_manager.clear_all_stats()

        all_stats = await self.retry_manager.get_all_stats()
        assert len(all_stats) == 0


class TestRetryStats:
    """Test cases for RetryStats class."""

    def test_calculate_average_first_attempt(self):
        """Test average calculation for first attempt."""
        stats = RetryStats()
        stats.calculate_average(3)
        assert stats.average_attempts == 3.0

    def test_calculate_average_multiple_attempts(self):
        """Test average calculation for multiple attempts."""
        stats = RetryStats()
        stats.total_retries = 2
        stats.average_attempts = 2.5  # (2 + 3) / 2

        stats.calculate_average(4)  # Adding a third attempt with 4 tries
        # New average: ((2.5 * 2) + 4) / 3 = (5 + 4) / 3 = 3.0
        assert stats.average_attempts == 3.0


class TestGlobalRetryManager:
    """Test cases for global retry manager functions."""

    def test_get_retry_manager_singleton(self):
        """Test that get_retry_manager returns the same instance."""
        manager1 = get_retry_manager()
        manager2 = get_retry_manager()

        assert manager1 is manager2

    @pytest.mark.asyncio
    async def test_retry_mcp_call_convenience_function(self):
        """Test the convenience function for MCP calls."""
        mock_func = AsyncMock(return_value="success")

        result = await retry_mcp_call(
            func=mock_func, server_id="test-server", max_attempts=2, strategy="linear"
        )

        assert result == "success"
        assert mock_func.call_count == 1


class TestConcurrentOperations:
    """Test cases for concurrent retry operations."""

    def setup_method(self):
        """Setup for each test method."""
        self.retry_manager = RetryManager()

    @pytest.mark.asyncio
    async def test_concurrent_retries(self):
        """Test that concurrent retries work correctly."""

        async def failing_func():
            await asyncio.sleep(0.01)  # Small delay
            raise ConnectionError("Connection failed")

        async def succeeding_func():
            await asyncio.sleep(0.01)  # Small delay
            return "success"

        # Run concurrent retries
        tasks = [
            self.retry_manager.retry_with_backoff(
                succeeding_func, max_attempts=2, strategy="fixed", server_id="server-1"
            ),
            self.retry_manager.retry_with_backoff(
                succeeding_func, max_attempts=2, strategy="fixed", server_id="server-2"
            ),
        ]

        results = await asyncio.gather(*tasks)
        assert all(result == "success" for result in results)

    @pytest.mark.asyncio
    async def test_concurrent_stats_operations(self):
        """Test that concurrent statistics operations are thread-safe."""

        async def record_stats():
            for i in range(10):
                await self.retry_manager.record_retry(
                    f"server-{i % 3}", i + 1, success=True
                )

        # Run concurrent stats recording
        await asyncio.gather(*[record_stats() for _ in range(5)])

        # Verify stats were recorded correctly
        all_stats = await self.retry_manager.get_all_stats()
        assert len(all_stats) == 3  # server-0, server-1, server-2

        # Each server should have recorded some retries
        for server_id, stats in all_stats.items():
            assert stats.total_retries > 0
            assert (
                stats.successful_retries == stats.total_retries
            )  # All were successful
