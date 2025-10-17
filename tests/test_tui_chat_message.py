"""Tests for code_puppy.tui.models.chat_message.

This module tests the ChatMessage dataclass used in the TUI
for representing messages in the chat interface.
"""

import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

# Load enums first (needed for relative import in chat_message)
enums_path = Path(__file__).parent.parent / "code_puppy" / "tui" / "models" / "enums.py"
spec_enums = importlib.util.spec_from_file_location(
    "code_puppy.tui.models.enums", enums_path
)
enums_module = importlib.util.module_from_spec(spec_enums)
sys.modules["code_puppy.tui.models.enums"] = enums_module
spec_enums.loader.exec_module(enums_module)

MessageType = enums_module.MessageType

# Now load chat_message module
module_path = (
    Path(__file__).parent.parent / "code_puppy" / "tui" / "models" / "chat_message.py"
)
spec = importlib.util.spec_from_file_location(
    "code_puppy.tui.models.chat_message", module_path
)
chat_message_module = importlib.util.module_from_spec(spec)
sys.modules["code_puppy.tui.models.chat_message"] = chat_message_module
spec.loader.exec_module(chat_message_module)

ChatMessage = chat_message_module.ChatMessage


class TestChatMessageDataclass:
    """Test ChatMessage dataclass creation and behavior."""

    def test_create_basic_message(self):
        """Test creating a basic ChatMessage."""
        timestamp = datetime.now()
        message = ChatMessage(
            id="msg-1",
            type=MessageType.USER,
            content="Hello, world!",
            timestamp=timestamp,
        )

        assert message.id == "msg-1"
        assert message.type == MessageType.USER
        assert message.content == "Hello, world!"
        assert message.timestamp == timestamp
        assert message.metadata == {}  # Should be initialized in __post_init__
        assert message.group_id is None

    def test_metadata_defaults_to_empty_dict(self):
        """Test that metadata is initialized to empty dict if not provided."""
        message = ChatMessage(
            id="msg-1",
            type=MessageType.SYSTEM,
            content="System message",
            timestamp=datetime.now(),
        )

        assert message.metadata == {}
        assert isinstance(message.metadata, dict)

    def test_metadata_can_be_provided(self):
        """Test creating message with custom metadata."""
        metadata = {"user": "alice", "session_id": "abc123"}
        message = ChatMessage(
            id="msg-2",
            type=MessageType.AGENT,
            content="Agent response",
            timestamp=datetime.now(),
            metadata=metadata,
        )

        assert message.metadata == metadata
        assert message.metadata["user"] == "alice"

    def test_group_id_optional(self):
        """Test that group_id is optional and defaults to None."""
        message = ChatMessage(
            id="msg-3",
            type=MessageType.ERROR,
            content="Error occurred",
            timestamp=datetime.now(),
        )

        assert message.group_id is None

    def test_group_id_can_be_set(self):
        """Test creating message with group_id."""
        message = ChatMessage(
            id="msg-4",
            type=MessageType.INFO,
            content="Info message",
            timestamp=datetime.now(),
            group_id="group-123",
        )

        assert message.group_id == "group-123"

    def test_all_message_types(self):
        """Test creating messages with all MessageType values."""
        timestamp = datetime.now()

        for msg_type in MessageType:
            message = ChatMessage(
                id=f"msg-{msg_type.value}",
                type=msg_type,
                content=f"Content for {msg_type.value}",
                timestamp=timestamp,
            )
            assert message.type == msg_type

    def test_message_with_empty_content(self):
        """Test creating message with empty content."""
        message = ChatMessage(
            id="msg-5",
            type=MessageType.DIVIDER,
            content="",
            timestamp=datetime.now(),
        )

        assert message.content == ""

    def test_message_with_multiline_content(self):
        """Test creating message with multiline content."""
        content = """Line 1
Line 2
Line 3"""
        message = ChatMessage(
            id="msg-6",
            type=MessageType.TOOL_OUTPUT,
            content=content,
            timestamp=datetime.now(),
        )

        assert "\n" in message.content
        assert message.content.count("\n") == 2

    def test_metadata_mutability(self):
        """Test that metadata dict can be modified after creation."""
        message = ChatMessage(
            id="msg-7",
            type=MessageType.AGENT_REASONING,
            content="Reasoning content",
            timestamp=datetime.now(),
        )

        # Initially empty
        assert len(message.metadata) == 0

        # Add metadata
        message.metadata["key"] = "value"
        assert message.metadata["key"] == "value"

    def test_dataclass_equality(self):
        """Test that two messages with same data are equal."""
        timestamp = datetime(2025, 1, 1, 12, 0, 0)

        msg1 = ChatMessage(
            id="msg-eq",
            type=MessageType.USER,
            content="Test",
            timestamp=timestamp,
        )

        msg2 = ChatMessage(
            id="msg-eq",
            type=MessageType.USER,
            content="Test",
            timestamp=timestamp,
        )

        assert msg1 == msg2

    def test_dataclass_inequality(self):
        """Test that messages with different data are not equal."""
        timestamp = datetime.now()

        msg1 = ChatMessage(
            id="msg-1", type=MessageType.USER, content="A", timestamp=timestamp
        )

        msg2 = ChatMessage(
            id="msg-2", type=MessageType.USER, content="B", timestamp=timestamp
        )

        assert msg1 != msg2

    def test_message_is_not_hashable_due_to_mutable_metadata(self):
        """Test that ChatMessage is not hashable due to mutable metadata dict.
        
        Dataclasses with mutable default fields (like dict) are not hashable
        by default, which is correct behavior to prevent issues.
        """
        msg1 = ChatMessage(
            id="msg-1",
            type=MessageType.USER,
            content="A",
            timestamp=datetime.now(),
        )

        # Dataclasses with mutable defaults are not hashable
        with pytest.raises(TypeError, match="unhashable type"):
            hash(msg1)

        # Cannot be used in sets
        with pytest.raises(TypeError):
            {msg1}

        # Cannot be used as dict keys
        with pytest.raises(TypeError):
            {msg1: "value"}

    def test_nested_metadata(self):
        """Test message with nested metadata structures."""
        metadata = {
            "user": {"name": "Alice", "id": 123},
            "context": {"session": "abc", "thread": "xyz"},
        }

        message = ChatMessage(
            id="msg-nested",
            type=MessageType.SUCCESS,
            content="Success!",
            timestamp=datetime.now(),
            metadata=metadata,
        )

        assert message.metadata["user"]["name"] == "Alice"
        assert message.metadata["context"]["session"] == "abc"

    def test_timestamp_types(self):
        """Test that timestamp must be datetime."""
        timestamp = datetime.now()
        message = ChatMessage(
            id="msg-ts",
            type=MessageType.WARNING,
            content="Warning",
            timestamp=timestamp,
        )

        assert isinstance(message.timestamp, datetime)

    def test_message_with_special_characters(self):
        """Test message content with special characters."""
        content = "Special: 🐶 émojis & ünïcödë"
        message = ChatMessage(
            id="msg-special",
            type=MessageType.COMMAND_OUTPUT,
            content=content,
            timestamp=datetime.now(),
        )

        assert "🐶" in message.content
        assert "ünïcödë" in message.content

    def test_long_content(self):
        """Test message with very long content."""
        long_content = "A" * 10000
        message = ChatMessage(
            id="msg-long",
            type=MessageType.AGENT_RESPONSE,
            content=long_content,
            timestamp=datetime.now(),
        )

        assert len(message.content) == 10000

    def test_post_init_doesnt_overwrite_provided_metadata(self):
        """Test that __post_init__ doesn't overwrite explicitly provided metadata."""
        provided_metadata = {"existing": "data"}
        message = ChatMessage(
            id="msg-meta",
            type=MessageType.USER,
            content="Test",
            timestamp=datetime.now(),
            metadata=provided_metadata,
        )

        # Should keep the provided metadata, not replace with {}
        assert message.metadata == provided_metadata
        assert "existing" in message.metadata
