"""Tests for agent manager session tracking functionality.

Covers:
- Terminal session ID generation
- Process liveness checking
- Session data persistence (save/load)
- Dead session cleanup
- Session caching
"""

import json
import os
import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.agents.agent_manager import (
    _cleanup_dead_sessions,
    _ensure_session_cache_loaded,
    _get_session_file_path,
    _is_process_alive,
    _load_session_data,
    _save_session_data,
    get_terminal_session_id,
)


class TestTerminalSessionID:
    """Test terminal session ID generation."""

    def test_get_terminal_session_id_uses_ppid(self):
        """Test that get_terminal_session_id uses parent process ID."""
        with patch("os.getppid", return_value=12345):
            session_id = get_terminal_session_id()
            assert session_id == "session_12345"

    def test_get_terminal_session_id_fallback_to_pid(self):
        """Test fallback to PID when PPID not available."""
        with patch("os.getppid", side_effect=OSError):
            with patch("os.getpid", return_value=54321):
                session_id = get_terminal_session_id()
                assert session_id == "fallback_54321"

    def test_get_terminal_session_id_format(self):
        """Test that session ID format is consistent."""
        with patch("os.getppid", return_value=99999):
            session_id = get_terminal_session_id()
            assert session_id.startswith("session_")
            assert session_id == "session_99999"

    def test_get_terminal_session_id_handles_attribute_error(self):
        """Test handling of AttributeError when getting PPID."""
        with patch("os.getppid", side_effect=AttributeError):
            with patch("os.getpid", return_value=11111):
                session_id = get_terminal_session_id()
                assert session_id == "fallback_11111"

    def test_get_terminal_session_id_different_calls_same_ppid(self):
        """Test that same PPID produces same session ID across calls."""
        with patch("os.getppid", return_value=12345):
            session_id1 = get_terminal_session_id()
            session_id2 = get_terminal_session_id()
            assert session_id1 == session_id2


class TestProcessLiveness:
    """Test process liveness checking."""

    def test_is_process_alive_unix_signal_success(self):
        """Test that process is alive when signal 0 succeeds on Unix."""
        if os.name != "nt":  # Unix-like systems
            with patch("os.kill") as mock_kill:
                result = _is_process_alive(12345)
                assert result is True
                mock_kill.assert_called_once_with(12345, 0)

    def test_is_process_alive_unix_permission_error_means_exists(self):
        """Test that PermissionError means process exists on Unix."""
        if os.name != "nt":  # Unix-like systems
            with patch("os.kill", side_effect=PermissionError):
                result = _is_process_alive(12345)
                assert result is True

    def test_is_process_alive_unix_process_not_found(self):
        """Test that ProcessLookupError means process doesn't exist on Unix."""
        if os.name != "nt":  # Unix-like systems
            with patch("os.kill", side_effect=ProcessLookupError):
                result = _is_process_alive(12345)
                assert result is False

    def test_is_process_alive_unix_os_error_means_not_found(self):
        """Test that OSError means process doesn't exist on Unix."""
        if os.name != "nt":  # Unix-like systems
            with patch("os.kill", side_effect=OSError):
                result = _is_process_alive(12345)
                assert result is False

    def test_is_process_alive_invalid_pid_format(self):
        """Test handling of invalid PID format."""
        # None gets treated as OS error, which returns True (conservative)
        result = _is_process_alive(None)  # type: ignore
        assert isinstance(result, bool)

    def test_is_process_alive_string_pid(self):
        """Test conversion of string PID to int."""
        if os.name != "nt":  # Unix-like systems
            with patch("os.kill") as mock_kill:
                # String PID should be converted to int
                _is_process_alive("12345")  # type: ignore
                # Should call with int(12345)
                mock_kill.assert_called_once_with(12345, 0)

    def test_is_process_alive_windows(self):
        """Test Windows process checking."""
        if platform.system() == "Windows":
            # On Windows, should use OpenProcess
            result = _is_process_alive(12345)
            # Result depends on actual Windows API, just ensure no crash
            assert isinstance(result, bool)


