"""
Command history reader for TUI history tab.
"""

import os
import re
from datetime import datetime
from typing import Dict, List

from code_puppy.config import COMMAND_HISTORY_FILE


class HistoryFileReader:
    """Reads and parses the command history file for display in the TUI history tab."""

    def __init__(self, history_file_path: str = COMMAND_HISTORY_FILE):
        """Initialize the history file reader.

        Args:
            history_file_path: Path to the command history file. Defaults to the standard location.
        """
        self.history_file_path = history_file_path
        self._timestamp_pattern = re.compile(
            r"^# (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
        )

    def read_history(self, max_entries: int = 100) -> List[Dict[str, str]]:
        """Read command history from the history file.

        Args:
            max_entries: Maximum number of entries to read. Defaults to 100.

        Returns:
            List of history entries with timestamp and command, most recent first.
        """
        if not os.path.exists(self.history_file_path):
            return []

        try:
            with open(self.history_file_path, "r") as f:
                content = f.read()

            # Split content by timestamp marker
            raw_chunks = re.split(r"(# \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", content)

            # Filter out empty chunks
            chunks = [chunk for chunk in raw_chunks if chunk.strip()]

            entries = []

            # Process chunks in pairs (timestamp and command)
            i = 0
            while i < len(chunks) - 1:
                if self._timestamp_pattern.match(chunks[i]):
                    timestamp = self._timestamp_pattern.match(chunks[i]).group(1)
                    command_text = chunks[i + 1].strip()

                    if command_text:  # Skip empty commands
                        entries.append(
                            {"timestamp": timestamp, "command": command_text}
                        )

                    i += 2
                else:
                    # Skip invalid chunks
                    i += 1

            # Limit the number of entries and reverse to get most recent first
            return entries[-max_entries:][::-1]

        except Exception:
            # Return empty list on any error
            return []

    def format_timestamp(self, timestamp: str, format_str: str = "%H:%M:%S") -> str:
        """Format a timestamp string for display.

        Args:
            timestamp: ISO format timestamp string (YYYY-MM-DDThh:mm:ss)
            format_str: Format string for datetime.strftime

        Returns:
            Formatted timestamp string
        """
        try:
            dt = datetime.fromisoformat(timestamp)
            return dt.strftime(format_str)
        except (ValueError, TypeError):
            return timestamp
