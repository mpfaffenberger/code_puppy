"""
Custom message classes for TUI components.
"""

from textual.message import Message


class HistoryEntrySelected(Message):
    """Message sent when a history entry is selected from the sidebar."""
    
    def __init__(self, history_entry: dict) -> None:
        """Initialize with the history entry data."""
        self.history_entry = history_entry
        super().__init__()