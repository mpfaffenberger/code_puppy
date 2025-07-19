"""
Chat view component for displaying conversation history.
"""

import re
from typing import List

from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static

from ..models import ChatMessage, MessageType


class ChatView(VerticalScroll):
    """Main chat interface displaying conversation history."""

    DEFAULT_CSS = """
    ChatView {
        background: $background;
        scrollbar-background: $primary;
        scrollbar-color: $accent;
        margin: 1;
        padding: 1;
    }

    .user-message {
        background: #1e3a8a;
        color: #ffffff;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
    }

    .agent-message {
        background: #374151;
        color: #f3f4f6;
        margin: 1 0;
        padding: 1;
        border-left: thick #10b981;
        text-wrap: wrap;
    }

    .system-message {
        background: #1f2937;
        color: #d1d5db;
        margin: 1 0;
        padding: 1;
        text-style: italic;
        border-left: thick #6b7280;
        text-wrap: wrap;
    }

    .error-message {
        background: #7f1d1d;
        color: #fef2f2;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
    }

    .agent_reasoning-message {
        background: #581c87;
        color: #f3e8ff;
        margin: 1 0;
        padding: 1;
        border-left: thick #a855f7;
        text-wrap: wrap;
        text-style: italic;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []

    def _render_agent_message_with_syntax(self, prefix: str, content: str):
        """Render agent message with proper syntax highlighting for code blocks."""
        # Split content by code blocks
        parts = re.split(r"(```[\s\S]*?```)", content)
        rendered_parts = []

        # Add prefix as the first part
        rendered_parts.append(Text(prefix, style="bold"))

        for i, part in enumerate(parts):
            if part.startswith("```") and part.endswith("```"):
                # This is a code block
                lines = part.strip("`").split("\n")
                if lines:
                    # First line might contain language identifier
                    language = lines[0].strip() if lines[0].strip() else "text"
                    code_content = "\n".join(lines[1:]) if len(lines) > 1 else ""

                    if code_content.strip():
                        # Create syntax highlighted code
                        try:
                            syntax = Syntax(
                                code_content,
                                language,
                                theme="github-dark",
                                background_color="default",
                                line_numbers=True,
                                word_wrap=True,
                            )
                            rendered_parts.append(syntax)
                        except Exception:
                            # Fallback to plain text if syntax highlighting fails
                            rendered_parts.append(Text(part))
                    else:
                        rendered_parts.append(Text(part))
                else:
                    rendered_parts.append(Text(part))
            else:
                # Regular text
                if part.strip():
                    rendered_parts.append(Text(part))

        return Group(*rendered_parts)

    def add_message(self, message: ChatMessage) -> None:
        """Add a new message to the chat view."""
        self.messages.append(message)

        # Create the message widget
        css_class = f"{message.type.value}-message"

        if message.type == MessageType.USER:
            content = f"[bold]You:[/bold] {message.content}"
            # Use Static instead of Label to enable text wrapping
            message_widget = Static(content, classes=css_class)
        elif message.type == MessageType.AGENT:
            prefix = "Agent: "
            # Use Static widget with Rich renderable for agent messages to support syntax highlighting
            try:
                # Check if the message contains code blocks
                if "```" in message.content:
                    # Parse and render code blocks with syntax highlighting
                    rendered_content = self._render_agent_message_with_syntax(
                        prefix, message.content
                    )
                    message_widget = Static(rendered_content, classes=css_class)
                else:
                    # Regular text message
                    content = f"[bold]Agent:[/bold] {message.content}"
                    message_widget = Static(content, classes=css_class)
            except Exception:
                # Fallback to Static widget if parsing fails
                content = f"[bold]Agent:[/bold] {message.content}"
                message_widget = Static(content, classes=css_class)
        elif message.type == MessageType.SYSTEM:
            content = f"[bold]System:[/bold] {message.content}"
            message_widget = Static(content, classes=css_class)
        elif message.type == MessageType.AGENT_REASONING:
            content = f"[bold]AGENT REASONING:[/bold] {message.content}"
            message_widget = Static(content, classes=css_class)
        else:  # ERROR
            content = f"[bold]Error:[/bold] {message.content}"
            message_widget = Static(content, classes=css_class)

        self.mount(message_widget)

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        # Remove all message widgets (now only Static widgets)
        for widget in self.query(Static):
            widget.remove()
