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
    Label, RichLog, TextArea, TabbedContent, TabPane
)
from textual.binding import Binding
from textual.message import Message
from textual.reactive import reactive
from textual import on, work
from textual.events import Key
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
        self._placeholder_active = False
    
    async def on_focus(self) -> None:
        """Clear placeholder when focused."""
        if self._placeholder_active:
            self.text = ""
            self._placeholder_active = False
    
    def _on_key(self, event: Key) -> None:
        """Override internal key handler to intercept Enter keys."""
        # Debug: Log all key events to understand what we're receiving
        # self.app.log(f"Key event: {event.key}, str: {str(event)}, repr: {repr(event)}")
        
        # Clear placeholder on any key press (except special keys)
        if self._placeholder_active and event.key not in ("escape", "tab", "up", "down", "left", "right"):
            self.text = ""
            self._placeholder_active = False
        
        # Handle Enter and Shift+Enter specifically
        if event.key == "enter":
            # Plain Enter: send message
            self.post_message(self.MessageSent())
            return  # Don't call super() to prevent default newline behavior
        
        # Try multiple ways to detect Shift+Enter
        event_str = str(event).lower()
        if (event.key == "shift+enter" or 
            "shift+enter" in event_str or
            (event.key == "enter" and "shift" in event_str)):
            # Shift+Enter: insert newline
            self.insert("\n")
            return  # Don't call super()
        
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
        text-align: center;
    }
    """

    current_model = reactive("")
    puppy_name = reactive("")
    connection_status = reactive("Connected")

    def compose(self) -> ComposeResult:
        yield Static(id="status-content")

    def watch_current_model(self) -> None:
        self.update_status()

    def watch_puppy_name(self) -> None:
        self.update_status()

    def watch_connection_status(self) -> None:
        self.update_status()

    def update_status(self) -> None:
        """Update the status bar content."""
        status_widget = self.query_one("#status-content", Static)
        status_text = f"🐶 {self.puppy_name} | Model: {self.current_model} | Status: {self.connection_status}"
        status_widget.update(status_text)


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
    """Input area with text input and send button."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: 7;
        margin: 1;
    }

    #input-field {
        height: 5;
        width: 1fr;
        margin: 1 3 1 1;
        border: round $primary;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield CustomTextArea(
            id="input-field",
            show_line_numbers=False
        )


class Sidebar(Container):
    """Sidebar with history, models, and configuration."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 30;
        background: $surface;
        border-right: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        with TabbedContent(initial="history"):
            with TabPane("History", id="history"):
                yield ListView(id="history-list")
            with TabPane("Models", id="models"):
                yield ListView(id="model-list")
            with TabPane("Config", id="config"):
                yield ListView(id="config-list")


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
    }

    #chat-container {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear_chat", "Clear Chat"),
        Binding("f1", "show_help", "Help"),
        Binding("f2", "toggle_sidebar", "Toggle Sidebar"),
        Binding("f3", "focus_input", "Focus Input"),
        Binding("f4", "focus_chat", "Focus Chat"),
        Binding("ctrl+1", "switch_to_history", "History Tab"),
        Binding("ctrl+2", "switch_to_models", "Models Tab"),
        Binding("ctrl+3", "switch_to_config", "Config Tab"),
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

        # Add welcome message
        self.add_system_message(
            f"Welcome to Code Puppy TUI! Model: {self.current_model}"
        )

        # Set placeholder text for input field
        input_field = self.query_one("#input-field", CustomTextArea)
        input_field.text = "Type your message and press Enter to send (Ctrl+Enter for new line)..."
        input_field._placeholder_active = True

        # Load available models
        self.load_models_list()

        # Load configuration
        self.load_config_list()

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
                if input_field._placeholder_active:
                    input_field.text = ""
                    input_field._placeholder_active = False
                input_field.insert("\n")
                event.prevent_default()
                return
        
        # Let other keys pass through normally

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
        else:
            # If field is empty, restore placeholder
            input_field.text = "Type your message and press Enter to send (Ctrl+Enter for new line)..."
            input_field._placeholder_active = True

    @work(exclusive=True)
    async def process_message(self, message: str) -> None:
        """Process a user message asynchronously."""
        try:
            self.agent_busy = True

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
                async with self.agent.run_mcp_servers():
                    result = await self.agent.run(message, message_history=self.message_history)

                agent_response = result.output
                self.add_agent_message(agent_response.output_message)

                # Update message history
                new_msgs = result.new_messages()
                self.message_history.extend(new_msgs)

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

    def action_clear_chat(self) -> None:
        """Clear the chat history."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.clear_messages()
        self.message_history.clear()
        self.add_system_message("Chat history cleared")

    def action_show_help(self) -> None:
        """Show help information."""
        help_text = """
Code Puppy TUI Help:

Input Controls:
- Enter: Send message
- Ctrl+Enter: New line (multi-line input)
- Cmd+Left/Right: Move to beginning/end of line
- Standard text editing shortcuts supported

Keyboard Shortcuts:
- Ctrl+Q/Ctrl+C: Quit application
- Ctrl+L: Clear chat history
- F1: Show this help
- F2: Toggle sidebar
- F3: Focus input field
- F4: Focus chat area

Tab Navigation:
- Ctrl+1: Switch to History tab
- Ctrl+2: Switch to Models tab
- Ctrl+3: Switch to Config tab

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
        self.add_system_message(help_text)

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one(Sidebar)
        sidebar.display = not sidebar.display
    
    def action_focus_input(self) -> None:
        """Focus the input field."""
        input_field = self.query_one("#input-field", CustomTextArea)
        input_field.focus()
    
    def action_focus_chat(self) -> None:
        """Focus the chat area."""
        chat_view = self.query_one("#chat-view", ChatView)
        chat_view.focus()
    
    def action_switch_to_history(self) -> None:
        """Switch to history tab in sidebar."""
        try:
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = "history"
        except Exception:
            pass
    
    def action_switch_to_models(self) -> None:
        """Switch to models tab in sidebar."""
        try:
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = "models"
        except Exception:
            pass
    
    def action_switch_to_config(self) -> None:
        """Switch to config tab in sidebar."""
        try:
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = "config"
        except Exception:
            pass
    
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

    def load_models_list(self) -> None:
        """Load available models into the models tab."""
        try:
            # This would load from the models.json file
            # For now, just show current model
            model_list = self.query_one("#model-list", ListView)
            model_list.append(ListItem(Label(f"Current: {self.current_model}")))
        except Exception as e:
            self.add_error_message(f"Failed to load models: {e}")

    def load_config_list(self) -> None:
        """Load configuration into the config tab."""
        try:
            config_list = self.query_one("#config-list", ListView)
            config_list.append(ListItem(Label(f"Model: {get_model_name()}")))
            config_list.append(ListItem(Label(f"Puppy: {get_puppy_name()}")))
            config_list.append(ListItem(Label(f"Owner: {get_owner_name()}")))
            config_list.append(ListItem(Label(f"YOLO Mode: {get_yolo_mode()}")))
        except Exception as e:
            self.add_error_message(f"Failed to load config: {e}")


async def run_textual_ui():
    """Run the Textual UI interface."""
    app = CodePuppyTUI()
    await app.run_async()


if __name__ == "__main__":
    asyncio.run(run_textual_ui())