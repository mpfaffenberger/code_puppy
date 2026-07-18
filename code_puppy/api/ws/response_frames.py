"""Helpers for WebSocket response/error frame construction.

These utilities are intentionally kept separate from the giant chat handler so
the wire-protocol transformations can be tested and maintained independently.
"""

from __future__ import annotations

import uuid
from typing import Any

from code_puppy.api.error_parser import parse_api_error as _legacy_parse_api_error
from code_puppy.api.ws.schemas import (
    ServerAssistantMessageDelta,
    ServerAssistantMessageEnd,
    ServerAssistantMessageStart,
    ServerError,
    ServerStreamEnd,
)
from code_puppy.model_errors import normalize_model_error as _normalize_model_error

_UNKNOWN_ERROR_TYPE = "unknown_error"
_TOOL_HISTORY_ERROR_TYPE = "tool_history_error"

_CODE_TO_ERROR_TYPE: dict[str, str] = {
    "rate_limit_or_overloaded": "rate_limit",
    "backend_unavailable": "server_error",
    "auth_error": "auth_error",
    "quota_exceeded": "quota_exceeded",
    "content_blocked": "content_blocked",
    "invalid_tool_history": _TOOL_HISTORY_ERROR_TYPE,
}


def parse_api_error(exc: Exception) -> dict[str, Any]:
    """Convert an agent-run exception into a structured frontend error dict."""
    norm = _normalize_model_error(exc)
    if norm.code in _CODE_TO_ERROR_TYPE:
        error_type = _CODE_TO_ERROR_TYPE[norm.code]
        user_message = norm.user_message or str(exc)
        action_required = error_type in ("rate_limit", "quota_exceeded")
        return {
            "user_message": user_message,
            "error_type": error_type,
            "technical_details": repr(exc),
            "action_required": action_required,
        }
    return _legacy_parse_api_error(exc)


def has_streamed_content(collected_text: list[str | None]) -> bool:
    """Return True when the client has already received streaming output chunks."""
    return any((chunk or "").strip() for chunk in collected_text)


def build_error_response_frames(
    agent_error: Exception,
    collected_text: list[str | None],
    session_id: str,
) -> list[dict[str, Any]]:
    """Build ordered WebSocket frames for a failed agent run."""
    frames: list[dict[str, Any]] = []
    if has_streamed_content(collected_text):
        frames.append(
            ServerStreamEnd(
                success=False,
                session_id=session_id,
            ).model_dump(exclude_none=True)
        )
    parsed = parse_api_error(agent_error)
    frames.append(
        ServerError(
            error=parsed["user_message"],
            error_type=parsed["error_type"],
            technical_details=parsed["technical_details"],
            action_required=parsed.get("action_required"),
            session_id=session_id,
        ).model_dump(exclude_none=True)
    )
    return frames


def build_assistant_text_stream_frames(
    *,
    response_text: str,
    session_id: str,
    agent_name: str | None = None,
    model_name: str | None = None,
    tokens: dict[str, Any] | None = None,
    part_type: str = "text",
    part_index: int = 0,
    message_id: str | None = None,
    timestamp: float | None = None,
) -> list[
    ServerAssistantMessageStart
    | ServerAssistantMessageDelta
    | ServerAssistantMessageEnd
    | ServerStreamEnd
]:
    """Represent a complete assistant response using streaming-shaped frames."""
    import time as time_module

    now = timestamp if timestamp is not None else time_module.time()
    msg_id = message_id or f"msg-{session_id}-{uuid.uuid4().hex}"
    content = response_text or ""

    return [
        ServerAssistantMessageStart(
            message_id=msg_id,
            part_type=part_type,
            part_index=part_index,
            timestamp=now,
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
        ),
        ServerAssistantMessageDelta(
            message_id=msg_id,
            content=content,
            part_index=part_index,
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
        ),
        ServerAssistantMessageEnd(
            message_id=msg_id,
            part_type=part_type,
            part_index=part_index,
            full_content=content,
            timestamp=now,
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
        ),
        ServerStreamEnd(
            success=True,
            total_length=len(content),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tokens=tokens,
        ),
    ]


__all__ = [
    "build_assistant_text_stream_frames",
    "build_error_response_frames",
    "has_streamed_content",
    "parse_api_error",
]
