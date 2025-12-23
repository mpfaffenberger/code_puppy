"""Tests for theme persistence and config integration."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.themes.theme import Theme
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
def mock_config_dir(tmp_path):
    """Fixture providing a temporary config directory."""
    config_dir = tmp_path / ".code_puppy"
    config_dir.mkdir()
    return config_dir


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
        "name": "custom_theme",
        "description": "A custom theme for testing",
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
# TestThemePersistence
# =============================================================================


class TestThemePersistence:
    """Test theme persistence across manager instances."""

    def test_save_and_load_theme_persistence(self, mock_theme_dir, sample_theme_data):
        """Test that a saved theme can be loaded by a new manager instance."""
        # Create and save theme with first manager
        manager1 = ThemeManager(theme_dir=mock_theme_dir)
        theme = Theme.from_dict(sample_theme_data)
        manager1.save_theme(theme, "persistent_theme", description="Persistent theme")

        # Load with new manager instance
        manager2 = ThemeManager(theme_dir=mock_theme_dir)
        loaded_theme = manager2.load_theme("persistent_theme")

        assert loaded_theme.error_color == "bright_red"
        assert loaded_theme.warning_color == "bright_yellow"

    def test_theme_file_format_persistence(self, mock_theme_dir, sample_theme_data):
        """Test that theme files are saved in correct JSON format."""
        manager = ThemeManager(theme_dir=mock_theme_dir)
        theme = Theme.from_dict(sample_theme_data)
        manager.save_theme(theme, "format_test", description="Format test")

        theme_file = mock_theme_dir / "format_test.json"
        with open(theme_file, "r") as f:
            data = json.load(f)

        # Verify structure
        assert "name" in data
        assert "description" in data
        assert "created_at" in data
        assert "colors" in data
        assert isinstance(data["colors"], dict)

    def test_theme_backup_on_save(self, mock_theme_dir, sample_theme_data):
        """Test that saving a theme creates a backup of the original."""
        manager = ThemeManager(theme_dir=mock_theme_dir)
        theme = Theme.from_dict(sample_theme_data)

        # Save initial version
        manager.save_theme(theme, "backup_test", description="Initial")
        theme_file = mock_theme_dir / "backup_test.json"
        initial_mtime = os.path.getmtime(theme_file)

        # Modify and save again
        theme.error_color = "red"
        manager.save_theme(theme, "backup_test", description="Updated")

        # Check backup exists
        backup_file = mock_theme_dir / "backup_test.json.backup"
        assert backup_file.exists()

        # Verify backup has old content
        with open(backup_file, "r") as f:
            backup_data = json.load(f)
        assert backup_data["description"] == "Initial"

    def test_theme_metadata_persistence(self, mock_theme_dir, sample_theme_data):
        """Test that theme metadata is persisted correctly."""
        manager = ThemeManager(theme_dir=mock_theme_dir)
        theme = Theme.from_dict(sample_theme_data)

        manager.save_theme(
            theme,
            "metadata_test",
            description="Metadata test theme",
        )

        theme_file = mock_theme_dir / "metadata_test.json"
        with open(theme_file, "r") as f:
            data = json.load(f)

        assert data["name"] == "metadata_test"
        assert data["description"] == "Metadata test theme"
        assert "created_at" in data



# =============================================================================
# TestThemeConfigIntegration
# =============================================================================


class TestThemeConfigIntegration:
    """Test integration with the config system."""

    def test_set_theme_name_integration(self, monkeypatch):
        """Test set_theme_name integration with config system."""
        mock_set_config_value = MagicMock()
        monkeypatch.setattr(
            "code_puppy.themes.theme_manager.set_config_value",
            mock_set_config_value,
        )

        set_theme_name("midnight")
        mock_set_config_value.assert_called_once_with("theme", "midnight")

    def test_get_theme_name_integration(self, monkeypatch):
        """Test get_theme_name integration with config system."""
        mock_get_value = MagicMock(return_value="ocean")
        monkeypatch.setattr(
            "code_puppy.themes.theme_manager.get_value",
            mock_get_value,
        )

        theme_name = get_theme_name()
        assert theme_name == "ocean"
        mock_get_value.assert_called_once_with("theme")

    def test_apply_theme_saves_to_config(self, theme_manager, monkeypatch):
        """Test that apply_theme with theme_name saves to config."""
        mock_set_theme_name = MagicMock()
        monkeypatch.setattr(
            "code_puppy.themes.theme_manager.set_theme_name",
            mock_set_theme_name,
        )

        theme = Theme()
        theme_manager.apply_theme(theme, theme_name="custom")

        mock_set_theme_name.assert_called_once_with("custom")

    def test_apply_theme_invalid_name_does_not_save_to_config(
        self, theme_manager, monkeypatch
    ):
        """Test that applying with invalid theme name doesn't save to config."""
        mock_set_theme_name = MagicMock()
        monkeypatch.setattr(
            "code_puppy.themes.theme_manager.set_theme_name",
            mock_set_theme_name,
        )

        theme = Theme()
        theme_manager.apply_theme(theme, theme_name="invalid name!")

        # Should not be called due to invalid name
        mock_set_theme_name.assert_not_called()



# =============================================================================
# TestThemeManagerGetInstance
# =============================================================================


class TestThemeManagerGetInstance:
    """Test the global get_theme_manager singleton function."""

    def test_get_theme_manager_returns_singleton(self):
        """Test that get_theme_manager returns the same instance."""
        from code_puppy.themes.theme_manager import _global_theme_manager

        # Reset global instance
        import code_puppy.themes.theme_manager as tm_module
        tm_module._global_theme_manager = None

        manager1 = get_theme_manager()
        manager2 = get_theme_manager()

        assert manager1 is manager2

    def test_get_theme_manager_creates_instance_on_first_call(self):
        """Test that get_theme_manager creates an instance on first call."""
        from code_puppy.themes.theme_manager import _global_theme_manager

        # Reset global instance
        import code_puppy.themes.theme_manager as tm_module
        tm_module._global_theme_manager = None

        manager = get_theme_manager()
        assert isinstance(manager, ThemeManager)
        assert manager._current_theme is None
