"""
Code Puppy Textual UI Module

This module provides a modern TUI interface for Code Puppy using the Textual framework.
It maintains compatibility with existing functionality while providing an enhanced user experience.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from enum import Enum

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header, Footer, Static, Input, Button, ListView, ListItem,
    Label, RichLog, TextArea, TabbedContent, TabPane, ProgressBar,
    Select
)
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual import on, work
from textual.events import Key, Resize
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
import re

# Import existing Code Puppy components
from code_puppy.agent import get_code_generation_agent, session_memory
from code_puppy.config import get_model_name, get_puppy_name, get_owner_name, get_yolo_mode
from code_puppy.command_line.meta_command_handler import handle_meta_command
from code_puppy.tools.common import console as rich_console


class MessageType(Enum):
    """Types of messages in the chat interface."""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    ERROR = "error"


@dataclass
class ChatMessage:
    """Represents a message in the chat interface."""
    id: str
    type: MessageType
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CustomTextArea(TextArea):
    """Custom TextArea that sends a message with Enter and allows new lines with Shift+Enter."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _on_key(self, event: Key) -> None:
        """Override internal key handler to intercept Enter keys."""
        # Handle Enter specifically
        if event.key == "enter":
            # Plain Enter: send message
            self.post_message(self.MessageSent())
            return  # Don't call super() to prevent default newline behavior

        # For all other keys, use the default TextArea behavior
        super()._on_key(event)

    class MessageSent(Message):
        """Message sent when Enter key is pressed (without Shift)."""
        pass


