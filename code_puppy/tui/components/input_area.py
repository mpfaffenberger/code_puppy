"""
Input area component for message input.
"""

from textual.containers import Container
from textual.widgets import Static, ProgressBar
from textual.app import ComposeResult

from .custom_widgets import CustomTextArea


class InputArea(Container):
    """Input area with text input, progress bar, help text, and send button."""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: 9;
        margin: 1;
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

    #progress-bar {
        height: 1;
        width: 1fr;
        margin: 0 3 0 1;
        display: none;
    }

    #progress-bar.visible {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        yield ProgressBar(id="progress-bar", show_eta=False)
        yield CustomTextArea(id="input-field", show_line_numbers=False)
        yield Static(
            "Enter to send • Ctrl+Enter for new line • Ctrl+1 for help", id="input-help"
        )
