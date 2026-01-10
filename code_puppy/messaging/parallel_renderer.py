"""Parallel output renderer for multi-agent workflows.

Provides rendering utilities for displaying buffered output from completed
agent sessions in visually distinct Rich panels. Used by Pack Leader to
show results from parallel Husky workers.
"""

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.text import Text

from .messages import AnyMessage, MessageLevel, TextMessage

# =============================================================================
# Status Configuration
# =============================================================================

STATUS_ICONS = {
    "complete": "✅",
    "error": "❌",
    "running": "🔄",
}

STATUS_COLORS = {
    "complete": "green",
    "error": "red",
    "running": "yellow",
}

# =============================================================================
# Header Formatting
# =============================================================================


def format_agent_header(
    agent_name: str,
    session_id: str,
    status: str = "complete",
    message_count: int = 0,
) -> Text:
    """Format the header for an agent output panel.

    Args:
        agent_name: Name of the agent
        session_id: Session ID
        status: Status indicator ("complete", "error", "running")
        message_count: Number of messages in the output

    Returns:
        Rich Text object for the panel header

    Example:
        >>> header = format_agent_header("qa-expert", "qa-abc123", "complete", 5)
        >>> print(header)
        ✅ qa-expert | Session: qa-abc123 | Messages: 5
    """
    icon = STATUS_ICONS.get(status, "⚪")
    color = STATUS_COLORS.get(status, "white")

    header = Text()
    header.append(f"{icon} ", style=Style(color=color, bold=True))
    header.append(agent_name, style=Style(color=color, bold=True))
    header.append(" | ", style="dim")
    header.append("Session: ", style="dim")
    header.append(session_id, style="cyan")
    header.append(" | ", style="dim")
    header.append("Messages: ", style="dim")
    header.append(str(message_count), style="cyan")

    return header


# =============================================================================
# Message Rendering
# =============================================================================


def _render_message_simple(msg: AnyMessage) -> str:
    """Render a single message as simple text for panel display.

    Args:
        msg: The message to render

    Returns:
        Simple string representation of the message
    """
    if isinstance(msg, TextMessage):
        level_icon = {
            MessageLevel.DEBUG: "🔍",
            MessageLevel.INFO: "ℹ️",
            MessageLevel.WARNING: "⚠️",
            MessageLevel.ERROR: "❌",
            MessageLevel.SUCCESS: "✅",
        }.get(msg.level, "•")
        return f"{level_icon} {msg.text}"
    else:
        # For other message types, just show a generic indicator
        return f"• {type(msg).__name__}: {getattr(msg, 'text', getattr(msg, 'content', 'output'))}"


def _format_collapsed_summary(
    messages: List[AnyMessage],
    max_lines: int = 5,
) -> str:
    """Format a collapsed summary showing first N message lines.

    Args:
        messages: List of messages to summarize
        max_lines: Maximum number of lines to show

    Returns:
        Formatted summary string
    """
    if not messages:
        return "[dim]No messages[/dim]"

    lines = []
    for msg in messages[:max_lines]:
        lines.append(_render_message_simple(msg))

    result = "\n".join(lines)

    if len(messages) > max_lines:
        remaining = len(messages) - max_lines
        result += f"\n[dim]... and {remaining} more messages[/dim]"

    return result


def _format_full_output(messages: List[AnyMessage]) -> str:
    """Format full output showing all messages.

    Args:
        messages: List of messages to render

    Returns:
        Formatted output string
    """
    if not messages:
        return "[dim]No messages[/dim]"

    lines = [_render_message_simple(msg) for msg in messages]
    return "\n".join(lines)


# =============================================================================
# Main Rendering Function
# =============================================================================


def render_agent_output(
    messages: List[AnyMessage],
    agent_name: str,
    session_id: str,
    console: Optional[Console] = None,
    collapsed: bool = False,
    max_collapsed_lines: int = 5,
) -> None:
    """Render buffered agent output in a Rich Panel.

    Displays all messages from a completed agent session in a
    visually distinct panel with the agent name and status.

    Args:
        messages: List of buffered messages to render
        agent_name: Name of the agent that produced the output
        session_id: Session ID for reference
        console: Rich Console to use (creates default if None)
        collapsed: If True, show only summary with line count
        max_collapsed_lines: Lines to show when collapsed

    Example:
        >>> from code_puppy.messaging import TextMessage, MessageLevel
        >>> msgs = [
        ...     TextMessage(level=MessageLevel.INFO, text="Starting task"),
        ...     TextMessage(level=MessageLevel.SUCCESS, text="Task complete"),
        ... ]
        >>> render_agent_output(msgs, "husky", "husky-abc123")
        ╭─ ✅ husky | Session: husky-abc123 | Messages: 2 ─────────╮
        │ ℹ️ Starting task                                        │
        │ ✅ Task complete                                         │
        ╰────────────────────────────────────────────────────────╯
    """
    if console is None:
        console = Console()

    # Determine status based on messages
    status = "complete"
    for msg in messages:
        if isinstance(msg, TextMessage) and msg.level == MessageLevel.ERROR:
            status = "error"
            break

    # Format header
    header = format_agent_header(
        agent_name=agent_name,
        session_id=session_id,
        status=status,
        message_count=len(messages),
    )

    # Format content
    if collapsed:
        content = _format_collapsed_summary(messages, max_collapsed_lines)
    else:
        content = _format_full_output(messages)

    # Get border color based on status
    border_color = STATUS_COLORS.get(status, "white")

    # Render panel
    panel = Panel(
        content,
        title=header,
        border_style=Style(color=border_color),
        expand=False,
    )

    console.print(panel)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "render_agent_output",
    "format_agent_header",
    "STATUS_ICONS",
    "STATUS_COLORS",
]
