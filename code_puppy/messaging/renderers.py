"""
Renderer implementations for different UI modes.

These renderers consume messages from the queue and display them
appropriately for their respective interfaces.
"""

import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Optional

from rich.console import Console
from io import StringIO

from .message_queue import MessageQueue, UIMessage, MessageType


class MessageRenderer(ABC):
    """Base class for message renderers."""

    def __init__(self, queue: MessageQueue):
        self.queue = queue
        self._running = False
        self._task = None

    @abstractmethod
    async def render_message(self, message: UIMessage):
        """Render a single message."""
        pass

    async def start(self):
        """Start the renderer."""
        if self._running:
            return

        self._running = True
        # Mark the queue as having an active renderer
        self.queue.mark_renderer_active()
        self._task = asyncio.create_task(self._consume_messages())

    async def stop(self):
        """Stop the renderer."""
        self._running = False
        # Mark the queue as having no active renderer
        self.queue.mark_renderer_inactive()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _consume_messages(self):
        """Consume messages from the queue."""
        while self._running:
            try:
                message = await asyncio.wait_for(self.queue.get_async(), timeout=0.1)
                await self.render_message(message)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                # Log error but continue processing
                print(f"Error rendering message: {e}")


class InteractiveRenderer(MessageRenderer):
    """Renderer for interactive CLI mode using Rich console."""

    def __init__(self, queue: MessageQueue, console: Optional[Console] = None):
        super().__init__(queue)
        self.console = console or Console()

    async def render_message(self, message: UIMessage):
        """Render a message using Rich console."""
        # Convert message type to appropriate Rich styling
        if message.type == MessageType.ERROR:
            style = "bold red"
        elif message.type == MessageType.WARNING:
            style = "yellow"
        elif message.type == MessageType.SUCCESS:
            style = "green"
        elif message.type == MessageType.TOOL_OUTPUT:
            style = "blue"
        elif message.type == MessageType.AGENT_REASONING:
            style = None
        elif message.type == MessageType.SYSTEM:
            style = "dim"
        else:
            style = None

        # Render the content
        if isinstance(message.content, str):
            if style:
                self.console.print(message.content, style=style)
            else:
                self.console.print(message.content)
        else:
            # For complex Rich objects (Tables, Markdown, Text, etc.)
            self.console.print(message.content)


class TUIRenderer(MessageRenderer):
    """Renderer for TUI mode that adds messages to the chat view."""

    def __init__(self, queue: MessageQueue, tui_app=None):
        super().__init__(queue)
        self.tui_app = tui_app

    def set_tui_app(self, app):
        """Set the TUI app reference."""
        self.tui_app = app

    async def render_message(self, message: UIMessage):
        """Render a message in the TUI chat view."""
        if not self.tui_app:
            return

        # Convert content to string for TUI display
        if hasattr(message.content, "__rich_console__"):
            # For Rich objects, render to plain text using a Console
            string_io = StringIO()
            temp_console = Console(file=string_io, width=80, legacy_windows=False)
            temp_console.print(message.content)
            content_str = string_io.getvalue().rstrip("\n")
        else:
            content_str = str(message.content)

        # Map message types to TUI message types
        if message.type in (MessageType.ERROR,):
            self.tui_app.add_error_message(content_str)
        elif message.type in (
            MessageType.SYSTEM,
            MessageType.INFO,
            MessageType.WARNING,
            MessageType.SUCCESS,
        ):
            self.tui_app.add_system_message(content_str)
        elif message.type == MessageType.AGENT_REASONING:
            # Agent reasoning messages should use the dedicated method
            self.tui_app.add_agent_reasoning_message(content_str)
        elif message.type in (
            MessageType.TOOL_OUTPUT,
            MessageType.COMMAND_OUTPUT,
        ):
            # These are typically agent/tool outputs
            self.tui_app.add_agent_message(content_str)
        else:
            # Default to system message
            self.tui_app.add_system_message(content_str)


class SynchronousInteractiveRenderer:
    """
    Synchronous renderer for interactive mode that doesn't require async.

    This is useful for cases where we want immediate rendering without
    the overhead of async message processing.
    """

    def __init__(self, queue: MessageQueue, console: Optional[Console] = None):
        self.queue = queue
        self.console = console or Console()
        self._running = False
        self._thread = None

    def start(self):
        """Start the synchronous renderer in a background thread."""
        if self._running:
            return

        self._running = True
        # Mark the queue as having an active renderer
        self.queue.mark_renderer_active()
        # Add ourselves as a listener for immediate processing
        self.queue.add_listener(self._render_message)
        self._thread = threading.Thread(target=self._consume_messages, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the synchronous renderer."""
        self._running = False
        # Mark the queue as having no active renderer
        self.queue.mark_renderer_inactive()
        # Remove ourselves as a listener
        self.queue.remove_listener(self._render_message)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _consume_messages(self):
        """Consume messages synchronously."""
        while self._running:
            message = self.queue.get_nowait()
            if message:
                self._render_message(message)
            else:
                # No messages, sleep briefly
                import time

                time.sleep(0.01)

    def _render_message(self, message: UIMessage):
        """Render a message using Rich console."""
        # Convert message type to appropriate Rich styling
        if message.type == MessageType.ERROR:
            style = "bold red"
        elif message.type == MessageType.WARNING:
            style = "yellow"
        elif message.type == MessageType.SUCCESS:
            style = "green"
        elif message.type == MessageType.TOOL_OUTPUT:
            style = "blue"
        elif message.type == MessageType.AGENT_REASONING:
            style = "purple"
        elif message.type == MessageType.SYSTEM:
            style = "dim"
        else:
            style = None

        # Render the content
        if isinstance(message.content, str):
            if style:
                self.console.print(message.content, style=style)
            else:
                self.console.print(message.content)
        else:
            # For complex Rich objects (Tables, Markdown, Text, etc.)
            self.console.print(message.content)
