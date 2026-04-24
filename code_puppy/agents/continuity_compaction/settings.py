"""Configuration scaling for continuity compaction."""

from __future__ import annotations

from dataclasses import dataclass

from code_puppy.config import (
    get_continuity_compaction_archive_retention_count,
    get_continuity_compaction_archive_retention_days,
    get_continuity_compaction_archive_retrieval_count,
    get_continuity_compaction_archive_retrieval_enabled,
    get_continuity_compaction_emergency_trigger_ratio,
    get_continuity_compaction_growth_history_window,
    get_continuity_compaction_predicted_growth_floor_ratio,
    get_continuity_compaction_predictive_trigger_min_ratio,
    get_continuity_compaction_recent_raw_floor_ratio,
    get_continuity_compaction_soft_trigger_ratio,
    get_continuity_compaction_target_ratio,
    get_continuity_compaction_semantic_timeout_seconds,
    get_continuity_compaction_task_retention_count,
)


@dataclass(slots=True)
class ContinuityCompactionSettings:
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
    semantic_timeout_seconds: int = 60
    archive_retrieval_enabled: bool = True
    archive_retrieval_count: int = 3
    task_retention_count: int = 100
    predictive_trigger_floor: int = 0


def _ratio_tokens(context_window: int, ratio: float) -> int:
    return max(1, int(round(context_window * ratio)))


def load_continuity_compaction_settings(
    context_window: int,
) -> ContinuityCompactionSettings:
    """Load percentage-based continuity compaction settings for a model context window."""
    context_window = max(1, int(context_window or 1))
    target = _ratio_tokens(context_window, get_continuity_compaction_target_ratio())
    recent_floor = _ratio_tokens(
        context_window, get_continuity_compaction_recent_raw_floor_ratio()
    )
    return ContinuityCompactionSettings(
        context_window=context_window,
        soft_trigger=_ratio_tokens(
            context_window, get_continuity_compaction_soft_trigger_ratio()
        ),
        emergency_trigger=_ratio_tokens(
            context_window, get_continuity_compaction_emergency_trigger_ratio()
        ),
        target_after_compaction=target,
        recent_raw_floor=recent_floor,
        predicted_growth_floor=_ratio_tokens(
            context_window,
            get_continuity_compaction_predicted_growth_floor_ratio(),
        ),
        growth_history_window=get_continuity_compaction_growth_history_window(),
        archive_retention_days=get_continuity_compaction_archive_retention_days(),
        archive_retention_count=get_continuity_compaction_archive_retention_count(),
        semantic_timeout_seconds=get_continuity_compaction_semantic_timeout_seconds(),
        archive_retrieval_enabled=get_continuity_compaction_archive_retrieval_enabled(),
        archive_retrieval_count=get_continuity_compaction_archive_retrieval_count(),
        task_retention_count=get_continuity_compaction_task_retention_count(),
        predictive_trigger_floor=_ratio_tokens(
            context_window,
            get_continuity_compaction_predictive_trigger_min_ratio(),
        ),
        mask_min_tokens=max(250, min(1000, int(context_window * 0.005))),
    )
