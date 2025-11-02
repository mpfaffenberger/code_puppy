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
