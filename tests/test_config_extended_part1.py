import configparser
import os
import tempfile
from unittest.mock import patch

import pytest

from code_puppy.config import (
    DEFAULT_SECTION,
    get_allow_recursion,
    get_auto_save_session,
    get_compaction_threshold,
    get_diff_context_lines,
    get_global_model_name,
    get_message_limit,
    get_owner_name,
    get_protected_token_count,
    get_puppy_name,
    get_use_dbos,
    get_value,
    get_yolo_mode,
    set_config_value,
)


class TestConfigExtendedPart1:
    """Test basic config operations in code_puppy/config.py"""

    @pytest.fixture
    def temp_config_dir(self):
        """Create a temporary config directory for isolated testing"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = os.path.join(temp_dir, "puppy.cfg")

            # Create a basic config file
            config = configparser.ConfigParser()
            config[DEFAULT_SECTION] = {
                "puppy_name": "TestPuppy",
                "owner_name": "TestOwner",
                "model": "gpt-4",
                "yolo_mode": "true",
                "allow_recursion": "false",
                "message_limit": "50",
                "protected_token_count": "25000",
                "compaction_threshold": "0.8",
                "diff_context_lines": "10",
                "enable_dbos": "true",
                "auto_save_session": "false",
            }
            with open(config_file, "w") as f:
                config.write(f)

            yield temp_dir, config_file

    @pytest.fixture
    def mock_config_file(self, temp_config_dir):
        """Mock the CONFIG_FILE to use our temporary config"""
        temp_dir, config_file = temp_config_dir
        with patch("code_puppy.config.CONFIG_FILE", config_file):
            yield config_file

    def test_get_value_with_existing_key(self, mock_config_file):
        """Test getting a value that exists in config"""
        result = get_value("puppy_name")
        assert result == "TestPuppy"

        result = get_value("yolo_mode")
        assert result == "true"

    def test_get_value_with_nonexistent_key(self, mock_config_file):
        """Test getting a value that doesn't exist returns None"""
        result = get_value("nonexistent_key")
        assert result is None

    def test_get_value_with_default_fallback(self, mock_config_file):
        """Test get_value returns None for missing keys (no default param)"""
        result = get_value("missing_key")
        assert result is None

    def test_set_value_new_key(self, mock_config_file):
        """Test setting a new config value"""
        set_config_value("new_key", "new_value")

        # Verify it was set
        result = get_value("new_key")
        assert result == "new_value"

    def test_set_value_existing_key(self, mock_config_file):
        """Test updating an existing config value"""
        # Verify original value
        original = get_value("puppy_name")
        assert original == "TestPuppy"

        # Update it
        set_config_value("puppy_name", "UpdatedPuppy")

        # Verify it was updated
        result = get_value("puppy_name")
        assert result == "UpdatedPuppy"

    def test_set_value_empty_string(self, mock_config_file):
        """Test setting a config value to empty string"""
        set_config_value("empty_key", "")
        result = get_value("empty_key")
        assert result == ""

    def test_boolean_conversion_true_values(self, mock_config_file):
        """Test various string representations that convert to True"""
        # Test existing true value
        assert get_yolo_mode() is True

        # Test setting various true values
        for true_val in ["true", "TRUE", "True", "1", "yes", "YES", "on", "ON"]:
            set_config_value("test_bool", true_val)
            # Note: get_yolo_mode specifically checks yolo_mode, so we'll test the pattern
            val = get_value("test_bool")
            assert val == true_val

    def test_boolean_conversion_false_values(self, mock_config_file):
        """Test various string representations that convert to False"""
        # Test existing false value
        assert get_allow_recursion() is False

        # Test setting various false values
        for false_val in ["false", "FALSE", "False", "0", "no", "NO", "off", "OFF"]:
            set_config_value("test_bool", false_val)
            val = get_value("test_bool")
            assert val == false_val

    def test_get_allow_recursion_default(self, temp_config_dir):
        """Test get_allow_recursion returns True when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without allow_recursion key
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {"puppy_name": "Test"}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_allow_recursion()
            assert result is True  # Default should be True

    def test_get_yolo_mode_default(self, temp_config_dir):
        """Test get_yolo_mode returns True when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without yolo_mode key
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {"puppy_name": "Test"}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_yolo_mode()
            assert result is True  # Default should be True

    def test_get_auto_save_session_default(self, temp_config_dir):
        """Test get_auto_save_session returns True when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without auto_save_session key
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {"puppy_name": "Test"}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_auto_save_session()
            assert result is True  # Default should be True

    def test_get_use_dbos_default(self, temp_config_dir):
        """Test get_use_dbos returns False when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without enable_dbos key
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {"puppy_name": "Test"}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_use_dbos()
            assert result is False  # Default should be False

    def test_integer_conversion_message_limit(self, mock_config_file):
        """Test integer conversion for message_limit"""
        result = get_message_limit()
        assert result == 50

        # Test default when not set
        set_config_value("message_limit", "")
        result = get_message_limit()
        assert result == 100  # Default should be 100

    def test_integer_conversion_protected_token_count(self, mock_config_file):
        """Test integer conversion for protected_token_count"""
        result = get_protected_token_count()
        assert result == 25000

        # Test default when not set
        set_config_value("protected_token_count", "")
        result = get_protected_token_count()
        assert isinstance(result, int)
        assert result > 0

    def test_float_conversion_compaction_threshold(self, mock_config_file):
        """Test float conversion for compaction_threshold"""
        result = get_compaction_threshold()
        assert result == 0.8

        # Test default when not set
        set_config_value("compaction_threshold", "")
        result = get_compaction_threshold()
        assert result == 0.85  # Default should be 0.85

    def test_integer_conversion_diff_context_lines(self, mock_config_file):
        """Test integer conversion for diff_context_lines"""
        result = get_diff_context_lines()
        assert result == 10

        # Test default when not set
        set_config_value("diff_context_lines", "")
        result = get_diff_context_lines()
        assert result == 6  # Default should be 6

    def test_get_puppy_name_default(self, temp_config_dir):
        """Test get_puppy_name returns default when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without puppy_name
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_puppy_name()
            assert result == "Puppy"  # Default should be "Puppy"

    def test_get_owner_name_default(self, temp_config_dir):
        """Test get_owner_name returns default when not set"""
        temp_dir, config_file = temp_config_dir

        # Create config without owner_name
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {}
        with open(config_file, "w") as f:
            config.write(f)

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_owner_name()
            assert result == "Master"  # Default should be "Master"

    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_global_model_name_with_valid_stored_model(
        self, mock_default, mock_validate, mock_config_file
    ):
        """Test get_global_model_name returns stored model when valid"""
        mock_validate.return_value = True
        mock_default.return_value = "fallback-model"

        result = get_global_model_name()
        assert result == "gpt-4"  # Should return the stored valid model
        mock_validate.assert_called_once_with("gpt-4")
        mock_default.assert_not_called()

    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_global_model_name_with_invalid_stored_model(
        self, mock_default, mock_validate, mock_config_file
    ):
        """Test get_global_model_name falls back when stored model is invalid"""
        mock_validate.return_value = False
        mock_default.return_value = "fallback-model"

        result = get_global_model_name()
        assert result == "fallback-model"  # Should return the default model
        mock_validate.assert_called_once_with("gpt-4")
        mock_default.assert_called_once()

    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_global_model_name_no_stored_model(
        self, mock_default, mock_validate, temp_config_dir
    ):
        """Test get_global_model_name when no model is stored"""
        temp_dir, config_file = temp_config_dir

        # Create config without model key
        config = configparser.ConfigParser()
        config[DEFAULT_SECTION] = {"puppy_name": "Test"}
        with open(config_file, "w") as f:
            config.write(f)

        mock_default.return_value = "default-model"

        with patch("code_puppy.config.CONFIG_FILE", config_file):
            result = get_global_model_name()
            assert result == "default-model"  # Should return the default model
            mock_validate.assert_not_called()
            mock_default.assert_called_once()

    def test_config_persistence_across_operations(self, mock_config_file):
        """Test that config values persist across multiple operations"""
        # Set multiple values
        set_config_value("test_key1", "value1")
        set_config_value("test_key2", "value2")
        set_config_value("test_key3", "value3")

        # Verify all values persist
        assert get_value("test_key1") == "value1"
        assert get_value("test_key2") == "value2"
        assert get_value("test_key3") == "value3"

        # Update one value
        set_config_value("test_key2", "updated_value2")

        # Verify only the updated value changed
        assert get_value("test_key1") == "value1"
        assert get_value("test_key2") == "updated_value2"
        assert get_value("test_key3") == "value3"

    def test_type_conversion_edge_cases(self, mock_config_file):
        """Test type conversion with edge case values"""
        # Test integer conversion with invalid values
        set_config_value("message_limit", "invalid")
        result = get_message_limit()
        assert result == 100  # Should fall back to default

        # Test float conversion with invalid values
        set_config_value("compaction_threshold", "invalid")
        result = get_compaction_threshold()
        assert result == 0.85  # Should fall back to default

        # Test integer conversion with out-of-range values
        set_config_value("diff_context_lines", "100")  # Above max of 50
        result = get_diff_context_lines()
        assert result == 50  # Should be clamped to max

        set_config_value("diff_context_lines", "-5")  # Below min of 0
        result = get_diff_context_lines()
        assert result == 0  # Should be clamped to min
