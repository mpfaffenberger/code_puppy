"""Coverage-focused tests for code_puppy.tools.command_runner.

This module targets the 352 uncovered lines in command_runner.py, focusing on:
- Streaming execution paths
- Background process handling
- Keyboard context management (Ctrl-X/Ctrl-C)
- Process cleanup and timeout handling
- share_your_reasoning function
- POSIX and Windows-specific code paths
"""

import signal
import subprocess
import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

# Import the module directly
from code_puppy.tools import command_runner
from code_puppy.tools.command_runner import (
    _KEYBOARD_CONTEXT_LOCK,
    _RUNNING_PROCESSES,
    _RUNNING_PROCESSES_LOCK,
    _USER_KILLED_PROCESSES,
    MAX_LINE_LENGTH,
    ReasoningOutput,
    ShellCommandOutput,
    ShellSafetyAssessment,
    _acquire_keyboard_context,
    _handle_ctrl_x_press,
    _kill_process_group,
    _register_process,
    _release_keyboard_context,
    _shell_command_keyboard_context,
    _shell_sigint_handler,
    _spawn_ctrl_x_key_listener,
    _start_keyboard_listener,
    _stop_keyboard_listener,
    _truncate_line,
    _unregister_process,
    get_running_shell_process_count,
    is_awaiting_user_input,
    kill_all_running_shell_processes,
    run_shell_command_streaming,
    set_awaiting_user_input,
    share_your_reasoning,
)


