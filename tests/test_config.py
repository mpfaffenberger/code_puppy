import configparser
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from code_puppy import config as cp_config

# Define constants used in config.py to avoid direct import if they change
CONFIG_DIR_NAME = ".code_puppy"
CONFIG_FILE_NAME = "puppy.cfg"
DEFAULT_SECTION_NAME = "puppy"


@pytest.fixture
def mock_config_paths(monkeypatch):
    # Ensure that tests don't interact with the actual user's config
    mock_home = "/mock_home"
    mock_config_dir = os.path.join(mock_home, CONFIG_DIR_NAME)
    mock_config_file = os.path.join(mock_config_dir, CONFIG_FILE_NAME)

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    monkeypatch.setattr(
        os.path,
        "expanduser",
        lambda path: mock_home if path == "~" else os.path.expanduser(path),
    )
    return mock_config_dir, mock_config_file


class TestEnsureConfigExists:
    def test_no_config_dir_or_file_prompts_and_creates(
        self, mock_config_paths, monkeypatch
    ):
        mock_cfg_dir, mock_cfg_file = mock_config_paths

        mock_os_path_exists = MagicMock()
        # First call for CONFIG_DIR, second for CONFIG_FILE (though isfile is used for file)
        mock_os_path_exists.side_effect = [
            False,
            False,
        ]  # CONFIG_DIR not exists, CONFIG_FILE not exists
        monkeypatch.setattr(os.path, "exists", mock_os_path_exists)

        mock_os_path_isfile = MagicMock(return_value=False)  # CONFIG_FILE not exists
        monkeypatch.setattr(os.path, "isfile", mock_os_path_isfile)

        mock_makedirs = MagicMock()
        monkeypatch.setattr(os, "makedirs", mock_makedirs)

        mock_input_values = {
            "What should we name the puppy? ": "TestPuppy",
            "What's your name (so Code Puppy knows its owner)? ": "TestOwner",
        }
        mock_input = MagicMock(side_effect=lambda prompt: mock_input_values[prompt])
        monkeypatch.setattr("builtins.input", mock_input)

        m_open = mock_open()
        with patch("builtins.open", m_open):
            config_parser = cp_config.ensure_config_exists()

        mock_makedirs.assert_called_once_with(mock_cfg_dir, exist_ok=True)
        m_open.assert_called_once_with(mock_cfg_file, "w")

        # Check what was written to file
        # The configparser object's write method is called with a file-like object
        # We can inspect the calls to that file-like object (m_open())
        # However, it's easier to check the returned config_parser object
        assert config_parser.sections() == [DEFAULT_SECTION_NAME]
        assert config_parser.get(DEFAULT_SECTION_NAME, "puppy_name") == "TestPuppy"
        assert config_parser.get(DEFAULT_SECTION_NAME, "owner_name") == "TestOwner"

    def test_config_dir_exists_file_does_not_prompts_and_creates(
        self, mock_config_paths, monkeypatch
    ):
        mock_cfg_dir, mock_cfg_file = mock_config_paths

        mock_os_path_exists = MagicMock(return_value=True)  # CONFIG_DIR exists
        monkeypatch.setattr(os.path, "exists", mock_os_path_exists)

        mock_os_path_isfile = MagicMock(return_value=False)  # CONFIG_FILE not exists
        monkeypatch.setattr(os.path, "isfile", mock_os_path_isfile)

        mock_makedirs = MagicMock()
        monkeypatch.setattr(os, "makedirs", mock_makedirs)

        mock_input_values = {
            "What should we name the puppy? ": "DirExistsPuppy",
            "What's your name (so Code Puppy knows its owner)? ": "DirExistsOwner",
        }
        mock_input = MagicMock(side_effect=lambda prompt: mock_input_values[prompt])
        monkeypatch.setattr("builtins.input", mock_input)

        m_open = mock_open()
        with patch("builtins.open", m_open):
            config_parser = cp_config.ensure_config_exists()

        mock_makedirs.assert_not_called()  # Dir already exists
        m_open.assert_called_once_with(mock_cfg_file, "w")

        assert config_parser.sections() == [DEFAULT_SECTION_NAME]
        assert config_parser.get(DEFAULT_SECTION_NAME, "puppy_name") == "DirExistsPuppy"
        assert config_parser.get(DEFAULT_SECTION_NAME, "owner_name") == "DirExistsOwner"

    def test_config_file_exists_and_complete_no_prompt_no_write(
        self, mock_config_paths, monkeypatch
    ):
        mock_cfg_dir, mock_cfg_file = mock_config_paths

        monkeypatch.setattr(
            os.path, "exists", MagicMock(return_value=True)
        )  # CONFIG_DIR exists
        monkeypatch.setattr(
            os.path, "isfile", MagicMock(return_value=True)
        )  # CONFIG_FILE exists

        # Mock configparser.ConfigParser instance and its methods
        mock_config_instance = configparser.ConfigParser()
        mock_config_instance[DEFAULT_SECTION_NAME] = {
            "puppy_name": "ExistingPuppy",
            "owner_name": "ExistingOwner",
        }

        def mock_read(file_path):
            # Simulate reading by populating the mock_config_instance if it were empty
            # For this test, we assume it's already populated as if read from file
            pass

        mock_cp = MagicMock(return_value=mock_config_instance)
        mock_config_instance.read = MagicMock(side_effect=mock_read)
        monkeypatch.setattr(configparser, "ConfigParser", mock_cp)

        mock_input = MagicMock()
        monkeypatch.setattr("builtins.input", mock_input)

        m_open = mock_open()
        with patch("builtins.open", m_open):
            returned_config_parser = cp_config.ensure_config_exists()

        mock_input.assert_not_called()
        m_open.assert_not_called()  # No write should occur
        mock_config_instance.read.assert_called_once_with(mock_cfg_file)

        assert returned_config_parser == mock_config_instance
        assert (
            returned_config_parser.get(DEFAULT_SECTION_NAME, "puppy_name")
            == "ExistingPuppy"
        )

    def test_config_file_exists_missing_one_key_prompts_and_writes(
        self, mock_config_paths, monkeypatch
    ):
        mock_cfg_dir, mock_cfg_file = mock_config_paths

        monkeypatch.setattr(os.path, "exists", MagicMock(return_value=True))
        monkeypatch.setattr(os.path, "isfile", MagicMock(return_value=True))

        mock_config_instance = configparser.ConfigParser()
        mock_config_instance[DEFAULT_SECTION_NAME] = {
            "puppy_name": "PartialPuppy"
        }  # owner_name is missing

        def mock_read(file_path):
            pass

        mock_cp = MagicMock(return_value=mock_config_instance)
        mock_config_instance.read = MagicMock(side_effect=mock_read)
        monkeypatch.setattr(configparser, "ConfigParser", mock_cp)

        mock_input_values = {
            "What's your name (so Code Puppy knows its owner)? ": "PartialOwnerFilled"
        }
        # Only owner_name should be prompted
        mock_input = MagicMock(side_effect=lambda prompt: mock_input_values[prompt])
        monkeypatch.setattr("builtins.input", mock_input)

        m_open = mock_open()
        with patch("builtins.open", m_open):
            returned_config_parser = cp_config.ensure_config_exists()

        mock_input.assert_called_once()  # Only called for the missing key
        m_open.assert_called_once_with(mock_cfg_file, "w")
        mock_config_instance.read.assert_called_once_with(mock_cfg_file)

        assert (
            returned_config_parser.get(DEFAULT_SECTION_NAME, "puppy_name")
            == "PartialPuppy"
        )
        assert (
            returned_config_parser.get(DEFAULT_SECTION_NAME, "owner_name")
            == "PartialOwnerFilled"
        )


