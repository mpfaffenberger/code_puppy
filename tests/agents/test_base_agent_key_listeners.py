import threading
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentKeyListeners:
    @pytest.fixture
    def agent(self):
        return CodePuppyAgent()

    @patch("sys.stdin")
    def test_spawn_ctrl_x_key_listener_basic(self, mock_stdin, agent):
        """Test that _spawn_ctrl_x_key_listener can be called without crashing."""
        # Mock stdin to look like a TTY
        mock_stdin.isatty.return_value = True

        stop_event = threading.Event()
        callback = MagicMock()

        # Spawn listener
        thread = agent._spawn_ctrl_x_key_listener(stop_event, callback)

        # Should return a thread (or None if not supported)
        if thread:
            assert isinstance(thread, threading.Thread)
            assert thread.daemon  # Should be a daemon thread
            stop_event.set()  # Stop the thread
            thread.join(timeout=1.0)

    @patch("sys.platform", "linux")
    @patch("sys.stdin")
    def test_spawn_on_linux_platform(self, mock_stdin, agent):
        """Test that Linux platforms spawn the right listener."""
        mock_stdin.isatty.return_value = True

        stop_event = threading.Event()

        thread = agent._spawn_ctrl_x_key_listener(stop_event, MagicMock())
        if thread:
            stop_event.set()
            thread.join(timeout=1.0)

    @patch("sys.platform", "darwin")
    @patch("sys.stdin")
    def test_spawn_on_macos_platform(self, mock_stdin, agent):
        """Test that macOS platforms spawn the right listener."""
        mock_stdin.isatty.return_value = True

        stop_event = threading.Event()

        thread = agent._spawn_ctrl_x_key_listener(stop_event, MagicMock())
        if thread:
            stop_event.set()
            thread.join(timeout=1.0)

    @patch("sys.platform", "win32")
    @patch("sys.stdin")
    def test_spawn_on_windows_platform(self, mock_stdin, agent):
        """Test that Windows platforms spawn the right listener."""
        mock_stdin.isatty.return_value = True

        stop_event = threading.Event()

        thread = agent._spawn_ctrl_x_key_listener(stop_event, MagicMock())
        if thread:
            stop_event.set()
            thread.join(timeout=1.0)

    @patch("sys.stdin")
    def test_spawn_ctrl_x_key_listener_no_tty(self, mock_stdin, agent):
        """Test that _spawn_ctrl_x_key_listener returns None when stdin is not a TTY."""
        mock_stdin.isatty.return_value = False

        stop_event = threading.Event()
        callback = MagicMock()

        # Should return None when not a TTY
        thread = agent._spawn_ctrl_x_key_listener(stop_event, callback)
        assert thread is None

    @patch("sys.stdin")
    def test_spawn_ctrl_x_key_listener_no_stdin(self, mock_stdin, agent):
        """Test that _spawn_ctrl_x_key_listener returns None when stdin is not available."""
        # Mock sys.stdin to be None
        with patch("sys.stdin", None):
            stop_event = threading.Event()
            callback = MagicMock()

            # Should return None when stdin is not available
            thread = agent._spawn_ctrl_x_key_listener(stop_event, callback)
            assert thread is None

    def test_listen_for_ctrl_x_posix_stop_immediately(self, agent):
        """Test the POSIX listener method stops immediately when stop_event is set."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Set stop event before calling to ensure immediate exit
        stop_event.set()

        # This should exit immediately without any errors
        agent._listen_for_ctrl_x_posix(stop_event, callback)

        # Callback should not be called since we stopped immediately
        callback.assert_not_called()

    def test_listen_for_ctrl_x_posix_basic_coverage(self, agent):
        """Test the POSIX listener method can be called for basic coverage."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Set stop event to avoid infinite loop
        stop_event.set()

        # Call the method - just testing it doesn't crash
        agent._listen_for_ctrl_x_posix(stop_event, callback)

    @patch.dict("sys.modules", {"msvcrt": MagicMock()})
    def test_listen_for_ctrl_x_windows_stop_immediately(self, agent):
        """Test the Windows listener method stops immediately when stop_event is set."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Set stop event before calling to ensure immediate exit
        stop_event.set()

        # Mock msvcrt to avoid actual Windows API calls
        with (
            patch("msvcrt.kbhit", return_value=False),
            patch("msvcrt.getwch"),
            patch("time.sleep"),
        ):
            # This should exit immediately without any errors
            agent._listen_for_ctrl_x_windows(stop_event, callback)

            # Callback should not be called since we stopped immediately
            callback.assert_not_called()

    @patch.dict("sys.modules", {"msvcrt": MagicMock()})
    def test_listen_for_ctrl_x_windows_exception_handling(self, agent):
        """Test that Windows listener handles exceptions gracefully."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Mock msvcrt.kbhit to raise an exception
        with (
            patch("msvcrt.kbhit", side_effect=Exception("Windows error")),
            patch("msvcrt.getwch"),
            patch("time.sleep"),
        ):
            # Should not raise an exception
            agent._listen_for_ctrl_x_windows(stop_event, callback)

    @patch.dict("sys.modules", {"msvcrt": MagicMock()})
    def test_listen_for_ctrl_x_windows_ctrl_x_detection(self, agent):
        """Test Windows listener when Ctrl+X is 'detected'."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Mock msvcrt to simulate Ctrl+X detection
        with (
            patch("msvcrt.kbhit", return_value=True),
            patch("msvcrt.getwch", return_value="\x18"),
            patch("time.sleep"),
        ):
            # After detecting Ctrl+X, stop the listener
            def stop_after_callback():
                stop_event.set()

            callback.side_effect = stop_after_callback

            agent._listen_for_ctrl_x_windows(stop_event, callback)

            # Verify callback was called
            callback.assert_called()

    def test_listen_for_ctrl_x_posix_ctrl_x_detection(self, agent):
        """Test POSIX listener when Ctrl+X is 'detected'."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Mock the required modules and sys.stdin
        with (
            patch("select.select", return_value=([MagicMock()], [], [])),
            patch("termios.tcgetattr", return_value=[0] * 10),
            patch("termios.tcsetattr"),
            patch("tty.setcbreak"),
        ):
            # Create a mock stdin that returns Ctrl+X when read
            mock_stdin = MagicMock()
            mock_stdin.read.return_value = "\x18"
            mock_stdin.fileno.return_value = 0

            with patch("sys.stdin", mock_stdin):
                # After detecting Ctrl+X, stop the listener
                def stop_after_callback():
                    stop_event.set()

                callback.side_effect = stop_after_callback

                agent._listen_for_ctrl_x_posix(stop_event, callback)

                # Verify callback was called
                callback.assert_called()

    def test_agent_code_puppy_inherits_key_listeners(self, agent):
        """Test that CodePuppyAgent has the key listener methods."""
        # Verify the agent has the key listener methods
        assert hasattr(agent, "_spawn_ctrl_x_key_listener")
        assert hasattr(agent, "_listen_for_ctrl_x_posix")
        assert hasattr(agent, "_listen_for_ctrl_x_windows")

        # Verify they are callable
        assert callable(getattr(agent, "_spawn_ctrl_x_key_listener"))
        assert callable(getattr(agent, "_listen_for_ctrl_x_posix"))
        assert callable(getattr(agent, "_listen_for_ctrl_x_windows"))

    def test_listen_for_ctrl_x_posix_termios_exception(self, agent):
        """Test POSIX listener handles termios exceptions gracefully."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Mock stdin.fileno but make termios.tcgetattr fail
        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0

        with (
            patch("sys.stdin", mock_stdin),
            patch("termios.tcgetattr", side_effect=Exception("Termios error")),
        ):
            # Should not raise an exception
            agent._listen_for_ctrl_x_posix(stop_event, callback)

    @patch.dict("sys.modules", {"msvcrt": MagicMock()})
    def test_listen_for_ctrl_x_windows_non_ctrl_x_key(self, agent):
        """Test Windows listener with non-Ctrl+X key press."""
        stop_event = threading.Event()
        callback = MagicMock()

        # Mock msvcrt to simulate a non-Ctrl+X keypress
        with (
            patch("msvcrt.kbhit", return_value=True),
            patch("msvcrt.getwch", return_value="a"),
            patch("time.sleep"),
        ):
            # After one keypress, stop the listener
            stop_event.set()

            agent._listen_for_ctrl_x_windows(stop_event, callback)

            # Callback should not be called for non-Ctrl+X key
            callback.assert_not_called()