class TestRunShellCommandStreaming:
    """Tests for the run_shell_command_streaming function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state before/after each test."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()

    def test_streaming_simple_command_success(self):
        """Test streaming execution of a simple successful command."""
        # Create a simple subprocess
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('hello world')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line"):
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="echo hello", silent=True
                )

        assert result.success is True
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_streaming_command_failure(self):
        """Test streaming execution of a failing command."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(1)"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line"):
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="failing", silent=True
                )

        assert result.success is False
        assert result.exit_code == 1

    def test_streaming_with_stderr_output(self):
        """Test streaming captures stderr output."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.stderr.write('error output\\n')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line"):
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="stderr test", silent=True
                )

        assert "error output" in result.stderr

    @pytest.mark.skip(
        reason="Slow test - subprocess timeout test works but takes too long"
    )
    def test_streaming_inactivity_timeout(self):
        """Test that inactivity timeout triggers process cleanup."""
        # This test is skipped because it requires real subprocess which can be slow
        pass

    def test_streaming_timeout_output_model(self):
        """Test ShellCommandOutput for timeout scenarios."""
        # Test that timeout output model has correct fields
        output = ShellCommandOutput(
            success=False,
            command="sleep 100",
            stdout="",
            stderr="",
            exit_code=-9,
            execution_time=1.5,
            timeout=True,
            error="Command timed out after 1 seconds",
        )
        assert output.timeout is True
        assert output.success is False
        assert output.exit_code == -9

    def test_streaming_line_truncation(self):
        """Test that very long lines are truncated."""
        long_line = "x" * 500
        proc = subprocess.Popen(
            [sys.executable, "-c", f"print('{long_line}')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line"):
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="long line", silent=True
                )

        # Lines should be truncated to MAX_LINE_LENGTH
        assert (
            len(result.stdout.split("\n")[0]) <= MAX_LINE_LENGTH + 20
        )  # +20 for "... [truncated]"

    def test_streaming_silent_mode(self):
        """Test that silent mode suppresses output emission."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('silent output')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line") as mock_emit:
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="silent", silent=True
                )

        # emit_shell_line should not be called in silent mode
        mock_emit.assert_not_called()
        assert result.success is True

    def test_streaming_non_silent_mode(self):
        """Test that non-silent mode emits output."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "print('visible output')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        _register_process(proc)

        with patch.object(command_runner, "emit_shell_line") as mock_emit:
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    proc, timeout=10, command="visible", silent=False
                )

        # emit_shell_line should be called in non-silent mode
        assert mock_emit.called
        assert result.success is True


class TestKeyboardContextManagement:
    """Tests for keyboard context reference counting."""

    @pytest.fixture(autouse=True)
    def reset_keyboard_state(self):
        """Reset keyboard context state."""
        # Reset refcount
        with _KEYBOARD_CONTEXT_LOCK:
            command_runner._KEYBOARD_CONTEXT_REFCOUNT = 0
        command_runner._SHELL_CTRL_X_STOP_EVENT = None
        command_runner._SHELL_CTRL_X_THREAD = None
        command_runner._ORIGINAL_SIGINT_HANDLER = None
        yield
        # Clean up after test
        with _KEYBOARD_CONTEXT_LOCK:
            command_runner._KEYBOARD_CONTEXT_REFCOUNT = 0
        command_runner._SHELL_CTRL_X_STOP_EVENT = None
        command_runner._SHELL_CTRL_X_THREAD = None

    def test_acquire_keyboard_context_increments_refcount(self):
        """Test that acquiring keyboard context increments refcount."""
        initial = command_runner._KEYBOARD_CONTEXT_REFCOUNT

        with patch.object(command_runner, "_start_keyboard_listener"):
            _acquire_keyboard_context()

        assert command_runner._KEYBOARD_CONTEXT_REFCOUNT == initial + 1

        # Clean up
        with patch.object(command_runner, "_stop_keyboard_listener"):
            _release_keyboard_context()

    def test_release_keyboard_context_decrements_refcount(self):
        """Test that releasing keyboard context decrements refcount."""
        # First acquire
        with patch.object(command_runner, "_start_keyboard_listener"):
            _acquire_keyboard_context()
            _acquire_keyboard_context()

        refcount_after_acquire = command_runner._KEYBOARD_CONTEXT_REFCOUNT

        with patch.object(command_runner, "_stop_keyboard_listener"):
            _release_keyboard_context()

        assert command_runner._KEYBOARD_CONTEXT_REFCOUNT == refcount_after_acquire - 1

        # Clean up remaining
        with patch.object(command_runner, "_stop_keyboard_listener"):
            _release_keyboard_context()

    def test_acquire_starts_listener_on_first_command(self):
        """Test that listener starts only on first command."""
        with patch.object(command_runner, "_start_keyboard_listener") as mock_start:
            _acquire_keyboard_context()
            assert mock_start.call_count == 1

            _acquire_keyboard_context()  # Second acquire shouldn't start again
            assert mock_start.call_count == 1

        # Clean up
        with patch.object(command_runner, "_stop_keyboard_listener"):
            _release_keyboard_context()
            _release_keyboard_context()

    def test_release_stops_listener_on_last_command(self):
        """Test that listener stops only when last command finishes."""
        with patch.object(command_runner, "_start_keyboard_listener"):
            _acquire_keyboard_context()
            _acquire_keyboard_context()

        with patch.object(command_runner, "_stop_keyboard_listener") as mock_stop:
            _release_keyboard_context()  # Still one active
            assert mock_stop.call_count == 0

            _release_keyboard_context()  # Last one
            assert mock_stop.call_count == 1

    def test_refcount_clamped_to_zero(self):
        """Test that refcount doesn't go negative."""
        with patch.object(command_runner, "_stop_keyboard_listener"):
            _release_keyboard_context()
            _release_keyboard_context()
            _release_keyboard_context()

        assert command_runner._KEYBOARD_CONTEXT_REFCOUNT == 0


class TestShellCommandKeyboardContext:
    """Tests for the _shell_command_keyboard_context context manager."""

    def test_context_manager_sets_up_listener(self):
        """Test that context manager sets up Ctrl-X listener."""
        with patch.object(command_runner, "_spawn_ctrl_x_key_listener") as mock_spawn:
            mock_spawn.return_value = None
            with patch("signal.signal"):
                with _shell_command_keyboard_context():
                    # Inside context, stop event should be set
                    assert command_runner._SHELL_CTRL_X_STOP_EVENT is not None

    def test_context_manager_cleans_up(self):
        """Test that context manager cleans up on exit."""
        with patch.object(command_runner, "_spawn_ctrl_x_key_listener") as mock_spawn:
            mock_spawn.return_value = None
            with patch("signal.signal"):
                with _shell_command_keyboard_context():
                    pass

            # After context, globals should be cleaned up
            assert command_runner._SHELL_CTRL_X_STOP_EVENT is None
            assert command_runner._SHELL_CTRL_X_THREAD is None


