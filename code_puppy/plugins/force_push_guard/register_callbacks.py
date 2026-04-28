"""Callback registration for the force push guard plugin.

Hooks into the run_shell_command phase to intercept git force push
commands and prompt the user for approval before allowing them through.
Returns {"blocked": True} to deny, None to allow.
"""

import sys
from typing import Any, Dict, Optional

from rich.text import Text

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.plugins.force_push_guard.detector import detect_force_push


def _is_interactive() -> bool:
    """Check if we're in an interactive terminal that can show prompts."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, OSError):
        return False


async def force_push_guard_callback(
    context: Any, command: str, cwd: Optional[str] = None, timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """Intercept shell commands containing git force push operations.

    When a force push is detected:
    - Interactive TTY: prompt the user with approve/reject options.
    - Non-interactive (CI, sub-agent, piped): hard-block with an error.

    This runs on *every* shell command, but the heavy lifting (regex
    matching) is gated behind a cheap "push" substring check inside
    detect_force_push().

    Args:
        context: Execution context (unused).
        command: The shell command about to run.
        cwd: Working directory (unused).
        timeout: Command timeout (unused).

    Returns:
        None if the command is safe to proceed or user approved it.
        Dict with blocked=True if a force push was detected and rejected.
    """
    match = detect_force_push(command)
    if match is None:
        return None

    # --- Interactive TTY: ask the user ---
    if _is_interactive():
        return await _prompt_user_approval(command, match)

    # --- Non-interactive: hard-block ---
    return _block_command(command, match)


async def _prompt_user_approval(command: str, match: Any) -> Optional[Dict[str, Any]]:
    """Show an interactive approval prompt for the detected force push.

    Args:
        command: The original shell command.
        match: The ForcePushMatch from the detector.

    Returns:
        None if user approves, Dict with blocked=True if rejected.
    """
    from code_puppy.tools.common import get_user_approval_async

    panel_content = Text()
    panel_content.append("⚠️  Force push detected: ", style="bold yellow")
    panel_content.append(match.pattern_name, style="bold red")
    panel_content.append("\n", style="")
    panel_content.append(f"  {match.description}", style="dim")
    panel_content.append("\n\n", style="")
    panel_content.append("$ ", style="bold green")
    panel_content.append(command, style="bold white")
    panel_content.append(
        "\n\nForce pushing rewrites remote history and can destroy others' work.",
        style="yellow",
    )

    confirmed, user_feedback = await get_user_approval_async(
        title="Force Push Guard 🛡️",
        content=panel_content,
        border_style="red",
    )

    if confirmed:
        emit_info("⚠️  Force push approved — proceeding with caution.")
        return None  # Allow the command through

    # Rejected
    reason = user_feedback or "User rejected force push"
    return {
        "blocked": True,
        "reasoning": f"Force push rejected: {match.pattern_name} — {reason}",
        "error_message": (
            f"🛑 Force push rejected. Detected {match.pattern_name} "
            f"in command:\n  {command}\n"
            f"  {match.description}\n"
            f"Feedback: {reason}"
        ),
    }


def _block_command(command: str, match: Any) -> Dict[str, Any]:
    """Hard-block a force push in non-interactive contexts.

    Args:
        command: The original shell command.
        match: The ForcePushMatch from the detector.

    Returns:
        Dict with blocked=True and a descriptive error.
    """
    error_message = (
        f"🛑 Force push blocked! Detected {match.pattern_name} "
        f"in command:\n  {command}\n"
        f"  {match.description}\n\n"
        f"Force pushing rewrites remote history and can destroy others' work.\n"
        f"If you *really* need to force push, use the exact command directly\n"
        f"in your terminal (outside code puppy) after double-checking the target branch."
    )

    emit_warning(error_message)

    return {
        "blocked": True,
        "reasoning": f"Force push detected: {match.pattern_name} — {match.description}",
        "error_message": error_message,
    }


def register() -> None:
    """Register the force push guard callback."""
    register_callback("run_shell_command", force_push_guard_callback)


# Auto-register when this module is imported
register()