class StatusBar(Static):
    """Status bar showing current model, puppy name, and connection status."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: right;
        padding: 0 1;
    }

    #status-content {
        text-align: right;
        width: 100%;
    }
    """

    current_model = reactive("")
    puppy_name = reactive("")
    connection_status = reactive("Connected")
    agent_status = reactive("Ready")
    progress_visible = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static(id="status-content")

    def watch_current_model(self) -> None:
        self.update_status()

    def watch_puppy_name(self) -> None:
        self.update_status()

    def watch_connection_status(self) -> None:
        self.update_status()

    def watch_agent_status(self) -> None:
        self.update_status()

    def watch_progress_visible(self) -> None:
        self.update_status()

    def update_status(self) -> None:
        """Update the status bar content with responsive design."""
        from rich.text import Text
        import os

        status_widget = self.query_one("#status-content", Static)

        # Get current working directory
        cwd = os.getcwd()
        cwd_short = os.path.basename(cwd) if cwd != "/" else "/"

        # Add agent status indicator with different colors
        if self.agent_status == "Thinking":
            status_indicator = "🤔"
            status_color = "yellow"
        elif self.agent_status == "Processing":
            status_indicator = "⚡"
            status_color = "blue"
        elif self.agent_status == "Busy":
            status_indicator = "🔄"
            status_color = "orange"
        else:  # Ready
            status_indicator = "✅"
            status_color = "green"

        # Get terminal width for responsive content
        try:
            terminal_width = self.app.size.width if hasattr(self.app, 'size') else 80
        except:
            terminal_width = 80

        # Create responsive status text based on terminal width
        rich_text = Text()

        if terminal_width >= 120:
            # Extra wide - show full path and all info
            rich_text.append(f"📁 {cwd} | 🐶 {self.puppy_name} | Model: {self.current_model} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 100:
            # Full status display for wide terminals
            rich_text.append(f"📁 {cwd_short} | 🐶 {self.puppy_name} | Model: {self.current_model} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 80:
            # Medium display - shorten model name if needed
            model_display = self.current_model[:15] + "..." if len(self.current_model) > 18 else self.current_model
            rich_text.append(f"📁 {cwd_short} | 🐶 {self.puppy_name} | {model_display} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 60:
            # Compact display - use abbreviations
            puppy_short = self.puppy_name[:8] + "..." if len(self.puppy_name) > 10 else self.puppy_name
            model_short = self.current_model[:12] + "..." if len(self.current_model) > 15 else self.current_model
            rich_text.append(f"📁 {cwd_short} | 🐶 {puppy_short} | {model_short} | ")
            rich_text.append(f"{status_indicator}", style=status_color)
        else:
            # Minimal display for very narrow terminals
            cwd_mini = cwd_short[:8] + "..." if len(cwd_short) > 10 else cwd_short
            rich_text.append(f"📁 {cwd_mini} | ")
            rich_text.append(f"{status_indicator}", style=status_color)

        rich_text.justify = "right"
        status_widget.update(rich_text)


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
    }

    .agent-message {
        background: #374151;
        color: #f3f4f6;
        margin: 1 0;
        padding: 1;
        border-left: thick #10b981;
    }

    .system-message {
        background: #1f2937;
        color: #d1d5db;
        margin: 1 0;
        padding: 1;
        text-style: italic;
        border-left: thick #6b7280;
    }

    .error-message {
        background: #7f1d1d;
        color: #fef2f2;
        margin: 1 0;
        padding: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []

    def _render_agent_message_with_syntax(self, prefix: str, content: str):
        """Render agent message with proper syntax highlighting for code blocks."""
        from rich.console import Group
        from rich.text import Text

        # Split content by code blocks
        parts = re.split(r'(```[\s\S]*?```)', content)
        rendered_parts = []

        # Add prefix as the first part
        rendered_parts.append(Text(prefix, style="bold"))

        for i, part in enumerate(parts):
            if part.startswith('```') and part.endswith('```'):
                # This is a code block
                lines = part.strip('`').split('\n')
                if lines:
                    # First line might contain language identifier
                    language = lines[0].strip() if lines[0].strip() else "text"
                    code_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""

                    if code_content.strip():
                        # Create syntax highlighted code
                        try:
                            syntax = Syntax(
                                code_content,
                                language,
                                theme="github-dark",
                                background_color="default",
                                line_numbers=True,
                                word_wrap=True
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
        timestamp_str = message.timestamp.strftime("%H:%M:%S")

        if message.type == MessageType.USER:
            content = f"[{timestamp_str}] You: {message.content}"
            message_widget = Label(content, classes=css_class)
        elif message.type == MessageType.AGENT:
            prefix = f"[{timestamp_str}] Agent: "
            # Use Static widget with Rich renderable for agent messages to support syntax highlighting
            try:
                # Check if the message contains code blocks
                if '```' in message.content:
                    # Parse and render code blocks with syntax highlighting
                    rendered_content = self._render_agent_message_with_syntax(prefix, message.content)
                    message_widget = Static(rendered_content, classes=css_class)
                else:
                    # Regular text message
                    content = f"[{timestamp_str}] Agent: {message.content}"
                    message_widget = Label(content, classes=css_class)
            except Exception:
                # Fallback to simple label if parsing fails
                content = f"[{timestamp_str}] Agent: {message.content}"
                message_widget = Label(content, classes=css_class)
        elif message.type == MessageType.SYSTEM:
            content = f"[{timestamp_str}] System: {message.content}"
            message_widget = Label(content, classes=css_class)
        else:  # ERROR
            content = f"[{timestamp_str}] Error: {message.content}"
            message_widget = Label(content, classes=css_class)

        self.mount(message_widget)

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        # Remove all message widgets (both Label and Static)
        for widget in self.query(Label):
            widget.remove()
        for widget in self.query(Static):
            widget.remove()


class InputArea(Container):
    """Input area with text input, progress bar, help text, and send button."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: 9;
        margin: 1;
    }

    #input-field {
        height: 5;
        width: 1fr;
        margin: 1 3 0 1;
        border: round $primary;
        background: $surface;
    }

    #input-help {
        height: 1;
        width: 1fr;
        margin: 0 3 1 1;
        color: $text-muted;
        text-align: center;
    }

    #progress-bar {
        height: 1;
        width: 1fr;
        margin: 0 3 0 1;
        display: none;
    }

    #progress-bar.visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        yield ProgressBar(id="progress-bar", show_eta=False)
        yield CustomTextArea(
            id="input-field",
            show_line_numbers=False
        )
        yield Static("Enter to send • Ctrl+Enter for new line", id="input-help")


class Sidebar(Container):
    """Sidebar with session history."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 30;
        min-width: 20;
        max-width: 50;
        background: $surface;
        border-right: solid $primary;
        display: none;
    }

    #sidebar-title {
        dock: top;
        height: 3;
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
    }

    #history-list {
        height: 1fr;
    }

    .history-interactive {
        color: #34d399;
    }

    .history-tui {
        color: #60a5fa;
    }

    .history-system {
        color: #fbbf24;
        text-style: italic;
    }

    .history-command {
        color: #f87171;
    }

    .history-generic {
        color: #d1d5db;
    }

    .history-empty {
        color: #6b7280;
        text-style: italic;
    }

    .history-error {
        color: #ef4444;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("📜 Session History", id="sidebar-title")
        yield ListView(id="history-list")


class SettingsScreen(ModalScreen):
    """Settings configuration screen."""

    DEFAULT_CSS = """
    SettingsScreen {
        align: center middle;
    }

    #settings-dialog {
        width: 80;
        height: 33;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #settings-form {
        height: 1fr;
    }

    .setting-row {
        layout: horizontal;
        height: 3;
        margin: 0 0 1 0;
    }

    .setting-label {
        width: 20;
        text-align: right;
        padding: 1 1 0 0;
    }

    .setting-input {
        width: 1fr;
        margin: 0 0 0 1;
    }

    #settings-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #save-button, #cancel-button {
        margin: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.settings_data = {}

    def compose(self) -> ComposeResult:
        with Container(id="settings-dialog"):
            yield Static("⚙️  Settings Configuration", id="settings-title")
            with Container(id="settings-form"):
                with Container(classes="setting-row"):
                    yield Static("Puppy Name:", classes="setting-label")
                    yield Input(id="puppy-name-input", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("Owner Name:", classes="setting-label")
                    yield Input(id="owner-name-input", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("Model:", classes="setting-label")
                    yield Select([], id="model-select", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("YOLO Mode:", classes="setting-label")
                    yield Select([("Enabled", "true"), ("Disabled", "false")], value="false", id="yolo-select", classes="setting-input")

                with Container(classes="setting-row"):
                    yield Static("History Limit:", classes="setting-label")
                    yield Input(id="history-limit-input", classes="setting-input", placeholder="e.g., 50")

            with Container(id="settings-buttons"):
                yield Button("Save", id="save-button", variant="primary")
                yield Button("Cancel", id="cancel-button")

    def on_mount(self) -> None:
        """Load current settings when the screen mounts."""
        from code_puppy.config import get_puppy_name, get_owner_name, get_yolo_mode, get_message_history_limit, get_model_name

        # Load current values
        puppy_name_input = self.query_one("#puppy-name-input", Input)
        owner_name_input = self.query_one("#owner-name-input", Input)
        model_select = self.query_one("#model-select", Select)
        yolo_select = self.query_one("#yolo-select", Select)
        history_limit_input = self.query_one("#history-limit-input", Input)

        puppy_name_input.value = get_puppy_name() or ""
        owner_name_input.value = get_owner_name() or ""
        history_limit_input.value = str(get_message_history_limit())

        # Load available models
        self.load_model_options(model_select)

        # Set current model selection
        current_model = get_model_name()
        model_select.value = current_model

        # Set YOLO mode selection
        current_yolo = get_yolo_mode()
        yolo_select.value = "true" if current_yolo else "false"

    def load_model_options(self, model_select):
        """Load available models into the model select widget."""
        try:
            import json
            from pathlib import Path

            # Use the same models file that the config system uses
            models_path = Path.home() / ".codepuppy_models.json"
            if not models_path.exists():
                models_path = Path(__file__).parent / "models.json"

            with open(models_path, 'r') as f:
                models_data = json.load(f)

            # Create options as (display_name, model_name) tuples
            model_options = []
            for model_name, model_config in models_data.items():
                model_type = model_config.get("type", "unknown")
                display_name = f"{model_name} ({model_type})"
                model_options.append((display_name, model_name))

            # Set the options on the select widget
            model_select.set_options(model_options)

        except Exception as e:
            # Fallback to a basic option if loading fails
            model_select.set_options([("gpt-4.1 (openai)", "gpt-4.1")])

    @on(Button.Pressed, "#save-button")
    def save_settings(self) -> None:
        """Save the modified settings."""
        from code_puppy.config import set_config_value, set_model_name

        try:
            # Get values from inputs
            puppy_name = self.query_one("#puppy-name-input", Input).value.strip()
            owner_name = self.query_one("#owner-name-input", Input).value.strip()
            selected_model = self.query_one("#model-select", Select).value
            yolo_mode = self.query_one("#yolo-select", Select).value
            history_limit = self.query_one("#history-limit-input", Input).value.strip()

            # Validate and save
            if puppy_name:
                set_config_value("puppy_name", puppy_name)
            if owner_name:
                set_config_value("owner_name", owner_name)

            # Save model selection
            if selected_model:
                set_model_name(selected_model)

            set_config_value("yolo_mode", yolo_mode)

            if history_limit.isdigit():
                set_config_value("message_history_limit", history_limit)

            # Return success message with model change info
            message = "Settings saved successfully!"
            if selected_model:
                message += f" Model switched to: {selected_model}"

            self.dismiss({"success": True, "message": message, "model_changed": bool(selected_model)})

        except Exception as e:
            self.dismiss({"success": False, "message": f"Error saving settings: {str(e)}"})

    @on(Button.Pressed, "#cancel-button")
    def cancel_settings(self) -> None:
        """Cancel settings changes."""
        self.dismiss({"success": False, "message": "Settings cancelled"})

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.cancel_settings()


class CodePuppyTUI(App):
    """Main Code Puppy TUI application."""

    TITLE = "Code Puppy - AI Code Assistant"
    SUB_TITLE = "Walmart Global Tech Edition"

    CSS = """
    Screen {
        layout: horizontal;
    }

    #main-area {
        layout: vertical;
        width: 1fr;
        min-width: 40;
    }

    #chat-container {
        height: 1fr;
        min-height: 10;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "toggle_history", "History"),
        Binding("f3", "focus_input", "Focus Input"),
        Binding("f4", "focus_chat", "Focus Chat"),
        Binding("f5", "open_settings", "Settings"),
        Binding("ctrl+up", "scroll_chat_up", "Scroll Up"),
        Binding("ctrl+down", "scroll_chat_down", "Scroll Down"),
        Binding("ctrl+home", "scroll_chat_top", "Scroll to Top"),
        Binding("ctrl+end", "scroll_chat_bottom", "Scroll to Bottom"),
    ]

    # Reactive variables for app state
    current_model = reactive("")
    puppy_name = reactive("")
    message_history: List[Dict] = []
    agent_busy = reactive(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent = None
        self.session_memory = None

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield StatusBar()
        yield Sidebar()
        with Container(id="main-area"):
            with Container(id="chat-container"):
                yield ChatView(id="chat-view")
            yield InputArea()
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the application when mounted."""
        # Load configuration
        self.current_model = get_model_name()
        self.puppy_name = get_puppy_name()

        # Initialize agent and session memory
        self.agent = get_code_generation_agent()
        self.session_memory = session_memory()

        # Update status bar
        status_bar = self.query_one(StatusBar)
        status_bar.current_model = self.current_model
        status_bar.puppy_name = self.puppy_name
        status_bar.agent_status = "Ready"

        # Add welcome message
        self.add_system_message(
            f"Welcome to Code Puppy TUI! Model: {self.current_model}"
        )

        # Input field starts empty and focused, help text shows below

        # Load session history
        self.load_history_list()

        # Apply responsive design adjustments
        self.apply_responsive_layout()

        # Auto-focus the input field so user can start typing immediately
        self.call_after_refresh(self.focus_input_field)

    def add_system_message(self, content: str) -> None:
        """Add a system message to the chat."""
        message = ChatMessage(
            id=f"sys_{datetime.now().timestamp()}",
            type=MessageType.SYSTEM,
            content=content,
            timestamp=datetime.now()
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the chat."""
        message = ChatMessage(
            id=f"user_{datetime.now().timestamp()}",
            type=MessageType.USER,
            content=content,
            timestamp=datetime.now()
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_agent_message(self, content: str) -> None:
        """Add an agent message to the chat."""
        message = ChatMessage(
            id=f"agent_{datetime.now().timestamp()}",
            type=MessageType.AGENT,
            content=content,
            timestamp=datetime.now()
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)

    def add_error_message(self, content: str) -> None:
        """Add an error message to the chat."""
        message = ChatMessage(
            id=f"error_{datetime.now().timestamp()}",
            type=MessageType.ERROR,
            content=content,
            timestamp=datetime.now()
        )
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.add_message(message)


    def on_custom_text_area_message_sent(self, event: CustomTextArea.MessageSent) -> None:
        """Handle message sent from custom text area."""
        self.action_send_message()

    async def on_key(self, event) -> None:
        """Handle app-level key events."""
        input_field = self.query_one("#input-field", CustomTextArea)

        # Only handle keys when input field is focused
        if input_field.has_focus:
            # Handle Ctrl+Enter for new lines (more reliable than Shift+Enter)
            if event.key == "ctrl+enter":
                input_field.insert("\n")
                event.prevent_default()
                return

        # Handle arrow keys for history list navigation when sidebar is visible
        if not input_field.has_focus:
            try:
                sidebar = self.query_one(Sidebar)
                if sidebar.display:
                    history_list = self.query_one("#history-list", ListView)
                    if event.key == "up":
                        # Move up in the history list
                        current_index = history_list.index
                        if current_index > 0:
                            history_list.index = current_index - 1
                        event.prevent_default()
                        return
                    elif event.key == "down":
                        # Move down in the history list
                        current_index = history_list.index
                        if current_index < len(history_list.children) - 1:
                            history_list.index = current_index + 1
                        event.prevent_default()
                        return
                    elif event.key == "enter":
                        # Show details of current history item
                        if history_list.highlighted_child and hasattr(history_list.highlighted_child, 'history_entry'):
                            history_entry = history_list.highlighted_child.history_entry
                            self.show_history_details(history_entry)
                        event.prevent_default()
                        return
            except Exception:
                pass

        # Let other keys pass through normally


    def refresh_history_display(self) -> None:
        """Refresh the history display with current session memory."""
        try:
            history_list = self.query_one("#history-list", ListView)
            # Remove all children manually to ensure proper clearing
            for child in list(history_list.children):
                child.remove()
            self.load_history_list()
        except Exception:
            pass  # Silently fail if history list not available

    def action_send_message(self) -> None:
        """Send the current message."""
        input_field = self.query_one("#input-field", CustomTextArea)
        message = input_field.text.strip()

        if message:
            # Clear input
            input_field.text = ""

            # Add user message to chat
            self.add_user_message(message)

            # Process the message
            self.process_message(message)
        # If field is empty after sending, do nothing - help text shows persistently below

    @work(exclusive=True)
    async def process_message(self, message: str) -> None:
        """Process a user message asynchronously."""
        try:
            self.agent_busy = True
            self.start_agent_progress("Thinking")

            # Handle meta commands
            if message.strip().startswith('~'):
                if message.strip().lower() in ('clear', '~clear'):
                    self.action_clear_chat()
                    return

                # Use the existing meta command handler
                try:
                    from code_puppy.tools.common import console as rich_console
                    from io import StringIO
                    import sys

                    # Capture the output from the meta command handler
                    old_stdout = sys.stdout
                    captured_output = StringIO()
                    sys.stdout = captured_output

                    # Also capture Rich console output
                    temp_console = rich_console
                    rich_console.file = captured_output

                    try:
                        # Call the existing meta command handler
                        result = handle_meta_command(message.strip(), rich_console)
                        if result:  # Command was handled
                            output = captured_output.getvalue()
                            if output.strip():
                                self.add_system_message(output.strip())
                            else:
                                self.add_system_message(f"Meta command '{message}' executed")
                        else:
                            self.add_system_message(f"Unknown meta command: {message}")
                    finally:
                        # Restore stdout and console
                        sys.stdout = old_stdout
                        rich_console.file = sys.__stdout__

                except Exception as e:
                    self.add_error_message(f"Error executing meta command: {str(e)}")
                return

            # Process with agent
            if self.agent:
                self.update_agent_progress("Processing", 25)
                async with self.agent.run_mcp_servers():
                    self.update_agent_progress("Processing", 50)
                    result = await self.agent.run(message, message_history=self.message_history)

                self.update_agent_progress("Processing", 75)
                agent_response = result.output
                self.add_agent_message(agent_response.output_message)

                # Update message history
                new_msgs = result.new_messages()
                self.message_history.extend(new_msgs)

                # Refresh config display to show updated message count
                self.refresh_config_display()

                # Refresh history display to show new interaction
                self.refresh_history_display()

                # Log to session memory
                if self.session_memory:
                    self.session_memory.log_task(
                        f"TUI interaction: {message}",
                        extras={
                            "output": agent_response.output_message,
                            "awaiting_user_input": agent_response.awaiting_user_input,
                        },
                    )
            else:
                self.add_error_message("Agent not initialized")

        except Exception as e:
            self.add_error_message(f"Error processing message: {str(e)}")
        finally:
            self.agent_busy = False
            self.stop_agent_progress()

    def action_clear_chat(self) -> None:
        """Clear the chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        self.message_history.clear()
        self.add_system_message("Chat history cleared")

    def action_show_help(self) -> None:
        """Show responsive help information."""
        help_text = self.get_responsive_help_text()
        self.add_system_message(help_text)

    def action_toggle_history(self) -> None:
        """Toggle history sidebar visibility."""
        sidebar = self.query_one(Sidebar)
        sidebar.display = not sidebar.display

    def action_focus_input(self) -> None:
        """Focus the input field."""
        input_field = self.query_one("#input-field", CustomTextArea)
        input_field.focus()

    def focus_input_field(self) -> None:
        """Focus the input field (used for auto-focus on startup)."""
        try:
            input_field = self.query_one("#input-field", CustomTextArea)
            input_field.focus()
        except Exception:
            pass  # Silently handle if widget not ready yet

    def action_focus_chat(self) -> None:
        """Focus the chat area."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.focus()


    def action_scroll_chat_up(self) -> None:
        """Scroll chat view up."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.scroll_up(animate=True)

    def action_scroll_chat_down(self) -> None:
        """Scroll chat view down."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.scroll_down(animate=True)

    def action_scroll_chat_top(self) -> None:
        """Scroll chat view to top."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.scroll_home(animate=True)

    def action_scroll_chat_bottom(self) -> None:
        """Scroll chat view to bottom."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.scroll_end(animate=True)

    def action_open_settings(self) -> None:
        """Open the settings configuration screen."""
        def handle_settings_result(result):
            if result and result.get("success"):
                # Update reactive variables
                from code_puppy.config import get_puppy_name, get_model_name
                self.puppy_name = get_puppy_name()

                # Handle model change if needed
                if result.get("model_changed"):
                    new_model = get_model_name()
                    self.current_model = new_model
                    # Reinitialize agent with new model
                    self.agent = get_code_generation_agent()

                # Update status bar
                status_bar = self.query_one(StatusBar)
                status_bar.puppy_name = self.puppy_name
                status_bar.current_model = self.current_model

                # Show success message
                self.add_system_message(result.get("message", "Settings updated"))
            elif result and not result.get("success") and "cancelled" not in result.get("message", "").lower():
                # Show error message (but not for cancellation)
                self.add_error_message(result.get("message", "Settings update failed"))

        self.push_screen(SettingsScreen(), handle_settings_result)

    def load_history_list(self) -> None:
        """Load session history into the history tab."""
        try:
            from datetime import datetime, timedelta

            history_list = self.query_one("#history-list", ListView)

            # Get history from session memory
            if self.session_memory:
                # Get recent history (last 24 hours by default)
                recent_history = self.session_memory.get_history(within_minutes=24*60)

                if not recent_history:
                    # No history available
                    history_list.append(ListItem(Label("No recent history", classes="history-empty")))
                    return

                # Filter out model loading entries and group history by type, display most recent first
                filtered_history = [
                    entry for entry in recent_history
                    if not entry.get("description", "").startswith("Agent loaded")
                ]

                # Get sidebar width for responsive text truncation
                try:
                    sidebar_width = self.query_one("Sidebar").size.width if hasattr(self.query_one("Sidebar"), 'size') else 30
                except:
                    sidebar_width = 30

                # Adjust text length based on sidebar width
                if sidebar_width >= 35:
                    max_text_length = 45
                    time_format = "%H:%M:%S"
                elif sidebar_width >= 25:
                    max_text_length = 30
                    time_format = "%H:%M"
                else:
                    max_text_length = 20
                    time_format = "%H:%M"

                for entry in reversed(filtered_history[-20:]):  # Show last 20 entries
                    timestamp_str = entry.get("timestamp", "")
                    description = entry.get("description", "Unknown task")

                    # Parse timestamp for display
                    try:
                        timestamp_obj = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        time_display = timestamp_obj.strftime(time_format)
                        date_display = timestamp_obj.strftime("%m/%d")
                    except:
                        time_display = timestamp_str[:5] if sidebar_width < 25 else timestamp_str[:8]
                        if len(time_display) < 5:
                            time_display = "??:??"
                        date_display = "??/??"

                    # Format description for display with responsive truncation
                    if description.startswith("Interactive task:"):
                        task_text = description[17:].strip()  # Remove "Interactive task: "
                        truncated = task_text[:max_text_length] + ('...' if len(task_text) > max_text_length else '')
                        display_text = f"[{time_display}] 💬 {truncated}"
                        css_class = "history-interactive"
                    elif description.startswith("TUI interaction:"):
                        task_text = description[16:].strip()  # Remove "TUI interaction: "
                        truncated = task_text[:max_text_length] + ('...' if len(task_text) > max_text_length else '')
                        display_text = f"[{time_display}] 🖥️ {truncated}"
                        css_class = "history-tui"
                    elif description.startswith("Command executed"):
                        cmd_text = description[18:].strip()  # Remove "Command executed: "
                        truncated = cmd_text[:max_text_length-5] + ('...' if len(cmd_text) > max_text_length-5 else '')
                        display_text = f"[{time_display}] ⚡ {truncated}"
                        css_class = "history-command"
                    else:
                        # Generic entry
                        truncated = description[:max_text_length] + ('...' if len(description) > max_text_length else '')
                        display_text = f"[{time_display}] 📝 {truncated}"
                        css_class = "history-generic"

                    label = Label(display_text, classes=css_class)
                    history_item = ListItem(label)
                    history_item.history_entry = entry  # Store full entry for detail view
                    history_list.append(history_item)
            else:
                history_list.append(ListItem(Label("Session memory not available", classes="history-error")))

        except Exception as e:
            self.add_error_message(f"Failed to load history: {e}")

    def show_history_details(self, history_entry: dict) -> None:
        """Show detailed information about a selected history entry."""
        try:
            timestamp = history_entry.get("timestamp", "Unknown time")
            description = history_entry.get("description", "No description")
            output = history_entry.get("output", "")
            awaiting_input = history_entry.get("awaiting_user_input", False)

            # Parse timestamp for better display
            try:
                from datetime import datetime
                timestamp_obj = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                formatted_time = timestamp_obj.strftime("%Y-%m-%d %H:%M:%S")
            except:
                formatted_time = timestamp

            # Create detailed view content
            details = [
                f"Timestamp: {formatted_time}",
                f"Description: {description}",
                "",
            ]

            if output:
                details.extend([
                    "Output:",
                    "─" * 40,
                    output,
                    "",
                ])

            if awaiting_input:
                details.append("⚠️  Was awaiting user input")

            # Display details as a system message in the chat
            detail_text = "\n".join(details)
            self.add_system_message(f"History Details:\n{detail_text}")

        except Exception as e:
            self.add_error_message(f"Failed to show history details: {e}")

    def set_agent_status(self, status: str, show_progress: bool = False) -> None:
        """Update agent status and optionally show/hide progress bar."""
        try:
            # Update status bar
            status_bar = self.query_one(StatusBar)
            status_bar.agent_status = status

            # Update progress bar visibility
            progress_bar = self.query_one("#progress-bar", ProgressBar)
            if show_progress:
                progress_bar.add_class("visible")
                progress_bar.display = True
                if status == "Thinking":
                    progress_bar.progress = 0  # Start from beginning
                elif status == "Processing":
                    progress_bar.progress = 50  # Mid-progress
            else:
                progress_bar.remove_class("visible")
                progress_bar.display = False
                progress_bar.progress = 0  # Reset progress

        except Exception:
            pass  # Silently fail if widgets not available

    def start_agent_progress(self, initial_status: str = "Thinking") -> None:
        """Start showing agent progress indicators."""
        self.set_agent_status(initial_status, show_progress=True)

    def update_agent_progress(self, status: str, progress: int = None) -> None:
        """Update agent progress during processing."""
        try:
            status_bar = self.query_one(StatusBar)
            status_bar.agent_status = status

            if progress is not None:
                progress_bar = self.query_one("#progress-bar", ProgressBar)
                progress_bar.progress = progress
        except Exception:
            pass

    def stop_agent_progress(self) -> None:
        """Stop showing agent progress indicators."""
        self.set_agent_status("Ready", show_progress=False)

    def on_resize(self, event: Resize) -> None:
        """Handle terminal resize events to update responsive elements."""
        try:
            # Apply responsive layout adjustments
            self.apply_responsive_layout()

            # Update status bar to reflect new width
            status_bar = self.query_one(StatusBar)
            status_bar.update_status()

            # Refresh history display with new responsive truncation
            self.refresh_history_display()

        except Exception:
            pass  # Silently handle resize errors

    def apply_responsive_layout(self) -> None:
        """Apply responsive layout adjustments based on terminal size."""
        try:
            terminal_width = self.size.width if hasattr(self, 'size') else 80
            terminal_height = self.size.height if hasattr(self, 'size') else 24
            sidebar = self.query_one(Sidebar)

            # Responsive sidebar width based on terminal width
            if terminal_width >= 120:
                sidebar.styles.width = 35
            elif terminal_width >= 100:
                sidebar.styles.width = 30
            elif terminal_width >= 80:
                sidebar.styles.width = 25
            elif terminal_width >= 60:
                sidebar.styles.width = 20
            else:
                sidebar.styles.width = 15

            # Auto-hide sidebar on very narrow terminals
            if terminal_width < 50:
                if sidebar.display:
                    sidebar.display = False
                    self.add_system_message("💡 Sidebar auto-hidden for narrow terminal. Press F2 to toggle.")

            # Adjust input area height for very short terminals
            if terminal_height < 20:
                input_area = self.query_one(InputArea)
                input_area.styles.height = 7
            else:
                input_area = self.query_one(InputArea)
                input_area.styles.height = 9

        except Exception:
            pass

    def get_responsive_help_text(self) -> str:
        """Generate responsive help text based on terminal size."""
        try:
            terminal_width = self.size.width if hasattr(self, 'size') else 80
        except:
            terminal_width = 80

        if terminal_width < 60:
            # Compact help for narrow terminals
            return """
Code Puppy TUI (Compact Mode):

Controls:
- Enter: Send message
- Ctrl+Enter: New line
- Ctrl+Q: Quit
- F2: Toggle history
- F3: Focus input
- F5: Settings

Use F1 for full help.
"""
        else:
            # Return the existing full help text
            return """
Code Puppy TUI Help:

Input Controls:
- Enter: Send message
- Ctrl+Enter: New line (multi-line input)
- Standard text editing shortcuts supported

Keyboard Shortcuts:
- Ctrl+Q/Ctrl+C: Quit application
- Ctrl+L: Clear chat history
- F1: Show this help
- F2: Toggle history
- F3: Focus input field
- F4: Focus chat area
- F5: Open settings

Chat Navigation:
- Ctrl+Up/Down: Scroll chat up/down
- Ctrl+Home: Scroll to top
- Ctrl+End: Scroll to bottom

Meta Commands:
- ~clear: Clear chat history
- ~m <model>: Switch model
- ~cd <dir>: Change directory
- ~help: Show help
- ~status: Show current status

Use the input area at the bottom to type messages.
The sidebar shows conversation history, available models, and configuration.
Agent responses support syntax highlighting for code blocks.
"""


async def run_textual_ui():
    """Run the Textual UI interface."""
    app = CodePuppyTUI()
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(run_textual_ui())