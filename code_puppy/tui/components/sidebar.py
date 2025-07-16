"""
Sidebar component with history tab.
"""

from textual.containers import Container
from textual.widgets import (
    ListView,
    TabbedContent,
    TabPane,
)
from textual.app import ComposeResult




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
        pass

