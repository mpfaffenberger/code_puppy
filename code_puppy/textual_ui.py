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
from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax

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
        background: $primary;
        color: $text;
        margin: 1 0;
        padding: 1;
    }

    .agent-message {
        background: $surface;
        color: $text;
        margin: 1 0;
        padding: 1;
        border-left: thick $accent;
    }

    .system-message {
        background: $warning;
        color: $text;
        margin: 1 0;
        padding: 1;
        text-style: italic;
    }

    .error-message {
        background: $error;
        color: $text;
        margin: 1 0;
        padding: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages: List[ChatMessage] = []

    def add_message(self, message: ChatMessage) -> None:
        """Add a new message to the chat view."""
        self.messages.append(message)

        # Create the message widget
        css_class = f"{message.type.value}-message"
        timestamp_str = message.timestamp.strftime("%H:%M:%S")

        if message.type == MessageType.USER:
            content = f"[{timestamp_str}] You: {message.content}"
        elif message.type == MessageType.AGENT:
            content = f"[{timestamp_str}] Agent: {message.content}"
        elif message.type == MessageType.SYSTEM:
            content = f"[{timestamp_str}] System: {message.content}"
        else:  # ERROR
            content = f"[{timestamp_str}] Error: {message.content}"

        message_widget = Label(content, classes=css_class)
        self.mount(message_widget)

        # Auto-scroll to bottom
        self.scroll_end(animate=True)

    def clear_messages(self) -> None:
        """Clear all messages from the chat view."""
        self.messages.clear()
        # Remove all message widgets
        for widget in self.query(Label):
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
        yield Input(
            placeholder="Type your message and press Enter to send...",
            id="input-field"
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
        Binding("enter", "send_message", "Send Message"),
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


    @on(Input.Submitted, "#input-field")
    def input_submitted(self) -> None:
        """Handle Enter key press in input field."""
        self.action_send_message()

    def action_send_message(self) -> None:
        """Send the current message."""
        input_field = self.query_one("#input-field", Input)
        message = input_field.value.strip()

        if message:
            # Clear input
            input_field.value = ""

            # Add user message to chat
            self.add_user_message(message)

            # Process the message
            self.process_message(message)

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

                # For other meta commands, we'd integrate with the existing handler
                self.add_system_message(f"Meta command: {message}")
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

Keyboard Shortcuts:
- Ctrl+Q: Quit application
- Ctrl+L: Clear chat history
- Ctrl+Enter: Send message
- F1: Show this help
- F2: Toggle sidebar

Meta Commands:
- ~clear: Clear chat history
- ~m <model>: Switch model
- ~cd <dir>: Change directory
- ~help: Show help

Use the input area at the bottom to type messages.
The sidebar shows conversation history, available models, and configuration.
        """
        self.add_system_message(help_text)

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one(Sidebar)
        sidebar.display = not sidebar.display

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