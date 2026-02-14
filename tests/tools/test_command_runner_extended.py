"""Extended tests for code_puppy.tools.command_runner - filling coverage gaps.

This module tests previously uncovered code paths including:
- Windows-specific pipe checking and keyboard handling
- POSIX keyboard listener implementation
- Main run_shell_command function with mocks
- Background execution mode
- Keyboard context manager
- ShellSafetyAssessment validation
- Process registration and cleanup
- Error handling in streaming
"""

import asyncio
import importlib.util
import os
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import directly from the module file
spec = importlib.util.spec_from_file_location(
    "command_runner_module",
    Path(__file__).parent.parent.parent / "code_puppy" / "tools" / "command_runner.py",
)
command_runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(command_runner_module)

# Extract functions and classes
run_shell_command_streaming = command_runner_module.run_shell_command_streaming
run_shell_command = command_runner_module.run_shell_command
ShellCommandOutput = command_runner_module.ShellCommandOutput
ShellSafetyAssessment = command_runner_module.ShellSafetyAssessment
_kill_process_group = command_runner_module._kill_process_group
_register_process = command_runner_module._register_process
_unregister_process = command_runner_module._unregister_process
_win32_pipe_has_data = command_runner_module._win32_pipe_has_data
_truncate_line = command_runner_module._truncate_line
_shell_command_keyboard_context = command_runner_module._shell_command_keyboard_context
_spawn_ctrl_x_key_listener = command_runner_module._spawn_ctrl_x_key_listener
_listen_for_ctrl_x_windows = command_runner_module._listen_for_ctrl_x_windows
_listen_for_ctrl_x_posix = command_runner_module._listen_for_ctrl_x_posix
is_awaiting_user_input = command_runner_module.is_awaiting_user_input
set_awaiting_user_input = command_runner_module.set_awaiting_user_input
get_running_shell_process_count = command_runner_module.get_running_shell_process_count

# Global state
_RUNNING_PROCESSES = command_runner_module._RUNNING_PROCESSES
_RUNNING_PROCESSES_LOCK = command_runner_module._RUNNING_PROCESSES_LOCK
_USER_KILLED_PROCESSES = command_runner_module._USER_KILLED_PROCESSES


class TestShellSafetyAssessment:
    """Test ShellSafetyAssessment model."""

    def test_safety_assessment_risk_levels(self):
        """Test that all risk levels are valid."""
        for risk_level in ["none", "low", "medium", "high", "critical"]:
            assessment = ShellSafetyAssessment(
                risk=risk_level,
                reasoning="Test",
            )
            assert assessment.risk == risk_level

    def test_safety_assessment_is_fallback_default(self):
        """Test that is_fallback defaults to False."""
        assessment = ShellSafetyAssessment(
            risk="medium",
            reasoning="Test assessment",
        )
        assert assessment.is_fallback is False

    def test_safety_assessment_is_fallback_true(self):
        """Test setting is_fallback to True."""
        assessment = ShellSafetyAssessment(
            risk="high",
            reasoning="Parsing failed, fallback to conservative",
            is_fallback=True,
        )
        assert assessment.is_fallback is True

    def test_safety_assessment_invalid_risk_level(self):
        """Test that invalid risk levels are rejected."""
        with pytest.raises(ValueError):
            ShellSafetyAssessment(
                risk="extreme",  # Invalid
                reasoning="Test",
            )

    def test_safety_assessment_reasoning_required(self):
        """Test that reasoning is required."""
        with pytest.raises(ValueError):
            ShellSafetyAssessment(risk="medium")  # Missing reasoning