class TestGetValue:
    @patch("configparser.ConfigParser")
    def test_get_value_exists(self, mock_config_parser_class, mock_config_paths):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()
        mock_parser_instance.get.return_value = "test_value"
        mock_config_parser_class.return_value = mock_parser_instance

        val = cp_config.get_value("test_key")

        mock_config_parser_class.assert_called_once()
        mock_parser_instance.read.assert_called_once_with(mock_cfg_file)
        mock_parser_instance.get.assert_called_once_with(
            DEFAULT_SECTION_NAME, "test_key", fallback=None
        )
        assert val == "test_value"

    @patch("configparser.ConfigParser")
    def test_get_value_not_exists(self, mock_config_parser_class, mock_config_paths):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()
        mock_parser_instance.get.return_value = None  # Simulate key not found
        mock_config_parser_class.return_value = mock_parser_instance

        val = cp_config.get_value("missing_key")

        assert val is None

    @patch("configparser.ConfigParser")
    def test_get_value_config_file_not_exists_graceful(
        self, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()
        mock_parser_instance.get.return_value = None
        mock_config_parser_class.return_value = mock_parser_instance

        val = cp_config.get_value("any_key")
        assert val is None


class TestSimpleGetters:
    @patch("code_puppy.config.get_value")
    def test_get_puppy_name_exists(self, mock_get_value):
        mock_get_value.return_value = "MyPuppy"
        assert cp_config.get_puppy_name() == "MyPuppy"
        mock_get_value.assert_called_once_with("puppy_name")

    @patch("code_puppy.config.get_value")
    def test_get_puppy_name_not_exists_uses_default(self, mock_get_value):
        mock_get_value.return_value = None
        assert cp_config.get_puppy_name() == "Puppy"  # Default value
        mock_get_value.assert_called_once_with("puppy_name")

    @patch("code_puppy.config.get_value")
    def test_get_owner_name_exists(self, mock_get_value):
        mock_get_value.return_value = "MyOwner"
        assert cp_config.get_owner_name() == "MyOwner"
        mock_get_value.assert_called_once_with("owner_name")

    @patch("code_puppy.config.get_value")
    def test_get_owner_name_not_exists_uses_default(self, mock_get_value):
        mock_get_value.return_value = None
        assert cp_config.get_owner_name() == "Master"  # Default value
        mock_get_value.assert_called_once_with("owner_name")


class TestGetConfigKeys:
    @patch("configparser.ConfigParser")
    def test_get_config_keys_with_existing_keys(
        self, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()

        section_proxy = {"key1": "val1", "key2": "val2"}
        mock_parser_instance.__contains__.return_value = True
        mock_parser_instance.__getitem__.return_value = section_proxy
        mock_config_parser_class.return_value = mock_parser_instance

        keys = cp_config.get_config_keys()

        mock_parser_instance.read.assert_called_once_with(mock_cfg_file)
        assert keys == sorted(
            [
                "allow_recursion",
                "auto_save_session",
                "compaction_strategy",
                "compaction_threshold",
                "http2",
                "enable_dbos",
                "key1",
                "key2",
                "max_saved_sessions",
                "message_limit",
                "model",
                "openai_reasoning_effort",
                "protected_token_count",
                "yolo_mode",
            ]
        )

    @patch("configparser.ConfigParser")
    def test_get_config_keys_empty_config(
        self, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()
        mock_parser_instance.__contains__.return_value = False
        mock_config_parser_class.return_value = mock_parser_instance

        keys = cp_config.get_config_keys()
        assert keys == sorted(
            [
                "allow_recursion",
                "auto_save_session",
                "compaction_strategy",
                "compaction_threshold",
                "http2",
                "enable_dbos",
                "max_saved_sessions",
                "message_limit",
                "model",
                "openai_reasoning_effort",
                "protected_token_count",
                "yolo_mode",
            ]
        )


class TestSetConfigValue:
    @patch("configparser.ConfigParser")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_value_new_key_section_exists(
        self, mock_file_open, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()

        section_dict = {}
        mock_parser_instance.read.return_value = [mock_cfg_file]
        mock_parser_instance.__contains__.return_value = True
        mock_parser_instance.__getitem__.return_value = section_dict
        mock_config_parser_class.return_value = mock_parser_instance

        cp_config.set_config_value("a_new_key", "a_new_value")

        assert section_dict["a_new_key"] == "a_new_value"
        mock_file_open.assert_called_once_with(mock_cfg_file, "w")
        mock_parser_instance.write.assert_called_once_with(mock_file_open())

    @patch("configparser.ConfigParser")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_value_update_existing_key(
        self, mock_file_open, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()

        section_dict = {"existing_key": "old_value"}
        mock_parser_instance.read.return_value = [mock_cfg_file]
        mock_parser_instance.__contains__.return_value = True
        mock_parser_instance.__getitem__.return_value = section_dict
        mock_config_parser_class.return_value = mock_parser_instance

        cp_config.set_config_value("existing_key", "updated_value")

        assert section_dict["existing_key"] == "updated_value"
        mock_file_open.assert_called_once_with(mock_cfg_file, "w")
        mock_parser_instance.write.assert_called_once_with(mock_file_open())

    @patch("configparser.ConfigParser")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_value_section_does_not_exist_creates_it(
        self, mock_file_open, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()

        created_sections_store = {}

        def mock_contains_check(section_name):
            return section_name in created_sections_store

        def mock_setitem_for_section_creation(section_name, value_usually_empty_dict):
            created_sections_store[section_name] = value_usually_empty_dict

        def mock_getitem_for_section_access(section_name):
            return created_sections_store[section_name]

        mock_parser_instance.read.return_value = [mock_cfg_file]
        mock_parser_instance.__contains__.side_effect = mock_contains_check
        mock_parser_instance.__setitem__.side_effect = mock_setitem_for_section_creation
        mock_parser_instance.__getitem__.side_effect = mock_getitem_for_section_access

        mock_config_parser_class.return_value = mock_parser_instance

        cp_config.set_config_value("key_in_new_section", "value_in_new_section")

        assert DEFAULT_SECTION_NAME in created_sections_store
        assert (
            created_sections_store[DEFAULT_SECTION_NAME]["key_in_new_section"]
            == "value_in_new_section"
        )

        mock_file_open.assert_called_once_with(mock_cfg_file, "w")
        mock_parser_instance.write.assert_called_once_with(mock_file_open())


class TestModelName:
    @patch("code_puppy.config.get_value")
    @patch("code_puppy.config._validate_model_exists")
    def test_get_model_name_exists(self, mock_validate_model_exists, mock_get_value):
        mock_get_value.return_value = "test_model_from_config"
        mock_validate_model_exists.return_value = True
        assert cp_config.get_global_model_name() == "test_model_from_config"
        mock_get_value.assert_called_once_with("model")
        mock_validate_model_exists.assert_called_once_with("test_model_from_config")

    @patch("configparser.ConfigParser")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_model_name(
        self, mock_file_open, mock_config_parser_class, mock_config_paths
    ):
        _, mock_cfg_file = mock_config_paths
        mock_parser_instance = MagicMock()

        section_dict = {}
        # This setup ensures that config[DEFAULT_SECTION_NAME] operations work on section_dict
        # and that the section is considered to exist or is created as needed.
        mock_parser_instance.read.return_value = [mock_cfg_file]

        # Simulate that the section exists or will be created and then available
        def get_section_or_create(name):
            if name == DEFAULT_SECTION_NAME:
                # Ensure subsequent checks for section existence pass
                mock_parser_instance.__contains__ = (
                    lambda s_name: s_name == DEFAULT_SECTION_NAME
                )
                return section_dict
            raise KeyError(name)

        mock_parser_instance.__getitem__.side_effect = get_section_or_create
        # Initial check for section existence (might be False if section needs creation)
        # We'll simplify by assuming it's True after first access or creation attempt.
        _section_exists_initially = False

        def initial_contains_check(s_name):
            nonlocal _section_exists_initially
            if s_name == DEFAULT_SECTION_NAME:
                if _section_exists_initially:
                    return True
                _section_exists_initially = (
                    True  # Simulate it's created on first miss then setitem
                )
                return False
            return False

        mock_parser_instance.__contains__.side_effect = initial_contains_check

        def mock_setitem_for_section(name, value):
            if name == DEFAULT_SECTION_NAME:  # For config[DEFAULT_SECTION_NAME] = {}
                pass  # section_dict is already our target via __getitem__ side_effect
            else:  # For config[DEFAULT_SECTION_NAME][key] = value
                section_dict[name] = value

        mock_parser_instance.__setitem__.side_effect = mock_setitem_for_section
        mock_config_parser_class.return_value = mock_parser_instance

        cp_config.set_model_name("super_model_7000")

        assert section_dict["model"] == "super_model_7000"
        mock_file_open.assert_called_once_with(mock_cfg_file, "w")
        mock_parser_instance.write.assert_called_once_with(mock_file_open())


class TestGetYoloMode:
    @patch("code_puppy.config.get_value")
    def test_get_yolo_mode_from_config_true(self, mock_get_value):
        true_values = ["true", "1", "YES", "ON"]
        for val in true_values:
            mock_get_value.reset_mock()
            mock_get_value.return_value = val
            assert cp_config.get_yolo_mode() is True, f"Failed for config value: {val}"
            mock_get_value.assert_called_once_with("yolo_mode")

    @patch("code_puppy.config.get_value")
    def test_get_yolo_mode_not_in_config_defaults_true(self, mock_get_value):
        mock_get_value.return_value = None

        assert cp_config.get_yolo_mode() is True
        mock_get_value.assert_called_once_with("yolo_mode")


class TestCommandHistory:
    @patch("os.path.isfile")
    @patch("pathlib.Path.touch")
    @patch("os.path.expanduser")
    @patch("os.makedirs")
    def test_initialize_command_history_file_creates_new_file(
        self, mock_makedirs, mock_expanduser, mock_touch, mock_isfile, mock_config_paths
    ):
        # Setup
        mock_cfg_dir, _ = mock_config_paths
        # First call is for COMMAND_HISTORY_FILE, second is for old history file
        mock_isfile.side_effect = [False, False]  # Both files don't exist
        mock_expanduser.return_value = "/mock_home"

        # Call the function
        cp_config.initialize_command_history_file()

        # Assert
        assert mock_isfile.call_count == 2
        assert mock_isfile.call_args_list[0][0][0] == cp_config.COMMAND_HISTORY_FILE
        mock_touch.assert_called_once()

    @patch("os.path.isfile")
    @patch("pathlib.Path.touch")
    @patch("os.path.expanduser")
    @patch("shutil.copy2")
    @patch("pathlib.Path.unlink")
    @patch("os.makedirs")
    def test_initialize_command_history_file_migrates_old_file(
        self,
        mock_makedirs,
        mock_unlink,
        mock_copy2,
        mock_expanduser,
        mock_touch,
        mock_isfile,
        mock_config_paths,
    ):
        # Setup
        mock_cfg_dir, _ = mock_config_paths
        # First call checks if COMMAND_HISTORY_FILE exists, second call checks if old history file exists
        mock_isfile.side_effect = [False, True]
        mock_expanduser.return_value = "/mock_home"

        # Call the function
        cp_config.initialize_command_history_file()

        # Assert
        assert mock_isfile.call_count == 2
        mock_touch.assert_called_once()
        mock_copy2.assert_called_once()
        mock_unlink.assert_called_once()

    @patch("os.path.isfile")
    @patch("os.makedirs")
    def test_initialize_command_history_file_file_exists(
        self, mock_makedirs, mock_isfile, mock_config_paths
    ):
        # Setup
        mock_isfile.return_value = True  # File already exists

        # Call the function
        cp_config.initialize_command_history_file()

        # Assert
        mock_isfile.assert_called_once_with(cp_config.COMMAND_HISTORY_FILE)
        # No other function should be called since file exists

    @patch("builtins.open", new_callable=mock_open)
    @patch("datetime.datetime")
    def test_save_command_to_history_with_timestamp(
        self, mock_datetime, mock_file, mock_config_paths
    ):
        # Setup
        mock_cfg_dir, mock_cfg_file = mock_config_paths
        mock_now = MagicMock()
        mock_now.isoformat.return_value = "2023-01-01T12:34:56"
        mock_datetime.now.return_value = mock_now

        # Call the function
        cp_config.save_command_to_history("test command")

        # Assert
        mock_file.assert_called_once_with(cp_config.COMMAND_HISTORY_FILE, "a")
        mock_file().write.assert_called_once_with(
            "\n# 2023-01-01T12:34:56\ntest command\n"
        )
        mock_now.isoformat.assert_called_once_with(timespec="seconds")

    @patch("builtins.open")
    @patch("rich.console.Console")
    def test_save_command_to_history_handles_error(
        self, mock_console_class, mock_file, mock_config_paths
    ):
        # Setup
        mock_file.side_effect = Exception("Test error")
        mock_console_instance = MagicMock()
        mock_console_class.return_value = mock_console_instance

        # Call the function
        cp_config.save_command_to_history("test command")

        # Assert
        mock_console_instance.print.assert_called_once()


class TestDefaultModelSelection:
    def setup_method(self):
        # Clear the cache before each test to ensure consistent behavior
        cp_config.clear_model_cache()

    @patch("code_puppy.config.get_value")
    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_model_name_no_stored_model(
        self, mock_default_model, mock_validate_model_exists, mock_get_value
    ):
        # When no model is stored in config, get_model_name should return the default model
        mock_get_value.return_value = None
        mock_default_model.return_value = "synthetic-GLM-4.6"

        result = cp_config.get_global_model_name()

        assert result == "synthetic-GLM-4.6"
        mock_get_value.assert_called_once_with("model")
        mock_validate_model_exists.assert_not_called()
        mock_default_model.assert_called_once()

    @patch("code_puppy.config.get_value")
    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_model_name_invalid_model(
        self, mock_default_model, mock_validate_model_exists, mock_get_value
    ):
        # When stored model doesn't exist in models.json, should return default model
        mock_get_value.return_value = "invalid-model"
        mock_validate_model_exists.return_value = False
        mock_default_model.return_value = "synthetic-GLM-4.6"

        result = cp_config.get_global_model_name()

        assert result == "synthetic-GLM-4.6"
        mock_get_value.assert_called_once_with("model")
        mock_validate_model_exists.assert_called_once_with("invalid-model")
        mock_default_model.assert_called_once()

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_default_model_from_models_json_with_valid_config(self, mock_load_config):
        # Test that the first model from models.json is selected when config is valid
        mock_load_config.return_value = {
            "test-model-1": {"type": "openai", "name": "test-model-1"},
            "test-model-2": {"type": "anthropic", "name": "test-model-2"},
            "test-model-3": {"type": "gemini", "name": "test-model-3"},
        }

        result = cp_config._default_model_from_models_json()

        assert result == "test-model-1"
        mock_load_config.assert_called_once()

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_default_model_from_models_json_prefers_synthetic_glm(self, mock_load_config):
        # Test that synthetic-GLM-4.6 is preferred even when other models come first
        mock_load_config.return_value = {
            "other-model-1": {"type": "openai", "name": "other-model-1"},
            "synthetic-GLM-4.6": {"type": "custom_openai", "name": "hf:zai-org/GLM-4.6"},
            "other-model-2": {"type": "anthropic", "name": "other-model-2"},
        }

        result = cp_config._default_model_from_models_json()

        assert result == "synthetic-GLM-4.6"
        mock_load_config.assert_called_once()

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_default_model_from_models_json_empty_config(self, mock_load_config):
        # Test that gpt-5 is returned when models.json is empty
        mock_load_config.return_value = {}

        result = cp_config._default_model_from_models_json()

        assert result == "gpt-5"
        mock_load_config.assert_called_once()

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_default_model_from_models_json_exception_handling(self, mock_load_config):
        # Test that gpt-5 is returned when there's an exception loading models.json
        mock_load_config.side_effect = Exception("Config load failed")

        result = cp_config._default_model_from_models_json()

        assert result == "gpt-5"
        mock_load_config.assert_called_once()

    def test_default_model_from_models_json_actual_file(self):
        # Test that the actual preferred model from models.json is returned
        # This test uses the real models.json file to verify correct behavior
        result = cp_config._default_model_from_models_json()

        # synthetic-GLM-4.6 should be selected as it's explicitly preferred
        assert result == "synthetic-GLM-4.6"

    @patch("code_puppy.config.get_value")
    def test_get_model_name_with_nonexistent_model_uses_first_from_models_json(
        self, mock_get_value
    ):
        # Test the exact scenario: when a model doesn't exist in the config,
        # the preferred default model from models.json is selected
        mock_get_value.return_value = "non-existent-model"

        # This will use the real models.json file through the ModelFactory
        result = cp_config.get_global_model_name()

        # Since "non-existent-model" doesn't exist in models.json,
        # it should fall back to the preferred model ("synthetic-GLM-4.6")
        assert result == "synthetic-GLM-4.6"
        mock_get_value.assert_called_once_with("model")
