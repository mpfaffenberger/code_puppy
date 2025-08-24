"""
Input area component for message input.
"""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Button, Static

from code_puppy.messaging.spinner import TextualSpinner

from .custom_widgets import CustomTextArea

# Alias SimpleSpinnerWidget to TextualSpinner for backward compatibility
SimpleSpinnerWidget = TextualSpinner


class SubmitCancelButton(Button):
    """A button that toggles between submit and cancel states."""

    is_cancel_mode = reactive(False)

    DEFAULT_CSS = """
    SubmitCancelButton {
        width: 3;
        min-width: 3;
        height: 3;
        content-align: center middle;
        border: none;
        background: $surface;
    }

    SubmitCancelButton:focus {
        border: none;
        color: $surface;
        background: $surface;
    }

    SubmitCancelButton:hover {
        border: none;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("▶️", **kwargs)
        self.id = "submit-cancel-button"

    def watch_is_cancel_mode(self, is_cancel: bool) -> None:
        """Update the button label when cancel mode changes."""
        self.label = "⏹️" if is_cancel else "▶️"

    def on_click(self) -> None:
        """Handle click event and bubble it up to parent."""
        # When clicked, send a ButtonClicked message that will be handled by the parent
        self.post_message(self.Clicked(self))

    class Clicked(Message):
        """Button was clicked."""

        def __init__(self, button: "SubmitCancelButton") -> None:
            self.is_cancel_mode = button.is_cancel_mode
            super().__init__()


class InputArea(Container):
    """Input area with text input, spinner, help text, and send button."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: 9;
        margin: 1;
    }

    #spinner {
        height: 1;
        width: 1fr;
        margin: 0 3 0 1;
        content-align: left middle;
        text-align: left;
        display: none;
    }

    #spinner.visible {
        display: block;
    }

    #input-container {
        height: 5;
        width: 1fr;
        margin: 1 3 0 1;
        align: center middle;
    }

    #input-field {
        height: 5;
        width: 1fr;
        border: round $primary;
        background: $surface;
    }

    #submit-cancel-button {
        height: 3;
        width: 3;
        min-width: 3;
        margin: 1 0 1 1;
        content-align: center middle;
        border: none;
        background: $surface;
    }

    #input-help {
        height: 1;
        width: 1fr;
        margin: 0 3 1 1;
        color: $text-muted;
        text-align: center;
    }
    """

    def on_mount(self) -> None:
        """Initialize the button state based on the app's agent_busy state."""
        app = self.app
        if hasattr(app, "agent_busy"):
            button = self.query_one(SubmitCancelButton)
            button.is_cancel_mode = app.agent_busy

    def compose(self) -> ComposeResult:
        yield SimpleSpinnerWidget(id="spinner")
        with Horizontal(id="input-container"):
            yield CustomTextArea(id="input-field", show_line_numbers=False)
            yield SubmitCancelButton()
        yield Static(
            "Enter to send • Alt+Enter for new line • Ctrl+1 for help",
            id="input-help",
        )

    def on_submit_cancel_button_clicked(
        self, event: SubmitCancelButton.Clicked
    ) -> None:
        """Handle button clicks based on current mode."""
        if event.is_cancel_mode:
            # Cancel mode - stop the current process
            self.post_message(self.CancelRequested())
        else:
            # Submit mode - send the message
            self.post_message(self.SubmitRequested())

        # Return focus to the input field
        self.app.call_after_refresh(self.focus_input_field)

    def focus_input_field(self) -> None:
        """Focus the input field after button click."""
        input_field = self.query_one("#input-field")
        input_field.focus()

    class SubmitRequested(Message):
        """Request to submit the current input."""

        pass

    class CancelRequested(Message):
        """Request to cancel the current process."""

        pass
