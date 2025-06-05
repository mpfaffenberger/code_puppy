# command_runner.py
import subprocess
import time
import os
from typing import Dict, Any, Optional
from code_puppy.tools.common import console
from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax
import shlex
import re
import threading, queue, termios, tty, sys
import select

def register_command_runner_tools(agent):
    @agent.tool
    def run_shell_command(context: RunContext, command: str, cwd: str = None, timeout: int = 60) -> Dict[str, Any]:
        if not command or not command.strip():
            console.print("[bold red]Error:[/bold red] Command cannot be empty")
            return {"error": "Command cannot be empty"}
        console.print("\n[bold white on blue] SHELL COMMAND [/bold white on blue]")
        console.print(f"[bold green]$ {command}[/bold green]")
        if cwd:
            console.print(f"[dim]Working directory: {cwd}[/dim]")
        console.print("[dim]" + "-" * 60 + "[/dim]")
        yolo_mode = os.getenv("YOLO_MODE", "false").lower() == "true"
        if not yolo_mode:
            user_input = input("Are you sure you want to run this command? (yes/no): ")
            if user_input.strip().lower() not in {"yes", "y"}:
                console.print("[bold yellow]Command execution canceled by user.[/bold yellow]")
                return {"success": False, "command": command, "error": "User canceled command execution"}

        # ------------------------------------------------------------------
        # Basic safety guardrails
        # ------------------------------------------------------------------
        BLOCKED_PATTERNS = [
            r"\brm\b.*\*(?!(\.\w+))",  # rm with wildcard
            r"\brm\s+-rf\s+/",           # rm -rf /
            r"\bsudo\s+rm",              # any sudo rm
            r"\breboot\b",               # system reboot
            r"\bshutdown\b",             # system shutdown
        ]
        lower_cmd = command.lower()
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, lower_cmd):
                console.print(f"[bold red]Refused to run dangerous command:[/bold red] {command}")
                return {"success": False, "command": command, "error": "Command blocked by safety guard"}

        # Extra guard: prompt again if command starts with `rm` or uses `--force`
        tokens = shlex.split(command)
        if tokens and tokens[0] == "rm":
            console.print("[bold yellow]Warning:[/bold yellow] You are about to run an 'rm' command.")
            extra = input("Type 'I understand' to proceed: ")
            if extra.strip().lower() != "i understand":
                console.print("[bold yellow]Command execution canceled by user.[/bold yellow]")
                return {"success": False, "command": command, "error": "User canceled command execution"}

        try:
            start_time = time.time()
            process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)

            # Use a queue to shuttle output from the reader thread
            q: "queue.Queue[str]" = queue.Queue()

            def _reader(pipe, tag):
                for line in iter(pipe.readline, ''):
                    q.put((tag, line))
                pipe.close()

            stdout_thread = threading.Thread(target=_reader, args=(process.stdout, 'STDOUT'), daemon=True)
            stderr_thread = threading.Thread(target=_reader, args=(process.stderr, 'STDERR'), daemon=True)
            stdout_thread.start()
            stderr_thread.start()

            # Save terminal state and switch to cbreak to capture ESC presses.
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            ESC_CODE = 27
            timed_out = False
            try:
                while True:
                    try:
                        tag, line = q.get_nowait()
                        if line.strip():
                            if tag == 'STDOUT':
                                console.print(line.rstrip())
                            else:
                                console.print(f"[bold yellow]{line.rstrip()}[/bold yellow]")
                    except queue.Empty:
                        pass

                    if process.poll() is not None:
                        break  # command finished

                    # Check for ESC key press
                    if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                        ch = sys.stdin.read(1)
                        if ord(ch) == ESC_CODE:
                            console.print("[bold red]⏹ ESC detected – terminating command...[/bold red]")
                            process.terminate()
                            timed_out = True
                            break

                    if time.time() - start_time > timeout:
                        console.print(f"[bold red]⏱ Command timed out after {timeout} seconds – killing...[/bold red]")
                        process.terminate()
                        timed_out = True
                        break

            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            stdout_remaining = ''.join(line for tag, line in list(q.queue) if tag == 'STDOUT')
            stderr_remaining = ''.join(line for tag, line in list(q.queue) if tag == 'STDERR')
            exit_code = process.returncode
            execution_time = time.time() - start_time
            success = (exit_code == 0) and not timed_out
            return {
                "success": success,
                "command": command,
                "stdout": stdout_remaining,
                "stderr": stderr_remaining,
                "exit_code": exit_code,
                "execution_time": execution_time,
                "timeout": timed_out,
                "error": None if success else "Command interrupted" if timed_out else "Command failed",
            }
        except Exception as e:
            console.print_exception(show_locals=True)
            console.print("[dim]" + "-" * 60 + "[/dim]\n")
            return {"success": False, "command": command, "error": f"Error executing command: {str(e)}", "stdout": "", "stderr": "", "exit_code": -1, "timeout": False}

    @agent.tool
    def share_your_reasoning(context: RunContext, reasoning: str, next_steps: str = None) -> Dict[str, Any]:
        console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")
        console.print("[bold cyan]Current reasoning:[/bold cyan]")
        console.print(Markdown(reasoning))
        if next_steps and next_steps.strip():
            console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
            console.print(Markdown(next_steps))
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
        return {"success": True, "reasoning": reasoning, "next_steps": next_steps}

