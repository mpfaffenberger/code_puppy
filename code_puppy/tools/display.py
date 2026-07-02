"""Common display utilities for rendering agent outputs.

This module provides non-streaming display functions for rendering
agent results and other structured content using termflow for markdown.
"""

from typing import Optional

from rich.console import Console
from rich.control import Control
from rich.segment import ControlType

from code_puppy.config import get_banner_color, get_output_level, get_subagent_verbose
from code_puppy.tools.subagent_context import is_subagent

#: EL2 (erase entire line) + CR. Rich drops control segments on
#: non-terminal output, so headless/piped runs stay byte-identical.
_ERASE_LINE_CONTROL = Control(
    (ControlType.ERASE_IN_LINE, 2), ControlType.CARRIAGE_RETURN
)


def erase_progress_line(console: Console) -> None:
    """Erase the current terminal line (the ``\\r``-overwrite slot).

    Replaces the old ``console.print(" " * 50, end="\\r")`` idiom, which
    assumed progress lines never exceed 50 cells. Longer lines (e.g.
    ``  \U0001f527 Calling agent_run_shell_command... 348 token(s)`` = 52+
    cells) left right-edge ghost tails like ``s)`` in the transcript.
    Erase-in-line clears the whole row regardless of length.
    """
    console.control(_ERASE_LINE_CONTROL)


def display_non_streamed_result(
    content: str,
    console: Optional[Console] = None,
    banner_text: str = "AGENT RESPONSE",
    banner_name: str = "agent_response",
) -> None:
    """Display a non-streamed result with markdown rendering via termflow.

    This function renders markdown content using termflow for beautiful
    terminal output. Use this instead of streaming for sub-agent responses
    or any other content that arrives all at once.

    Args:
        content: The content to display (can include markdown).
        console: Rich Console to use for output. If None, creates a new one.
        banner_text: Text to display in the banner (default: "AGENT RESPONSE").
        banner_name: Banner config key for color lookup (default: "agent_response").

    Example:
        >>> display_non_streamed_result("# Hello\n\nThis is **bold** text.")
        # Renders with AGENT RESPONSE banner and formatted markdown
    """
    # Skip display for sub-agents unless verbose mode or high output level.
    # In ``high`` mode the user has asked for maximum visibility, so sub-agent
    # responses must render regardless of the legacy ``subagent_verbose`` toggle.
    if is_subagent() and not get_subagent_verbose() and get_output_level() != "high":
        return

    from rich.text import Text
    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer
    from termflow.render.style import RenderFeatures

    if console is None:
        console = Console()

    # Clear any \r-repainted progress line, then move below it
    erase_progress_line(console)
    console.print()  # Newline before banner

    banner_color = get_banner_color(banner_name)
    console.print(
        Text.from_markup(
            f"[bold white on {banner_color}] {banner_text} [/bold white on {banner_color}]"
        )
    )

    # Use termflow for markdown rendering
    parser = TermflowParser()
    renderer = TermflowRenderer(
        output=console.file,
        width=console.width,
        features=RenderFeatures(clipboard=False),
    )

    # Process content line by line
    for line in content.split("\n"):
        events = parser.parse_line(line)
        renderer.render_all(events)

    # Finalize to close any open markdown blocks
    final_events = parser.finalize()
    renderer.render_all(final_events)


__all__ = ["display_non_streamed_result", "erase_progress_line"]
