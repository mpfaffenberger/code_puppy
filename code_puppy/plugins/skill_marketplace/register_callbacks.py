"""Register the /skill-market command with code-puppy's callback system."""

from typing import Optional

from code_puppy.callbacks import register_callback

_registered = False


def _custom_help() -> list[tuple[str, str]]:
    """Provide help text for marketplace commands."""
    return [
        ("skill-market", "Browse & install skills from the E2E Open Skills marketplace"),
    ]


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    """Route skill-market command to the TUI handler."""
    if name == "skill-market":
        from .tui import show_skill_marketplace

        show_skill_marketplace()
        return True
    return None


def register_skill_marketplace_commands() -> None:
    """Register marketplace commands. Safe to call multiple times."""
    global _registered
    if _registered:
        return

    register_callback("custom_command_help", _custom_help)
    register_callback("custom_command", _handle_custom_command)
    _registered = True
