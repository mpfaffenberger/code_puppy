"""Tests for per-model settings functionality."""

from unittest.mock import MagicMock, patch

import code_puppy.config as cp_config


class TestPerModelSettings:
    """Tests for the per-model settings functions."""

    @patch.object(cp_config, "get_value")
    def test_get_model_setting_returns_none_when_not_set(self, mock_get_value):
        """get_model_setting should return None when setting is not configured."""
        mock_get_value.return_value = None
        result = cp_config.get_model_setting("test-model", "temperature")
        assert result is None

    @patch.object(cp_config, "get_value")
    def test_get_model_setting_returns_default_when_not_set(self, mock_get_value):
        """get_model_setting should return default when setting is not configured."""
        mock_get_value.return_value = None
        result = cp_config.get_model_setting("test-model", "temperature", default=0.7)
        assert result == 0.7

    @patch.object(cp_config, "get_value")
    def test_get_model_setting_returns_float_value(self, mock_get_value):
        """get_model_setting should return float value when set."""
        mock_get_value.return_value = "0.5"
        result = cp_config.get_model_setting("test-model", "temperature")
        assert result == 0.5

    @patch.object(cp_config, "set_config_value")
    def test_set_model_setting_stores_value(self, mock_set_config_value):
        """set_model_setting should store the value with correct key format."""
        cp_config.set_model_setting("gpt-5", "temperature", 0.8)
        mock_set_config_value.assert_called_once_with(
            "model_settings_gpt_5_temperature", "0.8"
        )

    @patch.object(cp_config, "set_config_value")
    def test_set_model_setting_clears_value_when_none(self, mock_set_config_value):
        """set_model_setting should clear the value when None is passed."""
        cp_config.set_model_setting("gpt-5", "temperature", None)
        mock_set_config_value.assert_called_once_with(
            "model_settings_gpt_5_temperature", ""
        )

    def test_sanitize_model_name_handles_dots(self):
        """Model names with dots should be sanitized."""
        result = cp_config._sanitize_model_name_for_key("gpt-5.1")
        assert result == "gpt_5_1"

    def test_sanitize_model_name_handles_dashes(self):
        """Model names with dashes should be sanitized."""
        result = cp_config._sanitize_model_name_for_key("claude-4-5-sonnet")
        assert result == "claude_4_5_sonnet"

    def test_sanitize_model_name_handles_slashes(self):
        """Model names with slashes should be sanitized."""
        result = cp_config._sanitize_model_name_for_key("provider/model-name")
        assert result == "provider_model_name"


class TestEffectiveTemperature:
    """Tests for the get_effective_temperature function."""

    @patch.object(cp_config, "model_supports_setting", return_value=True)
    @patch.object(cp_config, "get_all_model_settings")
    @patch.object(cp_config, "get_temperature")
    @patch.object(cp_config, "get_global_model_name")
    def test_returns_per_model_temp_when_set(
        self, mock_get_model_name, mock_get_temp, mock_get_all_settings, mock_supports
    ):
        """Should return per-model temperature when configured."""
        mock_get_model_name.return_value = "test-model"
        mock_get_all_settings.return_value = {"temperature": 0.5}
        mock_get_temp.return_value = 0.7  # Global temp

        result = cp_config.get_effective_temperature("test-model")
        assert result == 0.5
        mock_get_all_settings.assert_called_once_with("test-model")

    @patch.object(cp_config, "model_supports_setting", return_value=True)
    @patch.object(cp_config, "get_all_model_settings")
    @patch.object(cp_config, "get_temperature")
    @patch.object(cp_config, "get_global_model_name")
    def test_falls_back_to_global_when_per_model_not_set(
        self, mock_get_model_name, mock_get_temp, mock_get_all_settings, mock_supports
    ):
        """Should fall back to global temperature when per-model not set."""
        mock_get_model_name.return_value = "test-model"
        mock_get_all_settings.return_value = {}  # No per-model setting
        mock_get_temp.return_value = 0.7  # Global temp

        result = cp_config.get_effective_temperature("test-model")
        assert result == 0.7

    @patch.object(cp_config, "model_supports_setting", return_value=True)
    @patch.object(cp_config, "get_all_model_settings")
    @patch.object(cp_config, "get_temperature")
    @patch.object(cp_config, "get_global_model_name")
    def test_returns_none_when_nothing_configured(
        self, mock_get_model_name, mock_get_temp, mock_get_all_settings, mock_supports
    ):
        """Should return None when neither per-model nor global is set."""
        mock_get_model_name.return_value = "test-model"
        mock_get_all_settings.return_value = {}
        mock_get_temp.return_value = None

        result = cp_config.get_effective_temperature("test-model")
        assert result is None

    @patch.object(cp_config, "model_supports_setting", return_value=True)
    @patch.object(cp_config, "get_all_model_settings")
    @patch.object(cp_config, "get_temperature")
    @patch.object(cp_config, "get_global_model_name")
    def test_uses_global_model_name_when_none_provided(
        self, mock_get_model_name, mock_get_temp, mock_get_all_settings, mock_supports
    ):
        """Should use global model name when no model_name argument provided."""
        mock_get_model_name.return_value = "default-model"
        mock_get_all_settings.return_value = {"temperature": 0.3}

        result = cp_config.get_effective_temperature(None)
        mock_get_model_name.assert_called_once()
        mock_get_all_settings.assert_called_once_with("default-model")
        assert result == 0.3


class TestGetAllModelSettings:
    """Tests for the get_all_model_settings function."""

    @patch("configparser.ConfigParser")
    def test_returns_empty_dict_when_no_settings(self, mock_config_parser):
        """Should return empty dict when no settings configured."""
        mock_config = MagicMock()
        mock_config.__contains__ = MagicMock(return_value=True)
        mock_config.__getitem__ = MagicMock(return_value={"some_other_key": "value"})
        mock_config_parser.return_value = mock_config

        result = cp_config.get_all_model_settings("test-model")
        assert result == {}

    @patch("configparser.ConfigParser")
    def test_returns_settings_for_model(self, mock_config_parser):
        """Should return all settings for the specified model."""
        mock_config = MagicMock()
        mock_config.__contains__ = MagicMock(return_value=True)
        mock_section = {
            "model_settings_test_model_temperature": "0.5",
            "model_settings_test_model_top_p": "0.9",
            "model_settings_other_model_temperature": "0.7",
            "some_other_key": "value",
        }
        mock_config.__getitem__ = MagicMock(return_value=mock_section)
        mock_config_parser.return_value = mock_config

        result = cp_config.get_all_model_settings("test-model")
        assert result == {"temperature": 0.5, "top_p": 0.9}
