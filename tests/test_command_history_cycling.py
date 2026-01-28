"""
Tests for command history cycling functionality.

This module tests both CLI and TUI command history navigation,
ensuring up/down arrow keys work correctly for cycling through
previously entered commands.
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from code_puppy.command_line.history_manager import (
    CommandHistoryManager,
    get_history_manager,
    create_prompt_toolkit_history_file,
)


class TestCommandHistoryManager:
    """Test the CommandHistoryManager class."""

    def test_empty_history_file(self):
        """Test behavior with an empty or non-existent history file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            os.unlink(temp_path)  # Remove the file to test non-existent case
            manager = CommandHistoryManager(temp_path)

            commands = manager.get_commands_for_prompt_toolkit()
            assert commands == []

            recent = manager.get_recent_commands()
            assert recent == []

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_add_and_retrieve_commands(self):
        """Test adding commands and retrieving them."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)

            # Add some test commands
            test_commands = [
                "ls -la",
                "git status",
                "python main.py",
                "echo 'hello world'",
            ]

            for cmd in test_commands:
                manager.add_command(cmd)

            # Test prompt_toolkit format (chronological order)
            pt_commands = manager.get_commands_for_prompt_toolkit()
            assert pt_commands == test_commands

            # Test TUI format (reverse chronological for up-arrow navigation)
            recent_commands = manager.get_recent_commands()
            assert recent_commands == list(reversed(test_commands))

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_malformed_history_handling(self):
        """Test handling of malformed history entries."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            # Write some malformed history
            f.write("# 2024-05-15T14:30:22\n")
            f.write("valid command 1\n")
            f.write("orphaned command without timestamp\n")
            f.write("# malformed timestamp\n")
            f.write("# 2024-05-15T15:30:22\n")
            f.write("valid command 2\n")
            f.write("\n")  # Empty line
            f.write("# 2024-05-15T16:30:22\n")
            f.write("")  # Empty command
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)
            commands = manager.get_commands_for_prompt_toolkit()

            # Should extract valid commands and handle malformed ones gracefully
            expected = [
                "valid command 1",
                "orphaned command without timestamp",
                "valid command 2",
            ]
            assert commands == expected

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_max_entries_limit(self):
        """Test that max_entries parameter works correctly."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)

            # Add many commands
            for i in range(20):
                manager.add_command(f"command {i}")

            # Test limiting to fewer commands
            limited_commands = manager.get_commands_for_prompt_toolkit(max_entries=5)
            assert len(limited_commands) == 5
            # Should get the most recent 5
            expected = [f"command {i}" for i in range(15, 20)]
            assert limited_commands == expected

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_empty_command_handling(self):
        """Test that empty commands are not added to history."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)

            # Try to add empty/whitespace commands
            manager.add_command("")
            manager.add_command("   ")
            manager.add_command("\n")
            manager.add_command("valid command")
            manager.add_command("\t\t")

            commands = manager.get_commands_for_prompt_toolkit()
            assert commands == ["valid command"]

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_history_stats(self):
        """Test history statistics functionality."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)

            # Add some commands including duplicates
            commands = ["ls", "git status", "ls", "python main.py", "ls"]
            for cmd in commands:
                manager.add_command(cmd)

            stats = manager.get_history_stats()
            assert stats["total_commands"] == 5
            assert stats["unique_commands"] == 3  # ls, git status, python main.py
            assert stats["history_file_exists"] is True
            assert stats["history_file_size"] > 0

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_clear_history(self):
        """Test clearing command history."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            manager = CommandHistoryManager(temp_path)

            # Add some commands
            manager.add_command("command 1")
            manager.add_command("command 2")

            # Verify commands exist
            assert len(manager.get_commands_for_prompt_toolkit()) == 2

            # Clear history
            result = manager.clear_history()
            assert result is True

            # Verify history is cleared
            assert len(manager.get_commands_for_prompt_toolkit()) == 0

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestPromptToolkitIntegration:
    """Test prompt_toolkit history file generation."""

    def test_create_prompt_toolkit_history_file(self):
        """Test creating a prompt_toolkit compatible history file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            # Create a properly formatted history file
            f.write("# 2024-05-15T14:30:22\n")
            f.write("first command\n")
            f.write("# 2024-05-15T15:30:22\n")
            f.write("second command\n")
            original_path = f.name

        try:
            # Mock the global history manager
            with patch(
                "code_puppy.command_line.history_manager.get_history_manager"
            ) as mock_get_manager:
                mock_manager = MagicMock()
                mock_manager.get_commands_for_prompt_toolkit.return_value = [
                    "first command",
                    "second command",
                ]
                mock_get_manager.return_value = mock_manager

                # Create prompt_toolkit history file
                pt_file = create_prompt_toolkit_history_file()

                assert pt_file is not None
                assert os.path.exists(pt_file)

                # Verify content
                with open(pt_file, "r") as f:
                    content = f.read()
                    lines = content.strip().split("\n")
                    assert lines == ["first command", "second command"]

                # Clean up temp file
                os.unlink(pt_file)

        finally:
            if os.path.exists(original_path):
                os.unlink(original_path)

    def test_create_prompt_toolkit_history_file_empty(self):
        """Test creating prompt_toolkit history file with no commands."""
        with patch(
            "code_puppy.command_line.history_manager.get_history_manager"
        ) as mock_get_manager:
            mock_manager = MagicMock()
            mock_manager.get_commands_for_prompt_toolkit.return_value = []
            mock_get_manager.return_value = mock_manager

            # Should return None for empty history
            pt_file = create_prompt_toolkit_history_file()
            assert pt_file is None


class TestGlobalHistoryManager:
    """Test the global history manager singleton."""

    def test_singleton_behavior(self):
        """Test that get_history_manager returns the same instance."""
        manager1 = get_history_manager()
        manager2 = get_history_manager()

        assert manager1 is manager2
        assert isinstance(manager1, CommandHistoryManager)



@pytest.mark.integration
class TestEndToEndHistory:
    """Integration tests for complete history workflow."""

    def test_full_workflow(self):
        """Test the complete workflow from adding commands to retrieving them."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            temp_path = f.name

        try:
            # Initialize manager
            manager = CommandHistoryManager(temp_path)

            # Simulate a user session
            session_commands = [
                "cd /tmp",
                "ls -la",
                "git init",
                "git add .",
                "git commit -m 'initial commit'",
                "python -m pytest",
            ]

            # Add commands one by one (simulating user input)
            for cmd in session_commands:
                manager.add_command(cmd)

            # Test CLI retrieval (chronological)
            cli_commands = manager.get_commands_for_prompt_toolkit()
            assert cli_commands == session_commands

            # Test TUI retrieval (reverse chronological for up-arrow)
            tui_commands = manager.get_recent_commands()
            assert tui_commands == list(reversed(session_commands))

            # Test limiting
            recent_3 = manager.get_recent_commands(max_entries=3)
            expected_recent_3 = list(reversed(session_commands[-3:]))
            assert recent_3 == expected_recent_3

            # Test stats
            stats = manager.get_history_stats()
            assert stats["total_commands"] == 6
            assert stats["unique_commands"] == 6

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
