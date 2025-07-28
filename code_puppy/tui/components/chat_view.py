"""
Chat view component for displaying conversation history.
"""

import re
from typing import List

from rich.console import Group
from rich.markdown import Markdown
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
        border: round $primary;
    }

    .agent-message {
        background: #374151;
        color: #f3f4f6;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .system-message {
        background: #1f2937;
        color: #d1d5db;
        margin: 1 0;
        padding: 1;
        text-style: italic;
        text-wrap: wrap;
        border: round $primary;
    }

    .error-message {
        background: #7f1d1d;
        color: #fef2f2;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .agent_reasoning-message {
        background: #1f2937;
        color: #f3e8ff;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        text-style: italic;
        border: round $primary;
    }

    .planned_next_steps-message {
        background: #1f2937;
        color: #f3e8ff;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        text-style: italic;
        border: round $primary;
    }

    .agent_response-message {
        background: #1f2937;
        color: #f3e8ff;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .info-message {
        background: #065f46;
        color: #d1fae5;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .success-message {
        background: #064e3b;
        color: #d1fae5;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .warning-message {
        background: #92400e;
        color: #fef3c7;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .tool_output-message {
        background: #1e40af;
        color: #dbeafe;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }

    .command_output-message {
        background: #7c2d12;
        color: #fed7aa;
        margin: 1 0;
        padding: 1;
        text-wrap: wrap;
        border: round $primary;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []
        self.message_groups: dict = {}  # Track groups for visual grouping

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
        # Handle grouping for ANY message type with same group_id
        if (
            message.group_id is not None
            and self.messages
            and self.messages[-1].group_id == message.group_id
        ):
            # Concatenate with the previous grouped message
            previous_message = self.messages[-1]

            # Create a separator for different message types in the same group
            if message.type != previous_message.type:
                separator = "\n" + "─" * 40 + "\n"
            else:
                separator = "\n"

            previous_message.content += separator + message.content

            # Update the existing widget with the concatenated content
            static_widgets = list(self.query(Static))
            if static_widgets:
                last_widget = static_widgets[-1]
                content = f"{previous_message.content}"

                # Apply the same rendering logic as below
                if (
                    "[" in previous_message.content
                    and "]" in previous_message.content
                    and (
                        previous_message.content.strip().startswith("$ ")
                        or previous_message.content.strip().startswith("git ")
                    )
                ):
                    # Treat as literal text
                    last_widget.update(Text(content))
                else:
                    # Try to render markup
                    try:
                        last_widget.update(Text.from_markup(content))
                    except Exception:
                        last_widget.update(Text(content))

            # Auto-scroll to bottom
            self.scroll_end(animate=True)
            return

        # Add to messages list
        self.messages.append(message)

        # Track groups for potential future use
        if message.group_id:
            if message.group_id not in self.message_groups:
                self.message_groups[message.group_id] = []
            self.message_groups[message.group_id].append(message)

        # Create the message widget
        css_class = f"{message.type.value}-message"

        if message.type == MessageType.USER:
            content = f"{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.AGENT:
            prefix = "AGENT: "
            content = f"{message.content}"
            message_widget = Static(
                Text.from_markup(message.content), classes=css_class
            )
            # Try to render markup
            try:
                message_widget = Static(Text.from_markup(content), classes=css_class)
            except Exception:
                message_widget = Static(Text(content), classes=css_class)

            # prefix = ""
            # try:
            #     if "```" in message.content:
            #         rendered_content = self._render_agent_message_with_syntax(
            #             prefix, message.content
            #         )
            #         message_widget = Static(rendered_content, classes=css_class)
            #     else:
            #         content = f"{message.content}"
            #         message_widget = Static(Text(content), classes=css_class)
            # except Exception:
            #     content = f"{message.content}"
            #     message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.SYSTEM:
            content = f"{message.content}"
            # Try to render markup
            try:
                message_widget = Static(Text.from_markup(content), classes=css_class)
            except Exception:
                message_widget = Static(Text(content), classes=css_class)

            # Heuristic: if message looks like a command with markup tags, treat as markup
            # if (
            #     "[" in message.content
            #     and "]" in message.content
            #     and (
            #         message.content.strip().startswith("$ ")
            #         or message.content.strip().startswith("git ")
            #     )
            # ):
            #     # Treat as literal text
            #     message_widget = Static(Text(content), classes=css_class)
            # else:
            #     # Try to render markup
            #     try:
            #         message_widget = Static(
            #             Text.from_markup(content), classes=css_class
            #         )
            #     except Exception:
            # message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.AGENT_REASONING:
            prefix = "AGENT REASONING:\n"
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.PLANNED_NEXT_STEPS:
            prefix = "PLANNED NEXT STEPS:\n"
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.AGENT_RESPONSE:
            prefix = "AGENT RESPONSE:\n"
            content = message.content

            try:
                # First try to render as markdown with proper syntax highlighting
                md = Markdown(content)
                # Create a group with the header and markdown content
                header = Text(prefix, style="bold")
                group_content = Group(header, md)
                message_widget = Static(group_content, classes=css_class)
            except Exception:
                # If markdown parsing fails, fall back to simple text display
                full_content = f"{prefix}{content}"
                message_widget = Static(Text(full_content), classes=css_class)
        elif message.type == MessageType.INFO:
            prefix = "INFO: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.SUCCESS:
            prefix = "SUCCESS: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.WARNING:
            prefix = "WARNING: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.TOOL_OUTPUT:
            prefix = "TOOL OUTPUT: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        elif message.type == MessageType.COMMAND_OUTPUT:
            prefix = "COMMAND: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)
        else:  # ERROR and fallback
            prefix = "Error: " if message.type == MessageType.ERROR else "Unknown: "
            content = f"{prefix}{message.content}"
            message_widget = Static(Text(content), classes=css_class)

        self.mount(message_widget)

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        self.message_groups.clear()  # Clear groups too
        # Remove all message widgets (now only Static widgets)
        for widget in self.query(Static):
            widget.remove()
