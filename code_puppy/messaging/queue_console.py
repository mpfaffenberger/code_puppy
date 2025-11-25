"""
Queue-based console that mimics Rich Console but sends messages to a queue.

This allows tools to use the same Rich console interface while having
their output captured and routed through our message queue system.
"""

import traceback
from typing import Any, Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from .message_queue import MessageQueue, MessageType, get_global_queue


class QueueConsole:
    """
    Console-like interface that sends messages to a queue instead of stdout.

    This is designed to be a drop-in replacement for Rich Console that
    routes messages through our queue system.
    """

    def __init__(
        self,
        queue: Optional[MessageQueue] = None,
        fallback_console: Optional[Console] = None,
    ):
        self.queue = queue or get_global_queue()
        self.fallback_console = fallback_console or Console()

    def print(
        self,
        *values: Any,
        sep: str = " ",
        end: str = "\n",
        style: Optional[str] = None,
        highlight: bool = True,
        **kwargs,
    ):
        """Print values to the message queue."""
        # Handle Rich objects properly
        if len(values) == 1 and hasattr(values[0], "__rich_console__"):
            # Single Rich object - pass it through directly
            content = values[0]
            message_type = self._infer_message_type_from_rich_object(content, style)
        else:
            # Convert to string, but handle Rich objects properly
            processed_values = []
            for v in values:
                if hasattr(v, "__rich_console__"):
                    # For Rich objects, try to extract their text content
                    from io import StringIO

                    from rich.console import Console

                    string_io = StringIO()
                    # Use markup=True to properly process rich styling
                    # Use a reasonable width to prevent wrapping issues
                    temp_console = Console(
                        file=string_io, width=80, legacy_windows=False, markup=True
                    )
                    temp_console.print(v)
                    processed_values.append(string_io.getvalue().rstrip("\n"))
                else:
                    processed_values.append(str(v))

            content = sep.join(processed_values) + end
            message_type = self._infer_message_type(content, style)

        # Create Rich Text object if style is provided and content is string
        if style and isinstance(content, str):
            content = Text(content, style=style)

        # Emit to queue
        self.queue.emit_simple(
            message_type, content, style=style, highlight=highlight, **kwargs
        )

    def print_exception(
        self,
        *,
        width: Optional[int] = None,
        extra_lines: int = 3,
        theme: Optional[str] = None,
        word_wrap: bool = False,
        show_locals: bool = False,
        indent_guides: bool = True,
        suppress: tuple = (),
        max_frames: int = 100,
    ):
        """Print exception information to the queue."""
        # Get the exception traceback
        exc_text = traceback.format_exc()

        # Emit as error message
        self.queue.emit_simple(
            MessageType.ERROR,
            f"Exception:\n{exc_text}",
            exception=True,
            show_locals=show_locals,
        )

    def log(
        self,
        *values: Any,
        sep: str = " ",
        end: str = "\n",
        style: Optional[str] = None,
        justify: Optional[str] = None,
        emoji: Optional[bool] = None,
        markup: Optional[bool] = None,
        highlight: Optional[bool] = None,
        log_locals: bool = False,
    ):
        """Log a message (similar to print but with logging semantics)."""
        content = sep.join(str(v) for v in values) + end

        # Log messages are typically informational
        message_type = MessageType.INFO
        if style:
            message_type = self._infer_message_type(content, style)

        if style and isinstance(content, str):
            content = Text(content, style=style)

        self.queue.emit_simple(
            message_type, content, log=True, style=style, log_locals=log_locals
        )

    def _infer_message_type_from_rich_object(
        self, content: Any, style: Optional[str] = None
    ) -> MessageType:
        """Infer message type from Rich object type and style."""
        if style:
            style_lower = style.lower()
            if "red" in style_lower or "error" in style_lower:
                return MessageType.ERROR
            elif "yellow" in style_lower or "warning" in style_lower:
                return MessageType.WARNING
            elif "green" in style_lower or "success" in style_lower:
                return MessageType.SUCCESS
            elif "blue" in style_lower:
                return MessageType.INFO
            elif "purple" in style_lower or "magenta" in style_lower:
                return MessageType.AGENT_REASONING
            elif "dim" in style_lower:
                return MessageType.SYSTEM

        # Infer from object type
        if isinstance(content, Markdown):
            return MessageType.AGENT_REASONING
        elif isinstance(content, Table):
            return MessageType.TOOL_OUTPUT
        elif hasattr(content, "lexer_name"):  # Syntax object
            return MessageType.TOOL_OUTPUT

        return MessageType.INFO

    def _infer_message_type(
        self, content: str, style: Optional[str] = None
    ) -> MessageType:
        """Infer message type from content and style."""
        if style:
            style_lower = style.lower()
            if "red" in style_lower or "error" in style_lower:
                return MessageType.ERROR
            elif "yellow" in style_lower or "warning" in style_lower:
                return MessageType.WARNING
            elif "green" in style_lower or "success" in style_lower:
                return MessageType.SUCCESS
            elif "blue" in style_lower:
                return MessageType.INFO
            elif "purple" in style_lower or "magenta" in style_lower:
                return MessageType.AGENT_REASONING
            elif "dim" in style_lower:
                return MessageType.SYSTEM

        # Infer from content patterns
        content_lower = content.lower()
        if any(word in content_lower for word in ["error", "failed", "exception"]):
            return MessageType.ERROR
        elif any(word in content_lower for word in ["warning", "warn"]):
            return MessageType.WARNING
        elif any(word in content_lower for word in ["success", "completed", "done"]):
            return MessageType.SUCCESS
        elif any(word in content_lower for word in ["tool", "command", "running"]):
            return MessageType.TOOL_OUTPUT

        return MessageType.INFO

    # Additional methods to maintain Rich Console compatibility
    def rule(self, title: str = "", *, align: str = "center", style: str = "rule.line"):
        """Print a horizontal rule."""
        self.queue.emit_simple(
            MessageType.SYSTEM,
            f"─── {title} ───" if title else "─" * 40,
            rule=True,
            style=style,
        )

    def status(self, status: str, *, spinner: str = "dots"):
        """Show a status message (simplified)."""
        self.queue.emit_simple(
            MessageType.INFO, f"⏳ {status}", status=True, spinner=spinner
        )

    def input(self, prompt: str = "") -> str:
        """Get user input without spinner interference.

        This method coordinates with the TUI to pause any running spinners
        and properly display the user input prompt.
        """
        # Set the global flag that we're awaiting user input
        from code_puppy.tools.command_runner import set_awaiting_user_input

        set_awaiting_user_input(True)

        # Emit the prompt as a system message so it shows in the TUI chat
        if prompt:
            self.queue.emit_simple(MessageType.SYSTEM, prompt, requires_user_input=True)

        # Create a new, isolated console instance specifically for input
        # This bypasses any spinner or queue system interference
        input_console = Console(file=__import__("sys").stderr, force_terminal=True)

        # Clear any spinner artifacts and position cursor properly
        if prompt:
            input_console.print(prompt, end="", style="bold cyan")

        # Use regular input() which will read from stdin
        # Since we printed the prompt to stderr, this should work cleanly
        try:
            user_response = input()

            # Show the user's response in the chat as well
            if user_response:
                self.queue.emit_simple(
                    MessageType.USER, f"User response: {user_response}"
                )

            return user_response
        except (KeyboardInterrupt, EOFError):
            # Handle interruption gracefully
            input_console.print("\n[yellow]Input cancelled[/yellow]")
            self.queue.emit_simple(MessageType.WARNING, "User input cancelled")
            return ""
        finally:
            # Clear the global flag for awaiting user input
            from code_puppy.tools.command_runner import set_awaiting_user_input

            set_awaiting_user_input(False)

    # File-like interface for compatibility
    @property
    def file(self):
        """Get the current file (for compatibility)."""
        return self.fallback_console.file

    @file.setter
    def file(self, value):
        """Set the current file (for compatibility)."""
        self.fallback_console.file = value


def get_queue_console(queue: Optional[MessageQueue] = None) -> QueueConsole:
    """Get a QueueConsole instance."""
    return QueueConsole(queue or get_global_queue())