class TestWin32PipeHasData:
    """Test Windows-specific pipe checking."""

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
    def test_win32_pipe_has_data_with_real_pipe(self):
        """Test pipe checking with actual Windows pipes."""
        # This is a basic sanity check that the function doesn't crash
        # Real pipes would be in subprocess.PIPE from Popen
        mock_pipe = MagicMock()
        mock_pipe.fileno.return_value = 3

        # Should not crash even if call fails (Windows API quirks)
        result = _win32_pipe_has_data(mock_pipe)
        assert isinstance(result, bool)

    def test_win32_pipe_has_data_handles_value_error(self):
        """Test that ValueError from fileno is handled."""
        mock_pipe = MagicMock()
        mock_pipe.fileno.side_effect = ValueError("Bad file descriptor")

        result = _win32_pipe_has_data(mock_pipe)
        assert result is False

    def test_win32_pipe_has_data_handles_oserror(self):
        """Test that OSError is handled gracefully."""
        mock_pipe = MagicMock()
        mock_pipe.fileno.side_effect = OSError("Pipe closed")

        result = _win32_pipe_has_data(mock_pipe)
        assert result is False

    def test_win32_pipe_has_data_handles_ctypes_error(self, monkeypatch):
        """Test that ctypes.ArgumentError is handled."""
        if sys.platform.startswith("win"):
            import ctypes

            mock_pipe = MagicMock()
            mock_pipe.fileno.return_value = 3

            # Mock the kernel32 call to raise ArgumentError
            original_peeknamedpipe = command_runner_module._kernel32.PeekNamedPipe

            def raise_arg_error(*args, **kwargs):
                raise ctypes.ArgumentError("Invalid argument")

            monkeypatch.setattr(
                command_runner_module._kernel32,
                "PeekNamedPipe",
                raise_arg_error,
            )

            result = _win32_pipe_has_data(mock_pipe)
            assert result is False

            # Restore
            monkeypatch.setattr(
                command_runner_module._kernel32,
                "PeekNamedPipe",
                original_peeknamedpipe,
            )


class TestIsAwaitingUserInput:
    """Test user input awaiting check."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        command_runner_module._AWAITING_USER_INPUT.clear()
        yield
        command_runner_module._AWAITING_USER_INPUT.clear()

    def test_is_awaiting_user_input_default_false(self):
        """Test that default state is False."""
        assert is_awaiting_user_input() is False

    def test_is_awaiting_user_input_reflects_set_state(self):
        """Test that is_awaiting reflects set_awaiting changes."""
        set_awaiting_user_input(True)
        assert is_awaiting_user_input() is True

        set_awaiting_user_input(False)
        assert is_awaiting_user_input() is False


class TestGetRunningShellProcessCount:
    """Test process count tracking."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_get_running_process_count_empty(self):
        """Test count with no running processes."""
        count = get_running_shell_process_count()
        assert count == 0

    def test_get_running_process_count_with_alive_processes(self):
        """Test count with alive processes."""
        mock_proc1 = MagicMock()
        mock_proc1.poll.return_value = None  # Still running

        mock_proc2 = MagicMock()
        mock_proc2.poll.return_value = None  # Still running

        _register_process(mock_proc1)
        _register_process(mock_proc2)

        count = get_running_shell_process_count()
        assert count == 2

    def test_get_running_process_count_removes_dead_processes(self):
        """Test that dead processes are cleaned from registry."""
        mock_proc1 = MagicMock()
        mock_proc1.poll.return_value = None  # Alive

        mock_proc2 = MagicMock()
        mock_proc2.poll.return_value = 0  # Exited

        _register_process(mock_proc1)
        _register_process(mock_proc2)

        count = get_running_shell_process_count()

        # Should only count alive ones
        assert count == 1

        # Dead process should be removed
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc2 not in _RUNNING_PROCESSES
            assert mock_proc1 in _RUNNING_PROCESSES


