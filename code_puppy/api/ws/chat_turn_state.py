"""Per-turn mutable state for the WebSocket chat handler.

This keeps WebSocket-only streaming/tool bookkeeping out of the top-level
handler flow without changing runtime behavior.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class WebSocketTurnState:
    """Mutable per-turn state for structured WebSocket streaming."""

    collected_text: list[str] = field(default_factory=list)
    active_parts: dict[int, dict[str, Any]] = field(default_factory=dict)
    tool_id_aliases: dict[str, str] = field(default_factory=dict)
    tool_group_ids: dict[str, str] = field(default_factory=dict)
    pending_tool_calls: dict[str, dict[str, Any]] = field(default_factory=dict)
    current_tool_name: str | None = None
    current_tool_group_id: str | None = None
    b1_streaming_used: bool = False
    agent_error: object | None = None
