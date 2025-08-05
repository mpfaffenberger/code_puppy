"""
Sidebar component with history tab.
"""

import time

from textual import on
from textual.app import ComposeResult
from textual.containers import Container
from textual.events import Key
from textual.widgets import Label, ListItem, ListView, TabbedContent, TabPane

from ..components.command_history_modal import CommandHistoryModal

# Import the shared message class and history reader
from ..models.command_history import HistoryFileReader


class Sidebar(Container):
    """Sidebar with session history."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Double-click detection variables
        self._last_click_time = 0
        self._last_clicked_item = None
        self._double_click_threshold = 0.5  # 500ms for double-click

        # Initialize history reader
        self.history_reader = HistoryFileReader()

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

        # Load command history
        self.load_command_history()

    @on(ListView.Highlighted)
    def on_list_highlighted(self, event: ListView.Highlighted) -> None:
        """Handle highlighting of list items to ensure they can be selected."""
        # This ensures the item gets focus when highlighted by arrow keys
        if event.list_view.id == "history-list":
            event.list_view.focus()

    @on(ListView.Selected)
    def on_list_selected(self, event: ListView.Selected) -> None:
        """Handle selection of list items (including mouse clicks).

        Implements double-click detection to allow users to retrieve history items
        by either pressing ENTER or double-clicking with the mouse.
        """
        if event.list_view.id == "history-list":
            current_time = time.time()
            selected_item = event.item

            # Check if this is a double-click
            if (
                selected_item == self._last_clicked_item
                and current_time - self._last_click_time <= self._double_click_threshold
                and hasattr(selected_item, "command_entry")
            ):
                # Double-click detected! Show command in modal
                command_entry = selected_item.command_entry
                self.app.push_screen(
                    CommandHistoryModal(
                        command=command_entry["command"],
                        timestamp=command_entry["timestamp"],
                    )
                )

                # Reset click tracking to prevent triple-click issues
                self._last_click_time = 0
                self._last_clicked_item = None
            else:
                # Single click - just update tracking
                self._last_click_time = current_time
                self._last_clicked_item = selected_item

    @on(Key)
    def on_key(self, event: Key) -> None:
        """Handle key events for the sidebar."""
        # Handle Enter key on the history list
        if event.key == "enter":
            history_list = self.query_one("#history-list", ListView)
            if (
                history_list.has_focus
                and history_list.highlighted_child
                and hasattr(history_list.highlighted_child, "command_entry")
            ):
                # Show command details in modal
                command_entry = history_list.highlighted_child.command_entry
                self.app.push_screen(
                    CommandHistoryModal(
                        command=command_entry["command"],
                        timestamp=command_entry["timestamp"],
                    )
                )

                # Stop propagation
                event.stop()
                event.prevent_default()

    def load_command_history(self) -> None:
        """Load command history from file into the history list."""
        try:
            # Clear existing items
            history_list = self.query_one("#history-list", ListView)
            history_list.clear()

            # Get command history entries (limit to last 50)
            entries = self.history_reader.read_history(max_entries=50)

            if not entries:
                # No history available
                history_list.append(
                    ListItem(Label("No command history", classes="history-empty"))
                )
                return

            # Add entries to the list (most recent first)
            for entry in entries:
                timestamp = entry["timestamp"]
                command = entry["command"]

                # Format timestamp for display
                time_display = self.history_reader.format_timestamp(timestamp)

                # Truncate command for display if needed
                display_text = command
                if len(display_text) > 60:
                    display_text = display_text[:57] + "..."

                # Create list item
                label = Label(
                    f"[{time_display}] {display_text}", classes="history-command"
                )
                list_item = ListItem(label)
                list_item.command_entry = entry
                history_list.append(list_item)

            # Focus on the most recent command (first in the list)
            if len(history_list.children) > 0:
                history_list.index = 0

        except Exception as e:
            # Add error item
            history_list = self.query_one("#history-list", ListView)
            history_list.clear()
            history_list.append(
                ListItem(
                    Label(f"Error loading history: {str(e)}", classes="history-error")
                )
            )