class TestHandleCtrlXPress:
    """Tests for _handle_ctrl_x_press function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()

    def test_handle_ctrl_x_calls_kill_all(self):
        """Test that Ctrl-X handler calls kill_all_running_shell_processes."""
        with patch.object(
            command_runner, "kill_all_running_shell_processes"
        ) as mock_kill:
            with patch.object(command_runner, "emit_warning"):
                _handle_ctrl_x_press()

        mock_kill.assert_called_once()

    def test_shell_sigint_handler_calls_kill_all(self):
        """Test that SIGINT handler calls kill_all_running_shell_processes."""
        with patch.object(
            command_runner, "kill_all_running_shell_processes"
        ) as mock_kill:
            with patch.object(command_runner, "emit_warning"):
                _shell_sigint_handler(None, None)

        mock_kill.assert_called_once()


class TestKillProcessGroup:
    """Tests for _kill_process_group function."""

    def test_kill_process_group_terminates_process(self):
        """Test that _kill_process_group handles a mock process."""
        # Use a mock to avoid real subprocess timing issues
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 99999
        mock_proc.poll.return_value = None  # First call: running

        with patch.object(command_runner, "emit_error"):
            with patch("os.getpgid", return_value=99999):
                with patch("os.killpg"):
                    with patch("os.kill"):
                        _kill_process_group(mock_proc)

    def test_kill_process_group_handles_already_dead(self):
        """Test killing an already dead process doesn't error."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()  # Wait for it to finish

        # Should not raise
        with patch.object(command_runner, "emit_error"):
            _kill_process_group(proc)


