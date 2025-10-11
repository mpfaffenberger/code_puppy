import os
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import config as cp_config


@pytest.fixture
def mock_config_paths(monkeypatch):
    mock_home = "/mock_home"
    mock_config_dir = os.path.join(mock_home, ".code_puppy")
    mock_config_file = os.path.join(mock_config_dir, "puppy.cfg")
    mock_contexts_dir = os.path.join(mock_config_dir, "contexts")

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    # Create a safe expanduser function that doesn't recurse
    original_expanduser = os.path.expanduser
    def mock_expanduser(path):
        if path == "~":
            return mock_home
        elif path.startswith("~" + os.sep):
            return mock_home + path[1:]
        else:
            return original_expanduser(path)
    monkeypatch.setattr(os.path, "expanduser", mock_expanduser)
    return mock_config_dir, mock_config_file, mock_contexts_dir


class TestAutoSaveSession:
    @patch("code_puppy.config.get_value")
    def test_get_auto_save_session_enabled_true_values(self, mock_get_value):
        true_values = ["true", "1", "YES", "on"]
        for val in true_values:
            mock_get_value.reset_mock()
            mock_get_value.return_value = val
            assert cp_config.get_auto_save_session() is True, f"Failed for config value: {val}"
            mock_get_value.assert_called_once_with("auto_save_session")

    @patch("code_puppy.config.get_value")
    def test_get_auto_save_session_enabled_false_values(self, mock_get_value):
        false_values = ["false", "0", "NO", "off", "invalid"]
        for val in false_values:
            mock_get_value.reset_mock()
            mock_get_value.return_value = val
            assert cp_config.get_auto_save_session() is False, f"Failed for config value: {val}"
            mock_get_value.assert_called_once_with("auto_save_session")

    @patch("code_puppy.config.get_value")
    def test_get_auto_save_session_default_true(self, mock_get_value):
        mock_get_value.return_value = None
        assert cp_config.get_auto_save_session() is True
        mock_get_value.assert_called_once_with("auto_save_session")

    @patch("code_puppy.config.set_config_value")
    def test_set_auto_save_session_enabled(self, mock_set_config_value):
        cp_config.set_auto_save_session(True)
        mock_set_config_value.assert_called_once_with("auto_save_session", "true")

    @patch("code_puppy.config.set_config_value")
    def test_set_auto_save_session_disabled(self, mock_set_config_value):
        cp_config.set_auto_save_session(False)
        mock_set_config_value.assert_called_once_with("auto_save_session", "false")


class TestMaxSavedSessions:
    @patch("code_puppy.config.get_value")
    def test_get_max_saved_sessions_valid_int(self, mock_get_value):
        mock_get_value.return_value = "15"
        assert cp_config.get_max_saved_sessions() == 15
        mock_get_value.assert_called_once_with("max_saved_sessions")

    @patch("code_puppy.config.get_value")
    def test_get_max_saved_sessions_zero(self, mock_get_value):
        mock_get_value.return_value = "0"
        assert cp_config.get_max_saved_sessions() == 0
        mock_get_value.assert_called_once_with("max_saved_sessions")

    @patch("code_puppy.config.get_value")
    def test_get_max_saved_sessions_negative_clamped_to_zero(self, mock_get_value):
        mock_get_value.return_value = "-5"
        assert cp_config.get_max_saved_sessions() == 0
        mock_get_value.assert_called_once_with("max_saved_sessions")

    @patch("code_puppy.config.get_value")
    def test_get_max_saved_sessions_invalid_value_defaults(self, mock_get_value):
        invalid_values = ["invalid", "not_a_number", "", None]
        for val in invalid_values:
            mock_get_value.reset_mock()
            mock_get_value.return_value = val
            assert cp_config.get_max_saved_sessions() == 20  # Default value
            mock_get_value.assert_called_once_with("max_saved_sessions")

    @patch("code_puppy.config.get_value")
    def test_get_max_saved_sessions_default(self, mock_get_value):
        mock_get_value.return_value = None
        assert cp_config.get_max_saved_sessions() == 20
        mock_get_value.assert_called_once_with("max_saved_sessions")

    @patch("code_puppy.config.set_config_value")
    def test_set_max_saved_sessions(self, mock_set_config_value):
        cp_config.set_max_saved_sessions(25)
        mock_set_config_value.assert_called_once_with("max_saved_sessions", "25")

    @patch("code_puppy.config.set_config_value")
    def test_set_max_saved_sessions_zero(self, mock_set_config_value):
        cp_config.set_max_saved_sessions(0)
        mock_set_config_value.assert_called_once_with("max_saved_sessions", "0")


class TestAutoSaveSessionFunctionality:
    @patch("code_puppy.config.get_auto_save_session")
    def test_auto_save_session_if_enabled_disabled(self, mock_get_auto_save):
        mock_get_auto_save.return_value = False
        result = cp_config.auto_save_session_if_enabled()
        assert result is False
        mock_get_auto_save.assert_called_once()

    @patch("code_puppy.config.get_auto_save_session")
    @patch("code_puppy.agents.agent_manager.get_current_agent")
    @patch("rich.console.Console")
    def test_auto_save_session_if_enabled_exception(
        self, mock_console_class, mock_get_agent, mock_get_auto_save, mock_config_paths
    ):
        mock_get_auto_save.return_value = True
        mock_agent = MagicMock()
        mock_agent.get_message_history.side_effect = Exception("Agent error")
        mock_get_agent.return_value = mock_agent

        mock_console_instance = MagicMock()
        mock_console_class.return_value = mock_console_instance

        result = cp_config.auto_save_session_if_enabled()
        assert result is False
        mock_console_instance.print.assert_called_once()


class TestCleanupOldSessions:
    @patch("code_puppy.config.get_max_saved_sessions")
    def test_cleanup_old_sessions_unlimited(self, mock_get_max_sessions, mock_config_paths):
        mock_get_max_sessions.return_value = 0  # 0 means unlimited
        # Should not attempt cleanup when unlimited
        cp_config._cleanup_old_sessions()
        mock_get_max_sessions.assert_called_once()