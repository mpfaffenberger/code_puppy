"""Tests for GUI-Cub config manager."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from code_puppy.tools.gui_cub.config_manager import (
    get_config_path,
    load_config,
    save_config,
    validate_config,
)


class TestConfigPath:
    """Test config path generation."""

    def test_get_config_path_returns_path_object(self):
        """Config path should return a Path object."""
        path = get_config_path()
        assert isinstance(path, Path)

    def test_get_config_path_includes_gui_cub(self):
        """Config path should include gui_cub directory."""
        path = get_config_path()
        assert "gui_cub" in str(path)

    def test_get_config_path_ends_with_config_json(self):
        """Config path should end with config.json."""
        path = get_config_path()
        assert path.name == "config.json"


class TestLoadConfig:
    """Test config loading."""

    def test_load_config_returns_none_if_not_exists(self, tmp_path):
        """Should return None if config file doesn't exist."""
        with patch("code_puppy.tools.gui_cub.config_manager.get_config_path", return_value=tmp_path / "missing.json"):
            config = load_config()
            assert config is None

    def test_load_config_returns_dict_if_exists(self, tmp_path):
        """Should return dict if config file exists."""
        config_file = tmp_path / "config.json"
        test_config = {"version": "1.0.0", "platform": {"os": "darwin"}}
        config_file.write_text(json.dumps(test_config))

        with patch("code_puppy.tools.gui_cub.config_manager.get_config_path", return_value=config_file):
            config = load_config()
            assert config == test_config

    def test_load_config_returns_none_on_invalid_json(self, tmp_path):
        """Should return None if JSON is invalid."""
        config_file = tmp_path / "config.json"
        config_file.write_text("invalid json {")

        with patch("code_puppy.tools.gui_cub.config_manager.get_config_path", return_value=config_file):
            config = load_config()
            assert config is None


class TestSaveConfig:
    """Test config saving."""

    def test_save_config_writes_json(self, tmp_path):
        """Should write config as JSON."""
        config_file = tmp_path / "config.json"
        test_config = {
            "version": "1.0.0",
            "platform": {"os": "darwin"},
            "metadata": {},
        }

        with patch("code_puppy.tools.gui_cub.config_manager.get_config_path", return_value=config_file), \
             patch("code_puppy.tools.gui_cub.config_manager._compute_config_hash", return_value="test_hash"):
            result = save_config(test_config)
            assert result is True

            loaded = json.loads(config_file.read_text())
            assert loaded["version"] == "1.0.0"
            assert loaded["platform"]["os"] == "darwin"

    def test_save_config_adds_hash(self, tmp_path):
        """Should add hash to metadata."""
        config_file = tmp_path / "config.json"
        test_config = {
            "version": "1.0.0",
            "metadata": {},
        }

        with patch("code_puppy.tools.gui_cub.config_manager.get_config_path", return_value=config_file), \
             patch("code_puppy.tools.gui_cub.config_manager._compute_config_hash", return_value="test_hash"):
            save_config(test_config)
            loaded = json.loads(config_file.read_text())
            assert loaded["metadata"]["hash"] == "test_hash"


class TestValidateConfig:
    """Test config validation."""

    @patch("pyautogui.size", return_value=(1920, 1080))
    @patch("sys.platform", "darwin")
    def test_validate_config_succeeds_when_valid(self, mock_size):
        """Should return True when config is valid."""
        config = {
            "platform": {"os": "darwin"},
            "display": {"primary_resolution": [1920, 1080]},
            "capabilities": {},
            "missing_capabilities": {},
        }

        valid, message = validate_config(config)
        assert valid is True
        assert "valid" in message.lower()

    @patch("pyautogui.size", return_value=(1920, 1080))
    @patch("sys.platform", "darwin")
    def test_validate_config_fails_on_resolution_change(self, mock_size):
        """Should fail when resolution changes."""
        config = {
            "platform": {"os": "darwin"},
            "display": {"primary_resolution": [1024, 768]},  # Different resolution
            "capabilities": {},
        }

        valid, message = validate_config(config)
        assert valid is False
        assert "resolution changed" in message.lower()

    @patch("pyautogui.size", return_value=(1920, 1080))
    @patch("sys.platform", "darwin")
    def test_validate_config_fails_on_os_change(self, mock_size):
        """Should fail when OS changes."""
        config = {
            "platform": {"os": "win32"},  # Different OS
            "display": {"primary_resolution": [1920, 1080]},
            "capabilities": {},
        }

        valid, message = validate_config(config)
        assert valid is False
        assert "os changed" in message.lower()