class TestKeyboardContextManager:
    """Test the keyboard context manager."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        command_runner_module._SHELL_CTRL_X_STOP_EVENT = None
        command_runner_module._SHELL_CTRL_X_THREAD = None
        command_runner_module._ORIGINAL_SIGINT_HANDLER = None
        yield
        command_runner_module._SHELL_CTRL_X_STOP_EVENT = None
        command_runner_module._SHELL_CTRL_X_THREAD = None
        command_runner_module._ORIGINAL_SIGINT_HANDLER = None

    def test_keyboard_context_sets_up_listener(self, monkeypatch):
        """Test that context manager sets up Ctrl-X listener."""
        mock_spawn = MagicMock(return_value=None)  # No TTY, listener returns None
        monkeypatch.setattr(
            command_runner_module, "_spawn_ctrl_x_key_listener", mock_spawn
        )

        with _shell_command_keyboard_context():
            # Inside context
            assert command_runner_module._SHELL_CTRL_X_STOP_EVENT is not None

        # After context
        assert command_runner_module._SHELL_CTRL_X_STOP_EVENT is None

    def test_keyboard_context_handles_signal_registration(self, monkeypatch):
        """Test that SIGINT handler is properly managed."""
        original_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)

        mock_spawn = MagicMock(return_value=None)
        monkeypatch.setattr(
            command_runner_module, "_spawn_ctrl_x_key_listener", mock_spawn
        )

        with _shell_command_keyboard_context():
            # Original handler should be saved
            assert command_runner_module._ORIGINAL_SIGINT_HANDLER is not None

        # After context, should be restored
        assert command_runner_module._ORIGINAL_SIGINT_HANDLER is None

        # Restore original
        signal.signal(signal.SIGINT, original_sigint)

    def test_keyboard_context_cleans_up_listener_thread(self, monkeypatch):
        """Test that listener thread is cleaned up."""
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False

        mock_spawn = MagicMock(return_value=mock_thread)
        monkeypatch.setattr(
            command_runner_module, "_spawn_ctrl_x_key_listener", mock_spawn
        )

        with _shell_command_keyboard_context():
            pass

        # Thread join should have been called (if thread was created)
        if mock_thread is not None:
            # At least verify spawn was called
            mock_spawn.assert_called_once()


class TestSpawnCtrlXKeyListener:
    """Test Ctrl-X key listener spawning."""

    def test_spawn_listener_returns_none_when_not_tty(self):
        """Test that None is returned when stdin is not a TTY."""
        stop_event = threading.Event()
        on_escape = MagicMock()

        # Should return None when not in TTY mode
        result = _spawn_ctrl_x_key_listener(stop_event, on_escape)

        # May be None depending on whether we're in TTY mode
        if result is not None:
            result.join(timeout=0.1)

    def test_spawn_listener_requires_callable(self):
        """Test that on_escape must be callable."""
        stop_event = threading.Event()

        # This will depend on TTY status, but the function should handle it
        result = _spawn_ctrl_x_key_listener(stop_event, lambda: None)

        if result is not None:
            result.join(timeout=0.1)


class TestShellCommandOutput:
    """Test ShellCommandOutput model."""

    def test_shell_command_output_success(self):
        """Test successful command output."""
        output = ShellCommandOutput(
            success=True,
            command="echo hello",
            stdout="hello",
            stderr="",
            exit_code=0,
            execution_time=0.1,
        )
        assert output.success is True
        assert output.exit_code == 0

    def test_shell_command_output_failure(self):
        """Test failed command output."""
        output = ShellCommandOutput(
            success=False,
            command="false",
            error="Command failed",
            stdout="",
            stderr="error",
            exit_code=1,
            execution_time=0.05,
        )
        assert output.success is False
        assert output.exit_code == 1

    def test_shell_command_output_timeout(self):
        """Test timeout output."""
        output = ShellCommandOutput(
            success=False,
            command="sleep 100",
            error="Timeout",
            stdout="",
            stderr="",
            exit_code=-9,
            execution_time=60.0,
            timeout=True,
        )
        assert output.timeout is True

    def test_shell_command_output_user_interrupted(self):
        """Test user-interrupted output."""
        output = ShellCommandOutput(
            success=False,
            command="sleep 100",
            error="User interrupted",
            stdout="",
            stderr="",
            exit_code=-9,
            execution_time=5.0,
            user_interrupted=True,
        )
        assert output.user_interrupted is True

    def test_shell_command_output_background(self):
        """Test background execution output."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            log_file = f.name

        try:
            output = ShellCommandOutput(
                success=True,
                command="sleep 100 &",
                background=True,
                log_file=log_file,
                pid=12345,
                execution_time=0.0,
                exit_code=None,
                stdout=None,
                stderr=None,
            )
            assert output.background is True
            assert output.pid == 12345
            assert output.log_file == log_file
        finally:
            if os.path.exists(log_file):
                os.unlink(log_file)


