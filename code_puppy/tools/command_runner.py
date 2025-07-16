import subprocess
import time
import sys
import os
from typing import Any, Dict

from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax

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


def get_confirmation(prompt: str = "Are you sure you want to run this command?") -> bool:
    """
    Get confirmation from user. Uses a simple approach to avoid issues with spinners.
    """
    import time

    # Print the prompt with an obvious prefix
    console.print("\n" + "=" * 60)
    console.print("👉 " + prompt + " (yes/no): ", end="")

    # Sleep briefly to ensure the prompt is displayed before any spinner starts
    time.sleep(3)

    # Get user input
    try:
        user_input = input()
        result = user_input.strip().lower() in {"yes", "y"}
        console.print("=" * 60)
        return result
    except (KeyboardInterrupt, EOFError):
        console.print("\nCancelled by user")
        console.print("=" * 60)
        return False

# This function is not currently used
def is_awaiting_user_input():
    """Check if we are awaiting user input - not used in current version."""
    return False

def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> Dict[str, Any]:
    if not command or not command.strip():
        console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return {"error": "Command cannot be empty"}
    console.print(
        f"\n[bold white on blue] SHELL COMMAND [/bold white on blue] \U0001f4c2 [bold green]$ {command}[/bold green]"
    )
    if cwd:
        console.print(f"[dim]Working directory: {cwd}[/dim]")
    console.print("[dim]" + "-" * 60 + "[/dim]")
    from code_puppy.config import get_yolo_mode

    yolo_mode = get_yolo_mode()
    if not yolo_mode:
        # Create a very visible confirmation prompt
        console.print(f"[bold yellow]Command:[/bold yellow] [green]{command}[/green]")

        import sys

        # Print directly to stdout to be more visible
        sys.stdout.write("\nAre you sure you want to run this command? (yes/no): ")
        sys.stdout.flush()

        # Get user input
        try:
            user_input = input()
            confirmed = user_input.strip().lower() in {"yes", "y"}
        except (KeyboardInterrupt, EOFError):
            console.print("\nCancelled by user")
            confirmed = False

        if not confirmed:
            console.print(
                "[bold yellow]Command execution canceled by user.[/bold yellow]"
            )
            return {
                "success": False,
                "command": command,
                "error": "User canceled command execution",
            }
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
                console.print("[bold white]STDOUT:[/bold white]")
                console.print(
                    Syntax(
                        stdout.strip(),
                        "bash",
                        theme="monokai",
                        background_color="default",
                    )
                )
            else:
                console.print("[yellow]No STDOUT output[/yellow]")
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
            if exit_code == 0:
                console.print(
                    f"[bold green]✓ Command completed successfully[/bold green] [dim](took {execution_time:.2f}s)[/dim]"
                )
            else:
                console.print(
                    f"[bold red]✗ Command failed with exit code {exit_code}[/bold red] [dim](took {execution_time:.2f}s)[/dim]"
                )
            if not stdout.strip() and not stderr.strip():
                console.print(
                    "[bold yellow]This command produced no output at all![/bold yellow]"
                )
            console.print("[dim]" + "-" * 60 + "[/dim]\n")
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
    console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")
    console.print("[bold cyan]Current reasoning:[/bold cyan]")
    console.print(Markdown(reasoning))
    if next_steps and next_steps.strip():
        console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
        console.print(Markdown(next_steps))
    console.print("[dim]" + "-" * 60 + "[/dim]\n")
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
