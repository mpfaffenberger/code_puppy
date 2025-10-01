"""
Command history management utilities for both CLI and TUI modes.

This module provides a unified interface for managing command history,
handling the conversion between the timestamped storage format and
the plain command format needed for prompt_toolkit history navigation.
"""

import os
import re
from typing import List, Optional
from datetime import datetime

from code_puppy.config import COMMAND_HISTORY_FILE


class CommandHistoryManager:
    """Manages command history for both CLI and TUI interfaces.
    
    Handles the conversion between the timestamped storage format:
    # 2024-05-15T14:30:22
    some command here
    
    And the plain command format needed for prompt_toolkit.
    """
    
    def __init__(self, history_file_path: str = COMMAND_HISTORY_FILE):
        """Initialize the history manager.
        
        Args:
            history_file_path: Path to the command history file.
        """
        self.history_file_path = history_file_path
        self._timestamp_pattern = re.compile(
            r"^# (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
        )
    
    def get_commands_for_prompt_toolkit(self, max_entries: int = 1000) -> List[str]:
        """Extract plain commands for prompt_toolkit history.
        
        Args:
            max_entries: Maximum number of commands to return.
            
        Returns:
            List of command strings, most recent last (prompt_toolkit format).
        """
        if not os.path.exists(self.history_file_path):
            return []
        
        try:
            with open(self.history_file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
            if not content:
                return []
            
            # Split content by lines and process
            lines = content.split("\n")
            commands = []
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                # Check if this line is a timestamp
                if self._timestamp_pattern.match(line):
                    # Next line should be the command
                    if i + 1 < len(lines):
                        command = lines[i + 1].strip()
                        if command:  # Skip empty commands
                            commands.append(command)
                    i += 2  # Skip both timestamp and command lines
                else:
                    # Handle legacy format or malformed entries
                    if line and not line.startswith("#"):
                        commands.append(line)
                    i += 1
            
            # Return most recent commands, but in chronological order for prompt_toolkit
            # (prompt_toolkit expects oldest first, newest last)
            return commands[-max_entries:] if commands else []
            
        except Exception as e:
            # Silently handle errors and return empty list
            return []
    
    def get_recent_commands(self, max_entries: int = 50) -> List[str]:
        """Get recent commands for TUI navigation (newest first).
        
        Args:
            max_entries: Maximum number of commands to return.
            
        Returns:
            List of command strings, most recent first (for TUI cycling).
        """
        commands = self.get_commands_for_prompt_toolkit(max_entries)
        # Reverse for TUI - we want newest first for up-arrow navigation
        return list(reversed(commands))
    
    def add_command(self, command: str) -> None:
        """Add a command to history with timestamp.
        
        Args:
            command: The command to add to history.
        """
        if not command or not command.strip():
            return
            
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.history_file_path), exist_ok=True)
            
            timestamp = datetime.now().isoformat(timespec="seconds")
            with open(self.history_file_path, "a", encoding="utf-8") as f:
                f.write(f"\n# {timestamp}\n{command.strip()}\n")
                
        except Exception:
            # Silently handle errors - don't interrupt user workflow
            pass
    
    def get_history_stats(self) -> dict:
        """Get statistics about the command history.
        
        Returns:
            Dictionary with history statistics.
        """
        commands = self.get_commands_for_prompt_toolkit()
        return {
            "total_commands": len(commands),
            "unique_commands": len(set(commands)),
            "history_file_exists": os.path.exists(self.history_file_path),
            "history_file_size": os.path.getsize(self.history_file_path) if os.path.exists(self.history_file_path) else 0
        }
    
    def clear_history(self) -> bool:
        """Clear all command history.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            if os.path.exists(self.history_file_path):
                with open(self.history_file_path, "w", encoding="utf-8") as f:
                    f.write("")  # Clear the file
            return True
        except Exception:
            return False


# Global instance for easy access
_global_history_manager = None


def get_history_manager() -> CommandHistoryManager:
    """Get the global command history manager instance.
    
    Returns:
        Singleton CommandHistoryManager instance.
    """
    global _global_history_manager
    if _global_history_manager is None:
        _global_history_manager = CommandHistoryManager()
    return _global_history_manager


def create_prompt_toolkit_history_file() -> Optional[str]:
    """Create a temporary history file compatible with prompt_toolkit.
    
    This function creates a temporary file containing only the commands
    (without timestamps) that prompt_toolkit can use for history navigation.
    
    Returns:
        Path to the temporary history file, or None if creation failed.
    """
    import tempfile
    
    try:
        history_manager = get_history_manager()
        commands = history_manager.get_commands_for_prompt_toolkit()
        
        if not commands:
            return None
        
        # Create a temporary file for prompt_toolkit
        fd, temp_path = tempfile.mkstemp(prefix="code_puppy_prompt_history_", suffix=".txt")
        
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for command in commands:
                f.write(f"{command}\n")
        
        return temp_path
        
    except Exception:
        return None