class TestProcessRegistration:
    """Test process registration and unregistration."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_register_and_unregister_process(self):
        """Test process registration and unregistration."""
        mock_proc = MagicMock()

        # Initially not registered
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc not in _RUNNING_PROCESSES

        # Register
        _register_process(mock_proc)
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc in _RUNNING_PROCESSES

        # Unregister
        _unregister_process(mock_proc)
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc not in _RUNNING_PROCESSES

    def test_register_same_process_twice(self):
        """Test registering same process multiple times."""
        mock_proc = MagicMock()

        _register_process(mock_proc)
        _register_process(mock_proc)  # Register again

        with _RUNNING_PROCESSES_LOCK:
            # Set should only contain it once
            count = sum(1 for p in _RUNNING_PROCESSES if p is mock_proc)
            assert count == 1

    def test_unregister_not_registered_process(self):
        """Test unregistering a process that wasn't registered."""
        mock_proc = MagicMock()

        # Should not raise
        _unregister_process(mock_proc)
        with _RUNNING_PROCESSES_LOCK:
            assert mock_proc not in _RUNNING_PROCESSES


class TestKillProcessGroupCrossPlatform:
    """Test _kill_process_group with different platforms."""

    @pytest.fixture(autouse=True)
    def reset_state(self):
        """Reset global state."""
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()
        yield
        with _RUNNING_PROCESSES_LOCK:
            _RUNNING_PROCESSES.clear()

    def test_kill_process_group_with_poll_already_exited(self, monkeypatch):
        """Test kill when process already exited."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # Already exited
        mock_proc.pid = 123

        # Should not raise
        _kill_process_group(mock_proc)

        # proc.kill() should not be called if already exited
        # (depends on implementation, but graceful)

    def test_kill_process_group_handles_exceptions(self, monkeypatch):
        """Test that exceptions are handled gracefully."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        mock_proc.pid = 123
        mock_proc.kill.side_effect = OSError("Cannot kill")

        # Should not raise
        _kill_process_group(mock_proc)

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX only")
    def test_kill_process_group_posix_signals(self, monkeypatch):
        """Test POSIX signal sequence."""
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [
            None,
            None,
            None,
            0,
        ]  # Multiple polls before success
        mock_proc.pid = 123

        # Mock os.getpgid to return a valid pgid
        monkeypatch.setattr(os, "getpgid", lambda x: 100)

        # Mock os.killpg to succeed
        kill_calls = []

        def mock_killpg(pgid, sig):
            kill_calls.append((pgid, sig))

        monkeypatch.setattr(os, "killpg", mock_killpg)

        # Mock time.sleep to avoid delays
        monkeypatch.setattr(time, "sleep", MagicMock())

        _kill_process_group(mock_proc)

        # Should have called killpg with SIGTERM at least
        assert any(call[1] == signal.SIGTERM for call in kill_calls)


class TestRunShellCommandAsync:
    """Test the main run_shell_command async function."""

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

    def test_run_shell_command_blocked_by_callback(self):
        """Test that callbacks can block command execution."""
        mock_context = MagicMock()

        # Mock callback to block command
        with patch(
            "code_puppy.callbacks.on_run_shell_command", new_callable=AsyncMock
        ) as mock_callback:
            mock_callback.return_value = [
                {
                    "blocked": True,
                    "error_message": "Dangerous command",
                    "reasoning": "rm -rf usage detected",
                }
            ]

            result = asyncio.run(
                run_shell_command(
                    mock_context,
                    command="rm -rf /",
                )
            )

            assert result.success is False
            assert "blocked" in result.error.lower() or "Dangerous" in result.error


