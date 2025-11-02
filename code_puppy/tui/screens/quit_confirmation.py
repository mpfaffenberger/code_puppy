"""
Quit confirmation modal screen.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label


class QuitConfirmationScreen(ModalScreen[bool]):
    """Confirmation modal for quitting the application."""

    DEFAULT_CSS = """
    QuitConfirmationScreen {
        align: center middle;
    }

    #quit-dialog {
        width: 50;
        height: 14;
        border: thick $error;
        background: $surface;
        padding: 1;
    }

    #quit-message {
        width: 100%;
        text-align: center;
        padding: 1 0;
        margin: 0 0 1 0;
        color: $text;
    }

    #quit-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
        width: 100%;
    }

    #cancel-button {
        margin: 0 1;
    }

    #quit-button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="quit-dialog"):
            yield Label("⚠️  Quit Code Puppy?", id="quit-title")
            yield Label(
                "Are you sure you want to quit?\nAny unsaved work will be lost.",
                id="quit-message",
            )
            with Horizontal(id="quit-buttons"):
                yield Button("Cancel", id="cancel-button", variant="default")
                yield Button("Quit", id="quit-button", variant="error")

    def on_mount(self) -> None:
        """Set initial focus to the Quit button."""
        quit_button = self.query_one("#quit-button", Button)
        quit_button.focus()

    @on(Button.Pressed, "#cancel-button")
    def cancel_quit(self) -> None:
        """Cancel quitting."""
        self.dismiss(False)

    @on(Button.Pressed, "#quit-button")
    def confirm_quit(self) -> None:
        """Confirm quitting."""
        self.dismiss(True)

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss(False)
        # Note: Enter key will automatically activate the focused button
        # No need to handle it here - Textual handles button activation
