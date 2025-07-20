import subprocess
import time
from typing import Any, Dict

from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax

from code_puppy.globals import is_tui_mode
from code_puppy.tools.common import console

# Flag to indicate if we need user input - this will be checked by interactive mode
# to determine if spinner should be shown
_AWAITING_USER_INPUT = False


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



def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> Dict[str, Any]:
    if not command or not command.strip():
        console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return {"error": "Command cannot be empty"}
    console.print("[dim]" + "-" * 60 + "[/dim]")
    console.print(
        "[cyan]SHELL COMMAND [/cyan]"
    )
    console.print(
        f"[bold green]$ {command}[/bold green]"
    )
    if cwd:
        console.print(f"[dim]Working directory: {cwd}[/dim]")
    from code_puppy.config import get_yolo_mode
    import time

    yolo_mode = get_yolo_mode()
    if not yolo_mode:
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
            console.print("\nCancelled by user")
            confirmed = False
        finally:
            # Clear the flag regardless of the outcome
            # But wait until *after* we've processed the input
            set_awaiting_user_input(False)

        if not confirmed:
            console.print(
                "[bold yellow]Command execution canceled by user.[/bold yellow]"
            )
            # No need to resume spinner if command was canceled
            return {
                "success": False,
                "command": command,
                "error": "User canceled command execution",
            }

        # Spinner will be automatically resumed when set_awaiting_user_input(False) was called
    try:
        start_time = time.time()
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            exit_code = process.returncode
            execution_time = time.time() - start_time
            if stdout.strip():
                console.print("\n[dim]STDOUT:[/dim]\n")
                console.print(
                    Syntax(
                        stdout.strip(),
                        "bash",
                        theme="monokai",
                        background_color="default",
                    )
                )

            if stderr.strip():
                console.print("\n[dim]STDERR:[/dim]\n")
                console.print(
                    Syntax(
                        stderr.strip(),
                        "bash",
                        theme="monokai",
                        background_color="default",
                    )
                )
            if exit_code == 0:
                console.print(
                    f"\n[bold green]✓ Command completed successfully[/bold green] [dim](took {execution_time:.2f}s)[/dim]"
                )
            else:
                console.print(
                    f"[bold red]✗ Command failed with exit code {exit_code}[/bold red] [dim](took {execution_time:.2f}s)[/dim]"
                )
            return {
                "success": exit_code == 0,
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "execution_time": execution_time,
                "timeout": False,
            }
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            execution_time = time.time() - start_time
            if stdout.strip():
                console.print(
                    "[bold white]STDOUT (incomplete due to timeout):[/bold white]"
                )
                console.print(
                    Syntax(
                        stdout.strip(),
                        "bash",
                        theme="monokai",
                        background_color="default",
                    )
                )
            if stderr.strip():
                console.print("[bold yellow]STDERR:[/bold yellow]")
                console.print(
                    Syntax(
                        stderr.strip(),
                        "bash",
                        theme="monokai",
                        background_color="default",
                    )
                )
            console.print(
                f"[bold red]⏱ Command timed out after {timeout} seconds[/bold red] [dim](ran for {execution_time:.2f}s)[/dim]"
            )
            console.print("[dim]" + "-" * 60 + "[/dim]\n")
            return {
                "success": False,
                "command": command,
                "stdout": stdout[-1000:],
                "stderr": stderr[-1000:],
                "exit_code": None,
                "execution_time": execution_time,
                "timeout": True,
                "error": f"Command timed out after {timeout} seconds",
            }
    except Exception as e:
        console.print_exception(show_locals=True)
        console.print("[dim]" + "-" * 60 + "[/dim]\n")
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
    from code_puppy.messaging import emit_agent_reasoning

    if not is_tui_mode:
        emit_agent_reasoning("[dim]" + "-" * 60 + "[/dim]\n")
    emit_agent_reasoning("\n[cyan]CURRENT REASONING:[/cyan]")
    emit_agent_reasoning(Markdown(reasoning))

    if next_steps and next_steps.strip():
        emit_agent_reasoning("\n[cyan]PLANNED NEXT STEPS:[/cyan]")
        emit_agent_reasoning(Markdown(next_steps))
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
