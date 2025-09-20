import os
import signal
import subprocess
import sys
import threading
import time
import traceback
from typing import Set

from pydantic import BaseModel
from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.text import Text

from code_puppy.messaging import (
    emit_divider,
    emit_error,
    emit_info,
    emit_system_message,
    emit_warning,
)
from code_puppy.state_management import is_tui_mode
from code_puppy.tools.common import generate_group_id

# Maximum line length for shell command output to prevent massive token usage
# This helps avoid exceeding model context limits when commands produce very long lines
MAX_LINE_LENGTH = 256


def _truncate_line(line: str) -> str:
    """Truncate a line to MAX_LINE_LENGTH if it exceeds the limit."""
    if len(line) > MAX_LINE_LENGTH:
        return line[:MAX_LINE_LENGTH] + "... [truncated]"
    return line

_AWAITING_USER_INPUT = False

_CONFIRMATION_LOCK = threading.Lock()

# Track running shell processes so we can kill them on Ctrl-C from the UI
_RUNNING_PROCESSES: Set[subprocess.Popen] = set()
_RUNNING_PROCESSES_LOCK = threading.Lock()
_USER_KILLED_PROCESSES = set()


def _register_process(proc: subprocess.Popen) -> None:
    with _RUNNING_PROCESSES_LOCK:
        _RUNNING_PROCESSES.add(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    with _RUNNING_PROCESSES_LOCK:
        _RUNNING_PROCESSES.discard(proc)


def _kill_process_group(proc: subprocess.Popen) -> None:
    """Attempt to aggressively terminate a process and its group.

    Cross-platform best-effort. On POSIX, uses process groups. On Windows, tries CTRL_BREAK_EVENT, then terminate().
    """
    try:
        if sys.platform.startswith("win"):
            try:
                # Try a soft break first if the group exists
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
                time.sleep(0.8)
            except Exception:
                pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                    time.sleep(0.8)
                except Exception:
                    pass
            if proc.poll() is None:
                try:
                    proc.kill()
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
    """Kill all currently tracked running shell processes.

    Returns the number of processes signaled.
    """
    procs: list[subprocess.Popen]
    with _RUNNING_PROCESSES_LOCK:
        procs = list(_RUNNING_PROCESSES)
    count = 0
    for p in procs:
        try:
            if p.poll() is None:
                _kill_process_group(p)
                count += 1
                _USER_KILLED_PROCESSES.add(p.pid)
        finally:
            _unregister_process(p)
    return count


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


def run_shell_command_streaming(
    process: subprocess.Popen,
    timeout: int = 60,
    command: str = "",
    group_id: str = None,
):
    start_time = time.time()
    last_output_time = [start_time]

    ABSOLUTE_TIMEOUT_SECONDS = 270

    stdout_lines = []
    stderr_lines = []

    stdout_thread = None
    stderr_thread = None

    def read_stdout():
        try:
            for line in iter(process.stdout.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    # Limit line length to prevent massive token usage
                    line = _truncate_line(line)
                    stdout_lines.append(line)
                    emit_system_message(line, message_group=group_id)
                    last_output_time[0] = time.time()
        except Exception:
            pass

    def read_stderr():
        try:
            for line in iter(process.stderr.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    # Limit line length to prevent massive token usage
                    line = _truncate_line(line)
                    stderr_lines.append(line)
                    emit_system_message(line, message_group=group_id)
                    last_output_time[0] = time.time()
        except Exception:
            pass

    def cleanup_process_and_threads(timeout_type: str = "unknown"):
        nonlocal stdout_thread, stderr_thread

        def nuclear_kill(proc):
            _kill_process_group(proc)

        try:
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
                error_msg = Text()
                error_msg.append(
                    "Process killed: inactivity timeout reached", style="bold red"
                )
                emit_error(error_msg, message_group=group_id)
                return cleanup_process_and_threads("absolute")

            if current_time - last_output_time[0] > timeout:
                error_msg = Text()
                error_msg.append(
                    "Process killed: inactivity timeout reached", style="bold red"
                )
                emit_error(error_msg, message_group=group_id)
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

        if exit_code != 0:
            emit_error(
                f"Command failed with exit code {exit_code}", message_group=group_id
            )
            emit_info(f"Took {execution_time:.2f}s", message_group=group_id)
            time.sleep(1)
            # Apply line length limits to stdout/stderr before returning
            truncated_stdout = [_truncate_line(line) for line in stdout_lines[-256:]]
            truncated_stderr = [_truncate_line(line) for line in stderr_lines[-256:]]
                
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
        # Apply line length limits to stdout/stderr before returning
        truncated_stdout = [_truncate_line(line) for line in stdout_lines[-256:]]
        truncated_stderr = [_truncate_line(line) for line in stderr_lines[-256:]]
            
        return ShellCommandOutput(
            success=exit_code == 0,
            command=command,
            stdout="\n".join(truncated_stdout),
            stderr="\n".join(truncated_stderr),
            exit_code=exit_code,
            execution_time=execution_time,
            timeout=False,
        )

    except Exception as e:
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error during streaming execution: {str(e)}",
            stdout="\n".join(stdout_lines[-1000:]),
            stderr="\n".join(stderr_lines[-1000:]),
            exit_code=-1,
            timeout=False,
        )


def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> ShellCommandOutput:
    command_displayed = False

    # Generate unique group_id for this command execution
    group_id = generate_group_id("shell_command", command)

    if not command or not command.strip():
        emit_error("Command cannot be empty", message_group=group_id)
        return ShellCommandOutput(
            **{"success": False, "error": "Command cannot be empty"}
        )

    emit_info(
        f"\n[bold white on blue] SHELL COMMAND [/bold white on blue] 📂 [bold green]$ {command}[/bold green]",
        message_group=group_id,
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

        if cwd:
            emit_info(f"[dim] Working directory: {cwd} [/dim]", message_group=group_id)

        # Set the flag to indicate we're awaiting user input
        set_awaiting_user_input(True)

        time.sleep(0.2)
        sys.stdout.write("Are you sure you want to run this command? (y(es)/n(o))\n")
        sys.stdout.flush()

        try:
            user_input = input()
            confirmed = user_input.strip().lower() in {"yes", "y"}
        except (KeyboardInterrupt, EOFError):
            emit_warning("\n Cancelled by user")
            confirmed = False
        finally:
            # Clear the flag regardless of the outcome
            set_awaiting_user_input(False)
            if confirmation_lock_acquired:
                _CONFIRMATION_LOCK.release()

        if not confirmed:
            result = ShellCommandOutput(
                success=False, command=command, error="User rejected the command!"
            )
            return result
    else:
        start_time = time.time()

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
            truncated_stdout = "\n".join([_truncate_line(line) for line in stdout_lines[-256:]])
            
        truncated_stderr = None
        if stderr:
            stderr_lines = stderr.split("\n")
            truncated_stderr = "\n".join([_truncate_line(line) for line in stderr_lines[-256:]])
            
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
    # Generate unique group_id for this reasoning session
    group_id = generate_group_id(
        "agent_reasoning", reasoning[:50]
    )  # Use first 50 chars for context

    if not is_tui_mode():
        emit_divider(message_group=group_id)
        emit_info(
            "\n[bold white on purple] AGENT REASONING [/bold white on purple]",
            message_group=group_id,
        )
    emit_info("[bold cyan]Current reasoning:[/bold cyan]", message_group=group_id)
    emit_system_message(Markdown(reasoning), message_group=group_id)
    if next_steps is not None and next_steps.strip():
        emit_info(
            "\n[bold cyan]Planned next steps:[/bold cyan]", message_group=group_id
        )
        emit_system_message(Markdown(next_steps), message_group=group_id)
    emit_info("[dim]" + "-" * 60 + "[/dim]\n", message_group=group_id)
    return ReasoningOutput(**{"success": True})


def register_agent_run_shell_command(agent):
    """Register only the agent_run_shell_command tool."""

    @agent.tool
    def agent_run_shell_command(
        context: RunContext, command: str = "", cwd: str = None, timeout: int = 60
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

        Warning:
            This tool can execute arbitrary shell commands. Exercise caution when
            running untrusted commands, especially those that modify system state.
        """
        return run_shell_command(context, command, cwd, timeout)


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
