"""
Message queue system for decoupling Rich console output from renderers.

This allows both TUI and interactive modes to consume the same messages
but render them differently based on their capabilities.
"""

import asyncio
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union
from rich.console import Console
from rich.text import Text


class MessageType(Enum):
    """Types of messages that can be sent through the queue."""
    
    # Basic content types
    INFO = "info"
    SUCCESS = "success" 
    WARNING = "warning"
    ERROR = "error"
    
    # Tool-specific types
    TOOL_OUTPUT = "tool_output"
    COMMAND_OUTPUT = "command_output"
    FILE_OPERATION = "file_operation"
    
    # Agent-specific types
    AGENT_REASONING = "agent_reasoning"
    AGENT_STATUS = "agent_status"
    
    # System types
    SYSTEM = "system"
    DEBUG = "debug"


@dataclass
class UIMessage:
    """A message to be displayed in the UI."""
    
    type: MessageType
    content: Union[str, Text, Any]  # Can be Rich Text, Table, Markdown, etc.
    timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.metadata is None:
            self.metadata = {}


class MessageQueue:
    """Thread-safe message queue for UI messages."""
    
    def __init__(self, maxsize: int = 1000):
        self._queue = queue.Queue(maxsize=maxsize)
        self._async_queue = asyncio.Queue(maxsize=maxsize)
        self._listeners = []
        self._running = False
        self._thread = None
        
    def start(self):
        """Start the queue processing."""
        if self._running:
            return
            
        self._running = True
        self._thread = threading.Thread(target=self._process_messages, daemon=True)
        self._thread.start()
        
    def get_buffered_messages(self):
        """Get all currently buffered messages without waiting."""
        messages = []
        while True:
            try:
                message = self._queue.get_nowait()
                messages.append(message)
            except queue.Empty:
                break
        return messages
        
    def stop(self):
        """Stop the queue processing."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            
    def emit(self, message: UIMessage):
        """Emit a message to the queue."""
        try:
            self._queue.put_nowait(message)
        except queue.Full:
            # Drop oldest message to make room
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(message)
            except queue.Empty:
                pass
                
    def emit_simple(
        self, 
        message_type: MessageType, 
        content: Any, 
        **metadata
    ):
        """Emit a simple message with just type and content."""
        msg = UIMessage(
            type=message_type,
            content=content,
            metadata=metadata
        )
        self.emit(msg)
        
    def get_nowait(self) -> Optional[UIMessage]:
        """Get a message without blocking."""
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None
            
    async def get_async(self) -> UIMessage:
        """Get a message asynchronously."""
        return await self._async_queue.get()
        
    def _process_messages(self):
        """Process messages from sync to async queue."""
        while self._running:
            try:
                message = self._queue.get(timeout=0.1)
                # Try to put in async queue if there's an event loop
                try:
                    loop = asyncio.get_running_loop()
                    # Use thread-safe call to put message in async queue
                    def put_message():
                        try:
                            self._async_queue.put_nowait(message)
                        except asyncio.QueueFull:
                            # Drop message if async queue is full
                            pass
                    loop.call_soon_threadsafe(put_message)
                except RuntimeError:
                    # No running loop, skip async queue
                    pass
                    
                # Notify listeners immediately for sync processing
                for listener in self._listeners:
                    try:
                        listener(message)
                    except Exception:
                        pass  # Don't let listener errors break processing
                        
            except queue.Empty:
                continue
                
    def add_listener(self, callback):
        """Add a listener for messages (for direct sync consumption)."""
        self._listeners.append(callback)
        
    def remove_listener(self, callback):
        """Remove a listener."""
        if callback in self._listeners:
            self._listeners.remove(callback)


# Global message queue instance
_global_queue: Optional[MessageQueue] = None
_queue_lock = threading.Lock()


def get_global_queue() -> MessageQueue:
    """Get or create the global message queue."""
    global _global_queue
    
    with _queue_lock:
        if _global_queue is None:
            _global_queue = MessageQueue()
            _global_queue.start()
    
    return _global_queue
    
    
def get_buffered_startup_messages():
    """Get any messages that were buffered before renderers started."""
    queue = get_global_queue()
    return queue.get_buffered_messages()


def emit_message(message_type: MessageType, content: Any, **metadata):
    """Convenience function to emit a message to the global queue."""
    queue = get_global_queue()
    queue.emit_simple(message_type, content, **metadata)


def emit_info(content: Any, **metadata):
    """Emit an info message."""
    emit_message(MessageType.INFO, content, **metadata)


def emit_success(content: Any, **metadata):
    """Emit a success message."""
    emit_message(MessageType.SUCCESS, content, **metadata)


def emit_warning(content: Any, **metadata):
    """Emit a warning message."""
    emit_message(MessageType.WARNING, content, **metadata)


def emit_error(content: Any, **metadata):
    """Emit an error message."""
    emit_message(MessageType.ERROR, content, **metadata)


def emit_tool_output(content: Any, tool_name: str = None, **metadata):
    """Emit tool output."""
    if tool_name:
        metadata["tool_name"] = tool_name
    emit_message(MessageType.TOOL_OUTPUT, content, **metadata)


def emit_command_output(content: Any, command: str = None, **metadata):
    """Emit command output."""
    if command:
        metadata["command"] = command
    emit_message(MessageType.COMMAND_OUTPUT, content, **metadata)


def emit_agent_reasoning(content: Any, **metadata):
    """Emit agent reasoning."""
    emit_message(MessageType.AGENT_REASONING, content, **metadata)


def emit_system_message(content: Any, **metadata):
    """Emit a system message."""
    emit_message(MessageType.SYSTEM, content, **metadata)