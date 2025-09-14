"""
Chat view component for displaying conversation history.
"""

import re
from typing import List

from rich.console import Group
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from textual import on
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ..models import ChatMessage, MessageType
from .copy_button import CopyButton


class ChatView(VerticalScroll):
    """Main chat interface displaying conversation history."""

    DEFAULT_CSS = """
    ChatView {
        background: $background;
        scrollbar-background: $primary;
        scrollbar-color: $accent;
        margin: 0 0 1 0;
        padding: 0;
    }

    .user-message {
        background: $primary-darken-3;
        color: #ffffff;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 1;
        padding-top: 1;
        text-wrap: wrap;
        border: none;
        border-left: thick $accent;
        text-style: bold;
    }

    .agent-message {
        background: transparent;
        color: #f3f4f6;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .system-message {
        background: transparent;
        color: #d1d5db;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-style: italic;
        text-wrap: wrap;
        border: none;
    }

    .error-message {
        background: transparent;
        color: #fef2f2;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .agent_reasoning-message {
        background: transparent;
        color: #f3e8ff;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        text-style: italic;
        border: none;
    }

    .planned_next_steps-message {
        background: transparent;
        color: #f3e8ff;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        text-style: italic;
        border: none;
    }

    .agent_response-message {
        background: transparent;
        color: #f3e8ff;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .info-message {
        background: transparent;
        color: #d1fae5;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .success-message {
        background: #0d9488;
        color: #d1fae5;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .warning-message {
        background: #d97706;
        color: #fef3c7;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .tool_output-message {
        background: #5b21b6;
        color: #dbeafe;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .command_output-message {
        background: #9a3412;
        color: #fed7aa;
        margin: 0 0 1 0;
        margin-top: 0;
        padding: 0;
        padding-top: 0;
        text-wrap: wrap;
        border: none;
    }

    .message-container {
        margin: 0 0 1 0;
        padding: 0;
        width: 1fr;
    }

    .copy-button-container {
        margin: 0 0 1 0;
        padding: 0 1;
        width: 1fr;
        height: auto;
        align: left top;
    }

    /* Ensure first message has no top spacing */
    ChatView > *:first-child {
        margin-top: 0;
        padding-top: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []
        self.message_groups: dict = {}  # Track groups for visual grouping
        self.group_widgets: dict = {}  # Track widgets by group_id for enhanced grouping
        self._scroll_pending = False  # Track if scroll is already scheduled

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

    def _append_to_existing_group(self, message: ChatMessage) -> None:
        """Append a message to an existing group by group_id."""
        if message.group_id not in self.group_widgets:
            # If group doesn't exist, fall back to normal message creation
            return

        # Find the most recent message in this group to append to
        group_widgets = self.group_widgets[message.group_id]
        if not group_widgets:
            return

        # Get the last widget entry for this group
        last_entry = group_widgets[-1]
        last_message = last_entry["message"]
        last_widget = last_entry["widget"]
        copy_button = last_entry.get("copy_button")

        # Create a separator for different message types in the same group
        if message.type != last_message.type:
            separator = "\n" + "─" * 40 + "\n"
        else:
            separator = "\n"

        # Handle content concatenation carefully to preserve Rich objects
        if hasattr(last_message.content, "__rich_console__") or hasattr(
            message.content, "__rich_console__"
        ):
            # If either content is a Rich object, convert both to text and concatenate
            from io import StringIO
            from rich.console import Console

            # Convert existing content to string
            if hasattr(last_message.content, "__rich_console__"):
                string_io = StringIO()
                temp_console = Console(
                    file=string_io, width=80, legacy_windows=False, markup=False
                )
                temp_console.print(last_message.content)
                existing_content = string_io.getvalue().rstrip("\n")
            else:
                existing_content = str(last_message.content)

            # Convert new content to string
            if hasattr(message.content, "__rich_console__"):
                string_io = StringIO()
                temp_console = Console(
                    file=string_io, width=80, legacy_windows=False, markup=False
                )
                temp_console.print(message.content)
                new_content = string_io.getvalue().rstrip("\n")
            else:
                new_content = str(message.content)

            # Combine as plain text
            last_message.content = existing_content + separator + new_content
        else:
            # Both are strings, safe to concatenate
            last_message.content += separator + message.content

        # Update the widget based on message type
        if last_message.type == MessageType.AGENT_RESPONSE:
            # Re-render agent response with updated content
            prefix = "AGENT RESPONSE:\n"
            try:
                md = Markdown(last_message.content)
                header = Text(prefix, style="bold")
                group_content = Group(header, md)
                last_widget.update(group_content)
            except Exception:
                full_content = f"{prefix}{last_message.content}"
                last_widget.update(Text(full_content))

            # Update the copy button if it exists
            if copy_button:
                copy_button.update_text_to_copy(last_message.content)
        else:
            # Handle other message types
            # After the content concatenation above, content is always a string
            # Try to parse markup when safe to do so
            try:
                # Try to parse as markup first - this handles rich styling correctly
                last_widget.update(Text.from_markup(last_message.content))
            except Exception:
                # If markup parsing fails, fall back to plain text
                # This handles cases where content contains literal square brackets
                last_widget.update(Text(last_message.content))

        # Add the new message to our tracking lists
        self.messages.append(message)
        if message.group_id in self.message_groups:
            self.message_groups[message.group_id].append(message)

        # Auto-scroll to bottom with refresh to fix scroll bar issues (debounced)
        self._schedule_scroll()

    def add_message(self, message: ChatMessage) -> None:
        """Add a new message to the chat view."""
        # Enhanced grouping: check if we can append to ANY existing group
        if message.group_id is not None and message.group_id in self.group_widgets:
            self._append_to_existing_group(message)
            return

        # Old logic for consecutive grouping (keeping as fallback)
        if (
            message.group_id is not None
            and self.messages
            and self.messages[-1].group_id == message.group_id
        ):
            # This case should now be handled by _append_to_existing_group above
            # but keeping for safety
            self._append_to_existing_group(message)
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
            # Add user indicator and make it stand out
            content_lines = message.content.split("\n")
            if len(content_lines) > 1:
                # Multi-line user message
                formatted_content = f"╔══ USER ══╗\n{message.content}\n╚══════════╝"
            else:
                # Single line user message
                formatted_content = f"▶ USER: {message.content}"

            message_widget = Static(Text(formatted_content), classes=css_class)
            # User messages are not collapsible - mount directly
            self.mount(message_widget)
            # Auto-scroll to bottom
            self._schedule_scroll()
            return
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

        elif message.type == MessageType.SYSTEM:
            # Check if content is a Rich object (like Markdown)
            if hasattr(message.content, "__rich_console__"):
                # Render Rich objects directly (like Markdown)
                message_widget = Static(message.content, classes=css_class)
            else:
                content = f"{message.content}"
                # Try to render markup
                try:
                    message_widget = Static(
                        Text.from_markup(content), classes=css_class
                    )
                except Exception:
                    message_widget = Static(Text(content), classes=css_class)

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

            # Try to create copy button - use simpler approach
            try:
                # Create copy button for agent responses
                copy_button = CopyButton(content)  # Copy the raw content without prefix

                # Mount the message first
                self.mount(message_widget)

                # Then mount the copy button directly
                self.mount(copy_button)

                # Track both the widget and copy button for group-based updates
                if message.group_id:
                    if message.group_id not in self.group_widgets:
                        self.group_widgets[message.group_id] = []
                    self.group_widgets[message.group_id].append(
                        {
                            "message": message,
                            "widget": message_widget,
                            "copy_button": copy_button,
                        }
                    )

                # Auto-scroll to bottom with refresh to fix scroll bar issues (debounced)
                self._schedule_scroll()
                return  # Early return only if copy button creation succeeded

            except Exception as e:
                # If copy button creation fails, fall back to normal message display
                # Log the error but don't let it prevent the message from showing
                import sys

                print(f"Warning: Copy button creation failed: {e}", file=sys.stderr)
                # Continue to normal message mounting below
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

        # Track the widget for group-based updates
        if message.group_id:
            if message.group_id not in self.group_widgets:
                self.group_widgets[message.group_id] = []
            self.group_widgets[message.group_id].append(
                {
                    "message": message,
                    "widget": message_widget,
                    "copy_button": None,  # Will be set if created
                }
            )

        # Auto-scroll to bottom with refresh to fix scroll bar issues (debounced)
        self._schedule_scroll()

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        self.message_groups.clear()  # Clear groups too
        self.group_widgets.clear()  # Clear widget tracking too
        # Remove all message widgets (Static widgets, CopyButtons, and any Vertical containers)
        for widget in self.query(Static):
            widget.remove()
        for widget in self.query(CopyButton):
            widget.remove()
        for widget in self.query(Vertical):
            widget.remove()

    @on(CopyButton.CopyCompleted)
    def on_copy_completed(self, event: CopyButton.CopyCompleted) -> None:
        """Handle copy button completion events."""
        if event.success:
            # Could add a temporary success message or visual feedback
            # For now, the button itself provides visual feedback
            pass
        else:
            # Show error message in chat if copy failed
            from datetime import datetime, timezone

            error_message = ChatMessage(
                id=f"copy_error_{datetime.now(timezone.utc).timestamp()}",
                type=MessageType.ERROR,
                content=f"Failed to copy to clipboard: {event.error}",
                timestamp=datetime.now(timezone.utc),
            )
            self.add_message(error_message)

    def _schedule_scroll(self) -> None:
        """Schedule a scroll operation, avoiding duplicate calls."""
        if not self._scroll_pending:
            self._scroll_pending = True
            self.call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        """Perform the actual scroll operation."""
        self._scroll_pending = False
        self.scroll_end(animate=False)
