"""Callback registration for the force push guard plugin.

Hooks into the run_shell_command phase to intercept and block git force
push commands before they execute. Returns {"blocked": True} to deny
the command, which the command runner handles gracefully.
"""

from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.messaging import emit_info
from code_puppy.plugins.force_push_guard.detector import detect_force_push


async def force_push_guard_callback(
    context: Any, command: str, cwd: Optional[str] = None, timeout: int = 60
) -> Optional[Dict[str, Any]]:
    """Intercept shell commands containing git force push operations.

    This runs on *every* shell command, so the heavy lifting (regex matching)
    is gated behind a cheap "push" substring check inside detect_force_push().

    Args:
        context: Execution context (unused).
        command: The shell command about to run.
        cwd: Working directory (unused).
        timeout: Command timeout (unused).

    Returns:
        None if the command is safe to proceed.
        Dict with blocked=True if a force push pattern was detected.
    """
    match = detect_force_push(command)
    if match is None:
        return None

    error_message = (
        f"🛑 Force push blocked! Detected {match.pattern_name} "
        f"in command:\n  {command}\n"
        f"  {match.description}\n\n"
        f"Force pushing rewrites remote history and can destroy others' work.\n"
        f"If you *really* need to force push, use the exact command directly\n"
        f"in your terminal (outside code puppy) after double-checking the target branch."
    )

    emit_info(error_message)

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
