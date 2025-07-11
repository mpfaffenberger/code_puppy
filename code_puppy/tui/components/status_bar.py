"""
Status bar component for the TUI.
"""

import os
from textual.widgets import Static
from textual.reactive import reactive
from textual.app import ComposeResult
from rich.text import Text


class StatusBar(Static):
    """Status bar showing current model, puppy name, and connection status."""

    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: right;
        padding: 0 1;
    }

    #status-content {
        text-align: right;
        width: 100%;
    }
    """

    current_model = reactive("")
    puppy_name = reactive("")
    connection_status = reactive("Connected")
    agent_status = reactive("Ready")
    progress_visible = reactive(False)

    def compose(self) -> ComposeResult:
        yield Static(id="status-content")

    def watch_current_model(self) -> None:
        self.update_status()

    def watch_puppy_name(self) -> None:
        self.update_status()

    def watch_connection_status(self) -> None:
        self.update_status()

    def watch_agent_status(self) -> None:
        self.update_status()

    def watch_progress_visible(self) -> None:
        self.update_status()

    def update_status(self) -> None:
        """Update the status bar content with responsive design."""
        status_widget = self.query_one("#status-content", Static)

        # Get current working directory
        cwd = os.getcwd()
        cwd_short = os.path.basename(cwd) if cwd != "/" else "/"

        # Add agent status indicator with different colors
        if self.agent_status == "Thinking":
            status_indicator = "🤔"
            status_color = "yellow"
        elif self.agent_status == "Processing":
            status_indicator = "⚡"
            status_color = "blue"
        elif self.agent_status == "Busy":
            status_indicator = "🔄"
            status_color = "orange"
        else:  # Ready
            status_indicator = "✅"
            status_color = "green"

        # Get terminal width for responsive content
        try:
            terminal_width = self.app.size.width if hasattr(self.app, 'size') else 80
        except:
            terminal_width = 80

        # Create responsive status text based on terminal width
        rich_text = Text()

        if terminal_width >= 120:
            # Extra wide - show full path and all info
            rich_text.append(f"📁 {cwd} | 🐶 {self.puppy_name} | Model: {self.current_model} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 100:
            # Full status display for wide terminals
            rich_text.append(f"📁 {cwd_short} | 🐶 {self.puppy_name} | Model: {self.current_model} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 80:
            # Medium display - shorten model name if needed
            model_display = self.current_model[:15] + "..." if len(self.current_model) > 18 else self.current_model
            rich_text.append(f"📁 {cwd_short} | 🐶 {self.puppy_name} | {model_display} | ")
            rich_text.append(f"{status_indicator} {self.agent_status}", style=status_color)
        elif terminal_width >= 60:
            # Compact display - use abbreviations
            puppy_short = self.puppy_name[:8] + "..." if len(self.puppy_name) > 10 else self.puppy_name
            model_short = self.current_model[:12] + "..." if len(self.current_model) > 15 else self.current_model
            rich_text.append(f"📁 {cwd_short} | 🐶 {puppy_short} | {model_short} | ")
            rich_text.append(f"{status_indicator}", style=status_color)
        else:
            # Minimal display for very narrow terminals
            cwd_mini = cwd_short[:8] + "..." if len(cwd_short) > 10 else cwd_short
            rich_text.append(f"📁 {cwd_mini} | ")
            rich_text.append(f"{status_indicator}", style=status_color)

        rich_text.justify = "right"
        status_widget.update(rich_text)