"""Test suite for GUI-Cub coordinate conversion utilities."""

import pytest

from code_puppy.tools.gui_cub.coordinates import (
    screen_to_window_coords,
    window_to_screen_coords,
)
from code_puppy.tools.gui_cub.result_types import WindowBoundsResult


class TestWindowToScreenCoords:
    """Test window-to-screen coordinate conversion."""

    def test_basic_conversion(self):
        """Test basic coordinate conversion."""
        bounds = WindowBoundsResult(
            success=True, x=100, y=50, width=800, height=600, title="Test Window"
        )

        screen_x, screen_y = window_to_screen_coords(200, 150, bounds)

        assert screen_x == 300  # 100 + 200
        assert screen_y == 200  # 50 + 150

    def test_zero_offset(self):
        """Test conversion with zero window offset."""
        bounds = WindowBoundsResult(
            success=True, x=0, y=0, width=1920, height=1080, title="Fullscreen"
        )

        screen_x, screen_y = window_to_screen_coords(100, 100, bounds)

        assert screen_x == 100
        assert screen_y == 100

    def test_negative_window_coords(self):
        """Test conversion with negative window coordinates (should work)."""
        bounds = WindowBoundsResult(
            success=True, x=500, y=300, width=800, height=600, title="Test"
        )

        # Negative window coords (outside window) but math still works
        screen_x, screen_y = window_to_screen_coords(-10, -10, bounds)

        assert screen_x == 490  # 500 + (-10)
        assert screen_y == 290  # 300 + (-10)

    def test_large_coordinates(self):
        """Test conversion with large coordinate values."""
        bounds = WindowBoundsResult(
            success=True, x=2000, y=1500, width=800, height=600, title="Test"
        )

        screen_x, screen_y = window_to_screen_coords(5000, 3000, bounds)

        assert screen_x == 7000
        assert screen_y == 4500

    def test_missing_window_bounds_x(self):
        """Test error when window bounds missing x coordinate."""
        bounds = WindowBoundsResult(
            success=True, x=None, y=100, width=800, height=600, title="Test"
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            window_to_screen_coords(100, 100, bounds)

    def test_missing_window_bounds_y(self):
        """Test error when window bounds missing y coordinate."""
        bounds = WindowBoundsResult(
            success=True, x=100, y=None, width=800, height=600, title="Test"
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            window_to_screen_coords(100, 100, bounds)


class TestScreenToWindowCoords:
    """Test screen-to-window coordinate conversion."""

    def test_basic_conversion(self):
        """Test basic coordinate conversion."""
        bounds = WindowBoundsResult(
            success=True, x=100, y=50, width=800, height=600, title="Test Window"
        )

        win_x, win_y = screen_to_window_coords(300, 200, bounds)

        assert win_x == 200  # 300 - 100
        assert win_y == 150  # 200 - 50

    def test_zero_offset(self):
        """Test conversion with zero window offset."""
        bounds = WindowBoundsResult(
            success=True, x=0, y=0, width=1920, height=1080, title="Fullscreen"
        )

        win_x, win_y = screen_to_window_coords(500, 400, bounds)

        assert win_x == 500
        assert win_y == 400

    def test_screen_coords_before_window(self):
        """Test conversion when screen coords are before window origin."""
        bounds = WindowBoundsResult(
            success=True, x=500, y=300, width=800, height=600, title="Test"
        )

        # Screen coords before window (results in negative window coords)
        win_x, win_y = screen_to_window_coords(400, 200, bounds)

        assert win_x == -100  # 400 - 500
        assert win_y == -100  # 200 - 300

    def test_large_coordinates(self):
        """Test conversion with large coordinate values."""
        bounds = WindowBoundsResult(
            success=True, x=1000, y=800, width=800, height=600, title="Test"
        )

        win_x, win_y = screen_to_window_coords(5000, 3000, bounds)

        assert win_x == 4000
        assert win_y == 2200

    def test_missing_window_bounds_x(self):
        """Test error when window bounds missing x coordinate."""
        bounds = WindowBoundsResult(
            success=True, x=None, y=100, width=800, height=600, title="Test"
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            screen_to_window_coords(100, 100, bounds)

    def test_missing_window_bounds_y(self):
        """Test error when window bounds missing y coordinate."""
        bounds = WindowBoundsResult(
            success=True, x=100, y=None, width=800, height=600, title="Test"
        )

        with pytest.raises(ValueError, match="Window bounds missing x/y coordinates"):
            screen_to_window_coords(100, 100, bounds)


class TestCoordinateRoundTrip:
    """Test that conversions are reversible."""

    def test_window_to_screen_to_window(self):
        """Test round-trip conversion: window -> screen -> window."""
        bounds = WindowBoundsResult(
            success=True, x=250, y=150, width=1024, height=768, title="Test"
        )

        # Start with window coords
        original_win_x, original_win_y = 400, 300

        # Convert to screen
        screen_x, screen_y = window_to_screen_coords(
            original_win_x, original_win_y, bounds
        )

        # Convert back to window
        win_x, win_y = screen_to_window_coords(screen_x, screen_y, bounds)

        # Should match original
        assert win_x == original_win_x
        assert win_y == original_win_y

    def test_screen_to_window_to_screen(self):
        """Test round-trip conversion: screen -> window -> screen."""
        bounds = WindowBoundsResult(
            success=True, x=100, y=50, width=1280, height=720, title="Test"
        )

        # Start with screen coords
        original_screen_x, original_screen_y = 800, 600

        # Convert to window
        win_x, win_y = screen_to_window_coords(
            original_screen_x, original_screen_y, bounds
        )

        # Convert back to screen
        screen_x, screen_y = window_to_screen_coords(win_x, win_y, bounds)

        # Should match original
        assert screen_x == original_screen_x
        assert screen_y == original_screen_y

    def test_multiple_windows_different_offsets(self):
        """Test conversions work correctly with different window bounds."""
        window1 = WindowBoundsResult(
            success=True, x=0, y=0, width=800, height=600, title="Window 1"
        )
        window2 = WindowBoundsResult(
            success=True, x=1000, y=500, width=800, height=600, title="Window 2"
        )

        # Same window coords in different windows -> different screen coords
        win_x, win_y = 100, 100

        screen1_x, screen1_y = window_to_screen_coords(win_x, win_y, window1)
        screen2_x, screen2_y = window_to_screen_coords(win_x, win_y, window2)

        assert screen1_x == 100  # 0 + 100
        assert screen1_y == 100  # 0 + 100
        assert screen2_x == 1100  # 1000 + 100
        assert screen2_y == 600  # 500 + 100


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
