"""
Chat message data model.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

from .enums import MessageType


@dataclass
class ChatMessage:
    """Represents a message in the chat interface."""

    id: str
    type: MessageType
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = None
    group_id: str = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
