import ctypes
import os
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from contextlib import contextmanager
from typing import Callable, Literal, Optional, Set

from pydantic import BaseModel
from pydantic_ai import RunContext
from rich.text import Text

from code_puppy.messaging import (  # Structured messaging types
    AgentReasoningMessage,
    ShellOutputMessage,
    ShellStartMessage,
    emit_error,
    emit_info,
    emit_shell_line,
    emit_warning,
    get_message_bus,
)
from code_puppy.tools.common import generate_group_id, get_user_approval_async

# Maximum line length for shell command output to prevent massive token usage
# This helps avoid exceeding model context limits when commands produce very long lines
MAX_LINE_LENGTH = 256


def _truncate_line(line: str) -> str:
    """Truncate a line to MAX_LINE_LENGTH if it exceeds the limit."""
    if len(line) > MAX_LINE_LENGTH:
        return line[:MAX_LINE_LENGTH] + "... [truncated]"
    return line


# Windows-specific: Check if pipe has data available without blocking
# This is needed because select() doesn't work on pipes on Windows
if sys.platform.startswith("win"):
    import msvcrt

    # Load kernel32 for PeekNamedPipe
    _kernel32 = ctypes.windll.kernel32

    def _win32_pipe_has_data(pipe) -> bool:
        """Check if a Windows pipe has data available without blocking.

        Uses PeekNamedPipe from kernel32.dll to check if there's data
        in the pipe buffer without actually reading it.

        Args:
            pipe: A file object with a fileno() method (e.g., process.stdout)

        Returns:
            True if data is available, False otherwise (including on error)
        """
        try:
            # Get the Windows handle from the file descriptor
            handle = msvcrt.get_osfhandle(pipe.fileno())

            # PeekNamedPipe parameters:
            # - hNamedPipe: handle to the pipe
            # - lpBuffer: buffer to receive data (NULL = don't read)
            # - nBufferSize: size of buffer (0 = don't read)
            # - lpBytesRead: receives bytes read (NULL)
            # - lpTotalBytesAvail: receives total bytes available
            # - lpBytesLeftThisMessage: receives bytes left (NULL)
            bytes_available = ctypes.c_ulong(0)

            result = _kernel32.PeekNamedPipe(
                handle,
                None,  # Don't read data
                0,  # Buffer size 0
                None,  # Don't care about bytes read
                ctypes.byref(bytes_available),  # Get bytes available
                None,  # Don't care about bytes left in message
            )

            if result:
                return bytes_available.value > 0
            return False
        except (ValueError, OSError, ctypes.ArgumentError):
            # Handle closed, invalid, or other errors
            return False
else:
    # POSIX stub - not used, but keeps the code clean
    def _win32_pipe_has_data(pipe) -> bool:
        return False


_AWAITING_USER_INPUT = False

_CONFIRMATION_LOCK = threading.Lock()

# Track running shell processes so we can kill them on Ctrl-C from the UI
_RUNNING_PROCESSES: Set[subprocess.Popen] = set()
_RUNNING_PROCESSES_LOCK = threading.Lock()
_USER_KILLED_PROCESSES = set()

# Global state for shell command keyboard handling
_SHELL_CTRL_X_STOP_EVENT: Optional[threading.Event] = None
_SHELL_CTRL_X_THREAD: Optional[threading.Thread] = None
_ORIGINAL_SIGINT_HANDLER = None

# Stop event to signal reader threads to terminate
_READER_STOP_EVENT: Optional[threading.Event] = None


