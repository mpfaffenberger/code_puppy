"""Tests for mouse control tools."""

import pytest
from code_puppy.tools.gui_cub.result_types import (
    MouseActionResult,
    MouseDragResult,
    MouseScrollResult,
)
from tests.gui_cub.helpers import validate_result_type, assert_valid_coordinates


class TestMouseControlValidation:
    """Test mouse control parameter validation."""

    def test_valid_coordinates_pass(self):
        """Test that valid coordinates are accepted."""
        # Should not raise
        assert_valid_coordinates(100, 200)
        assert_valid_coordinates(0, 0)
        assert_valid_coordinates(1920, 1080)

    def test_negative_coordinates_fail(self):
        """Test that negative coordinates are rejected."""
        with pytest.raises(AssertionError):
            assert_valid_coordinates(-10, 100)

        with pytest.raises(AssertionError):
            assert_valid_coordinates(100, -10)

    def test_non_integer_coordinates_fail(self):
        """Test that non-integer coordinates are rejected."""
        with pytest.raises(AssertionError):
            assert_valid_coordinates(100.5, 200)

        with pytest.raises(AssertionError):
            assert_valid_coordinates(100, "200")


class TestMouseActionResultCreation:
    """Test MouseActionResult can be created correctly."""

    def test_create_click_result(self):
        """Test creating a mouse click result."""
        result = MouseActionResult(success=True, x=100, y=200, button="left", clicks=1)

        validate_result_type(result, MouseActionResult)
        assert result.x == 100
        assert result.y == 200
        assert result.button == "left"

    def test_create_double_click_result(self):
        """Test creating a double-click result."""
        result = MouseActionResult(success=True, x=100, y=200, button="left", clicks=2)

        assert result.clicks == 2

    def test_create_right_click_result(self):
        """Test creating a right-click result."""
        result = MouseActionResult(success=True, x=100, y=200, button="right", clicks=1)

        assert result.button == "right"


class TestMouseDragResult:
    """Test MouseDragResult model."""

    def test_create_drag_result(self):
        """Test creating a mouse drag result."""
        result = MouseDragResult(
            success=True, start_x=100, start_y=200, end_x=300, end_y=400, button="left"
        )

        validate_result_type(result, MouseDragResult)
        assert result.start_x == 100
        assert result.end_x == 300


class TestMouseScrollResult:
    """Test MouseScrollResult model."""

    def test_create_scroll_result(self):
        """Test creating a mouse scroll result."""
        result = MouseScrollResult(success=True, clicks=5, direction="up")

        validate_result_type(result, MouseScrollResult)
        assert result.clicks == 5
        assert result.direction == "up"
