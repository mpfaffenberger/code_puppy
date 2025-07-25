import subprocess
import threading
import time
import traceback
from typing import Any, Dict

from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy.globals import is_tui_mode
from code_puppy.messaging import (
    emit_command_output,
    emit_error,
    emit_info,
    emit_warning,
)

# Flag to indicate if we need user input - this will be checked by interactive mode
# to determine if spinner should be shown
_AWAITING_USER_INPUT = False

# Lock to ensure only one command can request confirmation at a time
_CONFIRMATION_LOCK = threading.Lock()


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
        from code_puppy.messaging.spinner import pause_all_spinners

        pause_all_spinners()
    else:
        # Resume all active spinners
        from code_puppy.messaging.spinner import resume_all_spinners

        resume_all_spinners()


def run_shell_command_streaming(
    process: subprocess.Popen,
    timeout: int = 60,
    command: str = "",
) -> Dict[str, Any]:
    """
    Execute a subprocess with real-time output streaming and dual timeout protection.

    Features:
    1. Real-time output streaming as lines are produced
    2. Inactivity timeout: Kill after N seconds of no output
    3. Absolute timeout: Kill after 4m30s total (prevents TCP timeouts)
    4. Separate handling of stdout and stderr

    Args:
        process: Already created subprocess.Popen object
        timeout: Kill after this many seconds of no output (inactivity timeout)
        command: Command string for logging purposes

    Returns:
        Dict with success, stdout, stderr, exit_code, etc.
    """
    start_time = time.time()
    last_output_time = [start_time]  # Use list for mutable reference in threads

    # Absolute timeout: 4 minutes 30 seconds to prevent TCP timeouts
    ABSOLUTE_TIMEOUT_SECONDS = 270

    stdout_lines = []
    stderr_lines = []
    command_shown = [False]  # Track if we've shown the command yet

    def emit_real_time_output(line: str, is_stderr: bool = False):
        """Emit output in real-time with Rich formatting."""
        if line.strip():
            # Show command header only on first output
            if not command_shown[0] and not is_tui_mode():
                emit_info(f"[bold green]$ {command}[/bold green]")
                command_shown[0] = True

            # Format output with syntax highlighting
            syntax_output = Syntax(
                line, "bash", theme="monokai", background_color="default"
            )
            emit_command_output(syntax_output)

    def read_stdout():
        """Thread function to read stdout line by line."""
        try:
            for line in iter(process.stdout.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    stdout_lines.append(line)
                    emit_real_time_output(line, is_stderr=False)
                    last_output_time[0] = time.time()
        except Exception:
            pass  # Process might be killed/closed

    def read_stderr():
        """Thread function to read stderr line by line."""
        try:
            for line in iter(process.stderr.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    stderr_lines.append(line)
                    emit_real_time_output(line, is_stderr=True)
                    last_output_time[0] = time.time()
        except Exception:
            pass  # Process might be killed/closed

    try:
        # Start reader threads for real-time output
        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)

        stdout_thread.start()
        stderr_thread.start()

        # Monitor process: check for inactivity and absolute (wall) timeout
        while process.poll() is None:
            current_time = time.time()

            # Absolute timeout
            if current_time - start_time > ABSOLUTE_TIMEOUT_SECONDS:
                process.kill()
                error_msg = Text()
                error_msg.append(
                    "⏰ Process killed: absolute timeout reached ", style="bold red"
                )
                error_msg.append(
                    f"({ABSOLUTE_TIMEOUT_SECONDS}s total)", style="bold red"
                )
                emit_error(error_msg)
                # Wait briefly for thread cleanup
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "command": command,
                    "stdout": "\n".join(stdout_lines),
                    "stderr": "\n".join(stderr_lines),
                    "exit_code": -9,
                    "execution_time": execution_time,
                    "timeout": True,
                    "timeout_type": "absolute",
                    "error": f"Process timed out after {ABSOLUTE_TIMEOUT_SECONDS}s total execution time",
                }

            # Inactivity timeout
            if current_time - last_output_time[0] > timeout:
                process.kill()
                error_msg = Text()
                error_msg.append(
                    "⏰ Process killed: inactivity timeout reached ", style="bold red"
                )
                error_msg.append(f"({timeout}s no output)", style="bold red")
                emit_error(error_msg)
                stdout_thread.join(timeout=1)
                stderr_thread.join(timeout=1)
                execution_time = time.time() - start_time
                return {
                    "success": False,
                    "command": command,
                    "stdout": "\n".join(stdout_lines),
                    "stderr": "\n".join(stderr_lines),
                    "exit_code": -9,
                    "execution_time": execution_time,
                    "timeout": True,
                    "timeout_type": "inactivity",
                    "error": f"Process timed out after {timeout}s of no output",
                }

            time.sleep(0.1)  # Don't go brrr

        # Wait for output threads to drain
        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

        exit_code = process.returncode
        execution_time = time.time() - start_time
        # Show execution summary
        if exit_code != 0:
            error_msg = Text()
            error_msg.append("✗ Command failed with exit code ", style="bold red")
            error_msg.append(str(exit_code))
            error_msg.append(f" (took {execution_time:.2f}s)", style="dim")
            emit_error(error_msg)
        return {
            "success": exit_code == 0,
            "command": command,
            "stdout": "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
            "exit_code": exit_code,
            "execution_time": execution_time,
            "timeout": False,
        }

    except Exception as e:
        return {
            "success": False,
            "command": command,
            "error": f"Error during streaming execution: {str(e)}",
            "stdout": "\n".join(stdout_lines),
            "stderr": "\n".join(stderr_lines),
            "exit_code": -1,
            "timeout": False,
        }


