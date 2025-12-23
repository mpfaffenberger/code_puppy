"""Integration tests for the theme system."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.themes import (
    PRESET_THEMES,
    PRESET_THEME_DESCRIPTIONS,
    get_all_themes,
    get_preset_theme,
    get_preset_theme_description,
    get_theme_info,
    get_theme_manager,
    get_theme_name,
    is_preset_theme,
    list_preset_themes,
    list_preset_themes_with_descriptions,
    set_theme_name,
    validate_theme_name,
)
from code_puppy.themes.theme import Theme
from code_puppy.themes.theme_manager import ThemeManager


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_theme_dir(tmp_path):
    """Fixture providing a temporary theme directory."""
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    return theme_dir


@pytest.fixture
def theme_manager(mock_theme_dir):
    """Fixture providing a ThemeManager instance with a temporary directory."""
    return ThemeManager(theme_dir=mock_theme_dir)


@pytest.fixture
def sample_theme_data():
    """Fixture providing sample theme data for JSON files."""
    return {
        "name": "integration_test",
        "description": "Integration test theme",
        "created_at": "2024-01-01T00:00:00",
        "colors": {
            "error_color": "bright_red",
            "warning_color": "bright_yellow",
            "success_color": "bright_green",
            "info_color": "bright_blue",
            "debug_color": "dim",
            "tool_output_color": "bright_cyan",
            "agent_reasoning_color": "bright_magenta",
            "agent_response_color": "bright_blue",
            "system_color": "bright_black",
        },
    }


# =============================================================================
# TestPresetThemes
# =============================================================================


class TestPresetThemes:
    """Test preset theme functionality."""

    def test_list_preset_themes(self):
        """Test listing all preset themes."""
        themes = list_preset_themes()
        assert isinstance(themes, list)
        assert len(themes) > 0
        assert "default" in themes
        assert "midnight" in themes

    def test_get_preset_theme_default(self):
        """Test getting the default preset theme."""
        theme = get_preset_theme("default")
        assert isinstance(theme, Theme)
        assert theme.error_color == "bold red"
        assert theme.warning_color == "yellow"

    def test_get_preset_theme_midnight(self):
        """Test getting the midnight preset theme."""
        theme = get_preset_theme("midnight")
        assert isinstance(theme, Theme)
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"

    def test_get_preset_theme_case_insensitive(self):
        """Test that preset theme names are case-insensitive."""
        theme1 = get_preset_theme("MIDNIGHT")
        theme2 = get_preset_theme("midnight")
        assert theme1.error_color == theme2.error_color

    def test_get_preset_theme_description(self):
        """Test getting preset theme descriptions."""
        desc = get_preset_theme_description("midnight")
        assert isinstance(desc, str)
        assert len(desc) > 0
        assert "blue" in desc.lower() or "purple" in desc.lower()

    def test_list_preset_themes_with_descriptions(self):
        """Test listing preset themes with their descriptions."""
        themes = list_preset_themes_with_descriptions()
        assert isinstance(themes, dict)
        assert len(themes) > 0
        assert "default" in themes
        assert isinstance(themes["default"], str)
        assert len(themes["default"]) > 0


# =============================================================================
# TestThemeSwitching
# =============================================================================


class TestThemeSwitching:
    """Test theme switching functionality."""

    def test_switch_between_presets(self, theme_manager):
        """Test switching between different preset themes."""
        theme1 = theme_manager.load_theme("default")
        theme2 = theme_manager.load_theme("midnight")

        assert theme1.error_color == "bold red"
        assert theme2.error_color == "bright_red"

        theme_manager.apply_theme(theme1)
        assert theme_manager._current_theme == theme1

        theme_manager.apply_theme(theme2)
        assert theme_manager._current_theme == theme2

    def test_switch_from_preset_to_custom(self, theme_manager, sample_theme_data):
        """Test switching from preset to custom theme."""
        # Save custom theme
        theme_file = theme_manager._theme_dir / "custom.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        # Load and apply preset
        preset_theme = theme_manager.load_theme("default")
        theme_manager.apply_theme(preset_theme)
        assert theme_manager._current_theme == preset_theme

        # Load and apply custom
        custom_theme = theme_manager.load_theme("custom")
        theme_manager.apply_theme(custom_theme)
        assert theme_manager._current_theme == custom_theme

    def test_get_current_theme_loads_from_config(self, theme_manager, monkeypatch):
        """Test that get_current_theme loads from config if not set."""
        mock_get_value = MagicMock(return_value="midnight")
        monkeypatch.setattr(
            "code_puppy.themes.theme_manager.get_value",
            mock_get_value,
        )

        current = theme_manager.get_current_theme()
        assert current.error_color == "bright_red"  # midnight theme
        assert theme_manager._current_theme == current



# =============================================================================
# TestThemeHelperFunctions
# =============================================================================


class TestThemeHelperFunctions:
    """Test theme helper functions."""

    def test_is_preset_theme_with_preset(self):
        """Test is_preset_theme with a preset theme."""
        assert is_preset_theme("default") is True
        assert is_preset_theme("midnight") is True
        assert is_preset_theme("MIDNIGHT") is True  # Case-insensitive

    def test_is_preset_theme_with_custom(self, theme_manager, sample_theme_data):
        """Test is_preset_theme with a custom theme."""
        # Save custom theme
        theme_file = theme_manager._theme_dir / "custom.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        assert is_preset_theme("custom") is False

    def test_is_preset_theme_with_nonexistent(self):
        """Test is_preset_theme with non-existent theme."""
        assert is_preset_theme("nonexistent") is False

    def test_get_theme_info_for_preset(self):
        """Test get_theme_info for a preset theme."""
        info = get_theme_info("midnight")
        assert info is not None
        assert info["name"] == "midnight"
        assert info["is_preset"] is True
        assert "description" in info

    def test_get_theme_info_for_custom(self, theme_manager, sample_theme_data, mock_theme_dir):
        """Test get_theme_info for a custom theme."""
        # Save custom theme
        theme_file = theme_manager._theme_dir / "custom.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        info = get_theme_info("custom", theme_dir=mock_theme_dir)
        assert info is not None
        assert info["name"] == "custom"
        assert info["is_preset"] is False
        assert info["description"] == "Integration test theme"

    def test_get_theme_info_for_nonexistent(self):
        """Test get_theme_info for non-existent theme."""
        info = get_theme_info("nonexistent")
        assert info is None

    def test_get_all_themes(self):
        """Test get_all_themes returns both presets and custom themes."""
        all_themes = get_all_themes()
        assert isinstance(all_themes, dict)
        assert len(all_themes) > 0
        assert "default" in all_themes
        assert all(all_themes[name] is not None for name in all_themes)


# =============================================================================
# TestThemeColors
# =============================================================================


class TestThemeColors:
    """Test theme color fields and validation."""

    def test_theme_has_all_required_color_fields(self):
        """Test that Theme has all required color fields."""
        theme = Theme()
        assert hasattr(theme, "error_color")
        assert hasattr(theme, "warning_color")
        assert hasattr(theme, "success_color")
        assert hasattr(theme, "info_color")
        assert hasattr(theme, "debug_color")
        assert hasattr(theme, "tool_output_color")
        assert hasattr(theme, "agent_reasoning_color")
        assert hasattr(theme, "agent_response_color")
        assert hasattr(theme, "system_color")

    def test_preset_themes_have_valid_colors(self):
        """Test that all preset themes have valid colors."""
        for name, theme in PRESET_THEMES.items():
            errors = theme.validate_colors()
            assert errors == [], f"Preset theme '{name}' has invalid colors: {errors}"

    def test_custom_theme_with_hex_colors(self):
        """Test creating a custom theme with hex colors."""
        theme = Theme(
            error_color="#FF0000",
            warning_color="#FFFF00",
            success_color="#00FF00",
            info_color="#0000FF",
            debug_color="dim",
            tool_output_color="#00FFFF",
            agent_reasoning_color="#FF00FF",
            agent_response_color="#000080",
            system_color="#808080",
        )
        errors = theme.validate_colors()
        assert errors == []


# =============================================================================
# TestThemeValidationIntegration
# =============================================================================


class TestThemeValidationIntegration:
    """Test integration of validation across the theme system."""

    def test_save_theme_validates_colors(self, theme_manager):
        """Test that save_theme validates colors before saving."""
        # Create theme with invalid color
        theme = Theme(error_color="not_a_color")

        with pytest.raises(ValueError, match="invalid colors"):
            theme_manager.save_theme(theme, "invalid_theme")

        # Verify file wasn't created
        theme_file = theme_manager._theme_dir / "invalid_theme.json"
        assert not theme_file.exists()

    def test_save_theme_validates_name(self, theme_manager):
        """Test that save_theme validates theme name before saving."""
        theme = Theme()

        with pytest.raises(ValueError, match="Invalid theme name"):
            theme_manager.save_theme(theme, "invalid name!")

        # Verify file wasn't created
        theme_file = theme_manager._theme_dir / "invalid name!.json"
        assert not theme_file.exists()
