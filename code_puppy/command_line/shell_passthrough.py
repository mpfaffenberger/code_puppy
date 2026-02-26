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

from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning

# The prefix character that triggers shell pass-through
SHELL_PASSTHROUGH_PREFIX = "!"


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

    The command's stdout and stderr are inherited from the parent process,
    so output streams directly to the user's terminal — no capture, no
    processing, no token counting. Just raw shell.

    Ctrl+C during execution kills the subprocess, not Code Puppy.

    Args:
        task: Raw user input starting with `!`.
    """
    command = extract_command(task)
    if not command:
        emit_warning("Empty command. Usage: !<command> (e.g., !ls -la)")
        return

    # Show what we're running
    header = Text()
    header.append("🐚 ", style="bold")
    header.append(command, style="bold cyan")
    emit_info(header)

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
            exit_msg = Text()
            exit_msg.append("✅ ", style="bold green")
            exit_msg.append(f"Done ", style="dim")
            exit_msg.append(f"({elapsed:.1f}s)", style="dim")
            emit_success(exit_msg)
        else:
            exit_msg = Text()
            exit_msg.append("❌ ", style="bold red")
            exit_msg.append(
                f"Exit code {result.returncode} ", style="bold red"
            )
            exit_msg.append(f"({elapsed:.1f}s)", style="dim")
            emit_warning(exit_msg)

    except KeyboardInterrupt:
        elapsed = time.monotonic() - start_time
        interrupt_msg = Text()
        interrupt_msg.append("\n⚡ ", style="bold yellow")
        interrupt_msg.append("Interrupted ", style="yellow")
        interrupt_msg.append(f"({elapsed:.1f}s)", style="dim")
        emit_warning(interrupt_msg)

    except Exception as e:
        emit_warning(f"Shell error: {e}")