def _register_process(proc: subprocess.Popen) -> None:
    with _RUNNING_PROCESSES_LOCK:
        _RUNNING_PROCESSES.add(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    with _RUNNING_PROCESSES_LOCK:
        _RUNNING_PROCESSES.discard(proc)


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Attempt to aggressively terminate a process and its group.

    Cross-platform best-effort. On POSIX, uses process groups. On Windows, tries taskkill with /T flag for tree kill.
    """
    try:
        if sys.platform.startswith("win"):
            # On Windows, use taskkill to kill the process tree
            # /F = force, /T = kill tree (children), /PID = process ID
            try:
                import subprocess as sp

                # Try taskkill first - more reliable on Windows
                sp.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True,
                    timeout=2,
                    check=False,
                )
                time.sleep(0.3)
            except Exception:
                # Fallback to Python's built-in methods
                pass

            # Double-check it's dead, if not use proc.kill()
            if proc.poll() is None:
                try:
                    proc.kill()
                    time.sleep(0.3)
                except Exception:
                    pass
            return

        # POSIX
        pid = proc.pid
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            time.sleep(1.0)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGINT)
                time.sleep(0.6)
            if proc.poll() is None:
                os.killpg(pgid, signal.SIGKILL)
                time.sleep(0.5)
        except (OSError, ProcessLookupError):
            # Fall back to direct kill of the process
            try:
                if proc.poll() is None:
                    proc.kill()
            except (OSError, ProcessLookupError):
                pass

        if proc.poll() is None:
            # Last ditch attempt; may be unkillable zombie
            try:
                for _ in range(3):
                    os.kill(proc.pid, signal.SIGKILL)
                    time.sleep(0.2)
                    if proc.poll() is not None:
                        break
            except Exception:
                pass
    except Exception as e:
        emit_error(f"Kill process error: {e}")


def kill_all_running_shell_processes() -> int:
    """Kill all currently tracked running shell processes and stop reader threads.

    Returns the number of processes signaled.
    """
    global _READER_STOP_EVENT

    # Signal reader threads to stop
    if _READER_STOP_EVENT:
        _READER_STOP_EVENT.set()

    procs: list[subprocess.Popen]
    with _RUNNING_PROCESSES_LOCK:
        procs = list(_RUNNING_PROCESSES)
    count = 0
    for p in procs:
        try:
            # Close pipes first to unblock readline()
            try:
                if p.stdout and not p.stdout.closed:
                    p.stdout.close()
                if p.stderr and not p.stderr.closed:
                    p.stderr.close()
                if p.stdin and not p.stdin.closed:
                    p.stdin.close()
            except (OSError, ValueError):
                pass

            if p.poll() is None:
                _kill_process_group(p)
                count += 1
                _USER_KILLED_PROCESSES.add(p.pid)
        finally:
            _unregister_process(p)
    return count


def get_running_shell_process_count() -> int:
    """Return the number of currently-active shell processes being tracked."""
    with _RUNNING_PROCESSES_LOCK:
        alive = 0
        stale: Set[subprocess.Popen] = set()
        for proc in _RUNNING_PROCESSES:
            if proc.poll() is None:
                alive += 1
            else:
                stale.add(proc)
        for proc in stale:
            _RUNNING_PROCESSES.discard(proc)
    return alive


# Function to check if user input is awaited
def is_awaiting_user_input():
    """Check if command_runner is waiting for user input."""
    global _AWAITING_USER_INPUT
    return _AWAITING_USER_INPUT


# Function to set user input flag
def set_awaiting_user_input(awaiting=True):
    """Set the flag indicating if user input is awaited."""
    global _AWAITING_USER_INPUT
    _AWAITING_USER_INPUT = awaiting

    # When we're setting this flag, also pause/resume all active spinners
    if awaiting:
        # Pause all active spinners (imported here to avoid circular imports)
        try:
            from code_puppy.messaging.spinner import pause_all_spinners

            pause_all_spinners()
        except ImportError:
            pass  # Spinner functionality not available
    else:
        # Resume all active spinners
        try:
            from code_puppy.messaging.spinner import resume_all_spinners

            resume_all_spinners()
        except ImportError:
            pass  # Spinner functionality not available


class ShellCommandOutput(BaseModel):
    success: bool
    command: str | None
    error: str | None = ""
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    execution_time: float | None
    timeout: bool | None = False
    user_interrupted: bool | None = False
    user_feedback: str | None = None  # User feedback when command is rejected
    background: bool = False  # True if command was run in background mode
    log_file: str | None = None  # Path to temp log file for background commands
    pid: int | None = None  # Process ID for background commands


class ShellSafetyAssessment(BaseModel):
    """Assessment of shell command safety risks.

    This model represents the structured output from the shell safety checker agent.
    It provides a risk level classification and reasoning for that assessment.

    Attributes:
        risk: Risk level classification. Can be one of:
              'none' (completely safe), 'low' (minimal risk), 'medium' (moderate risk),
              'high' (significant risk), 'critical' (severe/destructive risk).
        reasoning: Brief explanation (max 1-2 sentences) of why this risk level
                   was assigned. Should be concise and actionable.
        is_fallback: Whether this assessment is a fallback due to parsing failure.
                     Fallback assessments are not cached to allow retry with fresh LLM responses.
    """

    risk: Literal["none", "low", "medium", "high", "critical"]
    reasoning: str
    is_fallback: bool = False


def _listen_for_ctrl_x_windows(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
) -> None:
    """Windows-specific Ctrl-X listener."""
    import msvcrt
    import time

    while not stop_event.is_set():
        try:
            if msvcrt.kbhit():
                try:
                    # Try to read a character
                    # Note: msvcrt.getwch() returns unicode string on Windows
                    key = msvcrt.getwch()

                    # Check for Ctrl+X (\x18) or other interrupt keys
                    # Some terminals might not send \x18, so also check for 'x' with modifier
                    if key == "\x18":  # Standard Ctrl+X
                        try:
                            on_escape()
                        except Exception:
                            emit_warning(
                                "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                            )
                    # Note: In some Windows terminals, Ctrl+X might not be captured
                    # Users can use Ctrl+C as alternative, which is handled by signal handler
                except (OSError, ValueError):
                    # kbhit/getwch can fail on Windows in certain terminal states
                    # Just continue, user can use Ctrl+C
                    pass
        except Exception:
            # Be silent about Windows listener errors - they're common
            # User can use Ctrl+C as fallback
            pass
        time.sleep(0.05)


def _listen_for_ctrl_x_posix(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
) -> None:
    """POSIX-specific Ctrl-X listener."""
    import select
    import sys
    import termios
    import tty

    stdin = sys.stdin
    try:
        fd = stdin.fileno()
    except (AttributeError, ValueError, OSError):
        return
    try:
        original_attrs = termios.tcgetattr(fd)
    except Exception:
        return

    try:
        tty.setcbreak(fd)
        while not stop_event.is_set():
            try:
                read_ready, _, _ = select.select([stdin], [], [], 0.05)
            except Exception:
                break
            if not read_ready:
                continue
            data = stdin.read(1)
            if not data:
                break
            if data == "\x18":  # Ctrl+X
                try:
                    on_escape()
                except Exception:
                    emit_warning(
                        "Ctrl+X handler raised unexpectedly; Ctrl+C still works."
                    )
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)


def _spawn_ctrl_x_key_listener(
    stop_event: threading.Event,
    on_escape: Callable[[], None],
) -> Optional[threading.Thread]:
    """Start a Ctrl+X key listener thread for CLI sessions."""
    try:
        import sys
    except ImportError:
        return None

    stdin = getattr(sys, "stdin", None)
    if stdin is None or not hasattr(stdin, "isatty"):
        return None
    try:
        if not stdin.isatty():
            return None
    except Exception:
        return None

    def listener() -> None:
        try:
            if sys.platform.startswith("win"):
                _listen_for_ctrl_x_windows(stop_event, on_escape)
            else:
                _listen_for_ctrl_x_posix(stop_event, on_escape)
        except Exception:
            emit_warning(
                "Ctrl+X key listener stopped unexpectedly; press Ctrl+C to cancel."
            )

    thread = threading.Thread(
        target=listener, name="shell-command-ctrl-x-listener", daemon=True
    )
    thread.start()
    return thread


@contextmanager
def _shell_command_keyboard_context():
    """Context manager to handle keyboard interrupts during shell command execution.

    This context manager:
    1. Disables the agent's Ctrl-C handler (so it doesn't cancel the agent)
    2. Enables a Ctrl-X listener to kill the running shell process
    3. Restores the original Ctrl-C handler when done
    """
    global _SHELL_CTRL_X_STOP_EVENT, _SHELL_CTRL_X_THREAD, _ORIGINAL_SIGINT_HANDLER

    # Handler for Ctrl-X: kill all running shell processes
    def handle_ctrl_x_press() -> None:
        emit_warning("\n🛑 Ctrl-X detected! Interrupting shell command...")
        kill_all_running_shell_processes()

    # Handler for Ctrl-C during shell execution: just kill the shell process, don't cancel agent
    def shell_sigint_handler(_sig, _frame):
        """During shell execution, Ctrl-C kills the shell but doesn't cancel the agent."""
        emit_warning("\n🛑 Ctrl-C detected! Interrupting shell command...")
        kill_all_running_shell_processes()

    # Set up Ctrl-X listener
    _SHELL_CTRL_X_STOP_EVENT = threading.Event()
    _SHELL_CTRL_X_THREAD = _spawn_ctrl_x_key_listener(
        _SHELL_CTRL_X_STOP_EVENT,
        handle_ctrl_x_press,
    )

    # Replace SIGINT handler temporarily
    try:
        _ORIGINAL_SIGINT_HANDLER = signal.signal(signal.SIGINT, shell_sigint_handler)
    except (ValueError, OSError):
        # Can't set signal handler (maybe not main thread?)
        _ORIGINAL_SIGINT_HANDLER = None

    try:
        yield
    finally:
        # Clean up: stop Ctrl-X listener
        if _SHELL_CTRL_X_STOP_EVENT:
            _SHELL_CTRL_X_STOP_EVENT.set()

        if _SHELL_CTRL_X_THREAD and _SHELL_CTRL_X_THREAD.is_alive():
            try:
                _SHELL_CTRL_X_THREAD.join(timeout=0.2)
            except Exception:
                pass

        # Restore original SIGINT handler
        if _ORIGINAL_SIGINT_HANDLER is not None:
            try:
                signal.signal(signal.SIGINT, _ORIGINAL_SIGINT_HANDLER)
            except (ValueError, OSError):
                pass

        # Clean up global state
        _SHELL_CTRL_X_STOP_EVENT = None
        _SHELL_CTRL_X_THREAD = None
        _ORIGINAL_SIGINT_HANDLER = None