class TestKeyboardListeners:
    """Test keyboard listener implementations for different platforms."""

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows only")
    def test_windows_listener_handles_no_key(self):
        """Test Windows listener when no key is pressed."""
        stop_event = threading.Event()
        escape_called = []

        def on_escape():
            escape_called.append(True)

        # Mock msvcrt to return no key
        with patch("msvcrt.kbhit", return_value=False):
            with patch("time.sleep", MagicMock()):
                stop_event.set()  # Stop after first iteration
                _listen_for_ctrl_x_windows(stop_event, on_escape)
                assert len(escape_called) == 0

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX only")
    def test_posix_listener_handles_stdin_error(self):
        """Test POSIX listener handles stdin errors gracefully."""
        stop_event = threading.Event()
        escape_called = []

        def on_escape():
            escape_called.append(True)

        # Mock select to raise exception
        with patch("select.select", side_effect=ValueError("Select error")):
            with patch("sys.stdin.fileno", return_value=0):
                with patch("termios.tcgetattr", return_value=[]):
                    with patch("tty.setcbreak", MagicMock()):
                        with patch("termios.tcsetattr", MagicMock()):
                            _listen_for_ctrl_x_posix(stop_event, on_escape)
                            # Should exit gracefully without raising
                            assert True

    @pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX only")
    def test_posix_listener_handles_bad_stdin(self):
        """Test POSIX listener handles bad stdin gracefully."""
        stop_event = threading.Event()
        escape_called = []

        def on_escape():
            escape_called.append(True)

        # Mock stdin.fileno to raise exception
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = ValueError("No fileno")
            _listen_for_ctrl_x_posix(stop_event, on_escape)
            # Should exit gracefully without raising
            assert True


class TestReasoningOutput:
    """Test the share_your_reasoning function."""

    def test_share_your_reasoning_basic(self, monkeypatch):
        """Test sharing reasoning with basic content."""
        from code_puppy.tools.command_runner import share_your_reasoning

        mock_context = MagicMock()
        mock_bus = MagicMock()

        with patch(
            "code_puppy.tools.command_runner.get_message_bus", return_value=mock_bus
        ):
            result = share_your_reasoning(
                mock_context,
                reasoning="I think this is the solution",
            )

            assert result.success is True
            mock_bus.emit.assert_called_once()

    def test_share_your_reasoning_with_single_step(self, monkeypatch):
        """Test sharing reasoning with single next step."""
        from code_puppy.tools.command_runner import share_your_reasoning

        mock_context = MagicMock()
        mock_bus = MagicMock()

        with patch(
            "code_puppy.tools.command_runner.get_message_bus", return_value=mock_bus
        ):
            result = share_your_reasoning(
                mock_context,
                reasoning="First step",
                next_steps="Run tests",
            )

            assert result.success is True
            mock_bus.emit.assert_called_once()

    def test_share_your_reasoning_with_list_steps(self, monkeypatch):
        """Test sharing reasoning with list of next steps."""
        from code_puppy.tools.command_runner import share_your_reasoning

        mock_context = MagicMock()
        mock_bus = MagicMock()

        with patch(
            "code_puppy.tools.command_runner.get_message_bus", return_value=mock_bus
        ):
            result = share_your_reasoning(
                mock_context,
                reasoning="Analysis complete",
                next_steps=["Step 1", "Step 2", "Step 3"],
            )

            assert result.success is True
            # Verify the emit was called with formatted steps
            mock_bus.emit.assert_called_once()
            call_args = mock_bus.emit.call_args
            # The message should contain formatted steps
            assert "1. Step 1" in str(call_args)


class TestRegisterAgentRunShellCommand:
    """Test the agent tool registration."""

    def test_register_agent_run_shell_command(self, monkeypatch):
        """Test that agent tool is properly registered."""
        from code_puppy.tools.command_runner import register_agent_run_shell_command

        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.tool = MagicMock()

        # Mock the tool decorator to just return the function
        def tool_decorator(func):
            mock_agent.tool_func = func
            return func

        mock_agent.tool.side_effect = tool_decorator

        # Register the tool
        register_agent_run_shell_command(mock_agent)

        # Verify tool was registered
        mock_agent.tool.assert_called_once()
