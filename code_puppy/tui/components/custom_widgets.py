"""
Custom widget components for the TUI.
"""

from textual.widgets import TextArea
from textual.events import Key
from textual.message import Message


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