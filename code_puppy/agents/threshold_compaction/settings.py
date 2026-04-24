"""Configuration scaling for threshold-driven compaction."""

from __future__ import annotations

from dataclasses import dataclass

from code_puppy.config import (
    get_threshold_compaction_archive_retention_count,
    get_threshold_compaction_archive_retention_days,
    get_threshold_compaction_emergency_trigger_ratio,
    get_threshold_compaction_growth_history_window,
    get_threshold_compaction_predicted_growth_floor_ratio,
    get_threshold_compaction_recent_raw_floor_ratio,
    get_threshold_compaction_soft_trigger_ratio,
    get_threshold_compaction_target_ratio,
)


@dataclass(slots=True)
class ThresholdSettings:
    context_window: int
    soft_trigger: int
    emergency_trigger: int
    target_after_compaction: int
    recent_raw_floor: int
    predicted_growth_floor: int
    growth_history_window: int
    archive_retention_days: int
    archive_retention_count: int
    mask_min_tokens: int


def _ratio_tokens(context_window: int, ratio: float) -> int:
    return max(1, int(round(context_window * ratio)))


def load_threshold_settings(context_window: int) -> ThresholdSettings:
    """Load percentage-based threshold settings for a model context window."""
    context_window = max(1, int(context_window or 1))
    target = _ratio_tokens(context_window, get_threshold_compaction_target_ratio())
    recent_floor = _ratio_tokens(
        context_window, get_threshold_compaction_recent_raw_floor_ratio()
    )
    return ThresholdSettings(
        context_window=context_window,
        soft_trigger=_ratio_tokens(
            context_window, get_threshold_compaction_soft_trigger_ratio()
        ),
        emergency_trigger=_ratio_tokens(
            context_window, get_threshold_compaction_emergency_trigger_ratio()
        ),
        target_after_compaction=target,
        recent_raw_floor=recent_floor,
        predicted_growth_floor=_ratio_tokens(
            context_window,
            get_threshold_compaction_predicted_growth_floor_ratio(),
        ),
        growth_history_window=get_threshold_compaction_growth_history_window(),
        archive_retention_days=get_threshold_compaction_archive_retention_days(),
        archive_retention_count=get_threshold_compaction_archive_retention_count(),
        mask_min_tokens=max(250, min(1000, int(context_window * 0.005))),
    )
