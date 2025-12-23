"""Tests for the ThemeManager class and its functionality."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.themes.theme import Theme, validate_theme_name
from code_puppy.themes.theme_manager import (
    DEFAULT_THEME,
    ThemeManager,
    get_all_themes,
    get_theme_info,
    get_theme_manager,
    get_theme_name,
    is_preset_theme,
    set_theme_name,
)
from code_puppy.themes.presets import PRESET_THEMES, list_preset_themes


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
        "name": "test_theme",
        "description": "Test theme description",
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
# TestThemeManagerInitialization
# =============================================================================


class TestThemeManagerInitialization:
    """Test ThemeManager initialization."""

    def test_theme_manager_initialization_default_dir(self, monkeypatch):
        """Test ThemeManager initialization with default directory."""
        # This test uses the default THEME_DIR from the module
        manager = ThemeManager()
        assert manager._theme_dir is not None
        assert manager._current_theme is None

    def test_theme_manager_initialization_custom_dir(self, mock_theme_dir):
        """Test ThemeManager initialization with custom directory."""
        manager = ThemeManager(theme_dir=mock_theme_dir)
        assert manager._theme_dir == mock_theme_dir
        assert manager._current_theme is None


# =============================================================================
# TestThemeManagerLoadTheme
# =============================================================================


class TestThemeManagerLoadTheme:
    """Test ThemeManager.load_theme functionality."""

    def test_load_theme_preset(self, theme_manager):
        """Test loading a preset theme."""
        theme = theme_manager.load_theme("default")
        assert theme.error_color == "bold red"
        assert theme.warning_color == "yellow"

    def test_load_theme_preset_case_insensitive(self, theme_manager):
        """Test loading a preset theme with different case."""
        theme = theme_manager.load_theme("MIDNIGHT")
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"

    def test_load_theme_custom_from_file(self, theme_manager, sample_theme_data):
        """Test loading a custom theme from JSON file."""
        theme_file = theme_manager._theme_dir / "custom.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        theme = theme_manager.load_theme("custom")
        assert theme.error_color == "bright_red"
        assert theme.warning_color == "bright_yellow"

    def test_load_theme_not_found_returns_default(self, theme_manager):
        """Test that loading a non-existent theme returns DEFAULT_THEME."""
        theme = theme_manager.load_theme("nonexistent")
        assert theme.error_color == DEFAULT_THEME.error_color

    def test_load_theme_invalid_json_returns_default(self, theme_manager):
        """Test that loading a theme with invalid JSON returns DEFAULT_THEME."""
        theme_file = theme_manager._theme_dir / "invalid.json"
        with open(theme_file, "w") as f:
            f.write("{ invalid json }")

        theme = theme_manager.load_theme("invalid")
        assert theme.error_color == DEFAULT_THEME.error_color



# =============================================================================
# TestThemeManagerSaveTheme
# =============================================================================


class TestThemeManagerSaveTheme:
    """Test ThemeManager.save_theme functionality."""

    def test_save_theme_success(self, theme_manager, sample_theme_data):
        """Test saving a theme successfully."""
        theme = Theme.from_dict(sample_theme_data)
        theme_manager.save_theme(theme, "test_theme", description="Test description")

        theme_file = theme_manager._theme_dir / "test_theme.json"
        assert theme_file.exists()

        with open(theme_file, "r") as f:
            saved_data = json.load(f)

        assert saved_data["name"] == "test_theme"
        assert saved_data["description"] == "Test description"
        assert "created_at" in saved_data
        assert saved_data["colors"]["error_color"] == "bright_red"

    def test_save_theme_invalid_name_raises_error(self, theme_manager):
        """Test that saving a theme with invalid name raises ValueError."""
        theme = Theme()
        with pytest.raises(ValueError, match="Invalid theme name"):
            theme_manager.save_theme(theme, "invalid name!")

    def test_save_theme_invalid_colors_raises_error(self, theme_manager):
        """Test that saving a theme with invalid colors raises ValueError."""
        theme = Theme(error_color="not_a_color")
        with pytest.raises(ValueError, match="invalid colors"):
            theme_manager.save_theme(theme, "invalid_colors_theme")



# =============================================================================
# TestThemeManagerListThemes
# =============================================================================


class TestThemeManagerListThemes:
    """Test ThemeManager theme listing functionality."""

    def test_list_available_themes_presets_only(self, theme_manager):
        """Test listing themes when only presets are available."""
        themes = theme_manager.list_available_themes()
        assert isinstance(themes, list)
        assert len(themes) > 0
        assert "default" in themes

    def test_list_custom_themes(self, theme_manager, sample_theme_data):
        """Test listing custom themes only."""
        # Create a custom theme
        theme_file = theme_manager._theme_dir / "custom.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        # Create a backup file (should be excluded)
        backup_file = theme_manager._theme_dir / "custom.json.backup"
        backup_file.touch()

        custom_themes = theme_manager.list_custom_themes()
        assert "custom" in custom_themes
        assert "custom.json.backup" not in custom_themes



# =============================================================================
# TestThemeManagerDeleteTheme
# =============================================================================


class TestThemeManagerDeleteTheme:
    """Test ThemeManager.delete_theme functionality."""

    def test_delete_custom_theme_success(self, theme_manager, sample_theme_data):
        """Test deleting a custom theme successfully."""
        # Create a custom theme
        theme_file = theme_manager._theme_dir / "to_delete.json"
        with open(theme_file, "w") as f:
            json.dump(sample_theme_data, f)

        # Also create a backup file
        backup_file = theme_manager._theme_dir / "to_delete.json.backup"
        backup_file.touch()

        result = theme_manager.delete_theme("to_delete")
        assert result is True
        assert not theme_file.exists()
        assert not backup_file.exists()

    def test_delete_preset_theme_raises_error(self, theme_manager):
        """Test that deleting a preset theme raises ValueError."""
        with pytest.raises(ValueError, match="Cannot delete preset theme"):
            theme_manager.delete_theme("default")

    def test_delete_nonexistent_theme_raises_error(self, theme_manager):
        """Test that deleting a non-existent theme raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            theme_manager.delete_theme("nonexistent")



