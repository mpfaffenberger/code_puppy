"""
Help modal screen.
"""

from textual.screen import ModalScreen
from textual.containers import Container, VerticalScroll
from textual.widgets import Static, Button
from textual.app import ComposeResult
from textual import on


class HelpScreen(ModalScreen):
    """Help modal screen."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-dialog {
        width: 80;
        height: 30;
        border: thick $primary;
        background: $surface;
        padding: 1;
    }

    #help-content {
        height: 1fr;
        margin: 0 0 1 0;
        overflow-y: auto;
    }

    #help-buttons {
        layout: horizontal;
        height: 3;
        align: center middle;
    }

    #dismiss-button {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Static("📚 Code Puppy TUI Help", id="help-title")
            with VerticalScroll(id="help-content"):
                yield Static(self.get_help_content(), id="help-text")
            with Container(id="help-buttons"):
                yield Button("Dismiss", id="dismiss-button", variant="primary")

    def get_help_content(self) -> str:
        """Get the help content text."""
        try:
            # Get terminal width for responsive help
            terminal_width = self.app.size.width if hasattr(self.app, "size") else 80
        except Exception:
            terminal_width = 80

        if terminal_width < 60:
            # Compact help for narrow terminals
            return """
Code Puppy TUI (Compact Mode):

Controls:
- Enter: Send message
- Ctrl+Enter: New line
- Ctrl+Q: Quit
- Ctrl+2: Toggle history
- Ctrl+3: Settings
- Ctrl+4: Focus prompt
- Ctrl+5: Focus response

Use this help for full details.
"""
        else:
            # Full help text
            return """
Code Puppy TUI Help:

Input Controls:
- Enter: Send message
- Ctrl+Enter: New line (multi-line input)
- Standard text editing shortcuts supported

Keyboard Shortcuts:
- Ctrl+Q/Ctrl+C: Quit application
- Ctrl+L: Clear chat history
- Ctrl+1: Show this help
- Ctrl+2: Toggle history
- Ctrl+3: Open settings
- Ctrl+4: Focus prompt (input field)
- Ctrl+5: Focus response (chat area)

Chat Navigation:
- Ctrl+Up/Down: Scroll chat up/down
- Ctrl+Home: Scroll to top
- Ctrl+End: Scroll to bottom

Meta Commands:
- ~clear: Clear chat history
- ~m <model>: Switch model
- ~cd <dir>: Change directory
- ~help: Show help
- ~status: Show current status

Use the input area at the bottom to type messages.
Press Ctrl+2 to view session history when needed.
Agent responses support syntax highlighting for code blocks.
Press Ctrl+3 to access all configuration settings.
"""

    @on(Button.Pressed, "#dismiss-button")
    def dismiss_help(self) -> None:
        """Dismiss the help modal."""
        self.dismiss()

    def on_key(self, event) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss()
