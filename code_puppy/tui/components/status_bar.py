"""
Status bar component for the TUI.
"""

import os

from rich.text import Text
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static


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
    token_count = reactive(0)
    token_capacity = reactive(0)
    token_proportion = reactive(0.0)

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

    def watch_token_count(self) -> None:
        self.update_status()

    def watch_token_capacity(self) -> None:
        self.update_status()

    def watch_token_proportion(self) -> None:
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
            terminal_width = self.app.size.width if hasattr(self.app, "size") else 80
        except Exception:
            terminal_width = 80

        # Create responsive status text based on terminal width
        rich_text = Text()

        # Token status with color coding
        token_status = ""
        token_color = "green"
        if self.token_count > 0 and self.token_capacity > 0:
            # Import here to avoid circular import
            from code_puppy.config import get_compaction_threshold

            get_compaction_threshold = get_compaction_threshold()

            if self.token_proportion > get_compaction_threshold:
                token_color = "red"
                token_status = f"🔴 {self.token_count}/{self.token_capacity} ({self.token_proportion:.1%})"
            elif self.token_proportion > (
                get_compaction_threshold - 0.15
            ):  # 15% before summarization threshold
                token_color = "yellow"
                token_status = f"🟡 {self.token_count}/{self.token_capacity} ({self.token_proportion:.1%})"
            else:
                token_color = "green"
                token_status = f"🟢 {self.token_count}/{self.token_capacity} ({self.token_proportion:.1%})"

        if terminal_width >= 140:
            # Extra wide - show full path and all info including tokens
            rich_text.append(
                f"📁 {cwd} | 🐶 {self.puppy_name} | Model: {self.current_model} | "
            )
            if token_status:
                rich_text.append(f"{token_status} | ", style=token_color)
            rich_text.append(
                f"{status_indicator} {self.agent_status}", style=status_color
            )
        elif terminal_width >= 100:
            # Full status display for wide terminals
            rich_text.append(
                f"📁 {cwd_short} | 🐶 {self.puppy_name} | Model: {self.current_model} | "
            )
            rich_text.append(
                f"{status_indicator} {self.agent_status}", style=status_color
            )
        elif terminal_width >= 120:
            # Medium display - shorten model name if needed
            model_display = (
                self.current_model[:15] + "..."
                if len(self.current_model) > 18
                else self.current_model
            )
            rich_text.append(
                f"📁 {cwd_short} | 🐶 {self.puppy_name} | {model_display} | "
            )
            if token_status:
                rich_text.append(f"{token_status} | ", style=token_color)
            rich_text.append(
                f"{status_indicator} {self.agent_status}", style=status_color
            )
        elif terminal_width >= 60:
            # Compact display - use abbreviations
            puppy_short = (
                self.puppy_name[:8] + "..."
                if len(self.puppy_name) > 10
                else self.puppy_name
            )
            model_short = (
                self.current_model[:12] + "..."
                if len(self.current_model) > 15
                else self.current_model
            )
            rich_text.append(f"📁 {cwd_short} | 🐶 {puppy_short} | {model_short} | ")
            rich_text.append(f"{status_indicator}", style=status_color)
        else:
            # Minimal display for very narrow terminals
            cwd_mini = cwd_short[:8] + "..." if len(cwd_short) > 10 else cwd_short
            rich_text.append(f"📁 {cwd_mini} | ")
            rich_text.append(f"{status_indicator}", style=status_color)

        rich_text.justify = "right"
        status_widget.update(rich_text)

    def update_token_info(
        self, current_tokens: int, max_tokens: int, proportion: float
    ) -> None:
        """Update token information in the status bar."""
        self.token_count = current_tokens
        self.token_capacity = max_tokens
        self.token_proportion = proportion
