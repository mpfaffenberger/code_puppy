"""Tests for window-focused VQA functionality.

These tests verify that the window-focused VQA implementation:
1. Captures active window by default (not full screen)
2. Supports explicit full screen capture via capture_mode parameter
3. Focuses specified windows when window_title is provided
4. Correctly converts between window-relative and screen-absolute coordinates
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.tools.gui_cub.coordinates import (
    screen_to_window_coords,
    window_to_screen_coords,
)
from code_puppy.tools.gui_cub.result_types import WindowBoundsResult


class TestCoordinateConversion:
    """Test coordinate conversion utilities."""

    def test_window_to_screen_coords_basic(self):
        """Test basic window-to-screen coordinate conversion."""
        # Create mock window bounds
        window_bounds = WindowBoundsResult(
            success=True,
            x=100,
            y=50,
            width=1200,
            height=800,
            window_title="Test Window",
        )

        # Button at (200, 150) within window
        screen_x, screen_y = window_to_screen_coords(200, 150, window_bounds)

        # Should add window offset
        assert screen_x == 300  # 100 + 200
        assert screen_y == 200  # 50 + 150

    def test_screen_to_window_coords_basic(self):
        """Test basic screen-to-window coordinate conversion."""
        # Create mock window bounds
        window_bounds = WindowBoundsResult(
            success=True,
            x=100,
            y=50,
            width=1200,
            height=800,
            window_title="Test Window",
        )

        # Click at screen (300, 200)
        window_x, window_y = screen_to_window_coords(300, 200, window_bounds)

        # Should subtract window offset
        assert window_x == 200  # 300 - 100
        assert window_y == 150  # 200 - 50

    def test_window_to_screen_coords_zero_offset(self):
        """Test conversion when window is at screen origin."""
        window_bounds = WindowBoundsResult(
            success=True, x=0, y=0, width=1920, height=1080, window_title="Fullscreen"
        )

        screen_x, screen_y = window_to_screen_coords(500, 300, window_bounds)

        # No offset needed
        assert screen_x == 500
        assert screen_y == 300

    def test_screen_to_window_coords_zero_offset(self):
        """Test conversion when window is at screen origin."""
        window_bounds = WindowBoundsResult(
            success=True, x=0, y=0, width=1920, height=1080, window_title="Fullscreen"
        )

        window_x, window_y = screen_to_window_coords(500, 300, window_bounds)

        # No offset needed
        assert window_x == 500
        assert window_y == 300

    def test_window_to_screen_coords_negative_not_allowed(self):
        """Test that window coordinates can be negative (off-window)."""
        window_bounds = WindowBoundsResult(
            success=True, x=100, y=50, width=1200, height=800, window_title="Test"
        )

        # Negative window coords are allowed (e.g., cursor outside window)
        screen_x, screen_y = window_to_screen_coords(-10, -20, window_bounds)
        assert screen_x == 90  # 100 + (-10)
        assert screen_y == 30  # 50 + (-20)

    def test_window_to_screen_coords_missing_bounds_x(self):
        """Test error handling when window bounds missing x coordinate."""
        window_bounds = WindowBoundsResult(
            success=True, x=None, y=50, width=1200, height=800
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            window_to_screen_coords(100, 100, window_bounds)

    def test_window_to_screen_coords_missing_bounds_y(self):
        """Test error handling when window bounds missing y coordinate."""
        window_bounds = WindowBoundsResult(
            success=True, x=100, y=None, width=1200, height=800
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            window_to_screen_coords(100, 100, window_bounds)

    @patch("code_puppy.tools.gui_cub.window_control._get_active_window_bounds_impl")
    def test_window_to_screen_coords_auto_fetch_bounds(self, mock_get_window):
        """Test automatic fetching of window bounds when not provided."""
        # Mock the window bounds fetch
        mock_get_window.return_value = WindowBoundsResult(
            success=True, x=100, y=50, width=1200, height=800, window_title="Auto"
        )

        # Call without providing bounds
        screen_x, screen_y = window_to_screen_coords(200, 150, None)

        # Should have fetched bounds automatically
        mock_get_window.assert_called_once()
        assert screen_x == 300
        assert screen_y == 200

    @patch("code_puppy.tools.gui_cub.window_control._get_active_window_bounds_impl")
    def test_window_to_screen_coords_auto_fetch_fails(self, mock_get_window):
        """Test error handling when auto-fetching window bounds fails."""
        # Mock a failed window bounds fetch
        mock_get_window.return_value = WindowBoundsResult(
            success=False, error="Window not found"
        )

        # Should raise ValueError with appropriate message
        with pytest.raises(ValueError, match="Could not get active window bounds"):
            window_to_screen_coords(200, 150, None)

    def test_round_trip_conversion(self):
        """Test that converting back and forth preserves coordinates."""
        window_bounds = WindowBoundsResult(
            success=True, x=100, y=50, width=1200, height=800, window_title="Test"
        )

        # Start with window coords
        original_window_x, original_window_y = 200, 150

        # Convert to screen
        screen_x, screen_y = window_to_screen_coords(
            original_window_x, original_window_y, window_bounds
        )

        # Convert back to window
        window_x, window_y = screen_to_window_coords(screen_x, screen_y, window_bounds)

        # Should match original
        assert window_x == original_window_x
        assert window_y == original_window_y


class TestWindowFocusedVQA:
    """Test window-focused VQA behavior."""

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    @patch("code_puppy.tools.gui_cub.screen_capture.run_desktop_vqa_analysis")
    async def test_full_screen_opt_in(self, mock_vqa, mock_capture):
        """Verify full screen capture requires explicit opt-in."""
        from code_puppy.tools.gui_cub.screen_capture import (
            take_desktop_screenshot_and_analyze,
        )

        # Mock screenshot result
        from code_puppy.tools.gui_cub.result_types import ScreenshotResult

        mock_capture.return_value = ScreenshotResult(
            success=True,
            screenshot_data=b"fake_png_data",
            width=1920,
            height=1080,
        )

        # Mock VQA result
        from code_puppy.tools.gui_cub.result_types import VQAResult

        mock_vqa.return_value = VQAResult(
            success=True,
            question="test",
            answer="Multiple windows visible",
            confidence=0.9,
        )

        # Call with capture_mode="full_screen"
        result = await take_desktop_screenshot_and_analyze(
            question="What windows are open?", capture_mode="full_screen"
        )

        # Verify screenshot was captured with None region (full screen)
        mock_capture.assert_called_once()
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] is None

        # Verify result has screen-absolute coordinate system
        assert result.coordinate_system == "screen_absolute"
        assert result.window_bounds is None

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.window_control._get_active_window_bounds_impl")
    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    @patch("code_puppy.tools.gui_cub.screen_capture.run_desktop_vqa_analysis")
    async def test_window_bounds_fallback_on_error(
        self, mock_vqa, mock_capture, mock_get_window
    ):
        """Test fallback to full screen when window bounds cannot be obtained."""
        from code_puppy.tools.gui_cub.screen_capture import (
            take_desktop_screenshot_and_analyze,
        )

        # Mock failed window bounds fetch
        mock_get_window.return_value = WindowBoundsResult(
            success=False, error="No active window"
        )

        # Mock screenshot
        from code_puppy.tools.gui_cub.result_types import ScreenshotResult

        mock_capture.return_value = ScreenshotResult(
            success=True,
            screenshot_data=b"fake_png_data",
            width=1920,
            height=1080,
        )

        # Mock VQA
        from code_puppy.tools.gui_cub.result_types import VQAResult

        mock_vqa.return_value = VQAResult(
            success=True, question="test", answer="Fallback result", confidence=0.8
        )

        # Call default (should try window, then fall back to full screen)
        result = await take_desktop_screenshot_and_analyze(question="What is visible?")

        # Verify screenshot was captured with None region (fallback to full screen)
        mock_capture.assert_called_once()
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] is None

        # Coordinate system should be screen_absolute since we fell back
        assert result.coordinate_system == "screen_absolute"

    @pytest.mark.asyncio
    @patch("code_puppy.tools.gui_cub.screen_capture.capture_screen")
    @patch("code_puppy.tools.gui_cub.screen_capture.run_desktop_vqa_analysis")
    async def test_explicit_region_overrides_window(self, mock_vqa, mock_capture):
        """Test that explicit region parameter overrides window capture."""
        from code_puppy.tools.gui_cub.screen_capture import (
            take_desktop_screenshot_and_analyze,
        )

        # Mock screenshot
        from code_puppy.tools.gui_cub.result_types import ScreenshotResult

        mock_capture.return_value = ScreenshotResult(
            success=True, screenshot_data=b"fake_png_data", width=500, height=400
        )

        # Mock VQA
        from code_puppy.tools.gui_cub.result_types import VQAResult

        mock_vqa.return_value = VQAResult(
            success=True, question="test", answer="Found in region", confidence=0.9
        )

        # Call with explicit region (should override active_window default)
        result = await take_desktop_screenshot_and_analyze(
            question="What's in this area?", region=(100, 100, 500, 400)
        )

        # Verify screenshot was captured with the explicit region
        mock_capture.assert_called_once()
        call_kwargs = mock_capture.call_args[1]
        assert call_kwargs["region"] == (100, 100, 500, 400)

        # Should still be screen_absolute since explicit region was provided
        assert result.coordinate_system == "screen_absolute"
