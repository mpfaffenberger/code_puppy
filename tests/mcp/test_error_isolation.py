"""
Comprehensive tests for code_puppy/mcp_/error_isolation.py

This module tests the error isolation system that prevents MCP server
errors from crashing the application, including quarantine logic and
exponential backoff.
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from code_puppy.mcp_.error_isolation import (
    ErrorCategory,
    ErrorStats,
    MCPErrorIsolator,
    QuarantinedServerError,
    get_error_isolator,
)


class TestErrorStats:
    """Test cases for ErrorStats dataclass."""

    def test_initialization_defaults(self):
        """Test ErrorStats initializes with correct defaults."""
        stats = ErrorStats()
        assert stats.total_errors == 0
        assert stats.consecutive_errors == 0
        assert stats.last_error is None
        assert stats.error_types == {}
        assert stats.quarantine_count == 0
        assert stats.quarantine_until is None

    def test_initialization_with_values(self):
        """Test ErrorStats initializes with provided values."""
        now = datetime.now()
        stats = ErrorStats(
            total_errors=5,
            consecutive_errors=2,
            last_error=now,
            error_types={"network": 3, "protocol": 2},
            quarantine_count=1,
            quarantine_until=now + timedelta(minutes=1),
        )
        assert stats.total_errors == 5
        assert stats.consecutive_errors == 2
        assert stats.last_error == now
        assert stats.error_types == {"network": 3, "protocol": 2}
        assert stats.quarantine_count == 1
        assert stats.quarantine_until is not None

    def test_error_types_incrementation(self):
        """Test error_types dict can be incremented."""
        stats = ErrorStats()
        stats.error_types["network"] = stats.error_types.get("network", 0) + 1
        stats.error_types["network"] = stats.error_types.get("network", 0) + 1
        assert stats.error_types["network"] == 2


class TestErrorCategory:
    """Test cases for ErrorCategory enum."""

    def test_all_categories_exist(self):
        """Test all expected error categories exist."""
        assert ErrorCategory.NETWORK.value == "network"
        assert ErrorCategory.PROTOCOL.value == "protocol"
        assert ErrorCategory.SERVER.value == "server"
        assert ErrorCategory.RATE_LIMIT.value == "rate_limit"
        assert ErrorCategory.AUTHENTICATION.value == "authentication"
        assert ErrorCategory.UNKNOWN.value == "unknown"

    def test_category_iteration(self):
        """Test all categories can be iterated."""
        categories = list(ErrorCategory)
        assert len(categories) == 6


class TestMCPErrorIsolator:
    """Test cases for MCPErrorIsolator class."""

    def setup_method(self):
        """Setup for each test method."""
        self.isolator = MCPErrorIsolator(
            quarantine_threshold=3, max_quarantine_minutes=30
        )

    def test_initialization(self):
        """Test isolator initializes with correct parameters."""
        assert self.isolator.quarantine_threshold == 3
        assert self.isolator.max_quarantine_duration == timedelta(minutes=30)
        assert self.isolator.server_stats == {}
        assert self.isolator._lock is not None

    def test_initialization_with_custom_parameters(self):
        """Test isolator with custom parameters."""
        isolator = MCPErrorIsolator(quarantine_threshold=5, max_quarantine_minutes=60)
        assert isolator.quarantine_threshold == 5
        assert isolator.max_quarantine_duration == timedelta(minutes=60)

    @pytest.mark.asyncio
    async def test_isolated_call_sync_success(self):
        """Test isolated_call with successful sync function."""
        mock_func = Mock(return_value="success")

        result = await self.isolator.isolated_call("server-1", mock_func)

        assert result == "success"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_isolated_call_sync_with_args(self):
        """Test isolated_call with sync function and arguments."""
        mock_func = Mock(return_value="result")

        result = await self.isolator.isolated_call(
            "server-1", mock_func, "arg1", "arg2", key="value"
        )

        assert result == "result"
        mock_func.assert_called_once_with("arg1", "arg2", key="value")

    @pytest.mark.asyncio
    async def test_isolated_call_async_success(self):
        """Test isolated_call with successful async function."""
        mock_func = AsyncMock(return_value="async_result")

        result = await self.isolator.isolated_call("server-2", mock_func)

        assert result == "async_result"
        mock_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_isolated_call_async_with_args(self):
        """Test isolated_call with async function and arguments."""
        mock_func = AsyncMock(return_value="async_result")

        result = await self.isolator.isolated_call(
            "server-2", mock_func, "arg1", key="value"
        )

        assert result == "async_result"
        mock_func.assert_called_once_with("arg1", key="value")

    @pytest.mark.asyncio
    async def test_isolated_call_sync_failure(self):
        """Test isolated_call records error on sync function failure."""
        mock_func = Mock(side_effect=ValueError("Test error"))

        with pytest.raises(ValueError):
            await self.isolator.isolated_call("server-3", mock_func)

        # Check error was recorded
        stats = self.isolator.get_error_stats("server-3")
        assert stats.total_errors == 1
        assert stats.consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_isolated_call_async_failure(self):
        """Test isolated_call records error on async function failure."""
        mock_func = AsyncMock(side_effect=RuntimeError("Async error"))

        with pytest.raises(RuntimeError):
            await self.isolator.isolated_call("server-4", mock_func)

        # Check error was recorded
        stats = self.isolator.get_error_stats("server-4")
        assert stats.total_errors == 1
        assert stats.consecutive_errors == 1

    @pytest.mark.asyncio
    async def test_isolated_call_success_resets_consecutive_errors(self):
        """Test successful call resets consecutive error count."""
        mock_func_fail = Mock(side_effect=ValueError("Error"))
        mock_func_success = Mock(return_value="success")

        # First call fails
        with pytest.raises(ValueError):
            await self.isolator.isolated_call("server-5", mock_func_fail)

        # Second call succeeds
        result = await self.isolator.isolated_call("server-5", mock_func_success)

        assert result == "success"
        stats = self.isolator.get_error_stats("server-5")
        assert stats.consecutive_errors == 0
        assert stats.total_errors == 1

    @pytest.mark.asyncio
    async def test_isolated_call_quarantined_server_raises_error(self):
        """Test isolated_call raises error for quarantined server."""
        # Manually quarantine a server
        await self.isolator.quarantine_server("server-6", 10)

        mock_func = Mock(return_value="success")

        with pytest.raises(QuarantinedServerError):
            await self.isolator.isolated_call("server-6", mock_func)

        # Verify function was never called
        mock_func.assert_not_called()

    @pytest.mark.asyncio
    async def test_quarantine_server(self):
        """Test manual server quarantine."""
        await self.isolator.quarantine_server("server-7", 60)

        stats = self.isolator.get_error_stats("server-7")
        assert stats.quarantine_count == 1
        assert stats.quarantine_until is not None

    @pytest.mark.asyncio
    async def test_quarantine_server_multiple_times(self):
        """Test server can be quarantined multiple times."""
        await self.isolator.quarantine_server("server-8", 30)
        await self.isolator.quarantine_server("server-8", 60)

        stats = self.isolator.get_error_stats("server-8")
        assert stats.quarantine_count == 2

    @pytest.mark.asyncio
    async def test_release_quarantine(self):
        """Test releasing server from quarantine."""
        await self.isolator.quarantine_server("server-9", 60)
        assert self.isolator.is_quarantined("server-9")

        await self.isolator.release_quarantine("server-9")
        assert not self.isolator.is_quarantined("server-9")

    @pytest.mark.asyncio
    async def test_release_quarantine_nonexistent_server(self):
        """Test releasing quarantine for nonexistent server doesn't error."""
        # Should not raise
        await self.isolator.release_quarantine("nonexistent")

    def test_is_quarantined_true(self):
        """Test is_quarantined returns True for quarantined server."""
        stats = ErrorStats()
        stats.quarantine_until = datetime.now() + timedelta(minutes=1)
        self.isolator.server_stats["server-10"] = stats

        assert self.isolator.is_quarantined("server-10") is True

    def test_is_quarantined_false_no_quarantine(self):
        """Test is_quarantined returns False when not quarantined."""
        assert self.isolator.is_quarantined("server-11") is False

    def test_is_quarantined_false_expired_quarantine(self):
        """Test is_quarantined returns False for expired quarantine."""
        stats = ErrorStats()
        stats.quarantine_until = datetime.now() - timedelta(seconds=1)
        self.isolator.server_stats["server-12"] = stats

        assert self.isolator.is_quarantined("server-12") is False
        # Verify quarantine_until was cleared
        assert stats.quarantine_until is None

    def test_get_error_stats_existing_server(self):
        """Test getting error stats for existing server."""
        stats_obj = ErrorStats(total_errors=5)
        self.isolator.server_stats["server-13"] = stats_obj

        stats = self.isolator.get_error_stats("server-13")
        assert stats == stats_obj
        assert stats.total_errors == 5

    def test_get_error_stats_nonexistent_server(self):
        """Test getting error stats for nonexistent server returns empty stats."""
        stats = self.isolator.get_error_stats("server-14")
        assert stats.total_errors == 0
        assert stats.consecutive_errors == 0

    def test_should_quarantine_false_below_threshold(self):
        """Test should_quarantine returns False below threshold."""
        stats = ErrorStats(consecutive_errors=2)  # Below threshold of 3
        self.isolator.server_stats["server-15"] = stats

        assert self.isolator.should_quarantine("server-15") is False

    def test_should_quarantine_true_at_threshold(self):
        """Test should_quarantine returns True at threshold."""
        stats = ErrorStats(consecutive_errors=3)  # At threshold
        self.isolator.server_stats["server-16"] = stats

        assert self.isolator.should_quarantine("server-16") is True

    def test_should_quarantine_true_above_threshold(self):
        """Test should_quarantine returns True above threshold."""
        stats = ErrorStats(consecutive_errors=5)  # Above threshold
        self.isolator.server_stats["server-17"] = stats

        assert self.isolator.should_quarantine("server-17") is True

    def test_should_quarantine_nonexistent_server(self):
        """Test should_quarantine returns False for nonexistent server."""
        assert self.isolator.should_quarantine("server-18") is False

    @pytest.mark.asyncio
    async def test_record_success(self):
        """Test recording successful call resets consecutive errors."""
        stats = ErrorStats(consecutive_errors=5, total_errors=5)
        self.isolator.server_stats["server-19"] = stats

        await self.isolator._record_success("server-19")

        assert stats.consecutive_errors == 0
        assert stats.total_errors == 5  # total_errors not changed

    @pytest.mark.asyncio
    async def test_record_error_increments_counters(self):
        """Test recording error increments error counters."""
        error = ValueError("Test error")

        await self.isolator._record_error("server-20", error)

        stats = self.isolator.get_error_stats("server-20")
        assert stats.total_errors == 1
        assert stats.consecutive_errors == 1
        assert stats.last_error is not None

    @pytest.mark.asyncio
    async def test_record_error_categorization(self):
        """Test recording error categorizes the error type."""
        error = ConnectionError("Connection failed")

        await self.isolator._record_error("server-21", error)

        stats = self.isolator.get_error_stats("server-21")
        assert "network" in stats.error_types
        assert stats.error_types["network"] == 1

    @pytest.mark.asyncio
    async def test_record_error_multiple_same_type(self):
        """Test recording multiple errors of same type increments counter."""
        error = ConnectionError("Connection failed")

        await self.isolator._record_error("server-22", error)
        await self.isolator._record_error("server-22", error)

        stats = self.isolator.get_error_stats("server-22")
        assert stats.error_types["network"] == 2

    @pytest.mark.asyncio
    async def test_record_error_triggers_quarantine_at_threshold(self):
        """Test recording error triggers quarantine at threshold."""
        error = ValueError("Test error")

        # Record errors up to threshold
        for i in range(3):
            await self.isolator._record_error("server-23", error)

        stats = self.isolator.get_error_stats("server-23")
        assert stats.consecutive_errors == 3
        assert stats.quarantine_until is not None
        assert stats.quarantine_count == 1

    def test_categorize_error_network_by_type(self):
        """Test error categorization for network errors by type."""
        errors = [
            ConnectionError("Connection failed"),
            TimeoutError("Timeout"),
            OSError("Network error"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.NETWORK

    def test_categorize_error_network_by_message(self):
        """Test error categorization for network errors by message."""
        errors = [
            Exception("Connection refused"),
            Exception("Network unreachable"),
            Exception("Connection timeout"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.NETWORK

    def test_categorize_error_protocol_by_type(self):
        """Test error categorization for protocol errors by type."""
        errors = [
            ValueError("json error"),
            RuntimeError("parse error"),
            TypeError("decode error"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.PROTOCOL

    def test_categorize_error_protocol_by_message(self):
        """Test error categorization for protocol errors by message."""
        errors = [
            Exception("Invalid json format"),
            Exception("Malformed schema"),
            Exception("Failed to parse response"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.PROTOCOL

    def test_categorize_error_authentication(self):
        """Test error categorization for authentication errors."""
        errors = [
            Exception("401 unauthorized"),
            Exception("403 forbidden"),
            Exception("Authentication failed"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.AUTHENTICATION

    def test_categorize_error_rate_limit(self):
        """Test error categorization for rate limit errors."""
        errors = [
            Exception("429 too many requests"),
            Exception("Rate limit exceeded"),
            Exception("Throttle detected"),
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.RATE_LIMIT

    def test_categorize_error_server(self):
        """Test error categorization for server errors."""
        errors = [
            Exception("500 internal server error"),
            Exception("502 error"),  # Contains 502 status code
            Exception("503 service unavailable"),
            Exception("501 not implemented"),  # Contains 501 status code
        ]

        for error in errors:
            category = self.isolator._categorize_error(error)
            assert category == ErrorCategory.SERVER

    def test_categorize_error_unknown(self):
        """Test error categorization defaults to unknown."""
        error = Exception("Some random error")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.UNKNOWN

    def test_categorize_error_protocol_by_message_decode(self):
        """Test protocol error categorization by 'decode' in message."""
        error = Exception("Failed to decode response")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.PROTOCOL

    def test_categorize_error_authentication_by_type(self):
        """Test authentication error by error type name."""

        # Create a custom exception with 'auth' in the name
        class AuthenticationError(Exception):
            pass

        error = AuthenticationError("Auth failed")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.AUTHENTICATION

    def test_categorize_error_rate_limit_by_message(self):
        """Test rate limit error categorization by '429' in message."""
        error = Exception("HTTP 429 Too Many Requests")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.RATE_LIMIT

    def test_categorize_error_server_by_type(self):
        """Test server error categorization by error type name."""

        class ServerError(Exception):
            pass

        error = ServerError("Server crashed")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.SERVER

    def test_categorize_error_rate_limit_by_type(self):
        """Test rate limit error categorization by error type name."""

        class RateLimitError(Exception):
            pass

        error = RateLimitError("Too many requests")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.RATE_LIMIT

    def test_categorize_error_protocol_by_message_json(self):
        """Test protocol error categorization by 'json' in message."""
        error = Exception("Invalid json received")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.PROTOCOL

    def test_categorize_error_protocol_by_message_malformed(self):
        """Test protocol error categorization by 'malformed' in message."""
        error = Exception("Malformed request body")
        category = self.isolator._categorize_error(error)
        assert category == ErrorCategory.PROTOCOL

    def test_calculate_quarantine_duration_first_quarantine(self):
        """Test quarantine duration for first quarantine."""
        # quarantine_count = 0 => 30 * 2^0 = 30 seconds
        duration = self.isolator._calculate_quarantine_duration(0)
        assert duration == 30

    def test_calculate_quarantine_duration_exponential_backoff(self):
        """Test exponential backoff increases quarantine duration."""
        # quarantine_count = 0 => 30 * 2^0 = 30
        # quarantine_count = 1 => 30 * 2^1 = 60
        # quarantine_count = 2 => 30 * 2^2 = 120
        # quarantine_count = 3 => 30 * 2^3 = 240
        assert self.isolator._calculate_quarantine_duration(0) == 30
        assert self.isolator._calculate_quarantine_duration(1) == 60
        assert self.isolator._calculate_quarantine_duration(2) == 120
        assert self.isolator._calculate_quarantine_duration(3) == 240

    def test_calculate_quarantine_duration_capped_at_max(self):
        """Test quarantine duration is capped at maximum."""
        # max_quarantine_minutes = 30, so max_seconds = 1800
        # quarantine_count = 10 => 30 * 2^10 = 30720 > 1800, should be capped
        duration = self.isolator._calculate_quarantine_duration(10)
        max_seconds = int(self.isolator.max_quarantine_duration.total_seconds())
        assert duration == max_seconds
        assert duration == 1800

    def test_get_or_create_stats_new_server(self):
        """Test getting or creating stats for new server."""
        stats = self.isolator._get_or_create_stats("server-24")
        assert stats.total_errors == 0
        assert "server-24" in self.isolator.server_stats

    def test_get_or_create_stats_existing_server(self):
        """Test getting existing stats returns same object."""
        original_stats = ErrorStats(total_errors=5)
        self.isolator.server_stats["server-25"] = original_stats

        stats = self.isolator._get_or_create_stats("server-25")
        assert stats is original_stats

    @pytest.mark.asyncio
    async def test_concurrent_isolated_calls(self):
        """Test isolated_call handles concurrent calls correctly."""

        async def slow_func(delay):
            await asyncio.sleep(delay)
            return f"result-{delay}"

        # Create tasks for concurrent calls
        tasks = [
            self.isolator.isolated_call(f"server-{i}", slow_func, 0.01)
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 5
        assert all(r.startswith("result-") for r in results)

    @pytest.mark.asyncio
    async def test_isolated_call_with_multiple_failures_triggers_quarantine(self):
        """Test multiple failures eventually trigger quarantine."""
        mock_func = Mock(side_effect=ValueError("Error"))

        # Make multiple calls that fail
        for i in range(3):
            with pytest.raises(ValueError):
                await self.isolator.isolated_call("server-26", mock_func)

        # Server should be quarantined now
        assert self.isolator.is_quarantined("server-26")

        # Next call should fail with QuarantinedServerError
        with pytest.raises(QuarantinedServerError):
            await self.isolator.isolated_call("server-26", mock_func)


class TestQuarantinedServerError:
    """Test cases for QuarantinedServerError exception."""

    def test_exception_can_be_raised(self):
        """Test QuarantinedServerError can be raised and caught."""
        with pytest.raises(QuarantinedServerError):
            raise QuarantinedServerError("Server is quarantined")

    def test_exception_message(self):
        """Test QuarantinedServerError preserves message."""
        message = "Server test-server is quarantined"
        with pytest.raises(QuarantinedServerError) as exc_info:
            raise QuarantinedServerError(message)

        assert str(exc_info.value) == message

    def test_exception_is_subclass_of_exception(self):
        """Test QuarantinedServerError is an Exception subclass."""
        assert issubclass(QuarantinedServerError, Exception)


class TestGetErrorIsolator:
    """Test cases for get_error_isolator singleton."""

    def teardown_method(self):
        """Clean up after each test."""
        # Reset the global isolator instance
        import code_puppy.mcp_.error_isolation as error_isolation_module

        error_isolation_module._isolator_instance = None

    def test_get_error_isolator_returns_instance(self):
        """Test get_error_isolator returns MCPErrorIsolator instance."""
        isolator = get_error_isolator()
        assert isinstance(isolator, MCPErrorIsolator)

    def test_get_error_isolator_singleton_behavior(self):
        """Test get_error_isolator returns same instance on multiple calls."""
        isolator1 = get_error_isolator()
        isolator2 = get_error_isolator()
        assert isolator1 is isolator2

    def test_get_error_isolator_creates_instance_on_first_call(self):
        """Test get_error_isolator creates instance on first call."""
        isolator = get_error_isolator()
        assert isolator is not None
        assert isinstance(isolator, MCPErrorIsolator)


class TestErrorIsolationIntegration:
    """Integration tests for error isolation system."""

    @pytest.mark.asyncio
    async def test_full_error_lifecycle(self):
        """Test full lifecycle: success -> failures -> quarantine -> recovery."""
        isolator = MCPErrorIsolator(quarantine_threshold=2, max_quarantine_minutes=30)
        mock_func = Mock(return_value="success")
        mock_func_fail = Mock(side_effect=ValueError("Error"))
        mock_func_success_again = Mock(return_value="recovered")

        # 1. Initial successful call
        result = await isolator.isolated_call("server", mock_func)
        assert result == "success"
        stats = isolator.get_error_stats("server")
        assert stats.consecutive_errors == 0

        # 2. Two failures trigger quarantine
        with pytest.raises(ValueError):
            await isolator.isolated_call("server", mock_func_fail)

        with pytest.raises(ValueError):
            await isolator.isolated_call("server", mock_func_fail)

        assert isolator.is_quarantined("server")
        stats = isolator.get_error_stats("server")
        assert stats.consecutive_errors == 2
        assert stats.quarantine_count == 1

        # 3. Verify server is quarantined
        with pytest.raises(QuarantinedServerError):
            await isolator.isolated_call("server", mock_func_success_again)

        # 4. Release quarantine
        await isolator.release_quarantine("server")
        assert not isolator.is_quarantined("server")

        # 5. Successful call after release resets consecutive errors
        result = await isolator.isolated_call("server", mock_func_success_again)
        assert result == "recovered"
        stats = isolator.get_error_stats("server")
        assert stats.consecutive_errors == 0
        assert stats.total_errors == 2  # Original failures still counted

    @pytest.mark.asyncio
    async def test_multiple_servers_isolation(self):
        """Test error isolation is per-server, not global."""
        isolator = MCPErrorIsolator(quarantine_threshold=1, max_quarantine_minutes=30)

        mock_fail = Mock(side_effect=ValueError("Error"))
        mock_success = Mock(return_value="success")

        # Fail on server1
        with pytest.raises(ValueError):
            await isolator.isolated_call("server1", mock_fail)

        # server2 should still work
        result = await isolator.isolated_call("server2", mock_success)
        assert result == "success"

        # server1 should be quarantined
        assert isolator.is_quarantined("server1")
        assert not isolator.is_quarantined("server2")

    @pytest.mark.asyncio
    async def test_error_stats_accumulation(self):
        """Test error statistics accumulate correctly across multiple errors."""
        isolator = MCPErrorIsolator(quarantine_threshold=5, max_quarantine_minutes=30)
        mock_func = Mock(
            side_effect=[
                ConnectionError("network error"),
                ValueError("protocol error"),
                RuntimeError("server error"),
            ]
        )

        for i in range(3):
            with pytest.raises(Exception):
                await isolator.isolated_call("server", mock_func)

        stats = isolator.get_error_stats("server")
        assert stats.total_errors == 3
        assert stats.consecutive_errors == 3
        assert len(stats.error_types) >= 1  # At least one error type recorded
