"""Edge case tests for config.py, callbacks.py, and session_storage.py.

Focuses on areas that don't require complex mocking:
- DBOS configuration testing
- Allow recursion testing
- Temperature configuration
- Config key management
- Callback error handling
- Session storage edge cases
"""

import configparser
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy import callbacks, session_storage
from code_puppy import config as cp_config


@pytest.fixture
def mock_config_paths(monkeypatch, tmp_path):
    """Mock XDG paths for isolated testing."""
    mock_config_dir = str(tmp_path / ".config" / "code_puppy")
    mock_config_file = os.path.join(mock_config_dir, "puppy.cfg")
    mock_data_dir = str(tmp_path / ".local" / "share" / "code_puppy")
    mock_cache_dir = str(tmp_path / ".cache" / "code_puppy")
    mock_state_dir = str(tmp_path / ".local" / "state" / "code_puppy")

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    monkeypatch.setattr(cp_config, "DATA_DIR", mock_data_dir)
    monkeypatch.setattr(cp_config, "CACHE_DIR", mock_cache_dir)
    monkeypatch.setattr(cp_config, "STATE_DIR", mock_state_dir)

    return mock_config_dir, mock_config_file, mock_data_dir


class TestDBOSConfiguration:
    """Test DBOS (Database Operating System) configuration."""

    def test_get_use_dbos_returns_false_by_default(self, mock_config_paths):
        """Test that DBOS is disabled by default."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_use_dbos()
        assert result is False

    @pytest.mark.parametrize("truthy_value", ["1", "true", "True", "yes", "on"])
    def test_get_use_dbos_returns_true_for_truthy_values(
        self, mock_config_paths, truthy_value
    ):
        """Test that various truthy values enable DBOS."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        os.makedirs(mock_cfg_dir, exist_ok=True)
        config = configparser.ConfigParser()
        config["puppy"] = {"enable_dbos": truthy_value}
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_use_dbos()
        assert result is True, f"Failed for value: {truthy_value}"

    @pytest.mark.parametrize("falsy_value", ["0", "false", "no", "off", ""])
    def test_get_use_dbos_returns_false_for_falsy_values(
        self, mock_config_paths, falsy_value
    ):
        """Test that falsy values disable DBOS."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        os.makedirs(mock_cfg_dir, exist_ok=True)
        config = configparser.ConfigParser()
        config["puppy"] = {"enable_dbos": falsy_value}
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_use_dbos()
        assert result is False, f"Failed for value: {falsy_value}"


class TestAllowRecursion:
    """Test allow_recursion configuration."""

    def test_get_allow_recursion_defaults_to_true(self, mock_config_paths):
        """Test that allow_recursion defaults to True when not set."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_allow_recursion()
        assert result is True

    def test_get_allow_recursion_respects_explicit_false(self, mock_config_paths):
        """Test that explicit false value is respected."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {"allow_recursion": "false"}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_allow_recursion()
        assert result is False

    @pytest.mark.parametrize("truthy", ["1", "true", "yes", "on"])
    def test_get_allow_recursion_respects_truthy_values(
        self, mock_config_paths, truthy
    ):
        """Test that truthy values are recognized."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        os.makedirs(mock_cfg_dir, exist_ok=True)
        config = configparser.ConfigParser()
        config["puppy"] = {"allow_recursion": truthy}
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_allow_recursion()
        assert result is True, f"Failed for: {truthy}"


class TestPuppyTokens:
    """Test puppy token configuration."""

    def test_get_puppy_token_returns_value_if_set(self, mock_config_paths):
        """Test getting puppy token when it's set."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {"puppy_token": "secret-token-123"}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_puppy_token()
        assert result == "secret-token-123"

    def test_get_puppy_token_returns_none_if_not_set(self, mock_config_paths):
        """Test getting puppy token when it's not set."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_puppy_token()
        assert result is None

    def test_set_puppy_token_persists_value(self, mock_config_paths):
        """Test setting puppy token."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        cp_config.set_puppy_token("new-token-456")

        saved_config = configparser.ConfigParser()
        saved_config.read(mock_cfg_file)
        assert saved_config["puppy"]["puppy_token"] == "new-token-456"


class TestXDGDirectoryHandling:
    """Test XDG Base Directory support."""

    def test_get_xdg_dir_respects_environment_variable(self):
        """Test that explicit XDG env var is respected."""
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": "/custom/config"}):
            result = cp_config._get_xdg_dir("XDG_CONFIG_HOME", ".config")
            assert result == "/custom/config/code_puppy"

    def test_get_xdg_dir_defaults_to_home_when_no_env_var(self):
        """Test fallback to ~/.code_puppy when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.path.expanduser") as mock_expand:
                mock_expand.return_value = "/home/user"
                result = cp_config._get_xdg_dir("XDG_CONFIG_HOME", ".config")
                assert result == "/home/user/.code_puppy"


