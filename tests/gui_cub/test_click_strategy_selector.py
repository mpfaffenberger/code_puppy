"""Tests for click strategy selection logic.

These tests validate the pure decision logic for selecting which click
strategy to use, separated from I/O operations.
"""

import pytest
from code_puppy.tools.gui_cub.core.click_strategy import (
    ClickStrategy,
    StrategyAttempt,
    StrategyConfig,
    DEFAULT_STRATEGY_CONFIG,
    select_next_strategy,
    should_retry_strategy,
    calculate_fallback_order,
    is_strategy_enabled,
)


class TestSelectNextStrategy:
    """Test strategy selection logic."""

    def test_returns_first_unattempted_strategy(self):
        """Should return first strategy that hasn't been attempted."""
        attempted = [
            StrategyAttempt(strategy=ClickStrategy.ACCESSIBILITY, success=False)
        ]
        config = DEFAULT_STRATEGY_CONFIG

        next_strategy = select_next_strategy(attempted, config, elapsed_time=1.0)

        assert next_strategy == ClickStrategy.OCR

    def test_returns_none_when_timeout_exceeded(self):
        """Should return None if timeout is exceeded."""
        attempted = []
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.ACCESSIBILITY],
            timeout_seconds=5.0,
        )

        next_strategy = select_next_strategy(attempted, config, elapsed_time=6.0)

        assert next_strategy is None

    def test_returns_none_when_all_strategies_attempted(self):
        """Should return None if all strategies have been tried."""
        attempted = [
            StrategyAttempt(strategy=ClickStrategy.ACCESSIBILITY, success=False),
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
            StrategyAttempt(strategy=ClickStrategy.MANUAL, success=False),
        ]
        config = DEFAULT_STRATEGY_CONFIG

        next_strategy = select_next_strategy(attempted, config, elapsed_time=2.0)

        assert next_strategy is None

    def test_skips_disabled_strategies(self):
        """Should only return enabled strategies."""
        attempted = []
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.OCR],  # Only OCR enabled
            timeout_seconds=5.0,
        )

        next_strategy = select_next_strategy(attempted, config, elapsed_time=1.0)

        assert next_strategy == ClickStrategy.OCR

    def test_respects_strategy_order(self):
        """Should return strategies in configured order."""
        attempted = []
        config = StrategyConfig(
            enabled_strategies=[
                ClickStrategy.OCR,
                ClickStrategy.ACCESSIBILITY,
                ClickStrategy.MANUAL,
            ],
            timeout_seconds=5.0,
        )

        # First call should return OCR (first in list)
        next_strategy = select_next_strategy(attempted, config, elapsed_time=1.0)
        assert next_strategy == ClickStrategy.OCR

        # After attempting OCR, should return ACCESSIBILITY (second in list)
        attempted.append(StrategyAttempt(strategy=ClickStrategy.OCR, success=False))
        next_strategy = select_next_strategy(attempted, config, elapsed_time=2.0)
        assert next_strategy == ClickStrategy.ACCESSIBILITY

    def test_exact_timeout_boundary(self):
        """Should return None at exact timeout boundary."""
        attempted = []
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.ACCESSIBILITY],
            timeout_seconds=5.0,
        )

        # Exactly at timeout
        next_strategy = select_next_strategy(attempted, config, elapsed_time=5.0)

        assert next_strategy is None


class TestShouldRetryStrategy:
    """Test retry decision logic."""

    def test_allows_retry_when_under_max_attempts(self):
        """Should allow retry if under max attempts and last failed."""
        attempts = [
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
        ]
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.OCR],
            max_retries_per_strategy=3,
        )

        should_retry = should_retry_strategy(ClickStrategy.OCR, attempts, config)

        assert should_retry is True

    def test_prevents_retry_when_max_attempts_reached(self):
        """Should prevent retry if max attempts reached."""
        attempts = [
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
        ]
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.OCR],
            max_retries_per_strategy=3,
        )

        should_retry = should_retry_strategy(ClickStrategy.OCR, attempts, config)

        assert should_retry is False

    def test_prevents_retry_when_last_attempt_succeeded(self):
        """Should not retry if last attempt succeeded."""
        attempts = [
            StrategyAttempt(strategy=ClickStrategy.OCR, success=False),
            StrategyAttempt(strategy=ClickStrategy.OCR, success=True),
        ]
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.OCR],
            max_retries_per_strategy=3,
        )

        should_retry = should_retry_strategy(ClickStrategy.OCR, attempts, config)

        assert should_retry is False

    def test_allows_first_attempt(self):
        """Should allow attempt if no previous attempts."""
        attempts = []
        config = DEFAULT_STRATEGY_CONFIG

        should_retry = should_retry_strategy(
            ClickStrategy.ACCESSIBILITY, attempts, config
        )

        assert should_retry is True


