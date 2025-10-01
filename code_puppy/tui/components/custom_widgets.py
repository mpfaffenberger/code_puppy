"""
Custom widget components for the TUI.
"""

from typing import List
from textual.binding import Binding
from textual.events import Key
from textual.message import Message
from textual.widgets import TextArea


class CustomTextArea(TextArea):
    """Custom TextArea with Enter handling and command history navigation."""

    # Define key bindings
    BINDINGS = [
        Binding("alt+enter", "insert_newline", ""),
        Binding("up", "history_previous", "Previous command"),
        Binding("down", "history_next", "Next command"),
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # History navigation state
        self.command_history: List[str] = []
        self.history_position: int = -1  # -1 means no history navigation active
        self.original_text: str = ""  # Store original text when starting history navigation
        self._history_loaded = False

    def on_mount(self) -> None:
        """Load command history when widget is mounted."""
        super().on_mount()
        self.load_command_history()
    
    def load_command_history(self) -> None:
        """Load command history from the history manager."""
        try:
            from code_puppy.command_line.history_manager import get_history_manager
            
            history_manager = get_history_manager()
            # Get recent commands (newest first for up-arrow navigation)
            self.command_history = history_manager.get_recent_commands(max_entries=100)
            self._history_loaded = True
            
        except Exception:
            # Silently handle errors - don't break the UI
            self.command_history = []
            self._history_loaded = True
    
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
        
        # Handle up/down arrows for history navigation
        if event.key == "up":
            self.action_history_previous()
            event.prevent_default()
            event.stop()
            return
        
        if event.key == "down":
            self.action_history_next()
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

            # Reset history navigation when submitting
            self.reset_history_navigation()
            
            # This handles plain Enter only, not escape+enter
            self.post_message(self.MessageSent())
            return  # Don't call super() to prevent default newline behavior

        # Reset history navigation on any other text input
        if event.key not in ("up", "down", "alt+enter", "escape+enter") and len(event.key) == 1:
            self.reset_history_navigation()

        # Let TextArea handle other keys
        super()._on_key(event)

    def action_insert_newline(self) -> None:
        """Action to insert a new line - called by shift+enter and escape+enter bindings."""
        self.insert("\n")
    
    def action_history_previous(self) -> None:
        """Navigate to the previous command in history (up arrow)."""
        if not self._history_loaded:
            self.load_command_history()
        
        if not self.command_history:
            return
        
        # If we're not in history navigation mode, save current text
        if self.history_position == -1:
            self.original_text = self.text
            self.history_position = 0
        else:
            # Move to previous command (older)
            if self.history_position < len(self.command_history) - 1:
                self.history_position += 1
        
        # Update text area with historical command
        if 0 <= self.history_position < len(self.command_history):
            self.text = self.command_history[self.history_position]
            # Move cursor to end
            self.move_cursor_to_end()
    
    def action_history_next(self) -> None:
        """Navigate to the next command in history (down arrow)."""
        if not self._history_loaded:
            self.load_command_history()
            
        if self.history_position == -1:
            # Not in history navigation mode
            return
        
        if self.history_position > 0:
            # Move to next command (newer)
            self.history_position -= 1
            self.text = self.command_history[self.history_position]
            self.move_cursor_to_end()
        else:
            # Return to original text
            self.text = self.original_text
            self.reset_history_navigation()
            self.move_cursor_to_end()
    
    def reset_history_navigation(self) -> None:
        """Reset history navigation state."""
        self.history_position = -1
        self.original_text = ""
    
    def move_cursor_to_end(self) -> None:
        """Move cursor to the end of the text."""
        if self.text:
            # Move to the end of the last line
            lines = self.text.split("\n")
            last_line = len(lines) - 1
            last_column = len(lines[-1])
            self.cursor_location = (last_line, last_column)

    class MessageSent(Message):
        """Message sent when Enter key is pressed (without Shift)."""

        pass
