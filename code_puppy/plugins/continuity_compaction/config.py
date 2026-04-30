"""Configuration helpers for the Continuity compaction plugin."""

from __future__ import annotations

from typing import Final

from code_puppy.config import get_value

CONFIG_KEYS: Final[tuple[str, ...]] = (
    "continuity_compaction_soft_trigger_ratio",
    "continuity_compaction_emergency_trigger_ratio",
    "continuity_compaction_target_ratio",
    "continuity_compaction_recent_raw_floor_ratio",
    "continuity_compaction_predicted_growth_floor_ratio",
    "continuity_compaction_predictive_trigger_min_ratio",
    "continuity_compaction_growth_history_window",
    "continuity_compaction_archive_retention_days",
    "continuity_compaction_archive_retention_count",
    "continuity_compaction_semantic_task_detection",
    "continuity_compaction_semantic_timeout_seconds",
    "continuity_compaction_archive_retrieval_enabled",
    "continuity_compaction_archive_retrieval_count",
    "continuity_compaction_task_retention_count",
)


def _get_bounded_float_config(
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    val = get_value(key)
    try:
        parsed = float(val) if val else default
    except (ValueError, TypeError):
        return default
    return max(minimum, min(maximum, parsed))


def _get_bounded_int_config(
    key: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    val = get_value(key)
    try:
        parsed = int(val) if val else default
    except (ValueError, TypeError):
        return default
    return max(minimum, min(maximum, parsed))


def _get_bool_config(key: str, default: bool) -> bool:
    val = get_value(key)
    if val is None:
        return default
    normalized = str(val).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def get_continuity_compaction_soft_trigger_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_soft_trigger_ratio",
        0.825,
        minimum=0.5,
        maximum=0.95,
    )


def get_continuity_compaction_emergency_trigger_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_emergency_trigger_ratio",
        0.9,
        minimum=0.6,
        maximum=0.98,
    )


def get_continuity_compaction_target_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_target_ratio",
        0.35,
        minimum=0.2,
        maximum=0.9,
    )


def get_continuity_compaction_recent_raw_floor_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_recent_raw_floor_ratio",
        0.2,
        minimum=0.05,
        maximum=0.75,
    )


def get_continuity_compaction_predicted_growth_floor_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_predicted_growth_floor_ratio",
        0.06,
        minimum=0.0,
        maximum=0.5,
    )


def get_continuity_compaction_predictive_trigger_min_ratio() -> float:
    return _get_bounded_float_config(
        "continuity_compaction_predictive_trigger_min_ratio",
        0.725,
        minimum=0.5,
        maximum=0.95,
    )


def get_continuity_compaction_growth_history_window() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_growth_history_window",
        10,
        minimum=1,
        maximum=100,
    )


def get_continuity_compaction_archive_retention_days() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_archive_retention_days",
        30,
        minimum=1,
        maximum=3650,
    )


def get_continuity_compaction_archive_retention_count() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_archive_retention_count",
        500,
        minimum=1,
        maximum=100000,
    )


def get_continuity_compaction_semantic_task_detection() -> bool:
    return _get_bool_config(
        "continuity_compaction_semantic_task_detection",
        True,
    )


def get_continuity_compaction_semantic_timeout_seconds() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_semantic_timeout_seconds",
        60,
        minimum=1,
        maximum=120,
    )


def get_continuity_compaction_archive_retrieval_enabled() -> bool:
    return _get_bool_config(
        "continuity_compaction_archive_retrieval_enabled",
        True,
    )


def get_continuity_compaction_archive_retrieval_count() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_archive_retrieval_count",
        3,
        minimum=0,
        maximum=20,
    )


def get_continuity_compaction_task_retention_count() -> int:
    return _get_bounded_int_config(
        "continuity_compaction_task_retention_count",
        100,
        minimum=1,
        maximum=1000,
    )
