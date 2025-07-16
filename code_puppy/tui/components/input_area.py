"""
Input area component for message input.
"""

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from .custom_widgets import CustomTextArea


class SimpleSpinnerWidget(Static):
    """A simple spinner widget using Static with timer-based animation."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self.frames = [
            "[bold cyan](●    )[/bold cyan]",
            "[bold cyan]( ●   )[/bold cyan]",
            "[bold cyan](  ●  )[/bold cyan]",
            "[bold cyan](   ● )[/bold cyan]",
            "[bold cyan](    ●)[/bold cyan]",
            "[bold cyan](   ● )[/bold cyan]",
            "[bold cyan](  ●  )[/bold cyan]",
            "[bold cyan]( ●   )[/bold cyan]",
            "[bold cyan](●    )[/bold cyan]"
            ]
        self._frame_index = 0
        self._is_spinning = False
        self._timer = None

    def start_spinning(self) -> None:
        """Start the spinner animation."""
        if not self._is_spinning:
            self._is_spinning = True
            self._frame_index = 0
            self.update("[bold cyan]🐶 Puppy is thinking... [/bold cyan]" + self.frames[0])
            # Start the animation timer using Textual's timer system
            self._timer = self.set_interval(0.10, self._update_frame)

    def stop_spinning(self) -> None:
        """Stop the spinner animation."""
        self._is_spinning = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.update("")

    def _update_frame(self) -> None:
        """Update to the next frame."""
        if self._is_spinning:
            self._frame_index = (self._frame_index + 1) % len(self.frames)
            current_frame = self.frames[self._frame_index]
            self.update("[bold cyan]🐶 Puppy is thinking... [/bold cyan]" + current_frame)


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