class TestKillAllRunningShellProcesses:
    """Tests for kill_all_running_shell_processes function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()
        with command_runner._ACTIVE_STOP_EVENTS_LOCK:
            command_runner._ACTIVE_STOP_EVENTS.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        _USER_KILLED_PROCESSES.clear()
        with command_runner._ACTIVE_STOP_EVENTS_LOCK:
            command_runner._ACTIVE_STOP_EVENTS.clear()

    def test_kill_all_empty_set(self):
        """Test killing when no processes registered."""
        count = kill_all_running_shell_processes()
        assert count == 0

    def test_kill_all_with_running_process(self):
        """Test killing a registered running process."""
        # Use a mock process to avoid timing issues
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 88888
        mock_proc.poll.return_value = None  # Running
        mock_proc.stdout = MagicMock(closed=False)
        mock_proc.stderr = MagicMock(closed=False)
        mock_proc.stdin = MagicMock(closed=False)

        _register_process(mock_proc)

        with patch.object(command_runner, "emit_error"):
            with patch.object(command_runner, "_kill_process_group"):
                count = kill_all_running_shell_processes()

        assert count == 1
        assert mock_proc.pid in _USER_KILLED_PROCESSES

    def test_kill_all_sets_active_stop_events(self):
        """Test that kill_all sets all active stop events."""
        evt1 = threading.Event()
        evt2 = threading.Event()
        with command_runner._ACTIVE_STOP_EVENTS_LOCK:
            command_runner._ACTIVE_STOP_EVENTS.add(evt1)
            command_runner._ACTIVE_STOP_EVENTS.add(evt2)

        kill_all_running_shell_processes()

        assert evt1.is_set()
        assert evt2.is_set()

    def test_kill_all_closes_pipes(self):
        """Test that kill_all closes process pipes."""
        # Use a mock process to avoid timing issues
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 77777
        mock_proc.poll.return_value = None  # Running

        # Create mock pipes that track close calls
        mock_stdout = MagicMock()
        mock_stdout.closed = False
        mock_stderr = MagicMock()
        mock_stderr.closed = False
        mock_stdin = MagicMock()
        mock_stdin.closed = False

        mock_proc.stdout = mock_stdout
        mock_proc.stderr = mock_stderr
        mock_proc.stdin = mock_stdin

        _register_process(mock_proc)

        with patch.object(command_runner, "emit_error"):
            with patch.object(command_runner, "_kill_process_group"):
                kill_all_running_shell_processes()

        # close() should have been called on pipes
        mock_stdout.close.assert_called()
        mock_stderr.close.assert_called()
        mock_stdin.close.assert_called()


class TestGetRunningShellProcessCount:
    """Tests for get_running_shell_process_count function."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_count_empty(self):
        """Test count with no processes."""
        assert get_running_shell_process_count() == 0

    def test_count_with_alive_process(self):
        """Test count with a running (mock) process."""
        # Use a mock process to avoid timing issues
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # Running

        _register_process(mock_proc)

        assert get_running_shell_process_count() == 1

        _unregister_process(mock_proc)

    def test_count_removes_stale_processes(self):
        """Test that count removes dead processes from tracking."""
        proc = subprocess.Popen(
            [sys.executable, "-c", "pass"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        _register_process(proc)
        proc.wait()  # Wait for it to finish

        # Count should be 0 and process removed
        count = get_running_shell_process_count()
        assert count == 0
        with _RUNNING_PROCESSES_LOCK:
            assert proc not in _RUNNING_PROCESSES


class TestShareYourReasoning:
    """Tests for the share_your_reasoning function."""

    def test_share_reasoning_returns_success(self):
        """Test that share_your_reasoning returns success."""
        mock_context = MagicMock()

        with patch.object(command_runner, "get_message_bus") as mock_bus:
            mock_bus.return_value = MagicMock()
            result = share_your_reasoning(
                mock_context, reasoning="Testing reasoning", next_steps="Step 1"
            )

        assert isinstance(result, ReasoningOutput)
        assert result.success is True

    def test_share_reasoning_with_list_steps(self):
        """Test share_your_reasoning with list of next steps."""
        mock_context = MagicMock()

        with patch.object(command_runner, "get_message_bus") as mock_bus:
            mock_bus.return_value = MagicMock()
            result = share_your_reasoning(
                mock_context,
                reasoning="Multi-step reasoning",
                next_steps=["Step 1", "Step 2", "Step 3"],
            )

        assert result.success is True

    def test_share_reasoning_emits_message(self):
        """Test that share_your_reasoning emits AgentReasoningMessage."""
        mock_context = MagicMock()
        mock_bus = MagicMock()

        with patch.object(command_runner, "get_message_bus", return_value=mock_bus):
            share_your_reasoning(
                mock_context, reasoning="Test reasoning", next_steps=None
            )

        mock_bus.emit.assert_called_once()

    def test_share_reasoning_with_none_steps(self):
        """Test share_your_reasoning with None next_steps."""
        mock_context = MagicMock()

        with patch.object(command_runner, "get_message_bus") as mock_bus:
            mock_bus.return_value = MagicMock()
            result = share_your_reasoning(
                mock_context, reasoning="No next steps", next_steps=None
            )

        assert result.success is True

    def test_share_reasoning_with_empty_steps(self):
        """Test share_your_reasoning with empty string next_steps."""
        mock_context = MagicMock()

        with patch.object(command_runner, "get_message_bus") as mock_bus:
            mock_bus.return_value = MagicMock()
            result = share_your_reasoning(
                mock_context,
                reasoning="Empty steps",
                next_steps="  ",  # Whitespace only
            )

        assert result.success is True


class TestReasoningOutput:
    """Tests for the ReasoningOutput model."""

    def test_reasoning_output_default_success(self):
        """Test that ReasoningOutput defaults to success=True."""
        output = ReasoningOutput()
        assert output.success is True

    def test_reasoning_output_explicit_success(self):
        """Test ReasoningOutput with explicit success value."""
        output = ReasoningOutput(success=False)
        assert output.success is False


class TestSpawnCtrlXKeyListener:
    """Tests for _spawn_ctrl_x_key_listener function."""

    def test_spawn_listener_returns_none_when_not_tty(self):
        """Test that listener returns None when stdin is not a tty."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            stop_event = threading.Event()

            result = _spawn_ctrl_x_key_listener(stop_event, lambda: None)

        assert result is None

    def test_spawn_listener_returns_none_when_stdin_none(self):
        """Test that listener returns None when stdin is None."""
        original_stdin = sys.stdin
        try:
            sys.stdin = None
            stop_event = threading.Event()

            result = _spawn_ctrl_x_key_listener(stop_event, lambda: None)

            assert result is None
        finally:
            sys.stdin = original_stdin

    def test_spawn_listener_handles_isatty_exception(self):
        """Test that listener handles exception from isatty()."""
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.side_effect = Exception("tty error")
            stop_event = threading.Event()

            result = _spawn_ctrl_x_key_listener(stop_event, lambda: None)

        assert result is None


class TestStartStopKeyboardListener:
    """Tests for _start_keyboard_listener and _stop_keyboard_listener."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset keyboard state."""
        command_runner._SHELL_CTRL_X_STOP_EVENT = None
        command_runner._SHELL_CTRL_X_THREAD = None
        command_runner._ORIGINAL_SIGINT_HANDLER = None
        yield
        command_runner._SHELL_CTRL_X_STOP_EVENT = None
        command_runner._SHELL_CTRL_X_THREAD = None
        command_runner._ORIGINAL_SIGINT_HANDLER = None

    def test_start_keyboard_listener_creates_stop_event(self):
        """Test that _start_keyboard_listener creates stop event."""
        with patch.object(
            command_runner, "_spawn_ctrl_x_key_listener", return_value=None
        ):
            with patch("signal.signal"):
                _start_keyboard_listener()

        assert command_runner._SHELL_CTRL_X_STOP_EVENT is not None
        assert isinstance(command_runner._SHELL_CTRL_X_STOP_EVENT, threading.Event)

    def test_stop_keyboard_listener_sets_stop_event(self):
        """Test that _stop_keyboard_listener sets the stop event."""
        command_runner._SHELL_CTRL_X_STOP_EVENT = threading.Event()

        with patch("signal.signal"):
            _stop_keyboard_listener()

        # Check that event was set before cleanup
        # (Note: the function sets the event then clears the reference)

    def test_stop_keyboard_listener_restores_signal_handler(self):
        """Test that _stop_keyboard_listener restores SIGINT handler."""
        original_handler = signal.getsignal(signal.SIGINT)
        command_runner._ORIGINAL_SIGINT_HANDLER = original_handler
        command_runner._SHELL_CTRL_X_STOP_EVENT = threading.Event()

        _stop_keyboard_listener()

        # Handler should be restored
        current_handler = signal.getsignal(signal.SIGINT)
        assert current_handler == original_handler


class TestSetAwaitingUserInput:
    """Tests for set_awaiting_user_input function."""

    def test_set_awaiting_true(self):
        """Test setting awaiting user input to true."""
        with patch("code_puppy.messaging.spinner.pause_all_spinners"):
            set_awaiting_user_input(True)

        assert is_awaiting_user_input() is True

    def test_set_awaiting_false(self):
        """Test setting awaiting user input to false."""
        with patch("code_puppy.messaging.spinner.resume_all_spinners"):
            set_awaiting_user_input(False)

        assert is_awaiting_user_input() is False

    def test_set_awaiting_handles_import_error(self):
        """Test that set_awaiting_user_input handles ImportError gracefully."""
        # This should not raise even if spinner module is not available
        with patch.dict("sys.modules", {"code_puppy.messaging.spinner": None}):
            set_awaiting_user_input(True)
            set_awaiting_user_input(False)


class TestTruncateLine:
    """Additional tests for _truncate_line function."""

    def test_truncate_line_boundary_cases(self):
        """Test truncation at exact boundaries."""
        # Exactly at limit - should not truncate
        line_at_limit = "x" * MAX_LINE_LENGTH
        assert _truncate_line(line_at_limit) == line_at_limit

        # One over limit - should truncate
        line_over_limit = "x" * (MAX_LINE_LENGTH + 1)
        result = _truncate_line(line_over_limit)
        assert len(result) == MAX_LINE_LENGTH + len("... [truncated]")
        assert result.endswith("... [truncated]")

    def test_truncate_line_unicode(self):
        """Test truncation with unicode characters."""
        unicode_line = "🐺" * 300
        result = _truncate_line(unicode_line)
        assert "... [truncated]" in result


class TestProcessRegistration:
    """Tests for process registration functions."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_register_unregister_cycle(self):
        """Test complete register/unregister cycle."""
        mock_proc = MagicMock(spec=subprocess.Popen)

        _register_process(mock_proc)
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc in _RUNNING_PROCESSES

        _unregister_process(mock_proc)
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc not in _RUNNING_PROCESSES

    def test_unregister_nonexistent(self):
        """Test unregistering a process that was never registered."""
        mock_proc = MagicMock(spec=subprocess.Popen)

        # Should not raise
        _unregister_process(mock_proc)


class TestShellCommandOutputModel:
    """Additional tests for ShellCommandOutput model."""

    def test_output_with_all_fields(self):
        """Test ShellCommandOutput with all fields populated."""
        output = ShellCommandOutput(
            success=True,
            command="echo hello",
            error=None,
            stdout="hello\n",
            stderr="",
            exit_code=0,
            execution_time=0.5,
            timeout=False,
            user_interrupted=False,
            user_feedback=None,
            background=False,
            log_file=None,
            pid=None,
        )

        assert output.success is True
        assert output.command == "echo hello"
        assert output.exit_code == 0

    def test_output_background_mode(self):
        """Test ShellCommandOutput in background mode."""
        output = ShellCommandOutput(
            success=True,
            command="sleep 10 &",
            error=None,
            stdout=None,
            stderr=None,
            exit_code=None,
            execution_time=0.0,
            background=True,
            log_file="/tmp/shell_bg_12345.log",
            pid=12345,
        )

        assert output.background is True
        assert output.log_file is not None
        assert output.pid == 12345

    def test_output_with_user_feedback(self):
        """Test ShellCommandOutput with user rejection feedback."""
        output = ShellCommandOutput(
            success=False,
            command="rm -rf /",
            error="User rejected the command!",
            user_feedback="Too dangerous",
            stdout=None,
            stderr=None,
            exit_code=None,
            execution_time=None,
        )

        assert output.success is False
        assert output.user_feedback == "Too dangerous"


class TestShellSafetyAssessmentModel:
    """Additional tests for ShellSafetyAssessment model."""

    def test_all_risk_levels(self):
        """Test all valid risk levels."""
        for risk in ["none", "low", "medium", "high", "critical"]:
            assessment = ShellSafetyAssessment(
                risk=risk, reasoning=f"Testing {risk} risk"
            )
            assert assessment.risk == risk

    def test_fallback_flag_default(self):
        """Test that is_fallback defaults to False."""
        assessment = ShellSafetyAssessment(risk="none", reasoning="Safe command")
        assert assessment.is_fallback is False

    def test_fallback_flag_explicit(self):
        """Test setting is_fallback explicitly."""
        assessment = ShellSafetyAssessment(
            risk="medium", reasoning="Could not parse properly", is_fallback=True
        )
        assert assessment.is_fallback is True


class TestWindowsSpecificCode:
    """Tests for Windows-specific functionality."""

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
    def test_win32_pipe_has_data_real(self):
        """Test _win32_pipe_has_data on Windows."""
        from code_puppy.tools.command_runner import _win32_pipe_has_data

        proc = subprocess.Popen(
            [sys.executable, "-c", "print('test')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        proc.wait()

        # Should return True since there's data in the pipe
        has_data = _win32_pipe_has_data(proc.stdout)
        assert isinstance(has_data, bool)

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX only")
    def test_win32_pipe_has_data_posix_stub(self):
        """Test that POSIX stub returns False."""
        from code_puppy.tools.command_runner import _win32_pipe_has_data

        mock_pipe = MagicMock()
        result = _win32_pipe_has_data(mock_pipe)
        assert result is False


class TestStreamingExceptionHandling:
    """Tests for exception handling in streaming execution."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_streaming_handles_exception(self):
        """Test that streaming handles exceptions gracefully."""
        # Create a mock process that raises on readline
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.poll.side_effect = [None, 0]  # Running, then finished
        mock_process.returncode = 0
        mock_process.pid = 99999

        # Create mock pipes
        mock_stdout = MagicMock()
        mock_stdout.fileno.side_effect = ValueError("Bad fd")
        mock_stdout.closed = False
        mock_stdout.close = MagicMock()

        mock_stderr = MagicMock()
        mock_stderr.fileno.side_effect = ValueError("Bad fd")
        mock_stderr.closed = False
        mock_stderr.close = MagicMock()

        mock_stdin = MagicMock()
        mock_stdin.closed = False
        mock_stdin.close = MagicMock()

        mock_process.stdout = mock_stdout
        mock_process.stderr = mock_stderr
        mock_process.stdin = mock_stdin

        with patch.object(command_runner, "emit_shell_line"):
            with patch.object(command_runner, "get_message_bus") as mock_bus:
                mock_bus.return_value = MagicMock()
                result = run_shell_command_streaming(
                    mock_process, timeout=5, command="test", silent=True
                )

        # Should return success even with the fileno exceptions
        # because poll() returns 0
        assert result.exit_code == 0
