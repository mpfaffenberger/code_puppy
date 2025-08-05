"""
Modal component for displaying command history entries.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from ..messages import CommandSelected


class CommandHistoryModal(ModalScreen):
    """Modal for displaying a command history entry."""

    def __init__(self, command: str, timestamp: str, **kwargs):
        """Initialize the modal with command data.

        Args:
            command: The command text to display
            timestamp: The timestamp when the command was executed
            **kwargs: Additional arguments to pass to the parent class
        """
        super().__init__(**kwargs)
        self.command = command
        self.timestamp = timestamp

    DEFAULT_CSS = """
    CommandHistoryModal {
        align: center middle;
    }

    #modal-container {
        width: 80%;
        height: auto;
        max-width: 100;
        max-height: 20;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }

    #command-display {
        width: 100%;
        min-height: 1;
        height: auto;
        max-height: 12;
        padding: 0 1;
        margin-bottom: 1;
        background: $surface-darken-1;
        border: solid $primary-darken-2;
        overflow: auto;
    }

    #timestamp-display {
        width: 100%;
        margin-bottom: 1;
        color: $text-muted;
        text-align: right;
    }

    .button-container {
        width: 100%;
        height: 3;
        align-horizontal: right;
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
            yield Label(f"Timestamp: {self.timestamp}", id="timestamp-display")

            # Display the command with automatic scrolling for long commands
            with Container(id="command-display"):
                yield Static(self.command)

            # Button container
            with Horizontal(classes="button-container"):
                yield Button("Cancel", id="cancel-button", variant="default")
                yield Button("Use Command", id="use-button", variant="primary")

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
