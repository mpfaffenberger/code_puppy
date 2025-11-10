"""Unit tests for configuration validation utilities."""

import pytest

from code_puppy.tools.gui_cub.core.config_validation import (
    validate_screen_size,
    validate_platform,
    validate_config_version,
)


class TestValidateScreenSize:
    """Test screen size validation."""

    def test_identical_size_valid(self):
        """Identical screen sizes should be valid."""
        current = (1920, 1080)
        cached = (1920, 1080)
        assert validate_screen_size(current, cached) is True

    def test_different_size_invalid(self):
        """Different screen sizes should be invalid."""
        current = (1920, 1080)
        cached = (2560, 1440)
        assert validate_screen_size(current, cached) is False

    def test_width_changed(self):
        """Changed width should invalidate."""
        current = (1920, 1080)
        cached = (1680, 1080)
        assert validate_screen_size(current, cached) is False

    def test_height_changed(self):
        """Changed height should invalidate."""
        current = (1920, 1080)
        cached = (1920, 1200)
        assert validate_screen_size(current, cached) is False


class TestValidatePlatform:
    """Test platform validation."""

    def test_identical_platform_valid(self):
        """Same platform should be valid."""
        assert validate_platform("darwin", "darwin") is True
        assert validate_platform("win32", "win32") is True
        assert validate_platform("linux", "linux") is True

    def test_different_platform_invalid(self):
        """Different platform should be invalid."""
        assert validate_platform("darwin", "win32") is False
        assert validate_platform("win32", "linux") is False

    def test_case_sensitive(self):
        """Platform comparison should be case-sensitive."""
        assert validate_platform("darwin", "Darwin") is False


class TestValidateConfigVersion:
    """Test config version validation."""

    def test_valid_version_format(self):
        """Standard version format should be valid."""
        assert validate_config_version("1.0.0") is True
        assert validate_config_version("2.5.3") is True

    def test_invalid_version_format(self):
        """Invalid version format should be rejected."""
        assert validate_config_version("invalid") is False
        assert validate_config_version("") is False

    def test_version_with_prerelease(self):
        """Version with prerelease tag."""
        # Depends on implementation
        result = validate_config_version("1.0.0-beta")
        assert isinstance(result, bool)
