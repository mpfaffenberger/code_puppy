"""Callback registration for the destructive command guard plugin.

Hooks into the run_shell_command phase to intercept destructive shell
commands (rm -rf /, git reset --hard, docker system prune -af, etc.) and
prompt the user for approval before allowing them through.

Returns {"blocked": True} to deny, None to allow.
"""

import sys
from typing import Any, Dict, Optional

from rich.text import Text

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.plugins.destructive_command_guard.detector import (
    detect_destructive_command,
)


def _is_interactive() -> bool:
    """Check if we're in an interactive terminal that can show prompts."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, OSError):
        return False


async def destructive_command_guard_callback(
    context: Any, command: str, cwd: Optional[str] = None, timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """Intercept shell commands containing destructive operations.

    When a destructive command is detected:
    - Interactive TTY: prompt the user with approve/reject options.
    - Non-interactive (CI, sub-agent, piped): hard-block with an error.

    This runs on *every* shell command, but the heavy lifting (regex
    matching) is gated behind a cheap substring pre-filter inside
    detect_destructive_command().

    Args:
        context: Execution context (unused).
        command: The shell command about to run.
        cwd: Working directory (unused).
        timeout: Command timeout (unused).

    Returns:
        None if the command is safe to proceed or user approved it.
        Dict with blocked=True if a destructive command was detected and rejected.
    """
    match = detect_destructive_command(command)
    if match is None:
        return None

    # --- Interactive TTY: ask the user ---
    if _is_interactive():
        return await _prompt_user_approval(command, match)

    # --- Non-interactive: hard-block ---
    return _block_command(command, match)


async def _prompt_user_approval(command: str, match: Any) -> Optional[Dict[str, Any]]:
    """Show an interactive approval prompt for the detected destructive command.

    Args:
        command: The original shell command.
        match: The DestructiveCommandMatch from the detector.

    Returns:
        None if user approves, Dict with blocked=True if rejected.
    """
    from code_puppy.tools.common import get_user_approval_async

    panel_content = Text()
    panel_content.append("⚠️  Destructive command detected: ", style="bold yellow")
    panel_content.append(match.pattern_name, style="bold red")
    panel_content.append("\n", style="")
    panel_content.append(f"  {match.description}", style="dim")
    panel_content.append("\n\n", style="")
    panel_content.append("$ ", style="bold green")
    panel_content.append(command, style="bold white")
    panel_content.append(
        "\n\nThis command could cause irreversible data loss.",
        style="yellow",
    )

    confirmed, user_feedback = await get_user_approval_async(
        title="Destructive Command Guard 🛡️",
        content=panel_content,
        border_style="red",
    )

    if confirmed:
        emit_info("⚠️  Destructive command approved — proceeding with caution.")
        return None  # Allow the command through

    # Rejected
    reason = user_feedback or "User rejected destructive command"
    return {
        "blocked": True,
        "reasoning": f"Destructive command rejected: {match.pattern_name} — {reason}",
        "error_message": (
            f"🛑 Destructive command rejected. Detected {match.pattern_name} "
            f"in command:\n  {command}\n"
            f"  {match.description}\n"
            f"Feedback: {reason}"
        ),
    }


def _block_command(command: str, match: Any) -> Dict[str, Any]:
    """Hard-block a destructive command in non-interactive contexts.

    Args:
        command: The original shell command.
        match: The DestructiveCommandMatch from the detector.

    Returns:
        Dict with blocked=True and a descriptive error.
    """
    error_message = (
        f"🛑 Destructive command blocked! Detected {match.pattern_name} "
        f"in command:\n  {command}\n"
        f"  {match.description}\n\n"
        f"This operation could cause irreversible data loss.\n"
        f"If you *really* need to run this, use the exact command directly\n"
        f"in your terminal (outside code puppy) after double-checking the target."
    )

    emit_warning(error_message)

    return {
        "blocked": True,
        "reasoning": f"Destructive command detected: {match.pattern_name} — {match.description}",
        "error_message": error_message,
    }


def register() -> None:
    """Register the destructive command guard callback."""
    register_callback("run_shell_command", destructive_command_guard_callback)


# Auto-register when this module is imported
register()
