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

    AGENT_REASONING = "agent_reasoning"
    PLANNED_NEXT_STEPS = "planned_next_steps"
