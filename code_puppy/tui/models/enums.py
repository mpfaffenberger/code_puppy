"""
Enums for the TUI module.
"""

from enum import Enum


class MessageType(Enum):
    """Types of messages in the chat interface."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    ERROR = "error"
    DIVIDER = "divider"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    TOOL_OUTPUT = "tool_output"
    COMMAND_OUTPUT = "command_output"

    AGENT_REASONING = "agent_reasoning"
    PLANNED_NEXT_STEPS = "planned_next_steps"
    AGENT_RESPONSE = "agent_response"


class MessageCategory(Enum):
    """Categories for grouping related message types."""

    INFORMATIONAL = "informational"
    TOOL_CALL = "tool_call"
    USER = "user"
    SYSTEM = "system"
    THINKING = "thinking"
    AGENT_RESPONSE = "agent_response"
    ERROR = "error"


# Mapping from MessageType to MessageCategory for grouping
MESSAGE_TYPE_TO_CATEGORY = {
    MessageType.INFO: MessageCategory.INFORMATIONAL,
    MessageType.SUCCESS: MessageCategory.INFORMATIONAL,
    MessageType.WARNING: MessageCategory.INFORMATIONAL,
    MessageType.TOOL_OUTPUT: MessageCategory.TOOL_CALL,
    MessageType.COMMAND_OUTPUT: MessageCategory.TOOL_CALL,
    MessageType.USER: MessageCategory.USER,
    MessageType.SYSTEM: MessageCategory.SYSTEM,
    MessageType.AGENT_REASONING: MessageCategory.THINKING,
    MessageType.PLANNED_NEXT_STEPS: MessageCategory.THINKING,
    MessageType.AGENT_RESPONSE: MessageCategory.AGENT_RESPONSE,
    MessageType.AGENT: MessageCategory.AGENT_RESPONSE,
    MessageType.ERROR: MessageCategory.ERROR,
    MessageType.DIVIDER: MessageCategory.SYSTEM,
}


def get_message_category(message_type: MessageType) -> MessageCategory:
    """Get the category for a given message type."""
    return MESSAGE_TYPE_TO_CATEGORY.get(message_type, MessageCategory.SYSTEM)
