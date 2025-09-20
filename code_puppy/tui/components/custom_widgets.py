"""
Custom widget components for the TUI.
"""

from textual.binding import Binding
from textual.events import Key
from textual.message import Message
from textual.widgets import TextArea


class CustomTextArea(TextArea):
    """Custom TextArea that sends a message with Enter and allows new lines with Shift+Enter."""

    # Define key bindings
    BINDINGS = [
        Binding("alt+enter", "insert_newline", ""),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_key(self, event):
        """Handle key events before they reach the internal _on_key handler."""
        # Let the binding system handle alt+enter
        if event.key == "alt+enter":
            # Don't prevent default - let the binding system handle it
            return
        
        # Handle escape+enter manually
        if event.key == "escape+enter":
            self.action_insert_newline()
            event.prevent_default()
            event.stop()
            return

    def _on_key(self, event: Key) -> None:
        """Override internal key handler to intercept Enter keys."""
        # Handle Enter key specifically
        if event.key == "enter":
            # Check if this key is part of an escape sequence (Alt+Enter)
            if hasattr(event, "is_cursor_sequence") or (
                hasattr(event, "meta") and event.meta
            ):
                # If it's part of an escape sequence, let the parent handle it
                # so that bindings can process it
                super()._on_key(event)
                return

            # This handles plain Enter only, not escape+enter
            self.post_message(self.MessageSent())
            return  # Don't call super() to prevent default newline behavior

        # Let TextArea handle other keys
        super()._on_key(event)

    def action_insert_newline(self) -> None:
        """Action to insert a new line - called by shift+enter and escape+enter bindings."""
        self.insert("\n")

    class MessageSent(Message):
        """Message sent when Enter key is pressed (without Shift)."""

        pass
