"""
Modal component for displaying command history entries.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.events import Key
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from ..messages import CommandSelected


class CommandHistoryModal(ModalScreen):
    """Modal for displaying a command history entry."""

    def __init__(self, **kwargs):
        """Initialize the modal with command history data.

        Args:
            **kwargs: Additional arguments to pass to the parent class
        """
        super().__init__(**kwargs)

        # Get the current command from the sidebar
        try:
            # We'll get everything from the sidebar on demand
            self.sidebar = None
            self.command = ""
            self.timestamp = ""
        except Exception:
            self.command = ""
            self.timestamp = ""

        # UI components to update
        self.command_display = None
        self.timestamp_display = None

    def on_mount(self) -> None:
        """Setup when the modal is mounted."""
        # Get the sidebar and current command entry
        try:
            self.sidebar = self.app.query_one("Sidebar")
            current_entry = self.sidebar.get_current_command_entry()
            self.command = current_entry["command"]
            self.timestamp = current_entry["timestamp"]
            self.update_display()
        except Exception as e:
            import logging

            logging.debug(f"Error initializing modal: {str(e)}")

    DEFAULT_CSS = """
    CommandHistoryModal {
        align: center middle;
    }

    #modal-container {
        width: 80%;
        max-width: 100;
        /* Set a definite height that's large enough but fits on screen */
        height: 22;  /* Increased height to make room for navigation hint */
        min-height: 18;
        background: $surface;
        border: solid $primary;
        /* Increase vertical padding to add more space between elements */
        padding: 1 2;
        /* Use vertical layout to ensure proper element sizing */
        layout: vertical;
    }

    #timestamp-display {
        width: 100%;
        margin-bottom: 1;
        color: $text-muted;
        text-align: right;
        /* Fix the height */
        height: 1;
        margin-top: 0;
    }

    #command-display {
        width: 100%;
        /* Allow this container to grow/shrink as needed but keep buttons visible */
        min-height: 3;
        height: 1fr;
        max-height: 12;
        padding: 0 1;
        margin-bottom: 1;
        margin-top: 1;
        background: $surface-darken-1;
        border: solid $primary-darken-2;
        overflow: auto;
    }

    #nav-hint {
        width: 100%;
        color: $text;
        text-align: center;
        margin: 1 0;
    }

    .button-container {
        width: 100%;
        /* Fix the height to ensure buttons are always visible */
        height: 3;
        align-horizontal: right;
        margin-top: 1;
    }

    Button {
        margin-right: 1;
    }

    #use-button {
        background: $success;
    }

    #cancel-button {
        background: $primary-darken-1;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the modal layout."""
        with Container(id="modal-container"):
            # Header with timestamp
            self.timestamp_display = Label(
                f"Timestamp: {self.timestamp}", id="timestamp-display"
            )
            yield self.timestamp_display

            # Scrollable content area that can expand/contract as needed
            # The content will scroll if it's too long, ensuring buttons remain visible
            with Container(id="command-display"):
                self.command_display = Static(self.command)
                yield self.command_display

            # Super simple navigation hint
            yield Label("Press Up/Down arrows to navigate history", id="nav-hint")

            # Fixed button container at the bottom
            with Horizontal(classes="button-container"):
                yield Button("Cancel", id="cancel-button", variant="default")
                yield Button("Use Command", id="use-button", variant="primary")

    def on_key(self, event: Key) -> None:
        """Handle key events for navigation."""
        # Handle arrow keys for navigation
        if event.key == "down":
            self.navigate_to_next_command()
            event.prevent_default()
        elif event.key == "up":
            self.navigate_to_previous_command()
            event.prevent_default()
        elif event.key == "escape":
            self.app.pop_screen()
            event.prevent_default()

    def navigate_to_next_command(self) -> None:
        """Navigate to the next command in history."""
        try:
            # Get the sidebar
            if not self.sidebar:
                self.sidebar = self.app.query_one("Sidebar")

            # Use sidebar's method to navigate
            if self.sidebar.navigate_to_next_command():
                # Get updated command entry
                current_entry = self.sidebar.get_current_command_entry()
                self.command = current_entry["command"]
                self.timestamp = current_entry["timestamp"]
                self.update_display()
        except Exception as e:
            # Log the error but don't crash
            import logging

            logging.debug(f"Error navigating to next command: {str(e)}")

    def navigate_to_previous_command(self) -> None:
        """Navigate to the previous command in history."""
        try:
            # Get the sidebar
            if not self.sidebar:
                self.sidebar = self.app.query_one("Sidebar")

            # Use sidebar's method to navigate
            if self.sidebar.navigate_to_previous_command():
                # Get updated command entry
                current_entry = self.sidebar.get_current_command_entry()
                self.command = current_entry["command"]
                self.timestamp = current_entry["timestamp"]
                self.update_display()
        except Exception as e:
            # Log the error but don't crash
            import logging

            logging.debug(f"Error navigating to previous command: {str(e)}")

    def update_display(self) -> None:
        """Update the display with the current command and timestamp."""
        if self.command_display:
            self.command_display.update(self.command)
        if self.timestamp_display:
            self.timestamp_display.update(f"Timestamp: {self.timestamp}")

    @on(Button.Pressed, "#use-button")
    def use_command(self) -> None:
        """Handle use button press."""
        # Post a message to the app with the selected command
        self.post_message(CommandSelected(self.command))
        self.app.pop_screen()

    @on(Button.Pressed, "#cancel-button")
    def cancel(self) -> None:
        """Handle cancel button press."""
        self.app.pop_screen()
