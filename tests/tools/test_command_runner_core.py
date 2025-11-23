"""Tests for code_puppy.tools.command_runner core helper functions.

This module tests pure helper functions and global-state utilities from
command_runner.py in isolation, focusing on:
- _truncate_line: string truncation logic
- set_awaiting_user_input: global flag toggling and spinner interaction
- kill_all_running_shell_processes: process cleanup delegation
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import directly from the module file to avoid heavy dependencies in __init__.py
spec = importlib.util.spec_from_file_location(
    "command_runner_module",
    Path(__file__).parent.parent.parent / "code_puppy" / "tools" / "command_runner.py",
)
command_runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command_runner_module)

# Extract the functions and globals we need to test
_truncate_line = command_runner_module._truncate_line
set_awaiting_user_input = command_runner_module.set_awaiting_user_input
kill_all_running_shell_processes = (
    command_runner_module.kill_all_running_shell_processes
)
_register_process = command_runner_module._register_process
_unregister_process = command_runner_module._unregister_process
_kill_process_group = command_runner_module._kill_process_group

# Access to global state (we'll reset these between tests)
_AWAITING_USER_INPUT = command_runner_module._AWAITING_USER_INPUT
_RUNNING_PROCESSES = command_runner_module._RUNNING_PROCESSES
_RUNNING_PROCESSES_LOCK = command_runner_module._RUNNING_PROCESSES_LOCK


class TestTruncateLine:
    """Test the _truncate_line function."""

    def test_truncate_line_shorter_than_max(self):
        """Test that short strings are returned unchanged."""
        short_string = "This is a short string"
        result = _truncate_line(short_string)
        assert result == short_string

    def test_truncate_line_exactly_max_length(self):
        """Test that strings exactly MAX_LINE_LENGTH are returned unchanged."""
        max_length = 256
        exact_string = "x" * max_length
        result = _truncate_line(exact_string)
        assert result == exact_string
        assert len(result) == max_length

    def test_truncate_line_longer_than_max(self):
        """Test that long strings are truncated with suffix."""
        max_length = 256
        long_string = "x" * 300
        result = _truncate_line(long_string)

        expected = "x" * max_length + "... [truncated]"
        assert result == expected
        assert len(result) == max_length + len("... [truncated]")

    def test_truncate_line_just_over_max(self):
        """Test truncation when string is just over the limit."""
        max_length = 256
        just_over_string = "x" * (max_length + 1)
        result = _truncate_line(just_over_string)

        expected = "x" * max_length + "... [truncated]"
        assert result == expected

    def test_truncate_line_empty_string(self):
        """Test that empty string is returned unchanged."""
        result = _truncate_line("")
        assert result == ""

    def test_truncate_line_none_not_allowed(self):
        """Test that None raises appropriate error."""
        with pytest.raises(TypeError):
            _truncate_line(None)  # type: ignore


class TestSetAwaitingUserInput:
    """Test the set_awaiting_user_input function."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Reset global state before and after each test."""
        # Reset before test
        command_runner_module._AWAITING_USER_INPUT = False
        yield
        # Reset after test
        command_runner_module._AWAITING_USER_INPUT = False

    def test_set_awaiting_true_calls_pause_spinners(self, monkeypatch):
        """Test that setting awaiting=True calls pause_all_spinners."""
        # Setup mock spinner functions
        mock_pause = MagicMock()
        mock_resume = MagicMock()

        # Mock the spinner module import to return our mock functions
        mock_spinner_module = MagicMock()
        mock_spinner_module.pause_all_spinners = mock_pause
        mock_spinner_module.resume_all_spinners = mock_resume

        with patch.dict(
            "sys.modules", {"code_puppy.messaging.spinner": mock_spinner_module}
        ):
            set_awaiting_user_input(True)

            assert command_runner_module._AWAITING_USER_INPUT is True
            mock_pause.assert_called_once()
            mock_resume.assert_not_called()

    def test_set_awaiting_false_calls_resume_spinners(self, monkeypatch):
        """Test that setting awaiting=False calls resume_all_spinners."""
        # Setup mock spinner functions
        mock_pause = MagicMock()
        mock_resume = MagicMock()

        # Mock the spinner module import to return our mock functions
        mock_spinner_module = MagicMock()
        mock_spinner_module.pause_all_spinners = mock_pause
        mock_spinner_module.resume_all_spinners = mock_resume

        with patch.dict(
            "sys.modules", {"code_puppy.messaging.spinner": mock_spinner_module}
        ):
            set_awaiting_user_input(False)

            assert command_runner_module._AWAITING_USER_INPUT is False
            mock_pause.assert_not_called()
            mock_resume.assert_called_once()

    def test_set_awaiting_handles_import_error(self, monkeypatch):
        """Test that function handles ImportError gracefully when spinner module not available."""

        # Create a mock that raises ImportError when the import is attempted
        def mock_import(name, *args, **kwargs):
            if name == "code_puppy.messaging.spinner":
                raise ImportError("No module named 'code_puppy.messaging.spinner'")
            # Use original import for everything else
            return __builtins__["__import__"](name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            set_awaiting_user_input(True)
            assert command_runner_module._AWAITING_USER_INPUT is True

            set_awaiting_user_input(False)
            assert command_runner_module._AWAITING_USER_INPUT is False

    def test_set_awaiting_default_true(self, monkeypatch):
        """Test that default parameter is True."""

        # Create a mock that raises ImportError when the import is attempted
        def mock_import(name, *args, **kwargs):
            if name == "code_puppy.messaging.spinner":
                raise ImportError("No module named 'code_puppy.messaging.spinner'")
            # Use original import for everything else
            return __builtins__["__import__"](name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            set_awaiting_user_input()
            assert command_runner_module._AWAITING_USER_INPUT is True


class TestKillAllRunningShellProcesses:
    """Test the kill_all_running_shell_processes function."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self):
        """Reset global state before and after each test."""
        # Clear running processes
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        # Clear running processes after test
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_kill_all_empty_registry(self, monkeypatch):
        """Test that empty registry returns 0 and doesn't call kill helper."""
        mock_kill = MagicMock()
        monkeypatch.setattr(command_runner_module, "_kill_process_group", mock_kill)

        result = kill_all_running_shell_processes()

        assert result == 0
        mock_kill.assert_not_called()

    def test_kill_all_processes_alive_calls_kill_helper(self, monkeypatch):
        """Test that alive processes have kill helper called and are unregistered."""
        # Setup mock kill helper
        mock_kill = MagicMock()
        monkeypatch.setattr(command_runner_module, "_kill_process_group", mock_kill)

        # Create fake processes - one alive, one dead
        alive_process = MagicMock()
        alive_process.poll.return_value = None  # Still running
        alive_process.pid = 123

        dead_process = MagicMock()
        dead_process.poll.return_value = 1  # Already exited
        dead_process.pid = 456

        # Register both processes
        _register_process(alive_process)
        _register_process(dead_process)

        result = kill_all_running_shell_processes()

        # Should have called kill helper only for alive process
        mock_kill.assert_called_once_with(alive_process)

        # Should return count of processes that were signaled (only alive one)
        assert result == 1

        # All processes should be unregistered
        verify_processes_registered_after = len(list(_RUNNING_PROCESSES))
        assert verify_processes_registered_after == 0

    def test_kill_all_handles_kill_helper_exception(self, monkeypatch):
        """Test that exceptions in kill helper don't prevent unregistration."""
        # Setup mock kill helper that raises exception
        mock_kill = MagicMock(side_effect=Exception("Kill failed"))
        monkeypatch.setattr(command_runner_module, "_kill_process_group", mock_kill)

        # Create fake process
        alive_process = MagicMock()
        alive_process.poll.return_value = None
        alive_process.pid = 123

        _register_process(alive_process)

        # The actual function will let the exception bubble up
        with pytest.raises(Exception, match="Kill failed"):
            kill_all_running_shell_processes()

        # Should still attempt kill
        mock_kill.assert_called_once_with(alive_process)

        # Should still be unregistered despite exception (finally block executes)
        verify_processes_registered = len(list(_RUNNING_PROCESSES))
        assert verify_processes_registered == 0

    def test_kill_all_concurrent_access_thread_safety(self, monkeypatch):
        """Test that function handles concurrent access safely with thread lock."""
        import threading

        mock_kill = MagicMock()
        monkeypatch.setattr(command_runner_module, "_kill_process_group", mock_kill)

        # Create multiple fake processes
        processes = []
        for i in range(5):
            proc = MagicMock()
            proc.poll.return_value = None
            proc.pid = 1000 + i
            processes.append(proc)
            _register_process(proc)

        results = []

        def kill_worker():
            try:
                result = kill_all_running_shell_processes()
                results.append(result)
            except Exception:
                # Handle potential exception from race condition
                results.append(0)

        # Start multiple threads calling kill_all simultaneously
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=kill_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All kill calls should be made (though race conditions mean some threads might see empty registry)
        assert mock_kill.call_count <= len(processes)

        # Registry should be empty
        verify_processes_registered = len(list(_RUNNING_PROCESSES))
        assert verify_processes_registered == 0

        # At least one thread should have successfully killed processes
        assert any(r > 0 for r in results) or mock_kill.call_count > 0

    def test_kill_all_tracks_killed_processes(self, monkeypatch):
        """Test that killed PIDs are added to _USER_KILLED_PROCESSES."""
        mock_kill = MagicMock()
        monkeypatch.setattr(command_runner_module, "_kill_process_group", mock_kill)

        # Clear the killed processes set
        command_runner_module._USER_KILLED_PROCESSES.clear()

        # Create fake process
        alive_process = MagicMock()
        alive_process.poll.return_value = None
        alive_process.pid = 123

        _register_process(alive_process)

        kill_all_running_shell_processes()

        # Verify PID was added to killed processes set
        assert alive_process.pid in command_runner_module._USER_KILLED_PROCESSES
