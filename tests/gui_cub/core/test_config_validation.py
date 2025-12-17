"""Unit tests for configuration validation utilities."""

from code_puppy.tools.gui_cub.core.config_validation import (
    validate_resolution_match,
    validate_platform_match,
    validate_scale_factor,
)


class TestValidateResolutionMatch:
    """Test resolution matching validation."""

    def test_identical_resolution_valid(self):
        """Identical resolutions should match."""
        cached = [1920, 1080]
        current = [1920, 1080]
        is_valid, _ = validate_resolution_match(cached, current)
        assert is_valid is True

    def test_different_resolution_invalid(self):
        """Different resolutions should not match."""
        cached = [1920, 1080]
        current = [2560, 1440]
        is_valid, msg = validate_resolution_match(cached, current)
        assert is_valid is False
        assert "resolution" in msg.lower()

    def test_width_changed(self):
        """Changed width should invalidate."""
        cached = [1680, 1080]
        current = [1920, 1080]
        is_valid, _ = validate_resolution_match(cached, current)
        assert is_valid is False

    def test_height_changed(self):
        """Changed height should invalidate."""
        cached = [1920, 1200]
        current = [1920, 1080]
        is_valid, _ = validate_resolution_match(cached, current)
        assert is_valid is False

    def test_none_cached_resolution(self):
        """None cached resolution should be invalid."""
        is_valid, msg = validate_resolution_match(None, [1920, 1080])
        assert is_valid is False
        assert "no cached" in msg.lower()

    def test_invalid_cached_format(self):
        """Invalid cached resolution format should be handled."""
        is_valid, msg = validate_resolution_match("invalid", [1920, 1080])
        assert is_valid is False
        assert "invalid" in msg.lower()

    def test_invalid_current_format(self):
        """Invalid current resolution format should be handled."""
        is_valid, msg = validate_resolution_match([1920, 1080], "invalid")
        assert is_valid is False
        assert "invalid" in msg.lower()


class TestValidatePlatformMatch:
    """Test platform matching validation."""

    def test_identical_platform_valid(self):
        """Same platform should match."""
        is_valid, _ = validate_platform_match("darwin", "darwin")
        assert is_valid is True
        is_valid, _ = validate_platform_match("win32", "win32")
        assert is_valid is True

    def test_different_platform_invalid(self):
        """Different platform should not match."""
        is_valid, msg = validate_platform_match("darwin", "win32")
        assert is_valid is False
        assert "platform" in msg.lower()


class TestValidateScaleFactor:
    """Test scale factor validation."""

    def test_valid_scale_factors(self):
        """Common scale factors should be valid."""
        is_valid, _ = validate_scale_factor(1.0)
        assert is_valid is True
        is_valid, _ = validate_scale_factor(2.0)
        assert is_valid is True

    def test_invalid_scale_zero(self):
        """Zero scale factor should be invalid."""
        is_valid, msg = validate_scale_factor(0.0)
        assert is_valid is False

    def test_invalid_scale_negative(self):
        """Negative scale factor should be invalid."""
        is_valid, _ = validate_scale_factor(-1.0)
        assert is_valid is False

    def test_none_scale_factor(self):
        """None scale factor should be handled."""
        is_valid, msg = validate_scale_factor(None)
        assert is_valid is False
        assert "scale" in msg.lower()