def run_shell_command_streaming(
    process: subprocess.Popen,
    timeout: int = 60,
    command: str = "",
    group_id: str = None,
):
    global _READER_STOP_EVENT
    _READER_STOP_EVENT = threading.Event()

    start_time = time.time()
    last_output_time = [start_time]

    ABSOLUTE_TIMEOUT_SECONDS = 270

    stdout_lines = []
    stderr_lines = []

    stdout_thread = None
    stderr_thread = None

    def read_stdout():
        try:
            fd = process.stdout.fileno()
        except (ValueError, OSError):
            return

        try:
            while True:
                # Check stop event first
                if _READER_STOP_EVENT and _READER_STOP_EVENT.is_set():
                    break

                # Use select to check if data is available (with timeout)
                if sys.platform.startswith("win"):
                    # Windows doesn't support select on pipes
                    # Use PeekNamedPipe via _win32_pipe_has_data() to check
                    # if data is available without blocking
                    try:
                        if _win32_pipe_has_data(process.stdout):
                            line = process.stdout.readline()
                            if not line:  # EOF
                                break
                            line = line.rstrip("\n\r")
                            line = _truncate_line(line)
                            stdout_lines.append(line)
                            emit_shell_line(line, stream="stdout")
                            last_output_time[0] = time.time()
                        else:
                            # No data available, check if process has exited
                            if process.poll() is not None:
                                # Process exited, do one final drain
                                try:
                                    remaining = process.stdout.read()
                                    if remaining:
                                        for line in remaining.splitlines():
                                            line = _truncate_line(line)
                                            stdout_lines.append(line)
                                            emit_shell_line(line, stream="stdout")
                                except (ValueError, OSError):
                                    pass
                                break
                            # Sleep briefly to avoid busy-waiting (100ms like POSIX)
                            time.sleep(0.1)
                    except (ValueError, OSError):
                        break
                else:
                    # POSIX: use select with timeout
                    try:
                        ready, _, _ = select.select([fd], [], [], 0.1)  # 100ms timeout
                    except (ValueError, OSError, select.error):
                        break

                    if ready:
                        line = process.stdout.readline()
                        if not line:  # EOF
                            break
                        line = line.rstrip("\n\r")
                        line = _truncate_line(line)
                        stdout_lines.append(line)
                        emit_shell_line(line, stream="stdout")
                        last_output_time[0] = time.time()
                    # If not ready, loop continues and checks stop event again
        except (ValueError, OSError):
            pass
        except Exception:
            pass

    def read_stderr():
        try:
            fd = process.stderr.fileno()
        except (ValueError, OSError):
            return

        try:
            while True:
                # Check stop event first
                if _READER_STOP_EVENT and _READER_STOP_EVENT.is_set():
                    break

                if sys.platform.startswith("win"):
                    # Windows doesn't support select on pipes
                    # Use PeekNamedPipe via _win32_pipe_has_data() to check
                    # if data is available without blocking
                    try:
                        if _win32_pipe_has_data(process.stderr):
                            line = process.stderr.readline()
                            if not line:  # EOF
                                break
                            line = line.rstrip("\n\r")
                            line = _truncate_line(line)
                            stderr_lines.append(line)
                            emit_shell_line(line, stream="stderr")
                            last_output_time[0] = time.time()
                        else:
                            # No data available, check if process has exited
                            if process.poll() is not None:
                                # Process exited, do one final drain
                                try:
                                    remaining = process.stderr.read()
                                    if remaining:
                                        for line in remaining.splitlines():
                                            line = _truncate_line(line)
                                            stderr_lines.append(line)
                                            emit_shell_line(line, stream="stderr")
                                except (ValueError, OSError):
                                    pass
                                break
                            # Sleep briefly to avoid busy-waiting (100ms like POSIX)
                            time.sleep(0.1)
                    except (ValueError, OSError):
                        break
                else:
                    try:
                        ready, _, _ = select.select([fd], [], [], 0.1)
                    except (ValueError, OSError, select.error):
                        break

                    if ready:
                        line = process.stderr.readline()
                        if not line:  # EOF
                            break
                        line = line.rstrip("\n\r")
                        line = _truncate_line(line)
                        stderr_lines.append(line)
                        emit_shell_line(line, stream="stderr")
                        last_output_time[0] = time.time()
        except (ValueError, OSError):
            pass
        except Exception:
            pass

    def cleanup_process_and_threads(timeout_type: str = "unknown"):
        nonlocal stdout_thread, stderr_thread

        def nuclear_kill(proc):
            _kill_process_group(proc)

        try:
            # Signal reader threads to stop first
            if _READER_STOP_EVENT:
                _READER_STOP_EVENT.set()

            if process.poll() is None:
                nuclear_kill(process)

            try:
                if process.stdout and not process.stdout.closed:
                    process.stdout.close()
                if process.stderr and not process.stderr.closed:
                    process.stderr.close()
                if process.stdin and not process.stdin.closed:
                    process.stdin.close()
            except (OSError, ValueError):
                pass

            # Unregister once we're done cleaning up
            _unregister_process(process)

            if stdout_thread and stdout_thread.is_alive():
                stdout_thread.join(timeout=3)
                if stdout_thread.is_alive():
                    emit_warning(
                        f"stdout reader thread failed to terminate after {timeout_type} timeout",
                        message_group=group_id,
                    )

            if stderr_thread and stderr_thread.is_alive():
                stderr_thread.join(timeout=3)
                if stderr_thread.is_alive():
                    emit_warning(
                        f"stderr reader thread failed to terminate after {timeout_type} timeout",
                        message_group=group_id,
                    )

        except Exception as e:
            emit_warning(f"Error during process cleanup: {e}", message_group=group_id)

        execution_time = time.time() - start_time
        return ShellCommandOutput(
            **{
                "success": False,
                "command": command,
                "stdout": "\n".join(stdout_lines[-256:]),
                "stderr": "\n".join(stderr_lines[-256:]),
                "exit_code": -9,
                "execution_time": execution_time,
                "timeout": True,
                "error": f"Command timed out after {timeout} seconds",
            }
        )

    try:
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        while process.poll() is None:
            current_time = time.time()

            if current_time - start_time > ABSOLUTE_TIMEOUT_SECONDS:
                emit_error(
                    "Process killed: absolute timeout reached",
                    message_group=group_id,
                )
                return cleanup_process_and_threads("absolute")

            if current_time - last_output_time[0] > timeout:
                emit_error(
                    "Process killed: inactivity timeout reached",
                    message_group=group_id,
                )
                return cleanup_process_and_threads("inactivity")

            time.sleep(0.1)

        if stdout_thread:
            stdout_thread.join(timeout=5)
        if stderr_thread:
            stderr_thread.join(timeout=5)

        exit_code = process.returncode
        execution_time = time.time() - start_time

        try:
            if process.stdout and not process.stdout.closed:
                process.stdout.close()
            if process.stderr and not process.stderr.closed:
                process.stderr.close()
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
        except (OSError, ValueError):
            pass

        _unregister_process(process)

        # Apply line length limits to stdout/stderr before returning
        truncated_stdout = [_truncate_line(line) for line in stdout_lines[-256:]]
        truncated_stderr = [_truncate_line(line) for line in stderr_lines[-256:]]

        # Emit structured ShellOutputMessage for the UI
        shell_output_msg = ShellOutputMessage(
            command=command,
            stdout="\n".join(truncated_stdout),
            stderr="\n".join(truncated_stderr),
            exit_code=exit_code,
            duration_seconds=execution_time,
        )
        get_message_bus().emit(shell_output_msg)

        # Reset the stop event now that we're done
        _READER_STOP_EVENT = None

        if exit_code != 0:
            time.sleep(1)
            return ShellCommandOutput(
                success=False,
                command=command,
                error="""The process didn't exit cleanly! If the user_interrupted flag is true,
                please stop all execution and ask the user for clarification!""",
                stdout="\n".join(truncated_stdout),
                stderr="\n".join(truncated_stderr),
                exit_code=exit_code,
                execution_time=execution_time,
                timeout=False,
                user_interrupted=process.pid in _USER_KILLED_PROCESSES,
            )

        return ShellCommandOutput(
            success=True,
            command=command,
            stdout="\n".join(truncated_stdout),
            stderr="\n".join(truncated_stderr),
            exit_code=exit_code,
            execution_time=execution_time,
            timeout=False,
        )

    except Exception as e:
        # Reset the stop event on exception too
        _READER_STOP_EVENT = None
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error during streaming execution: {str(e)}",
            stdout="\n".join(stdout_lines[-1000:]),
            stderr="\n".join(stderr_lines[-1000:]),
            exit_code=-1,
            timeout=False,
        )


