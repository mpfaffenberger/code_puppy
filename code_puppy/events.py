"""Versioned transport events shared by HTTP, SDK, and RPC clients."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from code_puppy.messaging.messages import BaseMessage


class EventEnvelope(BaseModel):
    """Stable public envelope around internal messages and lifecycle events."""

    schema_version: int = Field(default=1, ge=1)
    sequence: int = Field(ge=1)
    type: str
    session_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_message(cls, message: BaseMessage, *, sequence: int) -> "EventEnvelope":
        if not message.session_id:
            raise ValueError("A transport event requires a session_id")
        return cls(
            sequence=sequence,
            type=message.__class__.__name__,
            session_id=message.session_id,
            timestamp=message.timestamp,
            data=message.model_dump(mode="json"),
        )

    def json_line(self) -> str:
        return self.model_dump_json()
