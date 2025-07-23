"""
Sidebar component with history tab.
"""

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.widgets import ListView, TabbedContent, TabPane

# Import the shared message class
from ..messages import HistoryEntrySelected


class Sidebar(Container):
    """Sidebar with session history."""

    DEFAULT_CSS = """
    Sidebar {
        dock: left;
        width: 30;
        min-width: 20;
        max-width: 50;
        background: $surface;
        border-right: solid $primary;
        display: none;
    }

    #sidebar-tabs {
        height: 1fr;
    }

    #history-list {
        height: 1fr;
    }

    .history-interactive {
        color: #34d399;
    }

    .history-tui {
        color: #60a5fa;
    }

    .history-system {
        color: #fbbf24;
        text-style: italic;
    }

    .history-command {
        color: #f87171;
    }

    .history-generic {
        color: #d1d5db;
    }

    .history-empty {
        color: #6b7280;
        text-style: italic;
    }

    .history-error {
        color: #ef4444;
    }

    .file-item {
        color: #d1d5db;
    }
    """

    def compose(self) -> ComposeResult:
        """Create the sidebar layout with tabs."""
        with TabbedContent(id="sidebar-tabs"):
            with TabPane("📜 History", id="history-tab"):
                yield ListView(id="history-list")

    def on_mount(self) -> None:
        """Initialize the sidebar when mounted."""
        # Set up event handlers for keyboard interaction
        history_list = self.query_one("#history-list", ListView)

        # Add a class to make it focusable
        history_list.can_focus = True

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle highlighting of list items to ensure they can be selected."""
        # This ensures the item gets focus when highlighted by arrow keys
        if event.list_view.id == "history-list":
            event.list_view.focus()

    @on(Key)
    def on_key(self, event: Key) -> None:
        """Handle key events for the sidebar."""
        # Handle Enter key on the history list
        if event.key == "enter":
            history_list = self.query_one("#history-list", ListView)
            if (
                history_list.has_focus
                and history_list.highlighted_child
                and hasattr(history_list.highlighted_child, "history_entry")
            ):
                # Post a message to the app with the selected history entry
                history_entry = history_list.highlighted_child.history_entry
                self.post_message(HistoryEntrySelected(history_entry))

                # Stop propagation
                event.stop()
                event.prevent_default()
