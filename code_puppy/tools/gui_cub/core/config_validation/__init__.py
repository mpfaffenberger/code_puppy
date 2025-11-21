"""Config validation logic."""

from .validator import (
    validate_resolution_match,
    validate_platform_match,
    validate_scale_factor,
)

__all__ = [
    "validate_resolution_match",
    "validate_platform_match",
    "validate_scale_factor",
]
