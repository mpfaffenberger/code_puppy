"""Helpers for adapting streamed agent events into WS assistant frames.

This module intentionally handles only assistant-message framing and active-part
bookkeeping. Tool lifecycle reconciliation stays in ``chat_handler.py`` for the
next cleanup slice so we can extract the frontend streaming shape first without
changing surrounding orchestration.
"""

from __future__ import annotations

import time as time_module
from typing import Any, Awaitable, Callable

from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.schemas import (
    ServerAssistantMessageDelta,
    ServerAssistantMessageEnd,
    ServerAssistantMessageStart,
)


async def handle_assistant_part_start(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    part_type: str,
    part_obj: Any,
    session_id: str,
    agent_name: str,
    model_name: str,
    safe_send_json: Callable[[dict[str, Any]], Awaitable[None]],
    logger: Any,
    send_status_only_pending_tool_results: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """Handle text/thinking ``part_start`` events.

    Returns ``True`` when the event was fully handled and the caller should skip
    further inline processing.
    """
    if part_type not in ("TextPart", "ThinkingPart"):
        return False

    initial_content = extract_initial_content(part_obj)
    msg_type = "thinking" if part_type == "ThinkingPart" else "text"

    if turn_state.pending_tool_calls and part_type == "TextPart":
        if send_status_only_pending_tool_results is not None:
            await send_status_only_pending_tool_results()
        turn_state.current_tool_name = None

    if part_index in turn_state.active_parts:
        turn_state.active_parts[part_index]["type"] = msg_type
        message_id = turn_state.active_parts[part_index]["id"]
        if initial_content:
            turn_state.active_parts[part_index]["content"] = (
                initial_content + turn_state.active_parts[part_index]["content"]
            )
            turn_state.collected_text.insert(0, initial_content)
        logger.debug(
            "[Stream Debug] Part already exists, reusing message_id=%s",
            message_id,
        )
        return True

    message_id = f"msg-{int(time_module.time() * 1000)}-{part_index}"
    turn_state.active_parts[part_index] = {
        "id": message_id,
        "type": msg_type,
        "content": initial_content,
    }

    if initial_content:
        turn_state.collected_text.append(initial_content)

    if part_index == 0:
        turn_state.current_tool_group_id = None

    await safe_send_json(
        ServerAssistantMessageStart(
            message_id=message_id,
            part_type=msg_type,
            part_index=part_index,
            timestamp=time_module.time(),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_name=turn_state.current_tool_name,
        ).model_dump(exclude_none=True)
    )

    if initial_content:
        delta = ServerAssistantMessageDelta.model_construct(
            type="assistant_message_delta",
            message_id=message_id,
            content=initial_content,
            part_index=part_index,
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_name=turn_state.current_tool_name,
        )
        await safe_send_json(delta.model_dump(exclude_none=True))
        turn_state.b1_streaming_used = True

    return True


async def handle_assistant_part_delta(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    inner_data: dict[str, Any],
    delta_obj: Any,
    session_id: str,
    agent_name: str,
    model_name: str,
    safe_send_json: Callable[[dict[str, Any]], Awaitable[None]],
    logger: Any,
) -> bool:
    """Handle text/thinking ``part_delta`` events."""
    content_delta = extract_content_delta(inner_data, delta_obj)
    if not content_delta:
        return False

    turn_state.collected_text.append(content_delta)

    if part_index not in turn_state.active_parts:
        message_id = f"msg-{int(time_module.time() * 1000)}-{part_index}"
        turn_state.active_parts[part_index] = {
            "id": message_id,
            "type": "text",
            "content": "",
        }
        logger.debug(
            "[Stream Debug] Creating part on first delta: message_id=%s",
            message_id,
        )
        if part_index == 0:
            turn_state.current_tool_group_id = None
        await safe_send_json(
            ServerAssistantMessageStart(
                message_id=message_id,
                part_type="text",
                part_index=part_index,
                timestamp=time_module.time(),
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
                tool_name=turn_state.current_tool_name,
            ).model_dump(exclude_none=True)
        )

    part_info = turn_state.active_parts[part_index]
    message_id = part_info["id"]
    part_info["content"] += content_delta

    delta = ServerAssistantMessageDelta.model_construct(
        type="assistant_message_delta",
        message_id=message_id,
        content=content_delta,
        part_index=part_index,
        session_id=session_id,
        agent_name=agent_name,
        model_name=model_name,
        tool_name=turn_state.current_tool_name,
    )
    await safe_send_json(delta.model_dump(exclude_none=True))
    turn_state.b1_streaming_used = True
    return True


async def handle_assistant_part_end(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    session_id: str,
    agent_name: str,
    model_name: str,
    safe_send_json: Callable[[dict[str, Any]], Awaitable[None]],
) -> bool:
    """Handle non-tool ``part_end`` events and clean up active state."""
    part_info = turn_state.active_parts.get(part_index, {})
    if part_info.get("type", "text") == "tool_call":
        return False

    await safe_send_json(
        ServerAssistantMessageEnd(
            message_id=part_info.get("id", f"msg-{part_index}"),
            part_index=part_index,
            full_content=part_info.get("content", ""),
            timestamp=time_module.time(),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_name=turn_state.current_tool_name,
        ).model_dump(exclude_none=True)
    )

    turn_state.active_parts.pop(part_index, None)
    return True


def collect_final_stream_text_delta(
    *,
    turn_state: WebSocketTurnState,
    event: dict[str, Any],
) -> bool:
    """Append text delta content during the final post-stop queue drain."""
    if event.get("type", "") != "stream_event":
        return False

    event_data = event.get("data", {})
    if event_data.get("event_type", "") != "part_delta":
        return False

    content_delta = extract_content_delta(
        event_data.get("event_data", {}),
        event_data.get("event_data", {}).get("delta", {}),
    )
    if not content_delta:
        return False

    turn_state.collected_text.append(content_delta)
    return True


def extract_initial_content(part_obj: Any) -> str:
    """Return initial content attached to a part object, if any."""
    if hasattr(part_obj, "content") and part_obj.content:
        return part_obj.content
    if isinstance(part_obj, dict) and part_obj.get("content"):
        return part_obj.get("content", "")
    return ""


def extract_content_delta(inner_data: dict[str, Any], delta_obj: Any) -> str:
    """Return assistant text delta from direct or nested event payloads."""
    content_delta = inner_data.get("content_delta", "")
    if content_delta:
        return content_delta
    if isinstance(delta_obj, dict):
        return delta_obj.get("content_delta", "") or ""
    return ""
