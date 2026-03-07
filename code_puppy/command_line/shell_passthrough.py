"""Shell pass-through for direct command execution.

Prepend a prompt with `!` to execute it as a shell command directly,
bypassing the agent entirely. Inspired by Claude Code's `!` prefix.

Examples:
    !ls -la
    !git status
    !python --version
"""

import os
import subprocess
import sys
import time

from rich.console import Console
from rich.markup import escape as escape_rich_markup

from code_puppy.config import get_banner_color

# The prefix character that triggers shell pass-through
SHELL_PASSTHROUGH_PREFIX = "!"

# Banner identifier — matches the key in DEFAULT_BANNER_COLORS
_BANNER_NAME = "shell_passthrough"


def _get_console() -> Console:
    """Get a Rich console for direct output.

    Separated for testability — tests can mock this to capture output.
    """
    return Console()


def _format_banner() -> str:
    """Format the SHELL PASSTHROUGH banner using the configured color.

    Uses the same `[bold white on {color}]` pattern as rich_renderer.py
    so the banner looks consistent with SHELL COMMAND, EDIT FILE, etc.

    Returns:
        Rich markup string for the banner.
    """
    color = get_banner_color(_BANNER_NAME)
    return f"[bold white on {color}] 🐚 SHELL PASSTHROUGH [/bold white on {color}]"


def is_shell_passthrough(task: str) -> bool:
    """Check if user input is a shell pass-through command.

    A pass-through command starts with `!` followed by a non-empty command.
    A bare `!` with nothing after it is NOT a pass-through.

    Args:
        task: Raw user input string.

    Returns:
        True if the input is a shell pass-through command.
    """
    stripped = task.strip()
    return (
        stripped.startswith(SHELL_PASSTHROUGH_PREFIX)
        and len(stripped) > len(SHELL_PASSTHROUGH_PREFIX)
        and not stripped[len(SHELL_PASSTHROUGH_PREFIX) :].isspace()
    )


def extract_command(task: str) -> str:
    """Extract the shell command from a pass-through input.

    Strips the leading `!` prefix and any surrounding whitespace.

    Args:
        task: Raw user input (must pass `is_shell_passthrough` check).

    Returns:
        The shell command to execute.
    """
    return task.strip()[len(SHELL_PASSTHROUGH_PREFIX) :].strip()


def execute_shell_passthrough(task: str) -> None:
    """Execute a shell command directly, bypassing the agent.

    Renders a colored banner (matching the codebase banner system) so the
    user instantly sees they're in pass-through mode, then inherits stdio
    for raw terminal output.

    Ctrl+C during execution kills the subprocess, not Code Puppy.

    Args:
        task: Raw user input starting with `!`.
    """
    console = _get_console()
    command = extract_command(task)

    if not command:
        console.print("[yellow]Empty command. Usage: !<command> (e.g., !ls -la)[/yellow]")
        return

    # Escape command to prevent Rich markup injection
    safe_command = escape_rich_markup(command)

    # Banner + command on one line, context hint below
    banner = _format_banner()
    console.print(f"\n{banner} [dim]$ {safe_command}[/dim]")
    console.print("[dim]↳ Direct shell · Bypassing AI agent[/dim]")

    start_time = time.monotonic()

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=os.getcwd(),
            # Inherit stdio — output goes straight to the terminal
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        elapsed = time.monotonic() - start_time

        if result.returncode == 0:
            console.print(
                f"[bold green]✅ Done[/bold green] [dim]({elapsed:.1f}s)[/dim]"
            )
        else:
            console.print(
                f"[bold red]❌ Exit code {result.returncode}[/bold red] "
                f"[dim]({elapsed:.1f}s)[/dim]"
            )

    except KeyboardInterrupt:
        elapsed = time.monotonic() - start_time
        console.print(
            f"\n[bold yellow]⚡ Interrupted[/bold yellow] "
            f"[dim]({elapsed:.1f}s)[/dim]"
        )

    except Exception as e:
        safe_error = escape_rich_markup(str(e))
        console.print(f"[bold red]Shell error:[/bold red] {safe_error}")
