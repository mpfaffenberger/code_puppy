"""Common display utilities for rendering agent outputs.

This module provides non-streaming display functions for rendering
agent results and other structured content using termflow for markdown.
"""

from typing import Optional

from rich.console import Console

from code_puppy.config import get_banner_color, get_subagent_verbose
from code_puppy.tools.subagent_context import is_subagent


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
    # Skip display for sub-agents unless verbose mode
    if is_subagent() and not get_subagent_verbose():
        return

    import time

    from rich.text import Text
    from termflow import Parser as TermflowParser
    from termflow import Renderer as TermflowRenderer

    from code_puppy.messaging.spinner import pause_all_spinners, resume_all_spinners

    if console is None:
        console = Console()

    # Pause spinners and give time to clear
    pause_all_spinners()
    time.sleep(0.1)

    # Clear line and print banner
    console.print(" " * 50, end="\r")
    console.print()  # Newline before banner

    banner_color = get_banner_color(banner_name)
    console.print(
        Text.from_markup(
            f"[bold white on {banner_color}] {banner_text} [/bold white on {banner_color}]"
        )
    )

    # Use termflow for markdown rendering
    parser = TermflowParser()
    renderer = TermflowRenderer(output=console.file, width=console.width)

    # Process content line by line
    for line in content.split("\n"):
        events = parser.parse_line(line)
        renderer.render_all(events)

    # Finalize to close any open markdown blocks
    final_events = parser.finalize()
    renderer.render_all(final_events)

    # Resume spinners
    resume_all_spinners()


__all__ = ["display_non_streamed_result"]