class TestSessionDataPersistence:
    """Test session data save and load functionality."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary directory for session data."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_get_session_file_path_creates_correct_path(self):
        """Test that session file path is correctly constructed."""
        session_file = _get_session_file_path()
        assert session_file.name == "terminal_sessions.json"
        assert "code_puppy" in str(session_file)

    def test_save_session_data_creates_directory(self, temp_session_dir):
        """Test that save_session_data creates directory if missing."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "sessions" / "terminal_sessions.json"
            mock_path.return_value = session_file

            _save_session_data({"session_123": "code-puppy"})

            assert session_file.parent.exists()
            assert session_file.exists()

    def test_save_session_data_writes_json(self, temp_session_dir):
        """Test that save_session_data writes valid JSON."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "terminal_sessions.json"
            mock_path.return_value = session_file

            sessions = {"session_123": "code-puppy", "session_456": "planning-agent"}
            # Mock _is_process_alive to return True so sessions aren't filtered out during cleanup
            with patch(
                "code_puppy.agents.agent_manager._is_process_alive", return_value=True
            ):
                _save_session_data(sessions)

            with open(session_file, "r") as f:
                loaded = json.load(f)

            assert loaded["session_123"] == "code-puppy"
            assert loaded["session_456"] == "planning-agent"

    def test_save_session_data_handles_io_error(self):
        """Test that save_session_data handles IO errors gracefully."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = Path("/invalid/path/sessions.json")
            mock_path.return_value = session_file
            # Should not raise even with invalid path
            _save_session_data({"session_123": "code-puppy"})

    def test_load_session_data_returns_empty_dict_if_file_missing(self):
        """Test that load returns empty dict if file doesn't exist."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            mock_path.return_value = Path("/nonexistent/path/sessions.json")
            result = _load_session_data()
            assert result == {}

    def test_load_session_data_parses_valid_json(self, temp_session_dir):
        """Test that load_session_data parses valid JSON."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "terminal_sessions.json"
            mock_path.return_value = session_file

            # Create the file with test data
            sessions = {"session_789": "python-programmer"}
            session_file.parent.mkdir(parents=True, exist_ok=True)
            with open(session_file, "w") as f:
                json.dump(sessions, f)

            # Mock _is_process_alive to return True (so cleanup doesn't remove it)
            with patch(
                "code_puppy.agents.agent_manager._is_process_alive", return_value=True
            ):
                result = _load_session_data()
                assert result["session_789"] == "python-programmer"

    def test_load_session_data_handles_corrupted_json(self, temp_session_dir):
        """Test that load handles corrupted JSON gracefully."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "terminal_sessions.json"
            mock_path.return_value = session_file

            # Write corrupted JSON
            with open(session_file, "w") as f:
                f.write("{invalid json}")

            result = _load_session_data()
            assert result == {}

    def test_load_session_data_handles_io_error(self):
        """Test that load handles IO errors gracefully."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            # Point to a path that doesn't exist
            mock_path.return_value = Path("/invalid/nonexistent/path.json")
            result = _load_session_data()
            assert result == {}

    def test_save_load_roundtrip(self, temp_session_dir):
        """Test that data survives save -> load roundtrip."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "terminal_sessions.json"
            mock_path.return_value = session_file

            # Use non-standard session format to avoid PID-based cleanup
            original = {
                "fallback_111": "code-puppy",
                "fallback_222": "planning-agent",
                "fallback_333": "code-reviewer",
            }

            _save_session_data(original)
            loaded = _load_session_data()
            assert loaded == original

    def test_save_atomically_uses_temp_file(self, temp_session_dir):
        """Test that save uses atomic temp file approach."""
        with patch(
            "code_puppy.agents.agent_manager._get_session_file_path"
        ) as mock_path:
            session_file = temp_session_dir / "terminal_sessions.json"
            mock_path.return_value = session_file

            _save_session_data({"session_123": "code-puppy"})

            # Should not have created .tmp file (it should be renamed)
            temp_file = session_file.with_suffix(".tmp")
            assert not temp_file.exists()
            assert session_file.exists()


class TestDeadSessionCleanup:
    """Test dead session cleanup functionality."""

    def test_cleanup_removes_dead_sessions(self):
        """Test that cleanup removes sessions for dead processes."""
        sessions = {
            "session_12345": "code-puppy",  # Will be dead
            "session_99999": "planning-agent",  # Will be dead
        }

        with patch("code_puppy.agents.agent_manager._is_process_alive") as mock_alive:
            mock_alive.return_value = False  # All processes are dead
            result = _cleanup_dead_sessions(sessions)
            assert result == {}

    def test_cleanup_preserves_live_sessions(self):
        """Test that cleanup preserves sessions for live processes."""
        sessions = {
            "session_12345": "code-puppy",
            "session_99999": "planning-agent",
        }

        with patch("code_puppy.agents.agent_manager._is_process_alive") as mock_alive:
            mock_alive.return_value = True  # All processes are alive
            result = _cleanup_dead_sessions(sessions)
            assert result == sessions

    def test_cleanup_mixed_sessions(self):
        """Test cleanup with mix of live and dead processes."""
        sessions = {
            "session_111": "code-puppy",  # alive
            "session_222": "planning-agent",  # dead
            "session_333": "code-reviewer",  # alive
        }

        def is_alive(pid):
            return pid in [111, 333]  # Only these are alive

        with patch(
            "code_puppy.agents.agent_manager._is_process_alive", side_effect=is_alive
        ):
            result = _cleanup_dead_sessions(sessions)
            assert "session_111" in result
            assert "session_222" not in result
            assert "session_333" in result

    def test_cleanup_handles_invalid_session_format(self):
        """Test cleanup handles non-standard session ID formats."""
        sessions = {
            "session_12345": "code-puppy",
            "fallback_99999": "planning-agent",  # Non-standard format
            "invalid": "code-reviewer",  # Also non-standard
        }

        with patch("code_puppy.agents.agent_manager._is_process_alive") as mock_alive:
            mock_alive.return_value = False
            result = _cleanup_dead_sessions(sessions)

            # Non-standard formats should be kept
            assert "fallback_99999" in result
            assert "invalid" in result
            # But session_* format should be checked
            assert "session_12345" not in result

    def test_cleanup_handles_invalid_pid_conversion(self):
        """Test cleanup when PID can't be converted to int."""
        sessions = {
            "session_invalid": "code-puppy",  # Can't convert to int
            "session_12345": "planning-agent",
        }

        with patch("code_puppy.agents.agent_manager._is_process_alive"):
            result = _cleanup_dead_sessions(sessions)

            # Invalid format should be kept
            assert "session_invalid" in result

    def test_cleanup_empty_dict(self):
        """Test cleanup on empty sessions dict."""
        result = _cleanup_dead_sessions({})
        assert result == {}

    def test_cleanup_calls_is_process_alive(self):
        """Test that cleanup properly calls is_process_alive."""
        sessions = {
            "session_123": "code-puppy",
            "session_456": "planning-agent",
        }

        with patch("code_puppy.agents.agent_manager._is_process_alive") as mock_alive:
            mock_alive.return_value = True
            _cleanup_dead_sessions(sessions)

            # Should be called twice (once per session)
            assert mock_alive.call_count == 2
            mock_alive.assert_any_call(123)
            mock_alive.assert_any_call(456)


