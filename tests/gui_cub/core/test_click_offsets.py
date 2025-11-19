"""Tests for pure click offset calculation logic.

Tests the click_offsets module which calculates optimal click coordinates
for different UI element types.
"""

import pytest

from code_puppy.tools.gui_cub.core.click_offsets import (
    BoundingBox,
    apply_bounds_check,
    calculate_button_offset,
    calculate_checkbox_offset,
    calculate_confidence_adjustment,
    calculate_dropdown_offset,
    calculate_generic_offset,
    calculate_icon_offset,
    calculate_link_offset,
    calculate_menu_item_offset,
    calculate_multiline_adjustment,
    calculate_tab_offset,
    calculate_text_field_offset,
    generate_retry_offsets,
    is_multiline_text,
)


# ============================================================================
# Element-Specific Offset Tests
# ============================================================================


class TestButtonOffset:
    """Tests for button offset calculation."""

    def test_calculates_conservative_offset(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        offset = calculate_button_offset(bbox, conservative=True)

        assert offset.offset_x == 0
        assert offset.offset_y == -4  # -int(30 * 0.15)
        assert offset.strategy == "button_above_center"
        assert "15%" in offset.reasoning

    def test_calculates_aggressive_offset(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        offset = calculate_button_offset(bbox, conservative=False)

        assert offset.offset_x == 0
        assert offset.offset_y == -6  # -int(30 * 0.2)
        assert "20%" in offset.reasoning

    def test_works_with_small_button(self):
        bbox = BoundingBox(x=0, y=0, width=60, height=20, center_x=30, center_y=10)
        offset = calculate_button_offset(bbox)

        assert offset.offset_y == -3  # -int(20 * 0.15)

    def test_works_with_large_button(self):
        bbox = BoundingBox(x=0, y=0, width=200, height=60, center_x=100, center_y=30)
        offset = calculate_button_offset(bbox)

        assert offset.offset_y == -9  # -int(60 * 0.15)


class TestLinkOffset:
    """Tests for link offset calculation."""

    def test_calculates_left_edge_offset(self):
        bbox = BoundingBox(x=100, y=50, width=100, height=20, center_x=150, center_y=60)
        offset = calculate_link_offset(bbox)

        assert offset.offset_x == -30  # -int(100 * 0.3)
        assert offset.offset_y == 0
        assert offset.strategy == "link_left_edge"
        assert "left edge" in offset.reasoning.lower()

    def test_works_with_narrow_link(self):
        bbox = BoundingBox(x=0, y=0, width=50, height=15, center_x=25, center_y=7)
        offset = calculate_link_offset(bbox)

        assert offset.offset_x == -15  # -int(50 * 0.3)

    def test_works_with_wide_link(self):
        bbox = BoundingBox(x=0, y=0, width=300, height=20, center_x=150, center_y=10)
        offset = calculate_link_offset(bbox)

        assert offset.offset_x == -90  # -int(300 * 0.3)


class TestCheckboxOffset:
    """Tests for checkbox/radio button offset calculation."""

    def test_calculates_conservative_checkbox_offset(self):
        bbox = BoundingBox(x=100, y=50, width=100, height=20, center_x=150, center_y=60)
        offset = calculate_checkbox_offset(bbox, conservative=True)

        assert offset.offset_x == -60  # -int(100 * 0.6)
        assert offset.offset_y == 0
        assert offset.strategy == "checkbox_left"
        assert "60%" in offset.reasoning

    def test_calculates_aggressive_checkbox_offset(self):
        bbox = BoundingBox(x=100, y=50, width=100, height=20, center_x=150, center_y=60)
        offset = calculate_checkbox_offset(bbox, conservative=False)

        assert offset.offset_x == -80  # -int(100 * 0.8)
        assert "80%" in offset.reasoning

    def test_works_with_short_label(self):
        bbox = BoundingBox(x=0, y=0, width=80, height=16, center_x=40, center_y=8)
        offset = calculate_checkbox_offset(bbox)

        assert offset.offset_x == -48  # -int(80 * 0.6)


class TestTextFieldOffset:
    """Tests for text field offset calculation."""

    def test_calculates_center_left_offset(self):
        bbox = BoundingBox(x=100, y=50, width=200, height=30, center_x=200, center_y=65)
        offset = calculate_text_field_offset(bbox)

        assert offset.offset_x == -40  # -int(200 * 0.2)
        assert offset.offset_y == 0
        assert offset.strategy == "text_field_center_left"
        assert "cursor positioning" in offset.reasoning.lower()

    def test_works_with_narrow_field(self):
        bbox = BoundingBox(x=0, y=0, width=100, height=25, center_x=50, center_y=12)
        offset = calculate_text_field_offset(bbox)

        assert offset.offset_x == -20


class TestDropdownOffset:
    """Tests for dropdown offset calculation."""

    def test_calculates_right_side_offset(self):
        bbox = BoundingBox(x=100, y=50, width=150, height=30, center_x=175, center_y=65)
        offset = calculate_dropdown_offset(bbox)

        assert offset.offset_x == 45  # int(150 * 0.3)
        assert offset.offset_y == 0
        assert offset.strategy == "dropdown_right"
        assert "arrow" in offset.reasoning.lower()

    def test_works_with_wide_dropdown(self):
        bbox = BoundingBox(x=0, y=0, width=300, height=35, center_x=150, center_y=17)
        offset = calculate_dropdown_offset(bbox)

        assert offset.offset_x == 90  # int(300 * 0.3)


class TestIconOffset:
    """Tests for icon offset calculation."""

    def test_uses_exact_center(self):
        bbox = BoundingBox(x=100, y=50, width=32, height=32, center_x=116, center_y=66)
        offset = calculate_icon_offset(bbox)

        assert offset.offset_x == 0
        assert offset.offset_y == 0
        assert offset.strategy == "icon_center"
        assert "exact center" in offset.reasoning.lower()

    def test_works_for_any_size_icon(self):
        bbox = BoundingBox(x=0, y=0, width=64, height=64, center_x=32, center_y=32)
        offset = calculate_icon_offset(bbox)

        assert offset.offset_x == 0
        assert offset.offset_y == 0


class TestMenuItemOffset:
    """Tests for menu item offset calculation."""

    def test_calculates_center_left_offset(self):
        bbox = BoundingBox(
            x=10, y=100, width=180, height=25, center_x=100, center_y=112
        )
        offset = calculate_menu_item_offset(bbox)

        assert offset.offset_x == -36  # -int(180 * 0.2)
        assert offset.offset_y == 0
        assert offset.strategy == "menu_item_center_left"

    def test_works_with_narrow_menu_item(self):
        bbox = BoundingBox(x=0, y=0, width=100, height=20, center_x=50, center_y=10)
        offset = calculate_menu_item_offset(bbox)

        assert offset.offset_x == -20


class TestTabOffset:
    """Tests for tab offset calculation."""

    def test_calculates_slightly_above_center(self):
        bbox = BoundingBox(x=50, y=10, width=100, height=40, center_x=100, center_y=30)
        offset = calculate_tab_offset(bbox)

        assert offset.offset_x == 0
        assert offset.offset_y == -4  # -int(40 * 0.1)
        assert offset.strategy == "tab_above_center"

    def test_works_with_small_tab(self):
        bbox = BoundingBox(x=0, y=0, width=80, height=30, center_x=40, center_y=15)
        offset = calculate_tab_offset(bbox)

        assert offset.offset_y == -3  # -int(30 * 0.1)


class TestGenericOffset:
    """Tests for generic/unknown element offset calculation."""

    def test_uses_exact_center(self):
        bbox = BoundingBox(x=0, y=0, width=100, height=50, center_x=50, center_y=25)
        offset = calculate_generic_offset(bbox)

        assert offset.offset_x == 0
        assert offset.offset_y == 0
        assert offset.strategy == "generic_center"
        assert "center" in offset.reasoning.lower()


# ============================================================================
# Multi-line Text Detection Tests
# ============================================================================


class TestMultilineDetection:
    """Tests for multi-line text detection."""

    def test_detects_single_line_text(self):
        assert is_multiline_text(20) is False
        assert is_multiline_text(25) is False

    def test_detects_multiline_text(self):
        assert is_multiline_text(45) is True  # > 20 * 1.5 = 30
        assert is_multiline_text(60) is True
        assert is_multiline_text(100) is True

    def test_boundary_case(self):
        # Exactly at threshold (20 * 1.5 = 30)
        assert is_multiline_text(30) is False
        assert is_multiline_text(31) is True

    def test_custom_line_height(self):
        assert is_multiline_text(50, line_height=25) is True  # > 25 * 1.5 = 37.5
        assert is_multiline_text(35, line_height=25) is False


class TestMultilineAdjustment:
    """Tests for multi-line Y-offset adjustment."""

    def test_adjusts_to_upper_quarter(self):
        bbox = BoundingBox(x=0, y=0, width=200, height=60, center_x=100, center_y=30)
        adjusted = calculate_multiline_adjustment(bbox, current_offset_y=0)

        assert adjusted == -15  # -int(60 * 0.25)

    def test_uses_more_conservative_offset(self):
        bbox = BoundingBox(x=0, y=0, width=200, height=60, center_x=100, center_y=30)
        # If current offset is already -10, multiline is -15, use -15
        adjusted = calculate_multiline_adjustment(bbox, current_offset_y=-10)

        assert adjusted == -15

    def test_keeps_more_aggressive_existing_offset(self):
        bbox = BoundingBox(x=0, y=0, width=200, height=60, center_x=100, center_y=30)
        # If current offset is -20, multiline is -15, keep -20 (more conservative)
        adjusted = calculate_multiline_adjustment(bbox, current_offset_y=-20)

        assert adjusted == -20


# ============================================================================
# Bounds Checking Tests
# ============================================================================


class TestBoundsCheck:
    """Tests for coordinate bounds checking."""

    def test_keeps_coordinates_inside_bounds(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(120, 60, bbox)

        assert x == 120
        assert y == 60

    def test_constrains_x_coordinate_min(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(50, 60, bbox)  # x < bbox.x

        assert x == 100  # Constrained to bbox.x
        assert y == 60

    def test_constrains_x_coordinate_max(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(200, 60, bbox)  # x > bbox.x + bbox.width

        assert x == 180  # Constrained to 100 + 80
        assert y == 60

    def test_constrains_y_coordinate_min(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(120, 30, bbox)  # y < bbox.y

        assert x == 120
        assert y == 50  # Constrained to bbox.y

    def test_constrains_y_coordinate_max(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(120, 100, bbox)  # y > bbox.y + bbox.height

        assert x == 120
        assert y == 80  # Constrained to 50 + 30

    def test_constrains_both_coordinates(self):
        bbox = BoundingBox(x=100, y=50, width=80, height=30, center_x=140, center_y=65)
        x, y = apply_bounds_check(250, 150, bbox)  # Both outside

        assert x == 180
        assert y == 80


# ============================================================================
# Confidence Adjustment Tests
# ============================================================================


class TestConfidenceAdjustment:
    """Tests for confidence score adjustment."""

    def test_boosts_confidence_for_buttons(self):
        adjusted = calculate_confidence_adjustment(0.8, "button")
        assert adjusted == 0.9  # 0.8 + 0.1

    def test_boosts_confidence_for_links(self):
        adjusted = calculate_confidence_adjustment(0.7, "link")
        assert pytest.approx(adjusted, abs=1e-9) == 0.8

    def test_boosts_confidence_for_menu_items(self):
        adjusted = calculate_confidence_adjustment(0.85, "menu_item")
        assert pytest.approx(adjusted, abs=1e-9) == 0.95

    def test_caps_confidence_at_1_0(self):
        adjusted = calculate_confidence_adjustment(0.95, "button")
        assert adjusted == 1.0  # Capped

    def test_penalizes_confidence_for_checkboxes(self):
        adjusted = calculate_confidence_adjustment(0.8, "checkbox")
        assert pytest.approx(adjusted, abs=1e-9) == 0.72  # 0.8 * 0.9

    def test_penalizes_confidence_for_radio_buttons(self):
        adjusted = calculate_confidence_adjustment(0.9, "radio_button")
        assert pytest.approx(adjusted, abs=1e-9) == 0.81  # 0.9 * 0.9

    def test_no_adjustment_for_generic(self):
        adjusted = calculate_confidence_adjustment(0.75, "generic")
        assert adjusted == 0.75

    def test_no_adjustment_for_text_fields(self):
        adjusted = calculate_confidence_adjustment(0.8, "text_field")
        assert adjusted == 0.8


# ============================================================================
# Retry Offset Generation Tests
# ============================================================================


class TestRetryOffsets:
    """Tests for retry offset pattern generation."""

    def test_generates_requested_number_of_offsets(self):
        offsets = generate_retry_offsets(3)
        assert len(offsets) == 3

    def test_first_offset_is_slightly_above(self):
        offsets = generate_retry_offsets(5)
        offset_x, offset_y, strategy, reasoning = offsets[0]

        assert offset_x == 0
        assert offset_y == -5
        assert strategy == "slightly_above"
        assert "above" in reasoning.lower()

    def test_includes_directional_offsets(self):
        offsets = generate_retry_offsets(8)
        strategies = [offset[2] for offset in offsets]

        assert "slightly_above" in strategies
        assert "slightly_left" in strategies
        assert "slightly_right" in strategies
        assert "slightly_below" in strategies

    def test_includes_diagonal_offsets(self):
        offsets = generate_retry_offsets(8)
        strategies = [offset[2] for offset in offsets]

        assert "diagonal_up_left" in strategies
        assert "diagonal_up_right" in strategies

    def test_limits_to_available_offsets(self):
        # Should return all 8 predefined offsets, no more
        offsets = generate_retry_offsets(20)
        assert len(offsets) == 8

    def test_single_offset(self):
        offsets = generate_retry_offsets(1)
        assert len(offsets) == 1
        assert offsets[0][2] == "slightly_above"