async def run_shell_command(
    context: RunContext,
    command: str,
    cwd: str = None,
    timeout: int = 60,
    background: bool = False,
) -> ShellCommandOutput:
    command_displayed = False
    start_time = time.time()

    # Generate unique group_id for this command execution
    group_id = generate_group_id("shell_command", command)

    # Invoke safety check callbacks (only active in yolo_mode)
    # This allows plugins to intercept and assess commands before execution
    from code_puppy.callbacks import on_run_shell_command

    callback_results = await on_run_shell_command(context, command, cwd, timeout)

    # Check if any callback blocked the command
    # Callbacks can return None (allow) or a dict with blocked=True (reject)
    for result in callback_results:
        if result and isinstance(result, dict) and result.get("blocked"):
            return ShellCommandOutput(
                success=False,
                command=command,
                error=result.get("error_message", "Command blocked by safety check"),
                user_feedback=result.get("reasoning", ""),
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=None,
            )

    # Handle background execution - runs command detached and returns immediately
    # This happens BEFORE user confirmation since we don't wait for the command
    if background:
        # Create temp log file for output
        log_file = tempfile.NamedTemporaryFile(
            mode="w",
            prefix="shell_bg_",
            suffix=".log",
            delete=False,  # Keep file so agent can read it later
        )

        try:
            # Platform-specific process detachment
            if sys.platform.startswith("win"):
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=cwd,
                    creationflags=creationflags,
                )
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    cwd=cwd,
                    start_new_session=True,  # Fully detach on POSIX
                )

            log_file.close()  # Close our handle, process keeps writing

            # Emit UI messages so user sees what happened
            bus = get_message_bus()
            bus.emit(
                ShellStartMessage(
                    command=command,
                    cwd=cwd,
                    timeout=0,  # No timeout for background processes
                )
            )

            # Emit info about background execution
            emit_info(
                f"🚀 Background process started (PID: {process.pid}) - no timeout, runs until complete"
            )
            emit_info(f"📄 Output logging to: {log_file.name}")

            # Return immediately - don't wait, don't block
            return ShellCommandOutput(
                success=True,
                command=command,
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=0.0,
                background=True,
                log_file=log_file.name,
                pid=process.pid,
            )
        except Exception as e:
            log_file.close()
            # Emit error message so user sees what happened
            emit_error(f"❌ Failed to start background process: {e}")
            return ShellCommandOutput(
                success=False,
                command=command,
                error=f"Failed to start background process: {e}",
                stdout=None,
                stderr=None,
                exit_code=None,
                execution_time=None,
                background=True,
            )

    # Rest of the existing function continues...
    if not command or not command.strip():
        emit_error("Command cannot be empty", message_group=group_id)
        return ShellCommandOutput(
            **{"success": False, "error": "Command cannot be empty"}
        )

    from code_puppy.config import get_yolo_mode

    yolo_mode = get_yolo_mode()

    confirmation_lock_acquired = False

    # Only ask for confirmation if we're in an interactive TTY and not in yolo mode.
    if not yolo_mode and sys.stdin.isatty():
        confirmation_lock_acquired = _CONFIRMATION_LOCK.acquire(blocking=False)
        if not confirmation_lock_acquired:
            return ShellCommandOutput(
                success=False,
                command=command,
                error="Another command is currently awaiting confirmation",
            )

        command_displayed = True

        # Get puppy name for personalized messages
        from code_puppy.config import get_puppy_name

        puppy_name = get_puppy_name().title()

        # Build panel content
        panel_content = Text()
        panel_content.append("⚡ Requesting permission to run:\n", style="bold yellow")
        panel_content.append("$ ", style="bold green")
        panel_content.append(command, style="bold white")

        if cwd:
            panel_content.append("\n\n", style="")
            panel_content.append("📂 Working directory: ", style="dim")
            panel_content.append(cwd, style="dim cyan")

        # Use the common approval function (async version)
        confirmed, user_feedback = await get_user_approval_async(
            title="Shell Command",
            content=panel_content,
            preview=None,
            border_style="dim white",
            puppy_name=puppy_name,
        )

        # Release lock after approval
        if confirmation_lock_acquired:
            _CONFIRMATION_LOCK.release()

        if not confirmed:
            if user_feedback:
                result = ShellCommandOutput(
                    success=False,
                    command=command,
                    error=f"USER REJECTED: {user_feedback}",
                    user_feedback=user_feedback,
                    stdout=None,
                    stderr=None,
                    exit_code=None,
                    execution_time=None,
                )
            else:
                result = ShellCommandOutput(
                    success=False,
                    command=command,
                    error="User rejected the command!",
                    stdout=None,
                    stderr=None,
                    exit_code=None,
                    execution_time=None,
                )
            return result
    else:
        start_time = time.time()

    # Now that approval is done, activate the Ctrl-X listener and disable agent Ctrl-C
    with _shell_command_keyboard_context():
        # Emit structured ShellStartMessage for the UI
        bus = get_message_bus()
        bus.emit(
            ShellStartMessage(
                command=command,
                cwd=cwd,
                timeout=timeout,
            )
        )

        try:
            creationflags = 0
            preexec_fn = None
            if sys.platform.startswith("win"):
                try:
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
                except Exception:
                    creationflags = 0
            else:
                preexec_fn = os.setsid if hasattr(os, "setsid") else None

            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=cwd,
                bufsize=1,
                universal_newlines=True,
                preexec_fn=preexec_fn,
                creationflags=creationflags,
            )
            _register_process(process)
            try:
                return run_shell_command_streaming(
                    process, timeout=timeout, command=command, group_id=group_id
                )
            finally:
                # Ensure unregistration in case streaming returned early or raised
                _unregister_process(process)
        except Exception as e:
            emit_error(traceback.format_exc(), message_group=group_id)
            if "stdout" not in locals():
                stdout = None
            if "stderr" not in locals():
                stderr = None

            # Apply line length limits to stdout/stderr if they exist
            truncated_stdout = None
            if stdout:
                stdout_lines = stdout.split("\n")
                truncated_stdout = "\n".join(
                    [_truncate_line(line) for line in stdout_lines[-256:]]
                )

            truncated_stderr = None
            if stderr:
                stderr_lines = stderr.split("\n")
                truncated_stderr = "\n".join(
                    [_truncate_line(line) for line in stderr_lines[-256:]]
                )

            return ShellCommandOutput(
                success=False,
                command=command,
                error=f"Error executing command {str(e)}",
                stdout=truncated_stdout,
                stderr=truncated_stderr,
                exit_code=-1,
                timeout=False,
            )


