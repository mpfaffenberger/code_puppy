"""Click strategy selection logic."""

from .selector import (
    ClickStrategy,
    StrategyAttempt,
    StrategyConfig,
    DEFAULT_STRATEGY_CONFIG,
    select_next_strategy,
    should_retry_strategy,
    calculate_fallback_order,
    is_strategy_enabled,
)

__all__ = [
    "ClickStrategy",
    "StrategyAttempt",
    "StrategyConfig",
    "DEFAULT_STRATEGY_CONFIG",
    "select_next_strategy",
    "should_retry_strategy",
    "calculate_fallback_order",
    "is_strategy_enabled",
]
