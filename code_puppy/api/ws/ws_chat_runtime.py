"""Connection-scoped runtime state for the chat WebSocket.

This module intentionally stores only ephemeral mutable state that previously
lived as local variables inside ``websocket_chat``. Each WebSocket connection
creates its own instance so there is no shared mutable state across sessions.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WebSocketChatRuntime:
    """Ephemeral state for one active chat WebSocket connection."""

    session_id: str
    ctx: Any | None = None
    session_title: str = ""
    session_working_directory: str = ""
    session_pinned: bool = False
    last_context_sent_directory: str = ""
    existing_history: Any | None = None
    agent: Any | None = None
    agent_name: str = "code-puppy"
    model_name: str = "unknown"
    active_drain_task: asyncio.Task | None = None
    active_agent_task: asyncio.Task | None = None
    stop_draining: asyncio.Event = field(default_factory=asyncio.Event)

    def sync_from_ctx(self) -> None:
        """Refresh convenience aliases from the attached session context."""
        if self.ctx is None:
            return
        self.agent = getattr(self.ctx, "agent", None)
        self.agent_name = getattr(self.ctx, "agent_name", self.agent_name)
        self.model_name = getattr(self.ctx, "model_name", self.model_name)
        self.session_title = getattr(self.ctx, "title", self.session_title)
        self.session_working_directory = getattr(
            self.ctx,
            "working_directory",
            self.session_working_directory,
        )
        self.session_pinned = bool(getattr(self.ctx, "pinned", self.session_pinned))


__all__ = ["WebSocketChatRuntime"]
