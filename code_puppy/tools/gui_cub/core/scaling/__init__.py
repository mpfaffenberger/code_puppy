"""Scaling and coordinate conversion logic."""

from .calculator import (
    DisplayMetrics,
    calculate_scale_factor,
    convert_physical_to_logical,
    convert_logical_to_physical,
    is_valid_scale_factor,
    calculate_aspect_ratio,
    scales_match,
)

__all__ = [
    "DisplayMetrics",
    "calculate_scale_factor",
    "convert_physical_to_logical",
    "convert_logical_to_physical",
    "is_valid_scale_factor",
    "calculate_aspect_ratio",
    "scales_match",
]
