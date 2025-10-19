"""Tests for code_puppy.tui.models.enums.

This module tests the TUI enum definitions used throughout
the TUI interface for message type classification.
"""

import pytest

# Import the enum directly by importing only the enums module,
# bypassing the tui package __init__ which has heavy dependencies
import importlib.util
import sys
from pathlib import Path

# Load the enums module directly without triggering tui.__init__
module_path = Path(__file__).parent.parent / "code_puppy" / "tui" / "models" / "enums.py"
spec = importlib.util.spec_from_file_location("enums", module_path)
enums_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(enums_module)

MessageType = enums_module.MessageType


class TestMessageTypeEnum:
    """Test MessageType enum values and behavior."""

    def test_message_type_has_all_expected_values(self):
        """Test that MessageType enum has all expected message types."""
        expected_types = {
            "USER",
            "AGENT",
            "SYSTEM",
            "ERROR",
            "DIVIDER",
            "INFO",
            "SUCCESS",
            "WARNING",
            "TOOL_OUTPUT",
            "COMMAND_OUTPUT",
            "AGENT_REASONING",
            "PLANNED_NEXT_STEPS",
            "AGENT_RESPONSE",
        }
        
        actual_types = {member.name for member in MessageType}
        assert actual_types == expected_types

    def test_message_type_values_are_strings(self):
        """Test that all MessageType values are lowercase strings."""
        for member in MessageType:
            assert isinstance(member.value, str)
            # Most values should be lowercase versions of their names
            assert member.value == member.name.lower().replace("_", "_")

    def test_user_message_type(self):
        """Test USER message type."""
        assert MessageType.USER.value == "user"
        assert MessageType.USER.name == "USER"

    def test_agent_message_type(self):
        """Test AGENT message type."""
        assert MessageType.AGENT.value == "agent"
        assert MessageType.AGENT.name == "AGENT"

    def test_system_message_type(self):
        """Test SYSTEM message type."""
        assert MessageType.SYSTEM.value == "system"
        assert MessageType.SYSTEM.name == "SYSTEM"

    def test_error_message_type(self):
        """Test ERROR message type."""
        assert MessageType.ERROR.value == "error"
        assert MessageType.ERROR.name == "ERROR"

    def test_divider_message_type(self):
        """Test DIVIDER message type."""
        assert MessageType.DIVIDER.value == "divider"
        assert MessageType.DIVIDER.name == "DIVIDER"

    def test_info_message_type(self):
        """Test INFO message type."""
        assert MessageType.INFO.value == "info"
        assert MessageType.INFO.name == "INFO"

    def test_success_message_type(self):
        """Test SUCCESS message type."""
        assert MessageType.SUCCESS.value == "success"
        assert MessageType.SUCCESS.name == "SUCCESS"

    def test_warning_message_type(self):
        """Test WARNING message type."""
        assert MessageType.WARNING.value == "warning"
        assert MessageType.WARNING.name == "WARNING"

    def test_tool_output_message_type(self):
        """Test TOOL_OUTPUT message type."""
        assert MessageType.TOOL_OUTPUT.value == "tool_output"
        assert MessageType.TOOL_OUTPUT.name == "TOOL_OUTPUT"

    def test_command_output_message_type(self):
        """Test COMMAND_OUTPUT message type."""
        assert MessageType.COMMAND_OUTPUT.value == "command_output"
        assert MessageType.COMMAND_OUTPUT.name == "COMMAND_OUTPUT"

    def test_agent_reasoning_message_type(self):
        """Test AGENT_REASONING message type."""
        assert MessageType.AGENT_REASONING.value == "agent_reasoning"
        assert MessageType.AGENT_REASONING.name == "AGENT_REASONING"

    def test_planned_next_steps_message_type(self):
        """Test PLANNED_NEXT_STEPS message type."""
        assert MessageType.PLANNED_NEXT_STEPS.value == "planned_next_steps"
        assert MessageType.PLANNED_NEXT_STEPS.name == "PLANNED_NEXT_STEPS"

    def test_agent_response_message_type(self):
        """Test AGENT_RESPONSE message type."""
        assert MessageType.AGENT_RESPONSE.value == "agent_response"
        assert MessageType.AGENT_RESPONSE.name == "AGENT_RESPONSE"

    def test_enum_members_are_unique(self):
        """Test that all enum members have unique values."""
        values = [member.value for member in MessageType]
        assert len(values) == len(set(values)), "Duplicate enum values found"

    def test_can_access_by_value(self):
        """Test that enum members can be accessed by their value."""
        assert MessageType("user") == MessageType.USER
        assert MessageType("agent") == MessageType.AGENT
        assert MessageType("error") == MessageType.ERROR

    def test_invalid_value_raises_error(self):
        """Test that accessing invalid value raises ValueError."""
        with pytest.raises(ValueError):
            MessageType("invalid_type")

    def test_enum_is_iterable(self):
        """Test that MessageType enum can be iterated."""
        message_types = list(MessageType)
        assert len(message_types) == 13
        assert MessageType.USER in message_types
        assert MessageType.AGENT in message_types

    def test_enum_members_are_comparable(self):
        """Test that enum members can be compared."""
        assert MessageType.USER == MessageType.USER
        assert MessageType.USER != MessageType.AGENT
        assert MessageType.ERROR != MessageType.WARNING

    def test_enum_members_are_hashable(self):
        """Test that enum members can be used as dict keys or in sets."""
        message_dict = {
            MessageType.USER: "user message",
            MessageType.AGENT: "agent message",
        }
        assert message_dict[MessageType.USER] == "user message"
        
        message_set = {MessageType.USER, MessageType.AGENT, MessageType.ERROR}
        assert len(message_set) == 3
        assert MessageType.USER in message_set
