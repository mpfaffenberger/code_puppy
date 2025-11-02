"""
Chat view component for displaying conversation history.
"""

import re
from typing import List

from rich.console import Group
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Static

from ..models import ChatMessage, MessageCategory, MessageType, get_message_category


class ChatView(VerticalScroll):
    """Main chat interface displaying conversation history."""

    DEFAULT_CSS = """
    ChatView {
        background: $surface;
        scrollbar-background: $panel;
        scrollbar-color: $primary;
        scrollbar-color-hover: $primary-lighten-1;
        scrollbar-color-active: $primary-darken-1;
        margin: 0 0 1 0;
        padding: 1 2;
    }

    .user-message {
        background: $primary-background;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: tall $primary;
        border-title-align: left;
        text-style: bold;
    }

    .agent-message {
        background: $panel;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: round $panel-lighten-2;
    }

    .system-message {
        background: $panel;
        color: $text-muted;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-style: italic;
        text-wrap: wrap;
        border: dashed $panel-lighten-1;
    }

    .error-message {
        background: $error-darken-2;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: heavy $error;
        border-title-align: left;
    }

    .agent_reasoning-message {
        background: $accent-darken-2;
        color: $accent-lighten-2;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        text-style: italic;
        border: round $accent;
    }

    .planned_next_steps-message {
        background: $accent-darken-2;
        color: $accent-lighten-3;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        text-style: italic;
        border: round $accent-lighten-1;
    }

    .agent_response-message {
        background: $panel;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: double $accent;
    }

    .info-message {
        background: $success-darken-3;
        color: $success-lighten-2;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: round $success;
    }

    .success-message {
        background: $success-darken-1;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: heavy $success;
        border-title-align: center;
    }

    .warning-message {
        background: $warning-darken-2;
        color: $text;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: wide $warning;
        border-title-align: left;
    }

    .tool_output-message {
        background: $accent-darken-3;
        color: $accent-lighten-2;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: round $accent-darken-1;
    }

    .command_output-message {
        background: $warning-darken-3;
        color: $warning-lighten-2;
        margin: 1 0 1 0;
        padding: 1 2;
        height: auto;
        text-wrap: wrap;
        border: solid $warning-darken-1;
    }

    .message-container {
        margin: 0 0 1 0;
        padding: 0;
        width: 1fr;
    }

    /* Ensure first message has no top spacing */
    ChatView > *:first-child {
        margin-top: 0;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []
        self.message_groups: dict = {}  # Track groups for visual grouping
        self.group_widgets: dict = {}  # Track widgets by group_id for enhanced grouping
        self._scroll_pending = False  # Track if scroll is already scheduled
        self._last_message_category = None  # Track last message category for combining
        self._last_widget = None  # Track the last widget created for combining
        self._last_combined_message = (
            None  # Track the actual message we're combining into
        )

    def _should_suppress_message(self, message: ChatMessage) -> bool:
        """Check if a message should be suppressed based on user settings."""
        from code_puppy.config import (
            get_suppress_informational_messages,
            get_suppress_thinking_messages,
        )

        category = get_message_category(message.type)

        suppress_thinking = get_suppress_thinking_messages()
        suppress_info = get_suppress_informational_messages()

        # Check if thinking messages should be suppressed
        if category == MessageCategory.THINKING and suppress_thinking:
            return True

        # Check if informational messages should be suppressed
        if category == MessageCategory.INFORMATIONAL and suppress_info:
            return True

        return False

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
        # First check if this message should be suppressed
        if self._should_suppress_message(message):
            return  # Skip this message entirely

        # Get message category for combining logic
        message_category = get_message_category(message.type)

        # Enhanced grouping: check if we can append to ANY existing group
        if message.group_id is not None and message.group_id in self.group_widgets:
            self._append_to_existing_group(message)
            self._last_message_category = message_category
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
            self._last_message_category = message_category
            return

        # Category-based combining - combine consecutive messages of same category

        if (
            self.messages
            and self._last_message_category == message_category
            and self._last_widget is not None  # Make sure we have a widget to update
            and self._last_combined_message
            is not None  # Make sure we have a message to combine into
            and message_category
            != MessageCategory.AGENT_RESPONSE  # Don't combine agent responses (they're complete answers)
        ):
            # SAME CATEGORY: Add to existing container
            last_message = (
                self._last_combined_message
            )  # Use tracked message, not messages[-1]

            # Create a separator for different message types within the same category
            if message.type != last_message.type:
                # Different types but same category - add a visual separator
                separator = f"\n\n[dim]── {message.type.value.replace('_', ' ').title()} ──[/dim]\n"
            else:
                # Same type - simple spacing
                separator = "\n\n"

            # Append content to the last message
            if hasattr(last_message.content, "__rich_console__") or hasattr(
                message.content, "__rich_console__"
            ):
                # Handle Rich objects by converting to strings
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

            # Update the tracked widget with the combined content
            if self._last_widget is not None:
                try:
                    # Update the widget with the new combined content
                    self._last_widget.update(Text.from_markup(last_message.content))
                    # Force layout recalculation so the container grows
                    self._last_widget.refresh(layout=True)
                except Exception:
                    # If markup parsing fails, fall back to plain text
                    try:
                        self._last_widget.update(Text(last_message.content))
                        # Force layout recalculation so the container grows
                        self._last_widget.refresh(layout=True)
                    except Exception:
                        # If update fails, create a new widget instead
                        pass

            # Add to messages list but don't create a new widget
            self.messages.append(message)
            # Refresh the entire view to ensure proper layout
            self.refresh(layout=True)
            self._schedule_scroll()
            return

        # DIFFERENT CATEGORY: Create new container
        # Reset tracking so we don't accidentally update the wrong widget
        if self._last_message_category != message_category:
            self._last_widget = None
            self._last_message_category = None
            self._last_combined_message = None

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
            # Track this widget for potential combining
            self._last_widget = message_widget
            # Track the category of this message for future combining
            self._last_message_category = message_category
            # Track the actual message for combining
            self._last_combined_message = message
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

            # Make message selectable for easy copying
            message_widget.can_focus = False  # Don't interfere with navigation

            # Mount the message
            self.mount(message_widget)

            # Track this widget for potential combining
            self._last_widget = message_widget
            # Track the category of this message for future combining
            self._last_message_category = message_category
            # Track the actual message for combining
            self._last_combined_message = message

            # Track widget for group-based updates
            if message.group_id:
                if message.group_id not in self.group_widgets:
                    self.group_widgets[message.group_id] = []
                self.group_widgets[message.group_id].append(
                    {
                        "message": message,
                        "widget": message_widget,
                    }
                )

            # Auto-scroll to bottom with refresh to fix scroll bar issues (debounced)
            self._schedule_scroll()
            return
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

        # Track this widget for potential combining
        self._last_widget = message_widget

        # Track the widget for group-based updates
        if message.group_id:
            if message.group_id not in self.group_widgets:
                self.group_widgets[message.group_id] = []
            self.group_widgets[message.group_id].append(
                {
                    "message": message,
                    "widget": message_widget,
                }
            )

        # Auto-scroll to bottom with refresh to fix scroll bar issues (debounced)
        self._schedule_scroll()

        # Track the category of this message for future combining
        self._last_message_category = message_category
        # Track the actual message for combining (use the message we just added)
        self._last_combined_message = self.messages[-1] if self.messages else None

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        self.message_groups.clear()  # Clear groups too
        self.group_widgets.clear()  # Clear widget tracking too
        self._last_message_category = None  # Reset category tracking
        self._last_widget = None  # Reset widget tracking
        self._last_combined_message = None  # Reset combined message tracking
        # Remove all message widgets (Static widgets and any Vertical containers)
        for widget in self.query(Static):
            widget.remove()
        for widget in self.query(Vertical):
            widget.remove()

    def _schedule_scroll(self) -> None:
        """Schedule a scroll operation, avoiding duplicate calls."""
        if not self._scroll_pending:
            self._scroll_pending = True
            self.call_after_refresh(self._do_scroll)

    def _do_scroll(self) -> None:
        """Perform the actual scroll operation."""
        self._scroll_pending = False
        self.scroll_end(animate=False)
