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
from rich.markdown import Markdown
from rich.markup import escape as escape_rich_markup

from .message_queue import MessageQueue, MessageType, UIMessage


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
                # Note: Using sys.stderr - can't use messaging in renderer
                import sys

                sys.stderr.write(f"Error rendering message: {e}\n")


class InteractiveRenderer(MessageRenderer):
    """Renderer for interactive CLI mode using Rich console.

    Note: This async-based renderer is not currently used in the codebase.
    Interactive mode currently uses SynchronousInteractiveRenderer instead.
    A future refactoring might consolidate these renderers.
    """

    def __init__(self, queue: MessageQueue, console: Optional[Console] = None):
        super().__init__(queue)
        self.console = console or Console()

    async def render_message(self, message: UIMessage):
        """Render a message using Rich console."""
        # Handle human input requests
        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            await self._handle_human_input_request(message)
            return

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
        elif message.type == MessageType.PLANNED_NEXT_STEPS:
            style = None
        elif message.type == MessageType.AGENT_RESPONSE:
            # Special handling for agent responses - they'll be rendered as markdown
            style = None
        elif message.type == MessageType.SYSTEM:
            style = "dim"
        else:
            style = None

        # Make version messages dim regardless of message type
        if isinstance(message.content, str):
            if (
                "Current version:" in message.content
                or "Latest version:" in message.content
            ):
                style = "dim"

        # Render the content
        if isinstance(message.content, str):
            if message.type == MessageType.AGENT_RESPONSE:
                # Render agent responses as markdown
                try:
                    markdown = Markdown(message.content)
                    self.console.print(markdown)
                except Exception:
                    # Fallback to plain text if markdown parsing fails
                    safe_content = escape_rich_markup(message.content)
                    self.console.print(safe_content)
            elif style:
                # Escape Rich markup to prevent crashes from malformed tags
                safe_content = escape_rich_markup(message.content)
                self.console.print(safe_content, style=style)
            else:
                safe_content = escape_rich_markup(message.content)
                self.console.print(safe_content)
        else:
            # For complex Rich objects (Tables, Markdown, Text, etc.)
            self.console.print(message.content)

        # Ensure output is immediately flushed to the terminal
        # This fixes the issue where messages don't appear until user input
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()

    async def _handle_human_input_request(self, message: UIMessage):
        """Handle a human input request in async mode."""
        # This renderer is not currently used in practice, but if it were:
        # We would need async input handling here
        # For now, just render as a system message
        safe_content = escape_rich_markup(str(message.content))
        self.console.print(f"[bold cyan]INPUT REQUESTED:[/bold cyan] {safe_content}")
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()


class SynchronousInteractiveRenderer:
    """
    Synchronous renderer for interactive mode that doesn't require async.

    This is useful for cases where we want immediate rendering without
    the overhead of async message processing.

    Note: As part of the messaging system refactoring, we're keeping this class for now
    as it's essential for the interactive mode to function properly. Future refactoring
    could replace this with a simpler implementation that leverages the unified message
    queue system more effectively, or potentially convert interactive mode to use
    async/await consistently and use InteractiveRenderer instead.

    Current responsibilities:
    - Consumes messages from the queue in a background thread
    - Renders messages to the console in real-time without requiring async code
    - Registers as a direct listener to the message queue for immediate processing
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
        # Handle human input requests
        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            self._handle_human_input_request(message)
            return

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
        elif message.type == MessageType.AGENT_RESPONSE:
            # Special handling for agent responses - they'll be rendered as markdown
            style = None
        elif message.type == MessageType.SYSTEM:
            style = "dim"
        else:
            style = None

        # Make version messages dim regardless of message type
        if isinstance(message.content, str):
            if (
                "Current version:" in message.content
                or "Latest version:" in message.content
            ):
                style = "dim"

        # Render the content
        if isinstance(message.content, str):
            if message.type == MessageType.AGENT_RESPONSE:
                # Render agent responses as markdown
                try:
                    markdown = Markdown(message.content)
                    self.console.print(markdown)
                except Exception:
                    # Fallback to plain text if markdown parsing fails
                    safe_content = escape_rich_markup(message.content)
                    self.console.print(safe_content)
            elif style:
                # Escape Rich markup to prevent crashes from malformed tags
                # in shell output or other user-provided content
                safe_content = escape_rich_markup(message.content)
                self.console.print(safe_content, style=style)
            else:
                safe_content = escape_rich_markup(message.content)
                self.console.print(safe_content)
        else:
            # For complex Rich objects (Tables, Markdown, Text, etc.)
            self.console.print(message.content)

        # Ensure output is immediately flushed to the terminal
        # This fixes the issue where messages don't appear until user input
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()

    def _handle_human_input_request(self, message: UIMessage):
        """Handle a human input request in interactive mode."""
        prompt_id = message.metadata.get("prompt_id") if message.metadata else None
        if not prompt_id:
            self.console.print(
                "[bold red]Error: Invalid human input request[/bold red]"
            )
            return

        # Display the prompt - escape to prevent markup injection
        safe_content = escape_rich_markup(str(message.content))
        self.console.print(f"[bold cyan]{safe_content}[/bold cyan]")
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()

        # Get user input
        try:
            # Use basic input for now - could be enhanced with prompt_toolkit later
            response = input(">>> ")

            # Provide the response back to the queue
            from .message_queue import provide_prompt_response

            provide_prompt_response(prompt_id, response)

        except (EOFError, KeyboardInterrupt):
            # Handle Ctrl+C or Ctrl+D
            provide_prompt_response(prompt_id, "")
        except Exception as e:
            self.console.print(f"[bold red]Error getting input: {e}[/bold red]")
            provide_prompt_response(prompt_id, "")