class ReasoningOutput(BaseModel):
    success: bool = True


def share_your_reasoning(
    context: RunContext, reasoning: str, next_steps: str | None = None
) -> ReasoningOutput:
    # Emit structured AgentReasoningMessage for the UI
    reasoning_msg = AgentReasoningMessage(
        reasoning=reasoning,
        next_steps=next_steps if next_steps and next_steps.strip() else None,
    )
    get_message_bus().emit(reasoning_msg)

    return ReasoningOutput(success=True)


def register_agent_run_shell_command(agent):
    """Register only the agent_run_shell_command tool."""

    @agent.tool
    async def agent_run_shell_command(
        context: RunContext,
        command: str = "",
        cwd: str = None,
        timeout: int = 60,
        background: bool = False,
    ) -> ShellCommandOutput:
        """Execute a shell command with comprehensive monitoring and safety features.

        This tool provides robust shell command execution with streaming output,
        timeout handling, user confirmation (when not in yolo mode), and proper
        process lifecycle management. Commands are executed in a controlled
        environment with cross-platform process group handling.

        Args:
            command: The shell command to execute. Cannot be empty or whitespace-only.
            cwd: Working directory for command execution. If None,
                uses the current working directory. Defaults to None.
            timeout: Inactivity timeout in seconds. If no output is
                produced for this duration, the process will be terminated.
                Defaults to 60 seconds.
            background: If True, run the command in the background and return immediately.
                The command output will be written to a temporary log file.
                Use this for long-running processes like servers (npm run dev, python -m http.server),
                or any command you don't need to wait for.
                When background=True, the response includes:
                - log_file: Path to temp file containing stdout/stderr (read with read_file tool)
                - pid: Process ID of the background process
                Defaults to False.

        Returns:
            ShellCommandOutput: A structured response containing:
                - success (bool): True if command executed successfully (exit code 0)
                - command (str | None): The executed command string
                - error (str | None): Error message if execution failed
                - stdout (str | None): Standard output from the command (last 256 lines)
                - stderr (str | None): Standard error from the command (last 256 lines)
                - exit_code (int | None): Process exit code
                - execution_time (float | None): Total execution time in seconds
                - timeout (bool | None): True if command was terminated due to timeout
                - user_interrupted (bool | None): True if user killed the process
                - background (bool): True if command was run in background mode
                - log_file (str | None): Path to temp log file for background commands
                - pid (int | None): Process ID for background commands

        Examples:
            >>> # Basic command execution
            >>> result = agent_run_shell_command(ctx, "ls -la")
            >>> print(result.stdout)

            >>> # Command with working directory
            >>> result = agent_run_shell_command(ctx, "npm test", "/path/to/project")
            >>> if result.success:
            ...     print("Tests passed!")

            >>> # Command with custom timeout
            >>> result = agent_run_shell_command(ctx, "long_running_command", timeout=300)
            >>> if result.timeout:
            ...     print("Command timed out")

            >>> # Background command for long-running server
            >>> result = agent_run_shell_command(ctx, "npm run dev", background=True)
            >>> print(f"Server started with PID {result.pid}")
            >>> print(f"Logs available at: {result.log_file}")

        Warning:
            This tool can execute arbitrary shell commands. Exercise caution when
            running untrusted commands, especially those that modify system state.
        """
        return await run_shell_command(context, command, cwd, timeout, background)


