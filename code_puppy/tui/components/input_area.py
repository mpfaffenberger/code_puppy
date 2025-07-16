"""
Input area component for message input.
"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from .custom_widgets import CustomTextArea


from code_puppy.messaging.spinner import TextualSpinner

# Alias SimpleSpinnerWidget to TextualSpinner for backward compatibility
SimpleSpinnerWidget = TextualSpinner


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

    #input-field {
        height: 5;
        width: 1fr;
        margin: 1 3 0 1;
        border: round $primary;
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

    def compose(self) -> ComposeResult:
        yield SimpleSpinnerWidget(id="spinner")
        yield CustomTextArea(id="input-field", show_line_numbers=False)
        yield Static(
            "Enter to send • Ctrl+Enter for new line • Ctrl+1 for help", id="input-help"
        )
