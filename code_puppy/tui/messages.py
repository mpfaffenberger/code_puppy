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


class CommandSelected(Message):
    """Message sent when a command is selected from the history modal."""

    def __init__(self, command: str) -> None:
        """Initialize with the command text.

        Args:
            command: The command text that was selected
        """
        self.command = command
        super().__init__()
