"""
Disclaimer modal screen.
"""

from textual.screen import ModalScreen
from textual.containers import Container, VerticalScroll
from textual.widgets import Static, Button
from textual.app import ComposeResult
from textual import on


class DisclaimerScreen(ModalScreen):
    """Disclaimer modal screen."""

    DEFAULT_CSS = """
    DisclaimerScreen {
        align: center middle;
    }

    #disclaimer-dialog {
        width: 90;
        height: 20;
        border: thick $warning;
        background: $surface;
        padding: 1;
    }

    #disclaimer-title {
        text-align: center;
        color: $warning;
        text-style: bold;
        margin: 0 0 1 0;
    }

    #disclaimer-content {
        height: 1fr;
        margin: 0 0 1 0;
        overflow-y: auto;
    }

    #disclaimer-text {
        color: $warning;
    }

    #disclaimer-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #disclaimer-dismiss-button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="disclaimer-dialog"):
            yield Static("⚠️  DISCLAIMER: Be a responsible Puppy Owner", id="disclaimer-title")
            with VerticalScroll(id="disclaimer-content"):
                yield Static(self.get_disclaimer_content(), id="disclaimer-text")
            with Container(id="disclaimer-buttons"):
                yield Button("I Understand", id="disclaimer-dismiss-button", variant="primary")

    def get_disclaimer_content(self) -> str:
        """Get the disclaimer content text."""
        return """Prompt responsibly: Only use internal data available to all HO associates. No permission based data should be included in prompts.

All information entered will be monitored in accordance with applicable Walmart policies and used for enhancement of this tool and AI adoption at Walmart.

Refer to usage policies for best practices on secure usage:
https://one.walmart.com/content/uswire/en_us/work1/policies/people-policies/company-issued-equipment-useage.html"""

    @on(Button.Pressed, "#disclaimer-dismiss-button")
    def dismiss_disclaimer(self) -> None:
        """Dismiss the disclaimer modal."""
        self.dismiss()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss()