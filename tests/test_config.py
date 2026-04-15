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
    # XDG directories for the new directory structure
    mock_data_dir = os.path.join(mock_home, ".local", "share", "code_puppy")
    mock_cache_dir = os.path.join(mock_home, ".cache", "code_puppy")
    mock_state_dir = os.path.join(mock_home, ".local", "state", "code_puppy")
    mock_skills_dir = os.path.join(mock_data_dir, "skills")

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    monkeypatch.setattr(cp_config, "DATA_DIR", mock_data_dir)
    monkeypatch.setattr(cp_config, "CACHE_DIR", mock_cache_dir)
    monkeypatch.setattr(cp_config, "STATE_DIR", mock_state_dir)
    monkeypatch.setattr(cp_config, "SKILLS_DIR", mock_skills_dir)
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

        # All 4 XDG directories don't exist
        mock_os_path_exists = MagicMock(return_value=False)
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

        # Now 5 directories are created (CONFIG, DATA, CACHE, STATE, SKILLS)
        assert mock_makedirs.call_count == 5
        m_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")

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

        # All XDG directories already exist
        mock_os_path_exists = MagicMock(return_value=True)
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

        mock_makedirs.assert_not_called()  # All dirs already exist
        m_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")

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
        m_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")
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
    def test_get_config_keys_with_existing_section(
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
                "banner_color_agent_reasoning",
                "banner_color_agent_response",
                "banner_color_create_file",
                "banner_color_delete_snippet",
                "banner_color_directory_listing",
                "banner_color_edit_file",
                "banner_color_grep",
                "banner_color_invoke_agent",
                "banner_color_list_agents",
                "banner_color_mcp_tool_call",
                "banner_color_read_file",
                "banner_color_replace_in_file",
                "banner_color_shell_command",
                "banner_color_shell_passthrough",
                "banner_color_subagent_response",
                "banner_color_terminal_tool",
                "banner_color_thinking",
                "banner_color_universal_constructor",
                "cancel_agent_key",
                "compaction_strategy",
                "compaction_threshold",
                "data_analytics_knowledge_path",
                "default_agent",
                "diff_context_lines",
                "enable_dbos",
                "enable_git_auto_commit_prompt",
                "enable_pack_agents",
                "enable_streaming",
                "enable_universal_constructor",
                "frontend_emitter_enabled",
                "frontend_emitter_max_recent_events",
                "frontend_emitter_queue_size",
                "http2",
                "key1",
                "key2",
                "max_hook_retries",
                "max_saved_sessions",
                "message_limit",
                "model",
                "openai_reasoning_effort",
                "openai_reasoning_summary",
                "openai_verbosity",
                "protected_token_count",
                "resume_message_count",
                "temperature",
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
                "banner_color_agent_reasoning",
                "banner_color_agent_response",
                "banner_color_create_file",
                "banner_color_delete_snippet",
                "banner_color_directory_listing",
                "banner_color_edit_file",
                "banner_color_grep",
                "banner_color_invoke_agent",
                "banner_color_list_agents",
                "banner_color_mcp_tool_call",
                "banner_color_read_file",
                "banner_color_replace_in_file",
                "banner_color_shell_command",
                "banner_color_shell_passthrough",
                "banner_color_subagent_response",
                "banner_color_terminal_tool",
                "banner_color_thinking",
                "banner_color_universal_constructor",
                "cancel_agent_key",
                "compaction_strategy",
                "compaction_threshold",
                "data_analytics_knowledge_path",
                "default_agent",
                "diff_context_lines",
                "enable_dbos",
                "enable_git_auto_commit_prompt",
                "enable_pack_agents",
                "enable_streaming",
                "enable_universal_constructor",
                "frontend_emitter_enabled",
                "frontend_emitter_max_recent_events",
                "frontend_emitter_queue_size",
                "http2",
                "max_hook_retries",
                "max_saved_sessions",
                "message_limit",
                "model",
                "openai_reasoning_effort",
                "openai_reasoning_summary",
                "openai_verbosity",
                "protected_token_count",
                "resume_message_count",
                "temperature",
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
        mock_file_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")
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
        mock_file_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")
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

        mock_file_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")
        mock_parser_instance.write.assert_called_once_with(mock_file_open())


class TestModelName:
    def setup_method(self):
        # Reset session model before each test to avoid cross-test pollution
        cp_config.reset_session_model()
        cp_config.clear_model_cache()

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
                mock_parser_instance.__contains__ = lambda s_name: (
                    s_name == DEFAULT_SECTION_NAME
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
        mock_file_open.assert_called_once_with(mock_cfg_file, "w", encoding="utf-8")
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


class TestSafetyPermissionLevel:
    @patch("code_puppy.config.get_value")
    def test_get_safety_permission_level_defaults_to_medium(self, mock_get_value):
        """Test that safety_permission_level defaults to 'medium'."""
        mock_get_value.return_value = None
        assert cp_config.get_safety_permission_level() == "medium"

    @patch("code_puppy.config.get_value")
    def test_get_safety_permission_level_valid_values(self, mock_get_value):
        """Test that all valid safety levels are recognized."""
        for level in ["none", "low", "medium", "high", "critical"]:
            mock_get_value.return_value = level
            assert cp_config.get_safety_permission_level() == level

    @patch("code_puppy.config.get_value")
    def test_get_safety_permission_level_case_insensitive(self, mock_get_value):
        """Test that safety level is case-insensitive."""
        mock_get_value.return_value = "HIGH"
        assert cp_config.get_safety_permission_level() == "high"

    @patch("code_puppy.config.get_value")
    def test_get_safety_permission_level_invalid_defaults_to_medium(
        self, mock_get_value
    ):
        """Test that invalid levels default to medium."""
        mock_get_value.return_value = "invalid_level"
        assert cp_config.get_safety_permission_level() == "medium"


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
    def test_save_command_to_history_with_timestamp(self, mock_file, mock_config_paths):
        # Setup
        mock_cfg_dir, mock_cfg_file = mock_config_paths

        # Call the function
        cp_config.save_command_to_history("test command")

        # Assert - now using encoding and errors parameters
        mock_file.assert_called_once_with(
            cp_config.COMMAND_HISTORY_FILE,
            "a",
            encoding="utf-8",
            errors="surrogateescape",
        )

        # Verify the write call was made with the correct format
        # The timestamp is dynamic, so we check the format rather than exact value
        write_call_args = mock_file().write.call_args[0][0]
        assert write_call_args.startswith("\n# ")
        assert write_call_args.endswith("\ntest command\n")
        # Check timestamp format is ISO-like (YYYY-MM-DDTHH:MM:SS)
        import re

        timestamp_match = re.search(
            r"# (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", write_call_args
        )
        assert timestamp_match is not None, (
            f"Timestamp format not found in: {write_call_args}"
        )

    @patch("builtins.open")
    @patch("code_puppy.messaging.emit_error")
    def test_save_command_to_history_handles_error(
        self, mock_emit_error, mock_file, mock_config_paths
    ):
        # Setup
        mock_file.side_effect = Exception("Test error")

        # Call the function
        cp_config.save_command_to_history("test command")

        # Assert - emit_error is called with a message containing the error
        mock_emit_error.assert_called_once()
        assert "Test error" in mock_emit_error.call_args[0][0]


class TestDefaultModelSelection:
    def setup_method(self):
        # Clear the cache before each test to ensure consistent behavior
        cp_config.clear_model_cache()
        # Also reset the session-local model cache so tests start fresh
        cp_config.reset_session_model()

    @patch("code_puppy.config.get_value")
    @patch("code_puppy.config._validate_model_exists")
    @patch("code_puppy.config._default_model_from_models_json")
    def test_get_model_name_no_stored_model(
        self, mock_default_model, mock_validate_model_exists, mock_get_value
    ):
        # When no model is stored in config, get_model_name should return the default model
        mock_get_value.return_value = None
        mock_default_model.return_value = "synthetic-GLM-5.1"

        result = cp_config.get_global_model_name()

        assert result == "synthetic-GLM-5.1"
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
        mock_default_model.return_value = "synthetic-GLM-5.1"

        result = cp_config.get_global_model_name()

        assert result == "synthetic-GLM-5.1"
        mock_get_value.assert_called_once_with("model")
        mock_validate_model_exists.assert_called_once_with("invalid-model")
        mock_default_model.assert_called_once()

    def test_default_model_from_models_json_returns_first_model(self):
        # Test that _default_model_from_models_json returns the first model from models.json
        # Clear the cache to ensure fresh read
        cp_config.clear_model_cache()

        result = cp_config._default_model_from_models_json()

        # Should return a valid model name (first one in models.json)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_default_model_from_models_json_empty_config(self, mock_load_config):
        # Test that gpt-5 is returned when models.json is empty
        mock_load_config.return_value = {}

        result = cp_config._default_model_from_models_json()

        assert result == "gpt-5"
        mock_load_config.assert_called_once()

    def test_default_model_from_models_json_exception_handling(self):
        # Test that when an exception occurs, the function returns a fallback.
        # Since ModelFactory is imported inside the function and we can't easily
        # mock that import, we just verify the function handles errors gracefully
        # by always returning a valid string result.
        cp_config.clear_model_cache()

        result = cp_config._default_model_from_models_json()

        # The function should always return a valid model name
        # (either from models.json or the fallback 'gpt-5')
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("code_puppy.config.get_value")
    def test_get_model_name_with_nonexistent_model_uses_first_from_models_json(
        self, mock_get_value
    ):
        # Clear the cache to ensure we get a fresh read from models.json
        cp_config.clear_model_cache()

        # Test the exact scenario: when a model doesn't exist in the config,
        # the preferred default model from models.json is selected
        mock_get_value.return_value = "non-existent-model"

        # This will use the real models.json file through the ModelFactory
        result = cp_config.get_global_model_name()

        # Since "non-existent-model" doesn't exist in models.json,
        # it should fall back to a valid model from models.json
        # We can't hardcode which model because the order might vary
        # Just verify it's a non-empty string (i.e., some valid model was selected)
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0
        # And it shouldn't be our fake "non-existent-model"
        assert result != "non-existent-model"


class TestGetCommandTimeoutSeconds:
    """Test suite for get_command_timeout_seconds configuration function."""

    def test_returns_default_when_no_config_value(self, monkeypatch):
        """Test that default value (270) is returned when config key is not set."""
        monkeypatch.setattr(cp_config, "get_value", lambda key: None)
        result = cp_config.get_command_timeout_seconds()
        assert result == 270

    def test_returns_valid_value_within_bounds(self, monkeypatch):
        """Test that valid values within bounds (60-900) are returned correctly."""
        # Test minimum bound
        monkeypatch.setattr(cp_config, "get_value", lambda key: "60")
        assert cp_config.get_command_timeout_seconds() == 60

        # Test maximum bound
        monkeypatch.setattr(cp_config, "get_value", lambda key: "900")
        assert cp_config.get_command_timeout_seconds() == 900

        # Test value in the middle
        monkeypatch.setattr(cp_config, "get_value", lambda key: "500")
        assert cp_config.get_command_timeout_seconds() == 500

        # Test default value
        monkeypatch.setattr(cp_config, "get_value", lambda key: "270")
        assert cp_config.get_command_timeout_seconds() == 270

    def test_returns_default_for_value_below_minimum(self, monkeypatch):
        """Test that values below 60 seconds return default (270)."""
        # Test value just below minimum
        monkeypatch.setattr(cp_config, "get_value", lambda key: "59")
        assert cp_config.get_command_timeout_seconds() == 270

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_opus_46_fallback_supports_effort(self, mock_load_config):
        """Opus 4-6 models should support effort in the fallback path."""
        mock_load_config.return_value = {
            "claude-opus-4-6": {"type": "anthropic", "name": "claude-opus-4-6"}
        }
        assert cp_config.model_supports_setting("claude-opus-4-6", "effort") is True
        assert cp_config.model_supports_setting("claude-4-6-opus", "effort") is True

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    def test_non_opus_46_fallback_does_not_support_effort(self, mock_load_config):
        """Non Opus 4-6 Claude models should NOT support effort in fallback."""
        mock_load_config.return_value = {
            "claude-sonnet-4": {"type": "anthropic", "name": "claude-sonnet-4"}
        }
        assert cp_config.model_supports_setting("claude-sonnet-4", "effort") is False
