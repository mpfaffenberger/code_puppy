import sys
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass

from rich.text import Text

from code_puppy.config import get_disable_dangerous_command_guard
from code_puppy.messaging import emit_info, emit_warning


@dataclass(frozen=True)
class GuardSpec:
    title: str                  # "Force Push Guard "
    detected_label: str         # "Force push detected: "
    consequence: str            # "Force pushing rewrites remote history..."
    block_advice: str           # "If you *really* need to ... in your terminal ..."
    detect: Callable[[str], Optional[Any]]   # returns match with .pattern_name/.description


async def _prompt_user_approval(spec: GuardSpec, command: str, match: Any) -> Optional[Dict[str, Any]]:
    """Show an interactive approval prompt for the detected destructive command.

    Args:
        command: The original shell command.
        match: The DestructiveCommandMatch from the detector.

    Returns:
        None if user approves, Dict with blocked=True if rejected.
    """
    from code_puppy.tools.common import get_user_approval_async

    panel_content = Text()
    panel_content.append(spec.detected_label, style="bold yellow")
    panel_content.append(match.pattern_name, style="bold red")
    panel_content.append("\n", style="")
    panel_content.append(f"  {match.description}", style="dim")
    panel_content.append("\n\n", style="")
    panel_content.append("$ ", style="bold green")
    panel_content.append(command, style="bold white")
    panel_content.append("\n\n")                                                                                                                                                                                                                    
    panel_content.append(spec.consequence, style="yellow")

    confirmed, user_feedback = await get_user_approval_async(
        title=spec.title,
        content=panel_content,
        border_style="red",
    )

    if confirmed:
        emit_info("⚠️ Command approved — proceeding with caution.")
        return None  # Allow the command through

    # Rejected
    reason = user_feedback or "User rejected command"
    return {
        "blocked": True,
        "reasoning": f"Command rejected: {match.pattern_name} — {reason}",
        "error_message": (
            f"🛑 Command rejected. Detected {match.pattern_name} "
            f"in command:\n  {command}\n"
            f"  {match.description}\n"
            f"Feedback: {reason}"
        ),
    }


def _block_command(spec: GuardSpec, command: str, match: Any) -> Dict[str, Any]:
    """Hard-block a command in non-interactive contexts.

    Args:
        command: The original shell command.
        match: The CommandMatch from the detector.

    Returns:
        Dict with blocked=True and a descriptive error.
    """
    error_message = (
        f"🛑 Command blocked! Detected {match.pattern_name} "
        f"in command:\n  {command}\n"
        f"  {match.description}\n\n"
        f"  {spec.consequence}\n"
        f"  {spec.block_advice}\n"
    )

    emit_warning(error_message)

    return {
        "blocked": True,
        "reasoning": f"Command detected: {match.pattern_name} — {match.description}",
        "error_message": error_message,
    }

def _is_interactive() -> bool:
    """Check if we're in an interactive terminal that can show prompts."""
    try:
        return sys.stdin.isatty()
    except (AttributeError, OSError):
        return False


def make_shell_guard(spec: GuardSpec) -> Callable:
    async def guard(context, command, cwd=None, timeout=60):
        if get_disable_dangerous_command_guard():
            return None
        match = spec.detect(command)
        if match is None:
            return None
        if match.block_immediately or not _is_interactive():
            return _block_command(spec, command, match)

        return await _prompt_user_approval(spec, command, match)   # shared TTY/non-TTY logic
    return guard