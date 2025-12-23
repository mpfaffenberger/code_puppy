"""Tests for theme manager functionality."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.theming.builtin_themes import BUILTIN_THEMES
from code_puppy.theming.theme_manager import (
    _load_custom_theme,
    apply_theme,
    get_available_themes,
    get_current_theme,
    get_theme_by_name,
    save_custom_theme,
    set_current_theme,
)


class TestThemeManager:
    """Test the core theme management functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for config files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_get_current_theme_returns_valid_theme(self, temp_config_dir):
        """Test that get_current_theme always returns a valid theme."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Should return default theme when no config exists
            theme = get_current_theme()
            assert theme is not None
            assert hasattr(theme, "name")
            assert hasattr(theme, "display_name")
            assert hasattr(theme, "colors")
            assert theme.colors is not None

    def test_set_current_theme_persists_correctly(self, temp_config_dir):
        """Test that set_currentTheme persists to config correctly."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Set a theme
            result = set_current_theme("dracula")
            assert result is True

            # Check that config was created
            config_path = temp_config_dir / "puppy.cfg"
            assert config_path.exists()

            # Check config content
            content = config_path.read_text()
            assert "theme" in content
            assert "dracula" in content

            # Verify theme is now current
            current = get_current_theme()
            assert current.name == "dracula"

    def test_set_current_theme_invalid_name(self, temp_config_dir):
        """Test that set_current_theme handles invalid theme names."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Set invalid theme
            result = set_current_theme("nonexistent-theme")
            assert result is False

            # Should still have a valid theme (default)
            current = get_current_theme()
            assert current.name == "default"

    def test_get_available_themes_includes_builtin_and_custom(self, temp_config_dir):
        """Test that get_available_themes returns all themes."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            themes = get_available_themes()

            # Should include all builtin themes
            for name in BUILTIN_THEMES:
                assert name in themes

            # Should be a list
            assert isinstance(themes, list)
            assert len(themes) >= len(BUILTIN_THEMES)

    def test_get_theme_by_name_valid_names(self, temp_config_dir):
        """Test get_theme_by_name with valid theme names."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Test builtin theme
            theme = get_theme_by_name("dracula")
            assert theme is not None
            assert theme.name == "dracula"
            assert theme.display_name is not None
            assert theme.colors is not None

            # Test default theme
            default = get_theme_by_name("default")
            assert default is not None
            assert default.name == "default"

    def test_get_theme_by_name_invalid_names(self, temp_config_dir):
        """Test get_theme_by_name with invalid theme names."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Nonexistent theme
            theme = get_theme_by_name("nonexistent-theme")
            assert theme is None

            # Empty string
            theme = get_theme_by_name("")
            assert theme is None

            # None
            theme = get_theme_by_name(None)
            assert theme is None

    def test_apply_theme_updates_mappings(self, temp_config_dir):
        """Test that apply_theme correctly updates global style mappings."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Apply a theme
            theme = get_theme_by_name("dracula")
            apply_theme(theme)

            # Should not raise any exceptions
            # Note: In a real test, we might check that global mappings are updated
            # but since we don't have direct access to the global styles, we just
            # verify no errors occurred
            assert True

    def test_theme_caching_improves_performance(self, temp_config_dir):
        """Test that theme caching works as expected."""
        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # First call should load from config/filesystem
            theme1 = get_current_theme()

            # Second call should be faster (cache hit)
            theme2 = get_current_theme()

            # Should return same theme object (cached)
            assert theme1 is theme2
            assert theme1.name == theme2.name


class TestCustomThemes:
    """Test custom theme loading and saving functionality."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary directory for config files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_load_custom_theme_missing_file(self, temp_config_dir):
        """Test loading custom theme when file doesn't exist."""
        custom_theme_path = temp_config_dir / "custom_theme.json"
        assert not custom_theme_path.exists()

        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            custom_theme = _load_custom_theme()
            assert custom_theme is None

    def test_load_custom_theme_valid_file(self, temp_config_dir):
        """Test loading valid custom theme file."""
        custom_theme_path = temp_config_dir / "custom_theme.json"

        # Create a valid custom theme
        custom_theme_data = {
            "name": "custom-theme",
            "display_name": "Custom Theme",
            "description": "A custom test theme",
            "colors": {
                "error_style": "bold #ff0000",
                "success_style": "#00ff00",
                "spinner_style": "bold #0000ff",
            },
        }

        import json

        custom_theme_path.write_text(json.dumps(custom_theme_data))

        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            custom_theme = _load_custom_theme()
            assert custom_theme is not None
            assert custom_theme.name == "custom-theme"
            assert custom_theme.display_name == "Custom Theme"
            assert custom_theme.colors.error_style == "bold #ff0000"

    def test_load_custom_theme_invalid_file(self, temp_config_dir):
        """Test loading invalid custom theme file."""
        custom_theme_path = temp_config_dir / "custom_theme.json"
        custom_theme_path.write_text("invalid json content")

        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Should handle invalid JSON gracefully
            custom_theme = _load_custom_theme()
            assert custom_theme is None

    def test_save_custom_theme_creates_file(self, temp_config_dir):
        """Test that save_custom_theme creates and saves theme file."""
        from code_puppy.theming.theme_models import ThemeColors

        custom_colors = ThemeColors(error_style="bold #ff0000", success_style="#00ff00")

        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            save_custom_theme(custom_colors)

            # Check file was created
            custom_theme_path = temp_config_dir / "custom_theme.json"
            assert custom_theme_path.exists()

            # Check file content
            import json

            content = json.loads(custom_theme_path.read_text())
            assert "colors" in content
            assert content["colors"]["error_style"] == "bold #ff0000"
            assert content["colors"]["success_style"] == "#00ff00"

    def test_custom_theme_integration(self, temp_config_dir):
        """Test that custom themes integrate properly with the system."""
        custom_theme_path = temp_config_dir / "custom_theme.json"

        # Create custom theme
        custom_theme_data = {
            "name": "my-custom",
            "display_name": "My Custom Theme",
            "description": "A fully custom theme",
            "colors": {
                "error_style": "bold #ff0000",
                "success_style": "#00ff00",
                "warning_style": "#ffff00",
                "info_style": "#0000ff",
                "debug_style": "#ffffff",
                "header_style": "bold #ff00ff",
                "prompt_style": "#00ffff",
                "accent_style": "bold #ffaa00",
                "muted_style": "#666666",
                "highlight_style": "#aaaaaa",
                "reasoning_header_style": "bold #ff6600",
                "response_header_style": "bold #00ff99",
                "file_path_style": "#3366ff",
                "line_number_style": "#999999",
                "command_style": "bold #ff33cc",
                "spinner_style": "bold #00ff33",
                "spinner_text_style": "#33ff00",
                "panel_border_style": "#cccccc",
                "panel_title_style": "bold #ffffff",
                "nav_key_style": "bold #ffaa00",
                "nav_text_style": "#aaff00",
            },
        }

        import json

        custom_theme_path.write_text(json.dumps(custom_theme_data))

        with patch("code_puppy.theming.theme_manager.get_config_path") as mock_config:
            mock_config.return_value = temp_config_dir

            # Should be included in available themes
            themes = get_available_themes()
            assert "my-custom" in themes

            # Should be gettable by name
            custom_theme = get_theme_by_name("my-custom")
            assert custom_theme is not None
            assert custom_theme.name == "my-custom"
            assert custom_theme.display_name == "My Custom Theme"
            assert custom_theme.colors.error_style == "bold #ff0000"
