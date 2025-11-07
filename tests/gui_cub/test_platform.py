"""Comprehensive tests for platform detection and helpers."""

from __future__ import annotations

import sys
from unittest.mock import patch


from code_puppy.tools.gui_cub.platform import (
    CURRENT_PLATFORM,
    IS_MACOS,
    IS_WINDOWS,
    Platform,
    check_macos_accessibility_permission,
    convert_screenshot_to_screen_coords,
    get_platform,
    get_platform_display_name,
    get_screen_scale_factor,
    require_platform,
    get_display_info,
)

# Linux is not currently supported in gui_cub
IS_LINUX = False


class TestPlatformEnum:
    """Test Platform enum."""

    def test_platform_values(self):
        assert Platform.MACOS.value == "darwin"
        assert Platform.WINDOWS.value == "win32"

    def test_platform_enum_members(self):
        platforms = list(Platform)
        assert len(platforms) == 2
        assert Platform.MACOS in platforms
        assert Platform.WINDOWS in platforms


class TestPlatformConstants:
    """Test platform detection constants."""

    def test_current_platform(self):
        assert CURRENT_PLATFORM == sys.platform

    def test_platform_booleans_mutually_exclusive(self):
        # Only one platform should be True
        true_count = sum([IS_MACOS, IS_WINDOWS, IS_LINUX])
        assert true_count <= 1

    def test_macos_detection(self):
        if sys.platform == "darwin":
            assert IS_MACOS is True
            assert IS_WINDOWS is False
            assert IS_LINUX is False

    def test_windows_detection(self):
        if sys.platform == "win32":
            assert IS_WINDOWS is True
            assert IS_MACOS is False
            assert IS_LINUX is False

    def test_linux_detection(self):
        if sys.platform == "linux":
            assert IS_LINUX is True
            assert IS_MACOS is False
            assert IS_WINDOWS is False


class TestGetPlatform:
    """Test get_platform function."""

    def test_get_current_platform(self):
        platform = get_platform()
        if sys.platform == "darwin":
            assert platform == Platform.MACOS
        elif sys.platform == "win32":
            assert platform == Platform.WINDOWS
        elif sys.platform == "linux":
            assert platform == Platform.LINUX

    @patch("code_puppy.tools.gui_cub.platform.sys")
    def test_get_unsupported_platform(self, mock_sys):
        mock_sys.platform = "unsupported_os"
        platform = get_platform()
        assert platform is None


class TestRequirePlatform:
    """Test require_platform decorator."""

    def test_decorator_allows_correct_platform(self):
        current = get_platform()
        if current:

            @require_platform(current)
            def test_func():
                return {"success": True}

            result = test_func()
            assert result["success"] is True

    def test_decorator_blocks_wrong_platform(self):
        current = get_platform()
        if current == Platform.MACOS:
            wrong_platform = Platform.WINDOWS
        else:
            wrong_platform = Platform.MACOS

        @require_platform(wrong_platform)
        def test_func():
            return {"success": True}

        result = test_func()
        assert result["success"] is False
        assert "requires" in result["error"].lower()

    def test_decorator_allows_multiple_platforms(self):
        @require_platform(Platform.MACOS, Platform.WINDOWS)
        def test_func():
            return {"success": True}

        result = test_func()
        assert result["success"] is True

    def test_decorator_preserves_function_name(self):
        @require_platform(Platform.MACOS, Platform.WINDOWS)
        def my_function():
            """Test docstring."""
            return {"success": True}

        assert my_function.__name__ == "my_function"
        assert "Test docstring" in my_function.__doc__

    def test_decorator_error_message_format(self):
        @require_platform(Platform.WINDOWS)  # If not on Windows
        def test_func():
            return {"success": True}

        result = test_func()
        if not IS_WINDOWS:
            assert "This tool requires WINDOWS" in result["error"]


class TestGetPlatformDisplayName:
    """Test get_platform_display_name function."""

    def test_macos_display_name(self):
        if IS_MACOS:
            assert get_platform_display_name() == "macOS"

    def test_windows_display_name(self):
        if IS_WINDOWS:
            assert get_platform_display_name() == "Windows"

    def test_linux_display_name(self):
        if IS_LINUX:
            assert get_platform_display_name() == "Linux"

    def test_display_name_is_string(self):
        name = get_platform_display_name()
        assert isinstance(name, str)
        assert len(name) > 0


class TestGetScreenScaleFactor:
    """Test screen scale factor detection."""

    def test_scale_factor_returns_float(self):
        """Test that scale factor returns a valid float."""
        scale = get_screen_scale_factor()
        assert isinstance(scale, float)
        assert scale >= 1.0
        assert scale <= 4.0


class TestConvertScreenshotToScreenCoords:
    """Test coordinate conversion."""

    def test_convert_with_1x_scale(self):
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            940, 250, scale_factor=1.0
        )
        assert screen_x == 940
        assert screen_y == 250

    def test_convert_with_2x_scale(self):
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            940, 250, scale_factor=2.0
        )
        assert screen_x == 470
        assert screen_y == 125

    def test_convert_with_1_5x_scale(self):
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            900, 300, scale_factor=1.5
        )
        assert screen_x == 600
        assert screen_y == 200

    def test_convert_auto_detects_scale(self):
        """Test that scale is auto-detected when not provided."""
        screen_x, screen_y = convert_screenshot_to_screen_coords(1000, 600)
        assert isinstance(screen_x, int)
        assert isinstance(screen_y, int)

    def test_convert_returns_integers(self):
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            941, 251, scale_factor=2.0
        )
        assert isinstance(screen_x, int)
        assert isinstance(screen_y, int)


class TestCheckMacOSAccessibilityPermission:
    """Test macOS accessibility permission checking."""

    @patch("code_puppy.tools.gui_cub.platform.IS_MACOS", False)
    def test_non_macos_returns_true(self):
        has_permission, error = check_macos_accessibility_permission()
        assert has_permission is True
        assert error is None

    def test_permission_check_returns_tuple(self):
        """Test that permission check returns proper tuple."""
        result = check_macos_accessibility_permission()
        assert isinstance(result, tuple)
        assert len(result) == 2
        has_permission, error = result
        assert isinstance(has_permission, bool)
        if not has_permission:
            assert error is not None


class TestGetDisplayInfo:
    """Test display info collection."""

    def test_get_display_info_returns_dict(self):
        """Test that get_display_info returns a dictionary with expected keys."""
        info = get_display_info()

        assert isinstance(info, dict)
        assert "platform" in info
        assert isinstance(info["platform"], str)

    def test_display_info_has_platform_name(self):
        """Test that display info includes platform name."""
        info = get_display_info()

        assert info["platform"] in ["macOS", "Windows", "Linux", "Unknown"]

    def test_display_info_includes_macos_permission_on_macos(self):
        """Test that macOS permissions are checked on macOS."""
        if IS_MACOS:
            info = get_display_info()
            assert "macos_accessibility_permission" in info
            assert isinstance(info["macos_accessibility_permission"], bool)
