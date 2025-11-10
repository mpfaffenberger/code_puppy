"""Pure logic for click strategy selection and fallback.

This module contains the decision logic for which click strategy to use,
separated from I/O operations for easy testing.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class ClickStrategy(Enum):
    """Available click strategies in priority order."""

    ACCESSIBILITY = "accessibility"
    OCR = "ocr"
    MANUAL = "manual"


@dataclass
class StrategyAttempt:
    """Record of a strategy attempt."""

    strategy: ClickStrategy
    success: bool
    error_message: Optional[str] = None
    elapsed_time: float = 0.0


@dataclass
class StrategyConfig:
    """Configuration for click strategy fallback."""

    enabled_strategies: List[ClickStrategy]
    timeout_seconds: float = 5.0
    max_retries_per_strategy: int = 3


DEFAULT_STRATEGY_CONFIG = StrategyConfig(
    enabled_strategies=[
        ClickStrategy.ACCESSIBILITY,
        ClickStrategy.OCR,
        ClickStrategy.MANUAL,
    ],
    timeout_seconds=5.0,
    max_retries_per_strategy=3,
)


def select_next_strategy(
    attempted: List[StrategyAttempt],
    config: StrategyConfig,
    elapsed_time: float,
) -> Optional[ClickStrategy]:
    """Select the next click strategy to attempt.

    Decision logic:
    1. If timeout exceeded, return None
    2. Try strategies in order from config.enabled_strategies
    3. Skip already-attempted strategies
    4. Return first unattempted strategy or None

    Args:
        attempted: List of previously attempted strategies
        config: Strategy configuration
        elapsed_time: Time elapsed since start (seconds)

    Returns:
        Next strategy to attempt, or None if all exhausted or timeout
    """
    # Check timeout
    if elapsed_time >= config.timeout_seconds:
        return None

    # Get set of attempted strategies
    attempted_strategies = {attempt.strategy for attempt in attempted}

    # Find first enabled strategy that hasn't been attempted
    for strategy in config.enabled_strategies:
        if strategy not in attempted_strategies:
            return strategy

    # All strategies exhausted
    return None


def should_retry_strategy(
    strategy: ClickStrategy,
    attempts_for_strategy: List[StrategyAttempt],
    config: StrategyConfig,
) -> bool:
    """Determine if a strategy should be retried.

    Retry if:
    - Number of attempts < max_retries_per_strategy
    - AND last attempt failed

    Args:
        strategy: The strategy to check
        attempts_for_strategy: All attempts for this specific strategy
        config: Strategy configuration

    Returns:
        True if strategy should be retried, False otherwise
    """
    if not attempts_for_strategy:
        return True  # Haven't tried yet

    if len(attempts_for_strategy) >= config.max_retries_per_strategy:
        return False  # Max retries reached

    # Only retry if last attempt failed
    last_attempt = attempts_for_strategy[-1]
    return not last_attempt.success


def calculate_fallback_order(
    config: StrategyConfig,
    platform: str,
) -> List[ClickStrategy]:
    """Calculate the fallback order based on platform capabilities.

    Some platforms don't support certain strategies:
    - Linux: No accessibility API support
    - Some platforms: OCR may not be available

    Args:
        config: Strategy configuration
        platform: Platform identifier ("darwin", "win32", "linux")

    Returns:
        Ordered list of strategies to try
    """
    available_strategies = []

    for strategy in config.enabled_strategies:
        # Skip accessibility on Linux (not supported)
        if strategy == ClickStrategy.ACCESSIBILITY and platform == "linux":
            continue

        available_strategies.append(strategy)

    return available_strategies


def is_strategy_enabled(
    strategy: ClickStrategy,
    config: StrategyConfig,
) -> bool:
    """Check if a strategy is enabled in configuration.

    Args:
        strategy: Strategy to check
        config: Strategy configuration

    Returns:
        True if strategy is enabled, False otherwise
    """
    return strategy in config.enabled_strategies
