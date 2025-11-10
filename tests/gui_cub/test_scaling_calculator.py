"""Tests for coordinate scaling calculations.

These tests validate pure mathematical functions for HiDPI/Retina display
coordinate conversions, separated from I/O operations.
"""

import pytest
from code_puppy.tools.gui_cub.core.scaling import (
    DisplayMetrics,
    calculate_scale_factor,
    convert_physical_to_logical,
    convert_logical_to_physical,
    is_valid_scale_factor,
    calculate_aspect_ratio,
    scales_match,
)


class TestCalculateScaleFactor:
    """Test scale factor calculation from display metrics."""

    def test_calculates_2x_retina_scale(self):
        """Should calculate 2.0 for Retina displays."""
        metrics = DisplayMetrics(
            logical_width=1920,
            logical_height=1080,
            physical_width=3840,
            physical_height=2160,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 2.0

    def test_calculates_1x_normal_scale(self):
        """Should calculate 1.0 for non-HiDPI displays."""
        metrics = DisplayMetrics(
            logical_width=1920,
            logical_height=1080,
            physical_width=1920,
            physical_height=1080,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 1.0

    def test_calculates_1_5x_scale(self):
        """Should calculate 1.5 for 150% scaling."""
        metrics = DisplayMetrics(
            logical_width=1920,
            logical_height=1080,
            physical_width=2880,
            physical_height=1620,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 1.5

    def test_rounds_to_nearest_quarter(self):
        """Should round to nearest 0.25 (1.25, 1.5, 1.75, 2.0, etc.)."""
        # Scale of 1.37 should round to 1.25
        metrics = DisplayMetrics(
            logical_width=1000,
            logical_height=1000,
            physical_width=1370,  # 1.37x
            physical_height=1370,
        )

        scale = calculate_scale_factor(metrics)

        # 1.37 rounds to 1.25 (nearest 0.25)
        assert scale == 1.25

    def test_clamps_to_reasonable_bounds(self):
        """Should clamp scale factor to [1.0, 4.0] range."""
        # Unreasonably high scale
        metrics = DisplayMetrics(
            logical_width=100,
            logical_height=100,
            physical_width=1000,  # 10x scale
            physical_height=1000,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 4.0  # Clamped to max

    def test_uses_width_when_scales_differ(self):
        """Should use width scale when x and y differ significantly."""
        metrics = DisplayMetrics(
            logical_width=1000,
            logical_height=1000,
            physical_width=2000,  # 2.0x
            physical_height=1500,  # 1.5x (different!)
        )

        scale = calculate_scale_factor(metrics)

        # Should use width scale (2.0) when diff > 0.1
        assert scale == 2.0

    def test_averages_when_scales_similar(self):
        """Should average x and y scales when they're close."""
        metrics = DisplayMetrics(
            logical_width=1000,
            logical_height=1000,
            physical_width=2000,  # 2.0x
            physical_height=2050,  # 2.05x (close!)
        )

        scale = calculate_scale_factor(metrics)

        # Average of 2.0 and 2.05 = 2.025, rounds to 2.0
        assert scale == 2.0

    def test_returns_1_for_zero_dimensions(self):
        """Should return 1.0 for invalid (zero) dimensions."""
        metrics = DisplayMetrics(
            logical_width=0,
            logical_height=1080,
            physical_width=1920,
            physical_height=2160,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 1.0

    def test_returns_1_for_negative_dimensions(self):
        """Should return 1.0 for invalid (negative) dimensions."""
        metrics = DisplayMetrics(
            logical_width=-1920,
            logical_height=1080,
            physical_width=3840,
            physical_height=2160,
        )

        scale = calculate_scale_factor(metrics)

        assert scale == 1.0


class TestConvertPhysicalToLogical:
    """Test physical to logical coordinate conversion."""

    def test_converts_2x_retina_coordinates(self):
        """Should halve coordinates on 2x display."""
        logical_x, logical_y = convert_physical_to_logical(940, 250, 2.0)

        assert logical_x == 470
        assert logical_y == 125

    def test_keeps_1x_coordinates_same(self):
        """Should not change coordinates on 1x display."""
        logical_x, logical_y = convert_physical_to_logical(500, 300, 1.0)

        assert logical_x == 500
        assert logical_y == 300

    def test_converts_1_5x_coordinates(self):
        """Should convert 1.5x scaling correctly."""
        logical_x, logical_y = convert_physical_to_logical(1500, 900, 1.5)

        assert logical_x == 1000
        assert logical_y == 600

    def test_handles_zero_scale_gracefully(self):
        """Should default to 1.0 for zero scale factor."""
        logical_x, logical_y = convert_physical_to_logical(100, 200, 0.0)

        # Should use 1.0 as fallback
        assert logical_x == 100
        assert logical_y == 200

    def test_handles_negative_scale_gracefully(self):
        """Should default to 1.0 for negative scale factor."""
        logical_x, logical_y = convert_physical_to_logical(100, 200, -2.0)

        # Should use 1.0 as fallback
        assert logical_x == 100
        assert logical_y == 200

    def test_rounds_to_integers(self):
        """Should return integer coordinates."""
        # 945 / 2.0 = 472.5, should round to 472
        logical_x, logical_y = convert_physical_to_logical(945, 251, 2.0)

        assert isinstance(logical_x, int)
        assert isinstance(logical_y, int)


class TestConvertLogicalToPhysical:
    """Test logical to physical coordinate conversion (inverse)."""

    def test_converts_2x_retina_coordinates(self):
        """Should double coordinates on 2x display."""
        physical_x, physical_y = convert_logical_to_physical(470, 125, 2.0)

        assert physical_x == 940
        assert physical_y == 250

    def test_keeps_1x_coordinates_same(self):
        """Should not change coordinates on 1x display."""
        physical_x, physical_y = convert_logical_to_physical(500, 300, 1.0)

        assert physical_x == 500
        assert physical_y == 300

    def test_converts_1_5x_coordinates(self):
        """Should convert 1.5x scaling correctly."""
        physical_x, physical_y = convert_logical_to_physical(1000, 600, 1.5)

        assert physical_x == 1500
        assert physical_y == 900

    def test_round_trip_conversion(self):
        """Converting logical→physical→logical should return original."""
        original_x, original_y = 100, 200
        scale = 2.0

        # Convert to physical
        physical_x, physical_y = convert_logical_to_physical(
            original_x, original_y, scale
        )

        # Convert back to logical
        logical_x, logical_y = convert_physical_to_logical(
            physical_x, physical_y, scale
        )

        assert logical_x == original_x
        assert logical_y == original_y


class TestIsValidScaleFactor:
    """Test scale factor validation."""

    def test_accepts_common_scale_factors(self):
        """Should accept common scale values."""
        assert is_valid_scale_factor(1.0) is True
        assert is_valid_scale_factor(1.25) is True
        assert is_valid_scale_factor(1.5) is True
        assert is_valid_scale_factor(2.0) is True
        assert is_valid_scale_factor(3.0) is True

    def test_rejects_zero(self):
        """Should reject zero scale factor."""
        assert is_valid_scale_factor(0.0) is False

    def test_rejects_negative(self):
        """Should reject negative scale factors."""
        assert is_valid_scale_factor(-1.0) is False
        assert is_valid_scale_factor(-2.5) is False

    def test_rejects_too_large(self):
        """Should reject unreasonably large scale factors."""
        assert is_valid_scale_factor(5.0) is False
        assert is_valid_scale_factor(10.0) is False

    def test_accepts_boundary_values(self):
        """Should accept boundary values."""
        assert is_valid_scale_factor(4.0) is True  # Max valid
        assert is_valid_scale_factor(0.1) is True  # Small but valid

    def test_rejects_non_numbers(self):
        """Should reject non-numeric values."""
        assert is_valid_scale_factor("2.0") is False
        assert is_valid_scale_factor(None) is False


class TestCalculateAspectRatio:
    """Test aspect ratio calculation."""

    def test_calculates_16_9_ratio(self):
        """Should calculate 16:9 aspect ratio correctly."""
        ratio = calculate_aspect_ratio(1920, 1080)

        assert abs(ratio - 16 / 9) < 0.01  # ~1.778

    def test_calculates_4_3_ratio(self):
        """Should calculate 4:3 aspect ratio correctly."""
        ratio = calculate_aspect_ratio(1024, 768)

        assert abs(ratio - 4 / 3) < 0.01  # ~1.333

    def test_returns_zero_for_invalid_dimensions(self):
        """Should return 0.0 for invalid dimensions."""
        assert calculate_aspect_ratio(0, 1080) == 0.0
        assert calculate_aspect_ratio(1920, 0) == 0.0
        assert calculate_aspect_ratio(-100, 100) == 0.0


class TestScalesMatch:
    """Test scale matching with tolerance."""

    def test_exact_match(self):
        """Should match when scales are exactly equal."""
        assert scales_match(2.0, 2.0) is True

    def test_match_within_tolerance(self):
        """Should match when difference is within tolerance."""
        assert scales_match(2.0, 2.05, tolerance=0.1) is True
        assert scales_match(1.95, 2.0, tolerance=0.1) is True

    def test_no_match_outside_tolerance(self):
        """Should not match when difference exceeds tolerance."""
        assert scales_match(2.0, 2.2, tolerance=0.1) is False
        assert scales_match(1.5, 2.0, tolerance=0.1) is False

    def test_custom_tolerance(self):
        """Should respect custom tolerance values."""
        # Tight tolerance
        assert scales_match(2.0, 2.01, tolerance=0.001) is False

        # Loose tolerance
        assert scales_match(2.0, 2.5, tolerance=0.6) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
