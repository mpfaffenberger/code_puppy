"""Tests for code_puppy.tui.messages.

This module tests the custom Textual message classes used for
event communication in the TUI application.
"""

import importlib.util
from pathlib import Path

# Load the messages module directly without triggering tui.__init__
module_path = Path(__file__).parent.parent / "code_puppy" / "tui" / "messages.py"
spec = importlib.util.spec_from_file_location("messages", module_path)
messages_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(messages_module)

HistoryEntrySelected = messages_module.HistoryEntrySelected
CommandSelected = messages_module.CommandSelected


class TestHistoryEntrySelected:
    """Test HistoryEntrySelected message class."""

    def test_initialization_with_dict(self):
        """Test creating HistoryEntrySelected with a dictionary."""
        entry = {"id": 1, "command": "test command", "timestamp": "2025-01-01"}
        message = HistoryEntrySelected(entry)

        assert message.history_entry == entry
        assert message.history_entry["id"] == 1
        assert message.history_entry["command"] == "test command"

    def test_initialization_with_empty_dict(self):
        """Test creating HistoryEntrySelected with an empty dictionary."""
        entry = {}
        message = HistoryEntrySelected(entry)

        assert message.history_entry == {}
        assert len(message.history_entry) == 0

    def test_initialization_with_nested_dict(self):
        """Test creating HistoryEntrySelected with nested data."""
        entry = {"id": 1, "metadata": {"user": "test_user", "session": "abc123"}}
        message = HistoryEntrySelected(entry)

        assert message.history_entry["metadata"]["user"] == "test_user"
        assert message.history_entry["metadata"]["session"] == "abc123"

    def test_message_is_instance_of_textual_message(self):
        """Test that HistoryEntrySelected inherits from Textual Message."""
        from textual.message import Message

        entry = {"test": "data"}
        message = HistoryEntrySelected(entry)

        assert isinstance(message, Message)

    def test_history_entry_is_mutable(self):
        """Test that the stored history entry can be modified."""
        entry = {"id": 1}
        message = HistoryEntrySelected(entry)

        # Modify the entry
        message.history_entry["new_field"] = "new_value"

        assert message.history_entry["new_field"] == "new_value"
        assert len(message.history_entry) == 2


class TestCommandSelected:
    """Test CommandSelected message class."""

    def test_initialization_with_command_string(self):
        """Test creating CommandSelected with a command string."""
        command = "ls -la"
        message = CommandSelected(command)

        assert message.command == "ls -la"

    def test_initialization_with_empty_string(self):
        """Test creating CommandSelected with an empty command."""
        message = CommandSelected("")

        assert message.command == ""
        assert len(message.command) == 0

    def test_initialization_with_multiline_command(self):
        """Test creating CommandSelected with multiline command."""
        command = "echo 'line 1'\necho 'line 2'\necho 'line 3'"
        message = CommandSelected(command)

        assert message.command == command
        assert "\n" in message.command
        assert message.command.count("\n") == 2

    def test_initialization_with_special_characters(self):
        """Test creating CommandSelected with special characters."""
        command = "grep -r \"test\" . | awk '{print $1}'"
        message = CommandSelected(command)

        assert message.command == command
        assert '"' in message.command
        assert "'" in message.command

    def test_message_is_instance_of_textual_message(self):
        """Test that CommandSelected inherits from Textual Message."""
        from textual.message import Message

        message = CommandSelected("test")

        assert isinstance(message, Message)

    def test_command_is_string_type(self):
        """Test that command attribute is always a string."""
        message = CommandSelected("test command")

        assert isinstance(message.command, str)

    def test_long_command_string(self):
        """Test creating CommandSelected with a very long command."""
        long_command = "echo " + "a" * 1000
        message = CommandSelected(long_command)

        assert len(message.command) == 1005  # "echo " + 1000 'a's
        assert message.command.startswith("echo ")
        assert message.command.endswith("a")


class TestMessageComparison:
    """Test comparison and behavior between different message types."""

    def test_different_message_types_are_different_classes(self):
        """Test that HistoryEntrySelected and CommandSelected are distinct."""
        entry_msg = HistoryEntrySelected({"id": 1})
        command_msg = CommandSelected("test")

        assert type(entry_msg) is not type(command_msg)
        assert not isinstance(entry_msg, CommandSelected)
        assert not isinstance(command_msg, HistoryEntrySelected)

    def test_messages_can_be_created_independently(self):
        """Test that multiple messages can coexist."""
        msg1 = HistoryEntrySelected({"id": 1})
        msg2 = HistoryEntrySelected({"id": 2})
        msg3 = CommandSelected("test1")
        msg4 = CommandSelected("test2")

        assert msg1.history_entry != msg2.history_entry
        assert msg3.command != msg4.command

    def test_message_attributes_are_independent(self):
        """Test that message instances don't share state."""
        msg1 = CommandSelected("command1")
        msg2 = CommandSelected("command2")

        # Modify one shouldn't affect the other
        msg1.command = "modified"

        assert msg1.command == "modified"
        assert msg2.command == "command2"