class TestSessionCaching:
    """Test session cache management."""

    def test_ensure_session_cache_loaded_loads_once(self):
        """Test that session cache is loaded only once."""
        # Reset module globals
        import code_puppy.agents.agent_manager as am

        am._SESSION_FILE_LOADED = False
        am._SESSION_AGENTS_CACHE.clear()

        with patch("code_puppy.agents.agent_manager._load_session_data") as mock_load:
            mock_load.return_value = {"session_123": "code-puppy"}

            # First call should load
            _ensure_session_cache_loaded()
            assert mock_load.call_count == 1

            # Second call should not load again
            _ensure_session_cache_loaded()
            assert mock_load.call_count == 1

    def test_ensure_session_cache_loaded_updates_cache(self):
        """Test that ensure updates the cache dict."""
        import code_puppy.agents.agent_manager as am

        am._SESSION_FILE_LOADED = False
        am._SESSION_AGENTS_CACHE.clear()

        test_sessions = {
            "session_111": "code-puppy",
            "session_222": "planning-agent",
        }

        with patch("code_puppy.agents.agent_manager._load_session_data") as mock_load:
            mock_load.return_value = test_sessions

            _ensure_session_cache_loaded()

            assert am._SESSION_AGENTS_CACHE == test_sessions

    def test_ensure_session_cache_loaded_marks_as_loaded(self):
        """Test that ensure sets the loaded flag."""
        import code_puppy.agents.agent_manager as am

        am._SESSION_FILE_LOADED = False

        with patch("code_puppy.agents.agent_manager._load_session_data") as mock_load:
            mock_load.return_value = {}

            _ensure_session_cache_loaded()

            assert am._SESSION_FILE_LOADED is True