# ---------------------------------------------------------------------------
# Module-level helper functions (exposed for unit tests _and_ used as tools)
# ---------------------------------------------------------------------------

def run_shell_command(context: Optional[RunContext], command: str, cwd: str = None, timeout: int = 60) -> Dict[str, Any]:
    import subprocess, time, os as _os
    from rich.syntax import Syntax
    from code_puppy.tools.common import console as _console
    if not command or not command.strip():
        _console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return {"error": "Command cannot be empty"}
    _console.print("\n[bold white on blue] SHELL COMMAND [/bold white on blue]")
    _console.print(f"[bold green]$ {command}[/bold green]")
    if cwd:
        _console.print(f"[dim]Working directory: {cwd}[/dim]")
    _console.print("[dim]" + "-" * 60 + "[/dim]")
    yolo_mode = _os.getenv("YOLO_MODE", "false").lower() == "true"
    if not yolo_mode:
        user_input = input("Are you sure you want to run this command? (yes/no): ")
        if user_input.strip().lower() not in {"yes", "y"}:
            _console.print("[bold yellow]Command execution canceled by user.[/bold yellow]")
            return {"success": False, "command": command, "error": "User canceled command execution"}
    try:
        start_time = time.time()
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)

        # Use a queue to shuttle output from the reader thread
        q: "queue.Queue[str]" = queue.Queue()

        def _reader(pipe, tag):
            for line in iter(pipe.readline, ''):
                q.put((tag, line))
            pipe.close()

        stdout_thread = threading.Thread(target=_reader, args=(process.stdout, 'STDOUT'), daemon=True)
        stderr_thread = threading.Thread(target=_reader, args=(process.stderr, 'STDERR'), daemon=True)
        stdout_thread.start()
        stderr_thread.start()

        # Save terminal state and switch to cbreak to capture ESC presses.
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        ESC_CODE = 27
        timed_out = False
        try:
            while True:
                try:
                    tag, line = q.get_nowait()
                    if line.strip():
                        if tag == 'STDOUT':
                            _console.print(line.rstrip())
                        else:
                            _console.print(f"[bold yellow]{line.rstrip()}[/bold yellow]")
                except queue.Empty:
                    pass

                if process.poll() is not None:
                    break  # command finished

                # Check for ESC key press
                if sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
                    ch = sys.stdin.read(1)
                    if ord(ch) == ESC_CODE:
                        _console.print("[bold red]⏹ ESC detected – terminating command...[/bold red]")
                        process.terminate()
                        timed_out = True
                        break

                if time.time() - start_time > timeout:
                    _console.print(f"[bold red]⏱ Command timed out after {timeout} seconds – killing...[/bold red]")
                    process.terminate()
                    timed_out = True
                    break

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)
        stdout_remaining = ''.join(line for tag, line in list(q.queue) if tag == 'STDOUT')
        stderr_remaining = ''.join(line for tag, line in list(q.queue) if tag == 'STDERR')
        exit_code = process.returncode
        execution_time = time.time() - start_time
        success = (exit_code == 0) and not timed_out
        return {
            "success": success,
            "command": command,
            "stdout": stdout_remaining,
            "stderr": stderr_remaining,
            "exit_code": exit_code,
            "execution_time": execution_time,
            "timeout": timed_out,
            "error": None if success else "Command interrupted" if timed_out else "Command failed",
        }
    except Exception as e:
        _console.print_exception(show_locals=True)
        _console.print("[dim]" + "-" * 60 + "[/dim]\n")
        return {"success": False, "command": command, "error": f"Error executing command: {str(e)}", "stdout": "", "stderr": "", "exit_code": -1, "timeout": False}


def share_your_reasoning(context: Optional[RunContext], reasoning: str, next_steps: str | None = None) -> Dict[str, Any]:
    from rich.markdown import Markdown
    from code_puppy.tools.common import console as _console
    _console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")
    _console.print("[bold cyan]Current reasoning:[/bold cyan]")
    _console.print(Markdown(reasoning))
    if next_steps and next_steps.strip():
        _console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
        _console.print(Markdown(next_steps))
    _console.print("[dim]" + "-" * 60 + "[/dim]\n")
    return {"success": True, "reasoning": reasoning, "next_steps": next_steps}

# ---------------------------------------------------------------------------
# Original registration function now simply registers the helpers above
# ---------------------------------------------------------------------------
