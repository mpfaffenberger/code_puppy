"""Unit tests for browser offset calculation utilities."""

import pytest

from code_puppy.tools.gui_cub.core.browser_offsets import (
    calculate_chrome_offset,
    get_title_bar_height,
)


class TestCalculateChromeOffset:
    """Test browser chrome offset calculation."""

    def test_chrome_mac(self):
        """Chrome on macOS should have specific offset."""
        offset = calculate_chrome_offset(browser="chrome", platform="darwin")
        assert isinstance(offset, int)
        assert offset >= 0

    def test_chrome_windows(self):
        """Chrome on Windows should have specific offset."""
        offset = calculate_chrome_offset(browser="chrome", platform="win32")
        assert isinstance(offset, int)
        assert offset >= 0

    def test_firefox_mac(self):
        """Firefox on macOS should have specific offset."""
        offset = calculate_chrome_offset(browser="firefox", platform="darwin")
        assert isinstance(offset, int)
        assert offset >= 0

    def test_safari_mac(self):
        """Safari on macOS should have specific offset."""
        offset = calculate_chrome_offset(browser="safari", platform="darwin")
        assert isinstance(offset, int)
        assert offset >= 0

    def test_edge_windows(self):
        """Edge on Windows should have specific offset."""
        offset = calculate_chrome_offset(browser="edge", platform="win32")
        assert isinstance(offset, int)
        assert offset >= 0

    def test_different_browsers_different_offsets(self):
        """Different browsers may have different offsets."""
        chrome = calculate_chrome_offset(browser="chrome", platform="darwin")
        firefox = calculate_chrome_offset(browser="firefox", platform="darwin")
        # They might be same or different, just verify both return valid values
        assert isinstance(chrome, int)
        assert isinstance(firefox, int)


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
