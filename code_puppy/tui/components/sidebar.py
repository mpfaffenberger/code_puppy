"""
Sidebar component for session history.
"""

from textual.containers import Container
from textual.widgets import Static, ListView
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

    #sidebar-title {
        dock: top;
        height: 3;
        text-align: center;
        background: $primary;
        color: $text;
        padding: 1;
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
    """

    def compose(self) -> ComposeResult:
        yield Static("📜 Session History", id="sidebar-title")
        yield ListView(id="history-list")