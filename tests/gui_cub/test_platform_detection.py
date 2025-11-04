"""Tests for platform detection."""

import pytest
import sys

from code_puppy.tools.gui_cub.platform import IS_MACOS, IS_WINDOWS, IS_LINUX


class TestPlatformDetection:
    """Test platform detection flags."""
    
    def test_only_one_platform_is_true(self):
        """Verify exactly one platform flag is True."""
        platforms = [IS_MACOS, IS_WINDOWS, IS_LINUX]
        assert sum(platforms) == 1, "Exactly one platform should be detected"
    
    def test_platform_matches_sys_platform(self):
        """Verify platform detection matches sys.platform."""
        if sys.platform == "darwin":
            assert IS_MACOS is True
            assert IS_WINDOWS is False
            assert IS_LINUX is False
        elif sys.platform == "win32":
            assert IS_MACOS is False
            assert IS_WINDOWS is True
            assert IS_LINUX is False
        elif sys.platform.startswith("linux"):
            assert IS_MACOS is False
            assert IS_WINDOWS is False
            assert IS_LINUX is True