# =============================================================================
# TestThemeManagerExportImport
# =============================================================================


class TestThemeManagerExportImport:
    """Test ThemeManager export and import functionality."""

    def test_export_theme_success(self, theme_manager, tmp_path):
        """Test exporting a theme to a file."""
        export_path = tmp_path / "exported_theme.json"
        result = theme_manager.export_theme("default", str(export_path))

        assert result is True
        assert export_path.exists()

        with open(export_path, "r") as f:
            data = json.load(f)

        assert data["name"] == "default"
        assert "exported_at" in data
        assert "colors" in data

    def test_import_theme_success(self, theme_manager, tmp_path, sample_theme_data):
        """Test importing a theme from a file."""
        import_path = tmp_path / "import_theme.json"
        with open(import_path, "w") as f:
            json.dump(sample_theme_data, f)

        imported_name = theme_manager.import_theme(str(import_path))
        assert imported_name == "test_theme"

        # Verify the theme was saved
        theme_file = theme_manager._theme_dir / "test_theme.json"
        assert theme_file.exists()



# =============================================================================
# TestThemeManagerApplyTheme
# =============================================================================


class TestThemeManagerApplyTheme:
    """Test ThemeManager.apply_theme functionality."""

    def test_apply_theme_success(self, theme_manager):
        """Test applying a theme successfully."""
        theme = Theme(error_color="bright_red")
        result = theme_manager.apply_theme(theme)

        assert result is True
        assert theme_manager._current_theme == theme

    def test_apply_invalid_theme_returns_false(self, theme_manager):
        """Test that applying an invalid theme returns False."""
        # Create a theme with invalid colors
        theme = Theme(error_color="not_a_color")
        result = theme_manager.apply_theme(theme)

        assert result is False
        # Current theme should remain None
        assert theme_manager._current_theme is None
