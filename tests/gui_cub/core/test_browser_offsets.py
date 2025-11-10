"""Unit tests for browser offset calculation utilities."""

import pytest

from code_puppy.tools.gui_cub.core.browser_offsets import (
    apply_chrome_offset,
    get_title_bar_height,
)


class TestApplyChromeOffset:
    """Test browser chrome offset application."""

    def test_apply_offset_adds_to_y(self):
        """Applying offset should adjust Y coordinate."""
        x, y = 100, 100
        chrome_height = 85
        
        new_x, new_y = apply_chrome_offset(x, y, chrome_height)
        assert new_x == x  # X unchanged
        assert new_y == y + chrome_height  # Y adjusted

    def test_apply_offset_zero(self):
        """Zero offset should return same coordinates."""
        x, y = 100, 200
        new_x, new_y = apply_chrome_offset(x, y, 0)
        assert new_x == x
        assert new_y == y

    def test_apply_offset_with_low_confidence(self):
        """Low confidence should not apply offset."""
        x, y = 100, 100
        chrome_height = 85
        # Confidence below threshold (default 0.7)
        new_x, new_y = apply_chrome_offset(x, y, chrome_height, confidence=0.5)
        assert new_x == x
        assert new_y == y  # No offset applied

    def test_apply_offset_with_high_confidence(self):
        """High confidence should apply offset."""
        x, y = 100, 100
        chrome_height = 85
        new_x, new_y = apply_chrome_offset(x, y, chrome_height, confidence=0.9)
        assert new_x == x
        assert new_y == y + chrome_height


class TestGetTitleBarHeight:
    """Test platform title bar height retrieval."""

    def test_mac_title_bar(self):
        """macOS should have title bar height."""
        height = get_title_bar_height(platform="darwin")
        assert isinstance(height, int)
        assert height > 0  # macOS has visible title bar

    def test_windows_title_bar(self):
        """Windows should have title bar height."""
        height = get_title_bar_height(platform="win32")
        assert isinstance(height, int)
        assert height >= 0

    def test_linux_title_bar(self):
        """Linux should have title bar height."""
        height = get_title_bar_height(platform="linux")
        assert isinstance(height, int)
        assert height >= 0

    def test_unknown_platform(self):
        """Unknown platform should return reasonable default."""
        height = get_title_bar_height(platform="unknown")
        assert isinstance(height, int)
        assert height >= 0