class TestConfigKeys:
    """Test config key management."""

    def test_get_config_keys_includes_defaults(self, mock_config_paths):
        """Test that default keys are always included."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_config_keys()

        # Check some expected default keys
        expected_keys = [
            "yolo_mode",
            "model",
            "auto_save_session",
            "enable_dbos",
            "cancel_agent_key",
        ]
        for key in expected_keys:
            assert key in result, f"Expected key '{key}' not in config keys"

    def test_get_config_keys_includes_custom_keys(self, mock_config_paths):
        """Test that custom keys from config are included."""
        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths

        config = configparser.ConfigParser()
        config["puppy"] = {"custom_key_1": "value1", "custom_key_2": "value2"}
        os.makedirs(mock_cfg_dir, exist_ok=True)
        with open(mock_cfg_file, "w") as f:
            config.write(f)

        result = cp_config.get_config_keys()

        assert "custom_key_1" in result
        assert "custom_key_2" in result


# ==================== CALLBACKS TESTS ====================


class TestCallbacksErrorHandling:
    """Test callbacks error handling and edge cases."""

    def test_register_callback_rejects_invalid_phase(self):
        """Test that registering callback with invalid phase raises error."""

        def dummy_callback():
            pass

        with pytest.raises(ValueError, match="Unsupported phase"):
            callbacks.register_callback("invalid_phase", dummy_callback)

    def test_register_callback_rejects_non_callable(self):
        """Test that non-callable objects are rejected."""
        with pytest.raises(TypeError, match="Callback must be callable"):
            callbacks.register_callback("startup", "not a function")

    def test_register_callback_prevents_duplicates(self):
        """Test that duplicate registrations are prevented."""

        def my_callback():
            pass

        callbacks.clear_callbacks("startup")

        callbacks.register_callback("startup", my_callback)
        count_after_first = callbacks.count_callbacks("startup")

        # Try to register same callback again
        callbacks.register_callback("startup", my_callback)
        count_after_second = callbacks.count_callbacks("startup")

        # Count should not increase
        assert count_after_first == count_after_second

        # Cleanup
        callbacks.clear_callbacks("startup")

    def test_unregister_callback_returns_false_for_invalid_phase(self):
        """Test unregister returns False for invalid phase."""

        def dummy():
            pass

        result = callbacks.unregister_callback("invalid_phase", dummy)
        assert result is False

    def test_unregister_callback_returns_false_when_not_registered(self):
        """Test unregister returns False when callback not registered."""

        def unregistered_callback():
            pass

        callbacks.clear_callbacks("startup")
        result = callbacks.unregister_callback("startup", unregistered_callback)
        assert result is False

    def test_unregister_callback_returns_true_when_successful(self):
        """Test unregister returns True when successful."""

        def my_callback():
            pass

        callbacks.clear_callbacks("startup")
        callbacks.register_callback("startup", my_callback)

        result = callbacks.unregister_callback("startup", my_callback)
        assert result is True
        assert callbacks.count_callbacks("startup") == 0

    def test_clear_callbacks_specific_phase(self):
        """Test clearing callbacks for a specific phase."""

        def callback1():
            pass

        def callback2():
            pass

        callbacks.clear_callbacks()
        callbacks.register_callback("startup", callback1)
        callbacks.register_callback("shutdown", callback2)

        # Clear only startup
        callbacks.clear_callbacks("startup")

        assert callbacks.count_callbacks("startup") == 0
        assert callbacks.count_callbacks("shutdown") == 1

        # Cleanup
        callbacks.clear_callbacks()

    def test_get_callbacks_returns_copy(self):
        """Test that get_callbacks returns a copy, not the original list."""

        def my_callback():
            pass

        callbacks.clear_callbacks("startup")
        callbacks.register_callback("startup", my_callback)

        retrieved = callbacks.get_callbacks("startup")
        original_count = callbacks.count_callbacks("startup")

        # Modify the retrieved list
        retrieved.append(lambda: None)

        # Original should be unchanged
        assert callbacks.count_callbacks("startup") == original_count

        # Cleanup
        callbacks.clear_callbacks("startup")

    def test_count_callbacks_all_phases(self):
        """Test counting all callbacks across all phases."""

        def callback1():
            pass

        def callback2():
            pass

        def callback3():
            pass

        callbacks.clear_callbacks()
        callbacks.register_callback("startup", callback1)
        callbacks.register_callback("startup", callback2)
        callbacks.register_callback("shutdown", callback3)

        total = callbacks.count_callbacks()
        assert total >= 3  # At least 3 (may have others from other tests)

        # Cleanup
        callbacks.clear_callbacks()


# ==================== SESSION STORAGE TESTS ====================


class TestSessionStoragePathManagement:
    """Test session storage path handling."""

    def test_ensure_directory_creates_directory(self, tmp_path):
        """Test that ensure_directory creates missing directories."""
        test_path = tmp_path / "new_dir"
        assert not test_path.exists()

        result = session_storage.ensure_directory(test_path)

        assert test_path.exists()
        assert result == test_path

    def test_ensure_directory_handles_existing_directory(self, tmp_path):
        """Test that ensure_directory handles existing directories gracefully."""
        result = session_storage.ensure_directory(tmp_path)
        assert result == tmp_path

    def test_build_session_paths_creates_correct_paths(self, tmp_path):
        """Test that build_session_paths creates correct pickle and metadata paths."""
        paths = session_storage.build_session_paths(tmp_path, "test_session")

        assert paths.pickle_path == tmp_path / "test_session.pkl"
        assert paths.metadata_path == tmp_path / "test_session_meta.json"


class TestSessionSaveAndLoad:
    """Test saving and loading sessions."""

    def test_save_session_creates_pickle_and_metadata(self, tmp_path):
        """Test that save_session creates both pickle and metadata files."""
        history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        def mock_token_estimator(msg):
            return len(msg.get("content", "").split())

        metadata = session_storage.save_session(
            history=history,
            session_name="test",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
            auto_saved=False,
        )

        # Check pickle file exists
        assert (tmp_path / "test.pkl").exists()
        # Check metadata file exists
        assert (tmp_path / "test_meta.json").exists()
        # Check metadata content
        assert metadata.session_name == "test"
        assert metadata.message_count == 2
        assert metadata.auto_saved is False

    def test_load_session_retrieves_saved_history(self, tmp_path):
        """Test that load_session correctly retrieves saved history."""
        original_history = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]

        def mock_token_estimator(msg):
            return 10

        # Save session
        session_storage.save_session(
            history=original_history,
            session_name="test",
            base_dir=tmp_path,
            timestamp="2024-01-01T00:00:00",
            token_estimator=mock_token_estimator,
        )

        # Load it back
        loaded_history = session_storage.load_session("test", tmp_path)

        assert loaded_history == original_history

    def test_load_session_raises_for_missing_file(self, tmp_path):
        """Test that load_session raises FileNotFoundError for missing session."""
        with pytest.raises(FileNotFoundError):
            session_storage.load_session("nonexistent", tmp_path)

    def test_session_metadata_serialization(self):
        """Test that SessionMetadata serializes to dict correctly."""
        metadata = session_storage.SessionMetadata(
            session_name="test",
            timestamp="2024-01-01T00:00:00",
            message_count=5,
            total_tokens=100,
            pickle_path=Path("/tmp/test.pkl"),
            metadata_path=Path("/tmp/test_meta.json"),
            auto_saved=True,
        )

        serialized = metadata.as_serialisable()

        assert serialized["session_name"] == "test"
        assert serialized["message_count"] == 5
        assert serialized["total_tokens"] == 100
        assert serialized["auto_saved"] is True
        assert "file_path" in serialized


class TestSessionListingAndCleanup:
    """Test session listing and cleanup operations."""

    def test_list_sessions_returns_empty_for_nonexistent_dir(self, tmp_path):
        """Test that list_sessions returns empty list for nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"
        result = session_storage.list_sessions(nonexistent)
        assert result == []

    def test_list_sessions_returns_all_sessions(self, tmp_path):
        """Test that list_sessions returns all session names."""

        def mock_token_estimator(msg):
            return 10

        # Create multiple sessions
        for i in range(3):
            session_storage.save_session(
                history=[{"role": "user", "content": f"msg{i}"}],
                session_name=f"session_{i}",
                base_dir=tmp_path,
                timestamp="2024-01-01T00:00:00",
                token_estimator=mock_token_estimator,
            )

        result = session_storage.list_sessions(tmp_path)

        assert len(result) == 3
        assert "session_0" in result
        assert "session_1" in result
        assert "session_2" in result

    def test_cleanup_sessions_does_nothing_for_empty_dir(self, tmp_path):
        """Test that cleanup_sessions handles empty directories gracefully."""
        result = session_storage.cleanup_sessions(tmp_path, max_sessions=5)
        assert result == []

    def test_cleanup_sessions_removes_old_sessions(self, tmp_path):
        """Test that cleanup_sessions removes oldest sessions when limit exceeded."""

        def mock_token_estimator(msg):
            return 10

        # Create sessions with staggered timestamps (to simulate age)
        for i in range(5):
            session_path = tmp_path / f"session_{i}.pkl"
            # Create file and artificially age it
            session_path.touch()
            if i < 2:
                # Make first two older by changing mtime
                os.utime(session_path, (i, i))

        # Keep only 3 most recent
        removed = session_storage.cleanup_sessions(tmp_path, max_sessions=3)

        # Should remove oldest sessions
        assert len(removed) >= 2

        # Should have only 3 or fewer left
        remaining = session_storage.list_sessions(tmp_path)
        assert len(remaining) <= 3

    def test_cleanup_sessions_with_negative_max(self, tmp_path):
        """Test that cleanup_sessions returns empty list for negative max."""
        result = session_storage.cleanup_sessions(tmp_path, max_sessions=-1)
        assert result == []

    def test_cleanup_sessions_with_zero_max(self, tmp_path):
        """Test that cleanup_sessions returns empty list for zero max."""
        result = session_storage.cleanup_sessions(tmp_path, max_sessions=0)
        assert result == []
