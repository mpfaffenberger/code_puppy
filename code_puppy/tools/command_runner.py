# command_runner.py
import subprocess
import time
import os
from typing import Dict, Any
from code_puppy.tools.common import console
from code_puppy.agent import code_generation_agent
from pydantic_ai import RunContext
from rich.markdown import Markdown
from rich.syntax import Syntax

# Environment variables used in this module:
# - YOLO_MODE: When set to "true" (case-insensitive), bypasses the safety confirmation
#              prompt when running shell commands. This allows commands to execute
#              without user intervention, which can be useful for automation but
#              introduces security risks. Default is "false".


@code_generation_agent.tool
def run_shell_command(
    context: RunContext, command: str, cwd: str = None, timeout: int = 60
) -> Dict[str, Any]:
    """Run a shell command and return its output.

    Args:
        command: The shell command to execute.
        cwd: The current working directory to run the command in. Defaults to None (current directory).
        timeout: Maximum time in seconds to wait for the command to complete. Defaults to 60.

    Returns:
        A dictionary with the command result, including stdout, stderr, and exit code.
    """
    if not command or not command.strip():
        console.print("[bold red]Error:[/bold red] Command cannot be empty")
        return {"error": "Command cannot be empty"}

    # Display command execution in a visually distinct way
    console.print("\n[bold white on blue] SHELL COMMAND [/bold white on blue]")
    console.print(f"[bold green]$ {command}[/bold green]")
    if cwd:
        console.print(f"[dim]Working directory: {cwd}[/dim]")
    console.print("[dim]" + "-" * 60 + "[/dim]")

    # Check for YOLO_MODE environment variable to bypass safety check
    yolo_mode = os.getenv("YOLO_MODE", "false").lower() == "true"

    if not yolo_mode:
        # Prompt user for confirmation before running the command
        user_input = input("Are you sure you want to run this command? (yes/no): ")
        if user_input.strip().lower() not in {"yes", "y"}:
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

        # Execute the command with timeout
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

            # Display command output
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

            # Show execution summary
            if exit_code == 0:
                console.print(
                    f"[bold green]✓ Command completed successfully[/bold green] [dim](took {execution_time:.2f}s)[/dim]"
                )
            else:
                console.print(
                    f"[bold red]✗ Command failed with exit code {exit_code}[/bold red] [dim](took {execution_time:.2f}s)[/dim]"
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
            # Kill the process if it times out
            process.kill()
            stdout, stderr = process.communicate()
            execution_time = time.time() - start_time

            # Display timeout information
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
                "exit_code": None,  # No exit code since the process was killed
                "execution_time": execution_time,
                "timeout": True,
                "error": f"Command timed out after {timeout} seconds",
            }
    except Exception as e:
        # Display error information
        console.print_exception(show_locals=True)
        console.print("[dim]" + "-" * 60 + "[/dim]\n")

        return {
            "success": False,
            "command": command,
            "error": f"Error executing command: {str(e)}",
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timeout": False,
        }


@code_generation_agent.tool
def share_your_reasoning(
    context: RunContext, reasoning: str, next_steps: str = None
) -> Dict[str, Any]:
    """Share the agent's current reasoning and planned next steps with the user.

    Args:
        reasoning: The agent's current reasoning or thought process.
        next_steps: Optional description of what the agent plans to do next.

    Returns:
        A dictionary with the reasoning information.
    """
    console.print("\n[bold white on purple] AGENT REASONING [/bold white on purple]")

    # Display the reasoning with markdown formatting
    console.print("[bold cyan]Current reasoning:[/bold cyan]")
    console.print(Markdown(reasoning))

    # Display next steps if provided
    if next_steps and next_steps.strip():
        console.print("\n[bold cyan]Planned next steps:[/bold cyan]")
        console.print(Markdown(next_steps))

    console.print("[dim]" + "-" * 60 + "[/dim]\n")

    return {"success": True, "reasoning": reasoning, "next_steps": next_steps}
