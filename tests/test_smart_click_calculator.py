"""Tests for SmartClickCalculator - element-type-aware click offset calculation."""

import pytest
from code_puppy.tools.rpa.smart_click_calculator import (
    ClickPoint,
    SmartClickCalculator,
    TextBoundingBox,
)


class TestSmartClickCalculator:
    """Test suite for SmartClickCalculator."""

    @pytest.fixture
    def sample_button_bbox(self):
        """Sample OCR bounding box for a button."""
        return TextBoundingBox(
            text="Submit",
            confidence=0.89,
            x=500,
            y=300,
            width=80,
            height=30,
            center_x=540,
            center_y=315,
        )

    @pytest.fixture
    def sample_link_bbox(self):
        """Sample OCR bounding box for a link."""
        return TextBoundingBox(
            text="Learn More",
            confidence=0.92,
            x=100,
            y=200,
            width=120,
            height=20,
            center_x=160,
            center_y=210,
        )

    @pytest.fixture
    def sample_checkbox_bbox(self):
        """Sample OCR bounding box for a checkbox label."""
        return TextBoundingBox(
            text="I agree",
            confidence=0.87,
            x=50,
            y=400,
            width=70,
            height=20,
            center_x=85,
            center_y=410,
        )

    @pytest.fixture
    def multiline_bbox(self):
        """Sample OCR bounding box for multi-line text."""
        return TextBoundingBox(
            text="Submit Application",
            confidence=0.85,
            x=300,
            y=500,
            width=150,
            height=50,  # Multi-line (> 30px)
            center_x=375,
            center_y=525,
        )

    def test_button_offset_calculation(self, sample_button_bbox):
        """Test that button clicks are offset above center."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="button"
        )

        # Should be same X, but Y slightly above center
        assert point.x == sample_button_bbox.center_x
        assert point.y < sample_button_bbox.center_y
        assert point.offset_x == 0
        assert point.offset_y < 0  # Negative = above
        assert "button" in point.strategy.lower()
        assert point.confidence >= sample_button_bbox.confidence

    def test_link_offset_calculation(self, sample_link_bbox):
        """Test that link clicks are offset to the left."""
        point = SmartClickCalculator.calculate_click_point(
            sample_link_bbox, element_type="link"
        )

        # Should be left of center, same Y
        assert point.x < sample_link_bbox.center_x
        assert point.y == sample_link_bbox.center_y
        assert point.offset_x < 0  # Negative = left
        assert point.offset_y == 0
        assert "link" in point.strategy.lower()

    def test_checkbox_offset_calculation(self, sample_checkbox_bbox):
        """Test that checkbox clicks are offset far left."""
        point = SmartClickCalculator.calculate_click_point(
            sample_checkbox_bbox, element_type="checkbox"
        )

        # Should be significantly left of center (where checkbox is)
        assert point.x < sample_checkbox_bbox.center_x
        assert point.y == sample_checkbox_bbox.center_y
        assert point.offset_x < -20  # Significant left offset
        assert point.offset_y == 0
        assert "checkbox" in point.strategy.lower()

    def test_generic_no_offset(self, sample_button_bbox):
        """Test that generic elements use center with no offset."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="generic"
        )

        # Should be exact center
        assert point.x == sample_button_bbox.center_x
        assert point.y == sample_button_bbox.center_y
        assert point.offset_x == 0
        assert point.offset_y == 0
        assert "generic" in point.strategy.lower()

    def test_multiline_adjustment(self, multiline_bbox):
        """Test that multi-line text gets Y offset adjustment."""
        point = SmartClickCalculator.calculate_click_point(
            multiline_bbox, element_type="button"
        )

        # Should be adjusted upward for multi-line
        assert point.y < multiline_bbox.center_y
        assert "multiline" in point.strategy.lower()
        assert "adjusted" in point.reasoning.lower()

    def test_bounds_safety(self, sample_button_bbox):
        """Test that calculated points stay within bounding box."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="button"
        )

        # Point should be within bbox bounds
        assert (
            sample_button_bbox.x
            <= point.x
            <= sample_button_bbox.x + sample_button_bbox.width
        )
        assert (
            sample_button_bbox.y
            <= point.y
            <= sample_button_bbox.y + sample_button_bbox.height
        )

    def test_conservative_vs_aggressive_offsets(self, sample_button_bbox):
        """Test that conservative mode uses smaller offsets."""
        conservative = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="button", use_conservative_offsets=True
        )
        aggressive = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="button", use_conservative_offsets=False
        )

        # Aggressive should have larger offset magnitude
        assert abs(aggressive.offset_y) >= abs(conservative.offset_y)

    def test_generate_retry_points(self, sample_button_bbox):
        """Test generation of multiple retry points."""
        points = SmartClickCalculator.generate_retry_points(
            sample_button_bbox, element_type="button", num_points=5
        )

        # Should generate requested number of points
        assert len(points) == 5

        # First point should be optimal strategy
        assert "button" in points[0].strategy.lower()

        # Second point should be fallback center
        assert "fallback" in points[1].strategy.lower()
        assert points[1].x == sample_button_bbox.center_x
        assert points[1].y == sample_button_bbox.center_y

        # All points should be valid ClickPoint objects
        for point in points:
            assert isinstance(point, ClickPoint)
            assert point.x > 0
            assert point.y > 0
            assert 0.0 <= point.confidence <= 1.0

    def test_retry_points_ordering(self, sample_button_bbox):
        """Test that retry points are in priority order."""
        points = SmartClickCalculator.generate_retry_points(
            sample_button_bbox, element_type="button", num_points=3
        )

        # First point should have highest confidence
        assert points[0].confidence >= points[1].confidence
        assert points[1].confidence >= points[2].confidence

    def test_analyze_bounding_box(self, sample_button_bbox, multiline_bbox):
        """Test bounding box analysis for debugging."""
        analysis = SmartClickCalculator.analyze_bounding_box(sample_button_bbox)

        # Should return comprehensive analysis
        assert "text" in analysis
        assert "confidence" in analysis
        assert "width" in analysis
        assert "height" in analysis
        assert "aspect_ratio" in analysis
        assert "is_multiline" in analysis
        assert "estimated_type" in analysis

        # Single-line button should not be multiline
        assert analysis["is_multiline"] is False

        # Multi-line bbox should be detected
        multiline_analysis = SmartClickCalculator.analyze_bounding_box(multiline_bbox)
        assert multiline_analysis["is_multiline"] is True

    def test_element_type_variations(self, sample_button_bbox):
        """Test all element type variations."""
        element_types = [
            "button",
            "link",
            "checkbox",
            "radio_button",
            "text_field",
            "dropdown",
            "icon",
            "menu_item",
            "tab",
            "generic",
        ]

        for elem_type in element_types:
            point = SmartClickCalculator.calculate_click_point(
                sample_button_bbox,
                element_type=elem_type,  # type: ignore
            )

            # All should produce valid points
            assert isinstance(point, ClickPoint)
            assert point.x > 0
            assert point.y > 0
            assert len(point.strategy) > 0
            assert len(point.reasoning) > 0

    def test_low_confidence_handling(self):
        """Test that low-confidence OCR is handled appropriately."""
        low_conf_bbox = TextBoundingBox(
            text="Blurry",
            confidence=0.4,  # Low confidence
            x=100,
            y=100,
            width=50,
            height=20,
            center_x=125,
            center_y=110,
        )

        point = SmartClickCalculator.calculate_click_point(
            low_conf_bbox, element_type="button"
        )

        # Should still generate a point, but with adjusted confidence
        assert isinstance(point, ClickPoint)
        # Confidence should reflect OCR uncertainty
        assert point.confidence <= 0.6  # Shouldn't be too high

    def test_dropdown_right_offset(self, sample_button_bbox):
        """Test that dropdowns are clicked on the right side."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="dropdown"
        )

        # Should be right of center (where arrow is)
        assert point.x > sample_button_bbox.center_x
        assert point.offset_x > 0  # Positive = right
        assert "dropdown" in point.strategy.lower()

    def test_text_field_center_left(self, sample_button_bbox):
        """Test that text fields are clicked center-left."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="text_field"
        )

        # Should be left of center for cursor positioning
        assert point.x < sample_button_bbox.center_x
        assert point.offset_x < 0
        assert point.offset_y == 0  # No vertical offset
        assert "text_field" in point.strategy.lower()

    def test_icon_exact_center(self, sample_button_bbox):
        """Test that icons use exact center (no offset)."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="icon"
        )

        # Should be exact center
        assert point.x == sample_button_bbox.center_x
        assert point.y == sample_button_bbox.center_y
        assert point.offset_x == 0
        assert point.offset_y == 0
        assert "icon" in point.strategy.lower()

    def test_radio_button_like_checkbox(self, sample_checkbox_bbox):
        """Test that radio buttons behave like checkboxes."""
        checkbox_point = SmartClickCalculator.calculate_click_point(
            sample_checkbox_bbox, element_type="checkbox"
        )
        radio_point = SmartClickCalculator.calculate_click_point(
            sample_checkbox_bbox, element_type="radio_button"
        )

        # Both should have similar left offsets
        assert abs(checkbox_point.offset_x - radio_point.offset_x) < 5

    def test_menu_item_center_left(self, sample_button_bbox):
        """Test that menu items are clicked center-left."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="menu_item"
        )

        # Should be left of center
        assert point.x < sample_button_bbox.center_x
        assert point.offset_x < 0
        assert "menu_item" in point.strategy.lower()

    def test_tab_above_center(self, sample_button_bbox):
        """Test that tabs are clicked slightly above center."""
        point = SmartClickCalculator.calculate_click_point(
            sample_button_bbox, element_type="tab"
        )

        # Should be above center
        assert point.y < sample_button_bbox.center_y
        assert point.offset_y < 0
        assert point.offset_x == 0  # No horizontal offset
        assert "tab" in point.strategy.lower()