def register_agent_share_your_reasoning(agent):
    """Register only the agent_share_your_reasoning tool."""

    @agent.tool
    def agent_share_your_reasoning(
        context: RunContext, reasoning: str = "", next_steps: str | None = None
    ) -> ReasoningOutput:
        """Share the agent's current reasoning and planned next steps with the user.

        This tool provides transparency into the agent's decision-making process
        by displaying the current reasoning and upcoming actions in a formatted,
        user-friendly manner. It's essential for building trust and understanding
        between the agent and user.

        Args:
            reasoning: The agent's current thought process, analysis, or
                reasoning for the current situation. This should be clear,
                comprehensive, and explain the 'why' behind decisions.
            next_steps: Planned upcoming actions or steps
                the agent intends to take. Can be None if no specific next steps
                are determined. Defaults to None.

        Returns:
            ReasoningOutput: A simple response object containing:
                - success (bool): Always True, indicating the reasoning was shared

        Examples:
            >>> reasoning = "I need to analyze the codebase structure first"
            >>> next_steps = "First, I'll list the directory contents, then read key files"
            >>> result = agent_share_your_reasoning(ctx, reasoning, next_steps)

        Best Practice:
            Use this tool frequently to maintain transparency. Call it:
            - Before starting complex operations
            - When changing strategy or approach
            - To explain why certain decisions are being made
            - When encountering unexpected situations
        """
        return share_your_reasoning(context, reasoning, next_steps)
