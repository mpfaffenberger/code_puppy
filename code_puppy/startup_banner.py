"""Shared interactive-startup presentation (logo + help lines).

Both the classic interactive loop (``cli_runner.interactive_mode``) and the
Textual TUI (``tui.app.CooperApp.on_mount``) greet the user with the same
``CODE PUPPY`` logo and a block of help text. Keeping that here means one
source of truth (DRY) instead of two copies drifting apart.

The help text is *mode-aware*: a few classic hints (Ctrl+C to cancel, Alt+M
to toggle multiline, Ctrl+V image paste) are simply wrong for the Textual UI,
which cancels with Esc, steers with Ctrl+T, and is always multiline. We emit
the correct variant for each.
"""

from __future__ import annotations

import platform

from rich.text import Text

from code_puppy.keymap import (
    get_cancel_agent_display_name,
    get_pause_agent_display_name,
)
from code_puppy.messaging import emit_system_message

# Top-to-bottom blue -> cyan -> green gradient for the figlet logo.
_GRADIENT_COLORS = ["bright_blue", "bright_cyan", "bright_green"]

# Unicode escapes (not literal emoji) so they survive emoji-stripping filters.
_LIGHTBULB = "\U0001f4a1"  #
_DOG = "\U0001f436"  #


def build_logo_renderable() -> Text | None:
    """Return the gradient ``CODE PUPPY`` figlet logo as a Rich renderable.

    Returns ``None`` when ``pyfiglet`` isn't installed so callers can fall
    back to a plain greeting.
    """
    try:
        import pyfiglet
    except ImportError:
        return None

    intro_lines = pyfiglet.figlet_format("CODE PUPPY", font="ansi_shadow").split("\n")
    logo = Text()
    for line_num, line in enumerate(intro_lines):
        if line.strip():
            color_idx = min(line_num // 2, len(_GRADIENT_COLORS) - 1)
            logo.append(line + "\n", style=_GRADIENT_COLORS[color_idx])
        else:
            logo.append("\n")
    return logo


def emit_logo_fallback() -> None:
    """Emit a plain greeting when the figlet logo can't be built."""
    emit_system_message(f"{_DOG} Code Puppy is Loading...")


def emit_interactive_help(textual: bool = False) -> None:
    """Emit the interactive-mode help lines through the message bus.

    Both UIs consume the legacy queue, so this works in either mode — it just
    has to actually be *called* from each startup path. The truecolor warning
    is intentionally excluded (it's classic-only).
    """
    emit_system_message(
        "Type '/exit', '/quit', or press Ctrl+D to exit the interactive mode."
        if not textual
        else "Type '/exit' or '/quit' to exit. Ctrl+Q also quits."
    )
    emit_system_message("Type 'clear' to reset the conversation history.")
    emit_system_message("Type /help to view all commands")
    emit_system_message(
        "Type @ for path completion, or /model to pick a model. "
        + (
            "Shift+Enter inserts a newline; Enter submits."
            if textual
            else "Toggle multiline with Alt+M or F2; newline: Ctrl+J."
        )
    )

    if textual:
        emit_system_message(
            "Press Esc to cancel the running task. "
            "Press Ctrl+T to pause and inject a steering message. "
            "Press Ctrl+P for the command palette."
        )
    else:
        emit_system_message(
            "Paste images: Ctrl+V (even on Mac!), F3, or /paste command."
        )
        if platform.system() == "Darwin":
            emit_system_message(
                f"{_LIGHTBULB} macOS tip: Use Ctrl+V (not Cmd+V) to paste images in terminal."
            )
        cancel_key = get_cancel_agent_display_name()
        emit_system_message(
            f"Press {cancel_key} during processing to cancel the current task or "
            "inference. Use Ctrl+X to interrupt running shell commands."
        )
        pause_key = get_pause_agent_display_name()
        emit_system_message(
            f"Press {pause_key} during processing to pause the agent and inject a "
            "steering message."
        )

    emit_system_message(
        "Use /autosave_load to manually load a previous autosave session."
    )
    emit_system_message(
        "Use /diff to configure diff highlighting colors for file changes."
    )
    emit_system_message("To re-run the tutorial, use /tutorial.")
    emit_system_message(
        "!<command> to run shell commands directly (e.g., !git status)",
    )
