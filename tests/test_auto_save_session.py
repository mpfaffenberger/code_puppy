import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import config as cp_config
from code_puppy.session_storage import SessionMetadata


@pytest.fixture
def mock_config_paths(monkeypatch):
    mock_home = "/mock_home"
    mock_config_dir = os.path.join(mock_home, ".code_puppy")
    mock_config_file = os.path.join(mock_config_dir, "puppy.cfg")
    mock_contexts_dir = os.path.join(mock_config_dir, "contexts")
    mock_autosave_dir = os.path.join(mock_config_dir, "autosaves")

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    monkeypatch.setattr(cp_config, "CONTEXTS_DIR", mock_contexts_dir)
    monkeypatch.setattr(cp_config, "AUTOSAVE_DIR", mock_autosave_dir)

    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~":
            return mock_home
        if path.startswith("~" + os.sep):
            return mock_home + path[1:]
        return original_expanduser(path)

    monkeypatch.setattr(os.path, "expanduser", mock_expanduser)
    return SimpleNamespace(
        config_dir=mock_config_dir,
        config_file=mock_config_file,
        contexts_dir=mock_contexts_dir,
        autosave_dir=mock_autosave_dir,
    )


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

    @patch("code_puppy.config.save_session")
    @patch("code_puppy.config.datetime")
    @patch("code_puppy.config.get_auto_save_session")
    @patch("code_puppy.agents.agent_manager.get_current_agent")
    @patch("rich.console.Console")
    def test_auto_save_session_if_enabled_success(
        self,
        mock_console_class,
        mock_get_agent,
        mock_get_auto_save,
        mock_datetime,
        mock_save_session,
        mock_cleanup,
        mock_config_paths,
    ):
        mock_get_auto_save.return_value = True

        history = ["hey", "listen"]
        mock_agent = MagicMock()
        mock_agent.get_message_history.return_value = history
        mock_agent.estimate_tokens_for_message.return_value = 3
        mock_get_agent.return_value = mock_agent

        fake_now = MagicMock()
        fake_now.strftime.return_value = "20240101_010101"
        fake_now.isoformat.return_value = "2024-01-01T01:01:01"
        mock_datetime.datetime.now.return_value = fake_now

        metadata = SessionMetadata(
            session_name="auto_session_20240101_010101",
            timestamp="2024-01-01T01:01:01",
            message_count=len(history),
            total_tokens=6,
            pickle_path=Path(mock_config_paths.autosave_dir) / "auto_session_20240101_010101.pkl",
            metadata_path=Path(mock_config_paths.autosave_dir)
            / "auto_session_20240101_010101_meta.json",
        )
        mock_save_session.return_value = metadata

        mock_console = MagicMock()
        mock_console_class.return_value = mock_console

        result = cp_config.auto_save_session_if_enabled()

        assert result is True
        mock_save_session.assert_called_once()
        kwargs = mock_save_session.call_args.kwargs
        assert kwargs["base_dir"] == Path(mock_config_paths.autosave_dir)
        assert kwargs["session_name"] == "auto_session_20240101_010101"
        mock_cleanup.assert_called_once()
        mock_console.print.assert_called_once()

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
