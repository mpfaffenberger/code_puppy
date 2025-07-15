"""
Queue-based console that mimics Rich Console but sends messages to a queue.

This allows tools to use the same Rich console interface while having
their output captured and routed through our message queue system.
"""

import traceback
from typing import Any, Optional, Union

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.markdown import Markdown

from .message_queue import MessageQueue, MessageType, get_global_queue


class QueueConsole:
    """
    Console-like interface that sends messages to a queue instead of stdout.
    
    This is designed to be a drop-in replacement for Rich Console that
    routes messages through our queue system.
    """
    
    def __init__(self, queue: Optional[MessageQueue] = None, fallback_console: Optional[Console] = None):
        self.queue = queue or get_global_queue()
        self.fallback_console = fallback_console or Console()
        
    def print(
        self, 
        *values: Any, 
        sep: str = " ",
        end: str = "\n",
        style: Optional[str] = None,
        highlight: bool = True,
        **kwargs
    ):
        """Print values to the message queue."""
        # Join all values into a single string
        content = sep.join(str(v) for v in values) + end
        
        # Determine message type based on style or content
        message_type = self._infer_message_type(content, style)
        
        # Create Rich Text object if style is provided
        if style and isinstance(content, str):
            content = Text(content, style=style)
            
        # Emit to queue
        self.queue.emit_simple(
            message_type,
            content,
            style=style,
            highlight=highlight,
            **kwargs
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
            show_locals=show_locals
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
            message_type,
            content,
            log=True,
            style=style,
            log_locals=log_locals
        )
        
    def _infer_message_type(self, content: str, style: Optional[str] = None) -> MessageType:
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
            style=style
        )
        
    def status(self, status: str, *, spinner: str = "dots"):
        """Show a status message (simplified)."""
        self.queue.emit_simple(
            MessageType.INFO,
            f"⏳ {status}",
            status=True,
            spinner=spinner
        )
        
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