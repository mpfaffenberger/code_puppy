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
        title_bar = 30
        browser_chrome = 50
        
        new_x, new_y = apply_chrome_offset(x, y, title_bar, browser_chrome)
        assert new_x == x  # X unchanged
        assert new_y == y + title_bar + browser_chrome

    def test_apply_offset_zero(self):
        """Zero offsets should return same coordinates."""
        x, y = 100, 200
        new_x, new_y = apply_chrome_offset(x, y, 0, 0)
        assert new_x == x
        assert new_y == y

    def test_apply_offset_title_bar_only(self):
        """Only title bar offset."""
        x, y = 100, 100
        title_bar = 25
        new_x, new_y = apply_chrome_offset(x, y, title_bar, 0)
        assert new_x == x
        assert new_y == y + title_bar


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
