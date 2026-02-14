"""Tests for PTYSession.is_alive() in pty_manager.py."""

from unittest.mock import MagicMock, patch

from code_puppy.api.pty_manager import PTYSession


class TestPTYSessionIsAlive:
    """Tests for the PTYSession.is_alive() method."""

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    @patch("os.waitpid", return_value=(0, 0))
    def test_is_alive_returns_true_when_process_running(
        self, mock_waitpid: MagicMock
    ) -> None:
        """is_alive() returns True when os.waitpid reports process still running."""
        session = PTYSession(session_id="test-1", pid=12345)
        assert session.is_alive() is True
        mock_waitpid.assert_called_once_with(12345, 1)  # os.WNOHANG == 1

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    @patch("os.waitpid", return_value=(12345, 9))
    def test_is_alive_returns_false_when_process_exited(
        self, mock_waitpid: MagicMock
    ) -> None:
        """is_alive() returns False when os.waitpid reports process exited."""
        session = PTYSession(session_id="test-2", pid=12345)
        assert session.is_alive() is False
        mock_waitpid.assert_called_once_with(12345, 1)

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    @patch("os.waitpid", side_effect=ChildProcessError("No child processes"))
    def test_is_alive_returns_false_on_child_process_error(
        self, mock_waitpid: MagicMock
    ) -> None:
        """is_alive() returns False when the child process was already reaped."""
        session = PTYSession(session_id="test-3", pid=12345)
        assert session.is_alive() is False
        mock_waitpid.assert_called_once_with(12345, 1)

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", False)
    def test_is_alive_returns_false_when_pid_is_none(self) -> None:
        """is_alive() returns False when the session has no pid."""
        session = PTYSession(session_id="test-4", pid=None)
        assert session.is_alive() is False

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    def test_is_alive_windows_with_winpty(self) -> None:
        """is_alive() delegates to winpty_process.isalive() on Windows."""
        mock_winpty = MagicMock()
        mock_winpty.isalive.return_value = True

        session = PTYSession(session_id="test-5", winpty_process=mock_winpty)
        assert session.is_alive() is True
        mock_winpty.isalive.assert_called_once()

        # Also test when winpty reports not alive
        mock_winpty.isalive.return_value = False
        assert session.is_alive() is False

    @patch("code_puppy.api.pty_manager.IS_WINDOWS", True)
    def test_is_alive_windows_without_winpty_process(self) -> None:
        """is_alive() returns False on Windows when winpty_process is None."""
        session = PTYSession(session_id="test-6", winpty_process=None)
        assert session.is_alive() is False
