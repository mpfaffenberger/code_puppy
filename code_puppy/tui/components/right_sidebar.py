"""
Right sidebar component with status information.
"""

from datetime import datetime

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static


class RightSidebar(Static):
    """Right sidebar with status information and metrics."""

    DEFAULT_CSS = """
    RightSidebar {
        dock: right;
        width: 35;
        min-width: 25;
        max-width: 50;
        background: $panel;
        border-left: wide $primary;
        padding: 1 2;
    }
    """

    # Reactive variables
    context_used = reactive(0)
    context_total = reactive(100000)
    context_percentage = reactive(0.0)
    message_count = reactive(0)
    session_duration = reactive("0m")
    current_model = reactive("Unknown")
    agent_name = reactive("code-puppy")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.id = "right-sidebar"

    def on_mount(self) -> None:
        """Initialize the sidebar and start auto-refresh."""
        self._update_display()
        # Auto-refresh every second for live updates
        self.set_interval(1.0, self._update_display)

    def watch_context_used(self) -> None:
        """Update display when context usage changes."""
        self._update_display()

    def watch_context_total(self) -> None:
        """Update display when context total changes."""
        self._update_display()

    def watch_message_count(self) -> None:
        """Update display when message count changes."""
        self._update_display()

    def watch_current_model(self) -> None:
        """Update display when model changes."""
        self._update_display()

    def watch_agent_name(self) -> None:
        """Update display when agent changes."""
        self._update_display()

    def watch_session_duration(self) -> None:
        """Update display when session duration changes."""
        self._update_display()

    def _update_display(self) -> None:
        """Update the entire sidebar display with Rich Text."""
        status_text = Text()

        # Session Info Section
        status_text.append("Session Info\n\n", style="bold cyan")
        status_text.append(
            f"Time: {datetime.now().strftime('%H:%M:%S')}\n", style="green"
        )
        status_text.append(f"Messages: {self.message_count}\n", style="yellow")
        status_text.append(f"Duration: {self.session_duration}\n", style="magenta")

        # Agent Info Section
        status_text.append("\n")
        status_text.append("Agent Info\n\n", style="bold cyan")

        # Truncate model name if too long
        model_display = self.current_model
        if len(model_display) > 28:
            model_display = model_display[:25] + "..."

        status_text.append("Agent: ", style="bold")
        status_text.append(f"{self.agent_name}\n", style="green")
        status_text.append("Model: ", style="bold")
        status_text.append(f"{model_display}\n", style="green")

        # Context Window Section
        status_text.append("\n")
        status_text.append("Context Window\n\n", style="bold cyan")

        # Calculate percentage
        if self.context_total > 0:
            percentage = (self.context_used / self.context_total) * 100
        else:
            percentage = 0

        # Create visual progress bar (20 chars wide)
        bar_width = 20
        filled = int((self.context_used / max(1, self.context_total)) * bar_width)
        empty = bar_width - filled

        # Choose color based on usage
        if percentage < 50:
            bar_color = "green"
        elif percentage < 75:
            bar_color = "yellow"
        else:
            bar_color = "red"

        # Build the bar using block characters
        bar = "█" * filled + "░" * empty
        status_text.append(f"[{bar}]\n", style=bar_color)

        # Show stats in k format
        tokens_k = self.context_used / 1000
        max_k = self.context_total / 1000
        status_text.append(
            f"{tokens_k:.1f}k/{max_k:.0f}k ({percentage:.1f}%)\n", style="dim"
        )

        # Quick Actions Section
        status_text.append("\n")
        status_text.append("Quick Actions\n\n", style="bold cyan")
        status_text.append("Ctrl+Q: Quit\n", style="dim")
        status_text.append("Ctrl+L: Clear\n", style="dim")
        status_text.append("Ctrl+2: History\n", style="dim")
        status_text.append("Ctrl+3: Settings\n", style="dim")

        self.update(status_text)

    def update_context(self, used: int, total: int) -> None:
        """Update context usage values.

        Args:
            used: Number of tokens used
            total: Total token capacity
        """
        self.context_used = used
        self.context_total = total

    def update_session_info(
        self, message_count: int, duration: str, model: str, agent: str
    ) -> None:
        """Update session information.

        Args:
            message_count: Number of messages in session
            duration: Session duration as formatted string
            model: Current model name
            agent: Current agent name
        """
        self.message_count = message_count
        self.session_duration = duration
        self.current_model = model
        self.agent_name = agent
