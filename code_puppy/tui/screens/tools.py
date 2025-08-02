"""
Tools modal screen.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Markdown, Static

from code_puppy.tools.tools_content import tools_content


class ToolsScreen(ModalScreen):
    """Tools modal screen"""

    DEFAULT_CSS = """
    ToolsScreen {
        align: center middle;
    }

    #tools-dialog {
        width: 95;
        height: 40;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #tools-content {
        height: 1fr;
        margin: 0 0 1 0;
        overflow-y: auto;
    }

    #tools-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #dismiss-button {
        margin: 0 1;
    }

    #tools-markdown {
        margin: 0;
        padding: 0;
    }

    /* Style markdown elements for better readability */
    Markdown {
        margin: 0;
        padding: 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="tools-dialog"):
            yield Static("🛠️  Cooper's Toolkit\n", id="tools-title")
            with VerticalScroll(id="tools-content"):
                yield Markdown(tools_content, id="tools-markdown")
            with Container(id="tools-buttons"):
                yield Button("Dismiss", id="dismiss-button", variant="primary")

    @on(Button.Pressed, "#dismiss-button")
    def dismiss_tools(self) -> None:
        """Dismiss the tools modal."""
        self.dismiss()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss()
