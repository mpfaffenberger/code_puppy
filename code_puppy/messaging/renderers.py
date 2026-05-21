"""Renderer implementations for different UI modes.

These renderers consume messages from the queue and display them
appropriately for their respective interfaces.

Pause-awareness
---------------
While ``PauseController.is_paused()`` is True, renderer output must be
buffered (silenced visually) so background chatter (shell-command
banners, MCP auto-start notes, sub-agent narration, etc.) doesn't trash
the user's steering prompt. ``HUMAN_INPUT_REQUEST`` is the exception —
those are blocking prompts and buffering them would deadlock the runtime.

Two flush paths cover both wake-up modes:

1. **Lazy flush**: the next ``_render_message`` after pause clears
   drains the buffer first, preserving order.
2. **Active flush**: a resume listener on ``PauseController`` calls
   ``_flush_paused_buffer`` even when no new messages arrive after the
   pause clears.
"""

import asyncio
import threading
from abc import ABC, abstractmethod
from typing import List, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape as escape_rich_markup
from rich.text import Text

from .message_queue import MessageQueue, MessageType, UIMessage

# Threshold for emitting a ``[buffered N messages during pause]`` indicator
# when the buffer is drained. Below this we stay silent; the user pressed
# pause, output buffered, output flushed — no extra noise needed.
_BUFFER_FLUSH_INDICATOR_THRESHOLD = 50


def _flush_indicator(count: int) -> Text:
    """Build the dim indicator emitted before draining a large buffer.

    Returns a ``Text`` (not a markup string) so the square-bracketed body
    isn't mis-parsed as a Rich markup tag and silently dropped.
    """
    return Text(
        f"-- buffered {count} messages during pause --",
        style="dim",
    )


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


def _classify_style(message: UIMessage) -> Optional[str]:
    """Map a message's type to a Rich style string (or None for default).

    Shared by both renderers so styling stays consistent and the file
    isn't duplicating a chain of ``if`` branches.
    """
    style: Optional[str]
    if message.type == MessageType.ERROR:
        style = "bold red"
    elif message.type == MessageType.WARNING:
        style = "yellow"
    elif message.type == MessageType.SUCCESS:
        style = "green"
    elif message.type == MessageType.TOOL_OUTPUT:
        style = "blue"
    elif message.type == MessageType.SYSTEM:
        style = "dim"
    else:
        style = None

    if isinstance(message.content, str) and (
        "Current version:" in message.content or "Latest version:" in message.content
    ):
        style = "dim"

    return style


def _print_message(console: Console, message: UIMessage) -> None:
    """Print ``message`` to ``console`` using the standard styling rules."""
    style = _classify_style(message)
    content = message.content
    if isinstance(content, str):
        if message.type == MessageType.AGENT_RESPONSE:
            try:
                console.print(Markdown(content))
            except Exception:
                console.print(escape_rich_markup(content))
        elif style:
            console.print(escape_rich_markup(content), style=style)
        else:
            console.print(escape_rich_markup(content))
    else:
        # Complex Rich objects (Tables, Markdown, Text, etc.) pass through.
        console.print(content)

    # Ensure output is immediately flushed to the terminal so messages
    # don't get stuck waiting for the next user input.
    if hasattr(console.file, "flush"):
        console.file.flush()


class InteractiveRenderer(MessageRenderer):
    """Async renderer for interactive CLI mode using Rich console.

    Note: This async-based renderer is not currently used in the codebase.
    Interactive mode currently uses ``SynchronousInteractiveRenderer`` instead.
    Pause buffering is supplied here for safety with lazy-flush semantics only
    (no resume-listener-driven flush — the sync renderer is the production
    path and gets the full treatment).
    """

    def __init__(self, queue: MessageQueue, console: Optional[Console] = None):
        super().__init__(queue)
        self.console = console or Console()
        self._paused_buffer: List[UIMessage] = []
        self._buffer_lock = threading.Lock()

    async def render_message(self, message: UIMessage):
        """Render a message, honoring the pause controller's buffering."""
        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            # NEVER buffer blocking prompts — that would deadlock the runtime.
            await self._handle_human_input_request(message)
            return

        from code_puppy.messaging.pause_controller import get_pause_controller

        pc = get_pause_controller()
        with self._buffer_lock:
            if pc.is_paused():
                self._paused_buffer.append(message)
                return
            pending = self._paused_buffer
            self._paused_buffer = []
            if len(pending) >= _BUFFER_FLUSH_INDICATOR_THRESHOLD:
                try:
                    self.console.print(_flush_indicator(len(pending)))
                except Exception:
                    pass
            for msg in pending:
                _print_message(self.console, msg)
            _print_message(self.console, message)

    async def _handle_human_input_request(self, message: UIMessage):
        """Handle a human input request in async mode."""
        safe_content = escape_rich_markup(str(message.content))
        self.console.print(f"[bold cyan]INPUT REQUESTED:[/bold cyan] {safe_content}")
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()


class SynchronousInteractiveRenderer:
    """Synchronous renderer for interactive mode (production path).

    Responsibilities:
    - Consumes messages from the queue in a background thread.
    - Registers as a direct listener for immediate rendering on emit.
    - Buffers all output while ``PauseController.is_paused()`` is True
      and flushes (in order) on resume, both lazily (next message after
      resume) and actively (via a resume listener).

    ``HUMAN_INPUT_REQUEST`` is intentionally exempt from buffering since
    those are blocking prompts the runtime is waiting on.
    """

    def __init__(self, queue: MessageQueue, console: Optional[Console] = None):
        self.queue = queue
        self.console = console or Console()
        self._running = False
        self._thread = None
        self._paused_buffer: List[UIMessage] = []
        self._buffer_lock = threading.Lock()

    def start(self):
        """Start the synchronous renderer in a background thread."""
        if self._running:
            return

        self._running = True
        self.queue.mark_renderer_active()
        self.queue.add_listener(self._render_message)

        # Register active-flush listener so we drain even when nothing else
        # emits after the pause clears.
        from code_puppy.messaging.pause_controller import get_pause_controller

        try:
            get_pause_controller().add_resume_listener(self._flush_paused_buffer)
        except Exception:
            # Never let listener registration take down the renderer.
            pass

        self._thread = threading.Thread(target=self._consume_messages, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the synchronous renderer.

        Order matters: stop the consume thread *before* the final flush so
        no new messages slip into the buffer after we've drained it.
        """
        self._running = False
        self.queue.mark_renderer_inactive()
        self.queue.remove_listener(self._render_message)

        from code_puppy.messaging.pause_controller import get_pause_controller

        try:
            get_pause_controller().remove_resume_listener(self._flush_paused_buffer)
        except Exception:
            pass

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        # Drain any stragglers — we're shutting down, don't silently lose them.
        self._flush_paused_buffer()

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
        """Render or buffer one message based on the PauseController state."""
        if message.type == MessageType.HUMAN_INPUT_REQUEST:
            # Bypass the buffer — blocking prompt, buffering would deadlock.
            self._handle_human_input_request(message)
            return

        from code_puppy.messaging.pause_controller import get_pause_controller

        pc = get_pause_controller()

        # Hold the lock during the actual print so concurrent emitters (bus
        # listener thread vs. consume thread vs. resume-listener flush) see
        # a single serial ordering. Rich's console.print is microseconds-
        # fast so contention is negligible.
        with self._buffer_lock:
            if pc.is_paused():
                self._paused_buffer.append(message)
                return
            pending = self._paused_buffer
            self._paused_buffer = []
            if len(pending) >= _BUFFER_FLUSH_INDICATOR_THRESHOLD:
                try:
                    self.console.print(_flush_indicator(len(pending)))
                except Exception:
                    pass
            for buffered in pending:
                _print_message(self.console, buffered)
            _print_message(self.console, message)

    def _render_message_immediate(self, message: UIMessage) -> None:
        """Render bypassing the pause buffer. Public-ish for tests/teardown."""
        _print_message(self.console, message)

    def _flush_paused_buffer(self) -> None:
        """Drain and render any buffered messages. Safe to call any time."""
        with self._buffer_lock:
            if not self._paused_buffer:
                return
            pending = self._paused_buffer
            self._paused_buffer = []
            if len(pending) >= _BUFFER_FLUSH_INDICATOR_THRESHOLD:
                try:
                    self.console.print(_flush_indicator(len(pending)))
                except Exception:
                    pass
            for buffered in pending:
                _print_message(self.console, buffered)

    def _handle_human_input_request(self, message: UIMessage):
        """Handle a human input request in interactive mode."""
        prompt_id = message.metadata.get("prompt_id") if message.metadata else None
        if not prompt_id:
            self.console.print(
                "[bold red]Error: Invalid human input request[/bold red]"
            )
            return

        safe_content = escape_rich_markup(str(message.content))
        self.console.print(f"[bold cyan]{safe_content}[/bold cyan]")
        if hasattr(self.console.file, "flush"):
            self.console.file.flush()

        try:
            response = input(">>> ")
            from .message_queue import provide_prompt_response

            provide_prompt_response(prompt_id, response)
        except (EOFError, KeyboardInterrupt):
            from .message_queue import provide_prompt_response

            provide_prompt_response(prompt_id, "")
        except Exception as e:
            from .message_queue import provide_prompt_response

            self.console.print(f"[bold red]Error getting input: {e}[/bold red]")
            provide_prompt_response(prompt_id, "")