def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> Dict[str, Any]:
    # Flag to track if we've already displayed the command
    command_displayed = False
    if not command or not command.strip():
        emit_error("Command cannot be empty")
        return {"error": "Command cannot be empty"}

    from code_puppy.config import get_yolo_mode

    yolo_mode = get_yolo_mode()

    # Flag to track if we acquired the lock (for thread safety)
    confirmation_lock_acquired = False

    if not yolo_mode:
        # Acquire lock to ensure only one command can request confirmation at a time
        confirmation_lock_acquired = _CONFIRMATION_LOCK.acquire(blocking=False)
        if not confirmation_lock_acquired:
            # emit_warning("Another command is currently awaiting confirmation. Please respond to that first.")
            return {
                "success": False,
                "command": command,
                "error": "Another command is currently awaiting confirmation",
            }
        # Show command info before asking for confirmation
        if not is_tui_mode():
            emit_info("\n[dim]" + "-" * 60 + "[/dim]")
            emit_info(f"[bold green]$ {command}[/bold green]")
            emit_info("")

        command_displayed = True

        if cwd:
            emit_info(f"[dim]Working directory: {cwd}[/dim]")
        import sys

        # Import here to minimize dependencies
        from code_puppy.messaging.spinner import ConsoleSpinner

        # Simpler approach to find active spinners
        active_spinner = None
        try:
            # Look for active spinner in the caller's stack frames
            frame = sys._getframe()
            while frame:
                for var_name, var_val in frame.f_locals.items():
                    if isinstance(var_val, ConsoleSpinner):
                        active_spinner = var_val
                        active_spinner.pause()
                        break
                if active_spinner:
                    break
                frame = frame.f_back
        except Exception:
            # Just continue if we can't pause the spinner
            pass

        # First, set the flag to indicate we're awaiting user input - BEFORE printing anything
        # This ensures spinners immediately show "waiting" instead of "thinking"
        set_awaiting_user_input(True)

        # Allow a moment for spinners to update their text
        time.sleep(0.2)

        # Print directly to stdout to be more visible and use a custom prompt
        # that won't be overwritten by the Rich console or spinners
        sys.stdout.write("👉 Are you sure you want to run this command? (y(es)/n(o))\n")
        sys.stdout.flush()

        # Get user input
        try:
            # Need to keep the flag set during input() to prevent spinner display
            user_input = input()
            # Only clear the flag after we've got the input
            confirmed = user_input.strip().lower() in {"yes", "y"}

        except (KeyboardInterrupt, EOFError):
            emit_warning("\nCancelled by user")
            confirmed = False
        finally:
            # Clear the flag regardless of the outcome
            # But wait until *after* we've processed the input
            set_awaiting_user_input(False)

            # Release the lock only if we acquired it
            if confirmation_lock_acquired:
                _CONFIRMATION_LOCK.release()

        if not confirmed:
            emit_warning("Command execution canceled by user.")
            # No need to resume spinner if command was canceled
            result = {
                "success": False,
                "command": command,
                "error": "User canceled command execution",
            }
            # Lock release will happen in the finally block
            return result

        # Spinner will be automatically resumed when set_awaiting_user_input(False) was called
    else:
        # In yolo mode, show command info before executing
        if not is_tui_mode():
            emit_info("\n[dim]" + "-" * 60 + "[/dim]")
            emit_info(f"[bold green]$ {command}[/bold green]")
            emit_info("")

        command_displayed = True

        if cwd:
            emit_info(f"[dim]Working directory: {cwd}[/dim]")

    try:
        start_time = time.time()
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            bufsize=1,  # Line buffered for better streaming
            universal_newlines=True,
        )

        # Always use streaming execution
        return run_shell_command_streaming(process, timeout=timeout, command=command)
    except Exception as e:
        emit_error(traceback.format_exc())
        emit_info("[dim]" + "-" * 60 + "[/dim]\n")
        # Ensure stdout and stderr are always defined
        if "stdout" not in locals():
            stdout = None
        if "stderr" not in locals():
            stderr = None
        return {
            "success": False,
            "command": command,
            "error": f"Error executing command: {str(e)}",
            "stdout": stdout[-1000:] if stdout else None,
            "stderr": stderr[-1000:] if stderr else None,
            "exit_code": -1,
            "timeout": False,
        }


def share_your_reasoning(
    context: RunContext, reasoning: str, next_steps: str = None
) -> Dict[str, Any]:
    from code_puppy.messaging import emit_agent_reasoning, emit_planned_next_steps

    if not is_tui_mode():
        emit_agent_reasoning("[dim]" + "-" * 60 + "[/dim]\n")
        emit_agent_reasoning("\n[bold purple]AGENT REASONING:[/bold purple]")
    emit_agent_reasoning(Markdown(reasoning))

    if next_steps and next_steps.strip():
        if not is_tui_mode():
            emit_planned_next_steps("\n[bold purple]PLANNED NEXT STEPS:[/bold purple]")
        emit_planned_next_steps(Markdown(next_steps))
    return {"success": True, "reasoning": reasoning, "next_steps": next_steps}


def register_command_runner_tools(agent):
    @agent.tool
    def agent_run_shell_command(
        context: RunContext, command: str, cwd: str = None, timeout: int = 60
    ) -> Dict[str, Any]:
        return run_shell_command(context, command, cwd, timeout)

    @agent.tool
    def agent_share_your_reasoning(
        context: RunContext, reasoning: str, next_steps: str = None
    ) -> Dict[str, Any]:
        return share_your_reasoning(context, reasoning, next_steps)
