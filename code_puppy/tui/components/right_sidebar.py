"""
Right sidebar component with status information.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.widgets import Label, ProgressBar, Static


class RightSidebar(Container):
    """Right sidebar with status information and metrics."""

    DEFAULT_CSS = """
    RightSidebar {
        dock: right;
        width: 35;
        min-width: 25;
        max-width: 50;
        background: #1e293b;
        border-left: wide #3b82f6;
        padding: 1 2;
    }

    .status-section {
        height: auto;
        margin: 0 0 2 0;
        padding: 1;
        background: #0f172a;
        border: round #475569;
    }

    .section-title {
        color: #60a5fa;
        text-style: bold;
        margin: 0 0 1 0;
    }

    .status-label {
        color: #cbd5e1;
        margin: 0 0 1 0;
    }

    .status-value {
        color: #e0f2fe;
        text-style: bold;
    }

    #context-progress {
        height: 1;
        margin: 1 0 0 0;
    }

    #context-progress.progress-low {
        color: #10b981;
    }

    #context-progress.progress-medium {
        color: #fbbf24;
    }

    #context-progress.progress-high {
        color: #f97316;
    }

    #context-progress.progress-critical {
        color: #ef4444;
    }

    .metric-item {
        color: #94a3b8;
        margin: 0 0 1 0;
    }

    .metric-value {
        color: #e0f2fe;
        text-style: bold;
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

    def compose(self) -> ComposeResult:
        """Create the right sidebar layout."""
        with Vertical(classes="status-section"):
            yield Label("📊 Context Usage", classes="section-title")
            yield Label("", id="context-label", classes="status-label")
            yield ProgressBar(
                total=100,
                show_eta=False,
                show_percentage=True,
                id="context-progress",
            )

        with Vertical(classes="status-section"):
            yield Label("🤖 Agent Info", classes="section-title")
            yield Label("", id="agent-info", classes="status-label")

        with Vertical(classes="status-section"):
            yield Label("💬 Session Stats", classes="section-title")
            yield Label("", id="session-stats", classes="status-label")

        with Vertical(classes="status-section"):
            yield Label("🎯 Quick Actions", classes="section-title")
            yield Label(
                "Ctrl+L - Clear\nCtrl+2 - History\nCtrl+Q - Quit",
                classes="status-label",
            )

    def watch_context_used(self) -> None:
        """Update display when context usage changes."""
        self._update_context_display()

    def watch_context_total(self) -> None:
        """Update display when context total changes."""
        self._update_context_display()

    def watch_message_count(self) -> None:
        """Update session stats when message count changes."""
        self._update_session_stats()

    def watch_current_model(self) -> None:
        """Update agent info when model changes."""
        self._update_agent_info()

    def watch_agent_name(self) -> None:
        """Update agent info when agent changes."""
        self._update_agent_info()

    def _update_context_display(self) -> None:
        """Update the context usage display."""
        try:
            # Calculate percentage
            if self.context_total > 0:
                percentage = (self.context_used / self.context_total) * 100
            else:
                percentage = 0

            self.context_percentage = percentage

            # Format numbers with commas for readability
            used_str = f"{self.context_used:,}"
            total_str = f"{self.context_total:,}"

            # Update label
            context_label = self.query_one("#context-label", Label)
            context_label.update(
                f"Tokens: {used_str} / {total_str}\n{percentage:.1f}% used"
            )

            # Update progress bar
            progress_bar = self.query_one("#context-progress", ProgressBar)
            progress_bar.update(progress=percentage)

            # Update progress bar color based on percentage
            progress_bar.remove_class(
                "progress-low",
                "progress-medium",
                "progress-high",
                "progress-critical",
            )
            if percentage < 50:
                progress_bar.add_class("progress-low")
            elif percentage < 70:
                progress_bar.add_class("progress-medium")
            elif percentage < 85:
                progress_bar.add_class("progress-high")
            else:
                progress_bar.add_class("progress-critical")

        except Exception:
            pass  # Silently handle if widgets not ready

    def _update_agent_info(self) -> None:
        """Update the agent information display."""
        try:
            agent_info = self.query_one("#agent-info", Label)

            # Truncate model name if too long
            model_display = self.current_model
            if len(model_display) > 25:
                model_display = model_display[:22] + "..."

            agent_info.update(
                f"Agent: {self.agent_name}\nModel: {model_display}"
            )
        except Exception:
            pass

    def _update_session_stats(self) -> None:
        """Update the session statistics display."""
        try:
            stats_label = self.query_one("#session-stats", Label)
            stats_label.update(
                f"Messages: {self.message_count}\nDuration: {self.session_duration}"
            )
        except Exception:
            pass

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
