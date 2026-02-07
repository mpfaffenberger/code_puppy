"""Rich markup emission helper for gui-cub.

This module provides a helper function to emit Rich-formatted messages
that render correctly even when running as a sub-agent.

The standard emit_info() escapes Rich markup to prevent crashes from
malformed tags in shell output. This helper pre-renders the markup
into a Rich Text object which bypasses the escaping.
"""

from __future__ import annotations

from typing import Any

from rich.markup import MarkupError
from rich.text import Text

from code_puppy.messaging import emit_info

__all__ = ["emit_rich"]


def emit_rich(message: str | Text, **kwargs: Any) -> None:
    """Emit a message with Rich markup that will render correctly.

    This wraps emit_info() with Text.from_markup() to ensure Rich
    formatting tags like [bold], [green], [dim] are rendered as
    styles rather than being escaped to literal text.

    If the message is already a Text object, it's passed through directly.
    If the message contains malformed Rich tags, falls back to emitting
    the message as literal text.

    Args:
        message: A string containing Rich markup or a Text object
        **kwargs: Additional arguments passed to emit_info (e.g., message_group)

    Example:
        emit_rich("[bold green]Success![/bold green] Task completed.")
        emit_rich(f"[cyan]Processing[/cyan] {filename}", message_group=group_id)
    """
    # If already a Text object, pass through directly
    if isinstance(message, Text):
        emit_info(message, **kwargs)
        return

    try:
        emit_info(Text.from_markup(message), **kwargs)
    except MarkupError:
        # Fallback to literal text if markup is malformed
        emit_info(message, **kwargs)