class TestCalculateFallbackOrder:
    """Test platform-specific fallback order calculation."""

    def test_includes_all_strategies_on_macos(self):
        """macOS supports all strategies."""
        config = DEFAULT_STRATEGY_CONFIG

        order = calculate_fallback_order(config, platform="darwin")

        assert ClickStrategy.ACCESSIBILITY in order
        assert ClickStrategy.OCR in order
        assert ClickStrategy.MANUAL in order

    def test_excludes_accessibility_on_linux(self):
        """Linux doesn't support accessibility API."""
        config = DEFAULT_STRATEGY_CONFIG

        order = calculate_fallback_order(config, platform="linux")

        assert ClickStrategy.ACCESSIBILITY not in order
        assert ClickStrategy.OCR in order
        assert ClickStrategy.MANUAL in order

    def test_includes_all_strategies_on_windows(self):
        """Windows supports all strategies."""
        config = DEFAULT_STRATEGY_CONFIG

        order = calculate_fallback_order(config, platform="win32")

        assert ClickStrategy.ACCESSIBILITY in order
        assert ClickStrategy.OCR in order
        assert ClickStrategy.MANUAL in order

    def test_preserves_order_from_config(self):
        """Should preserve the order from configuration."""
        config = StrategyConfig(
            enabled_strategies=[
                ClickStrategy.MANUAL,
                ClickStrategy.OCR,
                ClickStrategy.ACCESSIBILITY,
            ],
            timeout_seconds=5.0,
        )

        order = calculate_fallback_order(config, platform="darwin")

        assert order == [
            ClickStrategy.MANUAL,
            ClickStrategy.OCR,
            ClickStrategy.ACCESSIBILITY,
        ]


class TestIsStrategyEnabled:
    """Test strategy enabled check."""

    def test_returns_true_for_enabled_strategy(self):
        """Should return True if strategy is in enabled list."""
        config = DEFAULT_STRATEGY_CONFIG

        is_enabled = is_strategy_enabled(ClickStrategy.ACCESSIBILITY, config)

        assert is_enabled is True

    def test_returns_false_for_disabled_strategy(self):
        """Should return False if strategy not in enabled list."""
        config = StrategyConfig(
            enabled_strategies=[ClickStrategy.OCR],
            timeout_seconds=5.0,
        )

        is_enabled = is_strategy_enabled(ClickStrategy.ACCESSIBILITY, config)

        assert is_enabled is False


class TestDefaultStrategyConfig:
    """Test default configuration."""

    def test_has_all_strategies_enabled(self):
        """Default config should enable all strategies."""
        assert len(DEFAULT_STRATEGY_CONFIG.enabled_strategies) == 3
        assert ClickStrategy.ACCESSIBILITY in DEFAULT_STRATEGY_CONFIG.enabled_strategies
        assert ClickStrategy.OCR in DEFAULT_STRATEGY_CONFIG.enabled_strategies
        assert ClickStrategy.MANUAL in DEFAULT_STRATEGY_CONFIG.enabled_strategies

    def test_has_reasonable_timeout(self):
        """Default timeout should be reasonable."""
        assert DEFAULT_STRATEGY_CONFIG.timeout_seconds == 5.0

    def test_allows_multiple_retries(self):
        """Default should allow multiple retries per strategy."""
        assert DEFAULT_STRATEGY_CONFIG.max_retries_per_strategy == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
