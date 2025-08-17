import os
import signal
import subprocess
import threading
import time
import traceback
import sys

from pydantic import BaseModel
from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text

from code_puppy.tools.common import console

_AWAITING_USER_INPUT = False

_CONFIRMATION_LOCK = threading.Lock()


class ShellCommandOutput(BaseModel):
    success: bool
    command: str | None
    error: str | None = ""
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    execution_time: float | None
    timeout: bool | None = False


def run_shell_command_streaming(
    process: subprocess.Popen, timeout: int = 60, command: str = ""
):
    start_time = time.time()
    last_output_time = [start_time]

    ABSOLUTE_TIMEOUT_SECONDS = 270

    stdout_lines = []
    stderr_lines = []
    command_shown = [False]

    stdout_thread = None
    stderr_thread = None

    def read_stdout():
        try:
            for line in iter(process.stdout.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    stdout_lines.append(line)
                    console.log(line)
                    last_output_time[0] = time.time()
        except Exception:
            pass

    def read_stderr():
        try:
            for line in iter(process.stderr.readline, ""):
                if line:
                    line = line.rstrip("\n\r")
                    stderr_lines.append(line)
                    console.log(line)
                    last_output_time[0] = time.time()
        except Exception:
            pass

    def cleanup_process_and_threads(timeout_type: str = "unknown"):
        nonlocal stdout_thread, stderr_thread

        def nuclear_kill(proc):
            pid = proc.pid
            try:
                pgid = os.getpgid(pid)
                console.print(f"Attempting to kill process group {pgid} (PID {pid})")
                os.killpg(pgid, signal.SIGTERM)
                time.sleep(1.5)
                if proc.poll() is None:
                    console.print("SIGTERM failed, escalating to SIGINT")
                    os.killpg(pgid, signal.SIGINT)
                    time.sleep(1)

                if proc.poll() is None:
                    console.print("SIGINT failed, escalating to SIGKILL")
                    os.killpg(pgid, signal.SIGKILL)
                    time.sleep(1)

                if proc.poll() is None:
                    console.print(
                        "Proc group kill failed, killing individual processes"
                    )
                    proc.kill()
                    time.sleep(0.5)
            except (OSError, ProcessLookupError):
                try:
                    if proc.poll() is None:
                        proc.kill()
                        time.sleep(0.5)
                except (OSError, ProcessLookupError):
                    pass

            if proc.poll() is None:
                try:
                    console.print(
                        f"Process {pid} refuses to die, trying platform-specific nuclear options"
                    )
                    for i in range(3):
                        try:
                            os.kill(pid, signal.SIGKILL)
                            time.sleep(0.2)
                            if proc.poll() is not None:
                                break
                        except (OSError, ProcessLookupError):
                            break

                    if proc.poll() is None:
                        console.print(f"Process {pid} is unkillable.")

                except Exception as e:
                    console.print(f"Nuclear kill attempt failed {e}")

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

            if stdout_thread and stdout_thread.is_alive():
                stdout_thread.join(timeout=3)
                if stdout_thread.is_alive():
                    console.print(
                        f"stdout reader thread failed to terminate after {timeout_type} seconds"
                    )

            if stderr_thread and stderr_thread.is_alive():
                stderr_thread.join(timeout=3)
                if stderr_thread.is_alive():
                    console.print(
                        f"stderr reader thread failed to terminate after {timeout_type} seconds"
                    )

        except Exception as e:
            console.log(f"Error during process cleanup {e}")

        execution_time = time.time() - start_time
        return ShellCommandOutput(
            **{
                "success": False,
                "command": command,
                "stdout": "\n".join(stdout_lines[-1000:]),
                "stderr": "\n".join(stderr_lines[-1000:]),
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
                console.print(error_msg)
                return cleanup_process_and_threads("absolute")

            if current_time - last_output_time[0] > timeout:
                error_msg = Text()
                error_msg.append(
                    "Process killed: inactivity timeout reached", style="bold red"
                )
                console.print(error_msg)
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

        if exit_code != 0:
            console.print(
                f"Command failed with exit code {exit_code}", style="bold red"
            )
            console.print(f"Took {execution_time:.2f}s", style="dim")
        return ShellCommandOutput(
            success=exit_code == 0,
            command=command,
            stdout="\n".join(stdout_lines[-1000:]),
            stderr="\n".join(stderr_lines[-1000:]),
            exit_code=exit_code,
            execution_time=execution_time,
            timeout=False,
        )

    except Exception as e:
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error durign streaming execution {str(e)}",
            stdout="\n".join(stdout_lines[-1000:]),
            stderr="\n".join(stderr_lines[-1000:]),
            exit_code=-1,
            timeout=False,
        )


def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> ShellCommandOutput:
    command_displayed = False
    if not command or not command.strip():
        console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return ShellCommandOutput(
            **{"success": False, "error": "Command cannot be empty"}
        )
    console.print(
        f"\n[bold white on blue] SHELL COMMAND [/bold white on blue] \U0001f4c2 [bold green]$ {command}[/bold green]"
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
            console.print(f"[dim] Working directory: {cwd} [/dim]")
        time.sleep(0.2)
        sys.stdout.write("Are you sure you want to run this command? (y(es)/n(o))\n")
        sys.stdout.flush()

        try:
            user_input = input()
            confirmed = user_input.strip().lower() in {"yes", "y"}
        except (KeyboardInterrupt, EOFError):
            console.print("\n Cancelled by user")
            confirmed = False
        finally:
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
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            bufsize=1,
            universal_newlines=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        return run_shell_command_streaming(process, timeout=timeout, command=command)
    except Exception as e:
        console.print(traceback.format_exc())
        if "stdout" not in locals():
            stdout = None
        if "stderr" not in locals():
            stderr = None
        return ShellCommandOutput(
            success=False,
            command=command,
            error=f"Error executing command {str(e)}",
            stdout="\n".join(stdout[-1000:]) if stdout else None,
            stderr="\n".join(stderr[-1000:]) if stderr else None,
            exit_code=-1,
            timeout=False,
        )


class ReasoningOutput(BaseModel):
    success: bool = True


def share_your_reasoning(
    context: RunContext, reasoning: str, next_steps: str | None = None
) -> ReasoningOutput:
    console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")
    console.print("[bold cyan]Current reasoning:[/bold cyan]")
    console.print(Markdown(reasoning))
    if next_steps is not None and next_steps.strip():
        console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
        console.print(Markdown(next_steps))
    console.print("[dim]" + "-" * 60 + "[/dim]\n")
    return ReasoningOutput(**{"success": True})


def register_command_runner_tools(agent):
    @agent.tool
    def agent_run_shell_command(
        context: RunContext, command: str, cwd: str = None, timeout: int = 60
    ) -> ShellCommandOutput:
        return run_shell_command(context, command, cwd, timeout)

    @agent.tool
    def agent_share_your_reasoning(
        context: RunContext, reasoning: str, next_steps: str | None = None
    ) -> ReasoningOutput:
        return share_your_reasoning(context, reasoning, next_steps)
