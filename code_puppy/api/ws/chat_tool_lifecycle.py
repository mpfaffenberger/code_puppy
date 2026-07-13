"""Helpers for websocket tool lifecycle reconciliation.

This module owns the tool-call/result bookkeeping that previously lived inside
``chat_handler.py``'s streaming drain loop. The goal is to preserve exact
frontend-visible behavior while isolating the most stateful tool lifecycle
logic from the endpoint handler.
"""

from __future__ import annotations

import json
import re
import time as time_module
import uuid
from typing import Any, Awaitable, Callable

from code_puppy.api.ws.chat_turn_state import WebSocketTurnState
from code_puppy.api.ws.schemas import ServerToolCall, ServerToolResult


async def handle_tool_call_start_event(
    *,
    turn_state: WebSocketTurnState,
    event_data: dict[str, Any],
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed_tool_lifecycle: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> bool:
    """Handle direct ``tool_call_start`` events from the stream queue."""
    tool_name = event_data.get("tool_name", "unknown")
    tool_args = event_data.get("tool_args", {})
    tool_id = str(uuid.uuid4())[:8]

    if turn_state.current_tool_group_id is None:
        turn_state.current_tool_group_id = f"tg-{str(uuid.uuid4())[:8]}"

    logger.debug("[ws] tool_call: %s", tool_name)
    turn_state.current_tool_name = tool_name
    turn_state.pending_tool_calls[tool_id] = {
        "tool_name": tool_name,
        "start_time": time_module.time(),
        "tool_group_id": turn_state.current_tool_group_id,
    }

    await send_typed_tool_lifecycle(
        ServerToolCall(
            tool_id=tool_id,
            tool_name=tool_name,
            args=tool_args,
            timestamp=time_module.time(),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_group_id=turn_state.current_tool_group_id,
        )
    )
    return True


async def handle_tool_call_complete_event(
    *,
    turn_state: WebSocketTurnState,
    event_data: dict[str, Any],
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed_tool_lifecycle: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> bool:
    """Handle direct ``tool_call_complete`` events from the stream queue."""
    tool_name = event_data.get("tool_name", "unknown")
    result = event_data.get("result", event_data.get("result_summary", ""))
    success = event_data.get("success", True)
    duration = event_data.get("duration_ms", 0)

    logger.debug("[ws] tool_result: %s", tool_name)
    turn_state.current_tool_name = None

    matching_tool_id = next(
        (
            tid
            for tid, info in turn_state.pending_tool_calls.items()
            if info["tool_name"] == tool_name
        ),
        None,
    )
    matching_pending_info = (
        turn_state.pending_tool_calls.get(matching_tool_id)
        if matching_tool_id
        else None
    )
    tool_group_id_for_result = resolve_tool_group_id(
        turn_state=turn_state,
        logger=logger,
        tool_id=matching_tool_id,
        pending_info=matching_pending_info,
        fallback_group_id=turn_state.current_tool_group_id,
        tool_name=tool_name,
        source="tool_call_complete",
    )

    if matching_tool_id:
        turn_state.pending_tool_calls.pop(matching_tool_id, None)

    await send_typed_tool_lifecycle(
        ServerToolResult(
            tool_id=matching_tool_id,
            tool_name=tool_name,
            result=result,
            success=success,
            duration_ms=duration,
            timestamp=time_module.time(),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_group_id=tool_group_id_for_result,
        )
    )
    return True


def handle_tool_part_start(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    part_obj: Any,
    logger: Any,
) -> bool:
    """Track ``ToolCallPart``/``ToolReturnPart`` state at ``part_start``."""
    part_type = _extract_attr_or_key(part_obj, "part_type")
    # ``part_type`` is often passed separately by the caller; this helper relies
    # on the explicit caller branch instead of introspecting it.
    del part_type
    logger.debug("[ws-tool] handle_tool_part_start called")
    return True


def start_tool_call_part(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    part_obj: Any,
    logger: Any,
) -> bool:
    """Record an in-flight tool call part until args are complete."""
    tool_name = _extract_attr_or_key(part_obj, "tool_name") or "unknown"
    tool_call_id = _extract_attr_or_key(part_obj, "tool_call_id")
    tool_args_str = _extract_attr_or_key(part_obj, "args") or ""
    tool_id = tool_call_id or str(uuid.uuid4())[:8]

    turn_state.active_parts[part_index] = {
        "id": tool_id,
        "raw_tool_call_id": tool_call_id,
        "type": "tool_call",
        "tool_name": tool_name,
        "args": tool_args_str,
        "args_buffer": tool_args_str,
        "start_time": time_module.time(),
    }
    turn_state.current_tool_name = tool_name

    logger.debug(
        "[WebSocket] ToolCallPart started: %s (id: %s)",
        tool_name,
        tool_id,
    )
    return True


async def start_tool_return_part(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    part_obj: Any,
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed_tool_lifecycle: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> bool:
    """Handle ``ToolReturnPart`` result emission on ``part_start``."""
    logger.info("[WebSocket] ToolReturnPart detected! part_index=%s", part_index)

    tool_call_id = _extract_attr_or_key(part_obj, "tool_call_id")
    tool_content = _coerce_tool_content(
        _extract_attr_or_key(part_obj, "content"), logger
    )

    result_sent = False
    if tool_call_id:
        resolved_pending_id = resolve_pending_tool_id(
            turn_state=turn_state,
            tool_call_id=tool_call_id,
        )
        if resolved_pending_id:
            result_sent = True
            pending_info = turn_state.pending_tool_calls[resolved_pending_id]
            pending_info["result"] = tool_content
            tool_name = pending_info.get("tool_name", "unknown")
            start_time = pending_info.get("start_time", time_module.time())
            duration_ms = (time_module.time() - start_time) * 1000
            group_id = resolve_tool_group_id(
                turn_state=turn_state,
                logger=logger,
                tool_id=resolved_pending_id,
                pending_info=pending_info,
                fallback_group_id=turn_state.current_tool_group_id,
                tool_name=tool_name,
                source="tool_return_resolved",
            )
            logger.info(
                "[WebSocket] ToolReturnPart: Sending result for %s (id: %s, raw: %s)",
                tool_name,
                resolved_pending_id,
                tool_call_id,
            )
            await send_typed_tool_lifecycle(
                ServerToolResult(
                    tool_id=resolved_pending_id,
                    tool_name=tool_name,
                    result=tool_content,
                    success=True,
                    duration_ms=duration_ms,
                    timestamp=time_module.time(),
                    session_id=session_id,
                    agent_name=agent_name or "code-puppy",
                    model_name=model_name or "unknown",
                    tool_group_id=group_id,
                )
            )
        else:
            logger.warning(
                "[WebSocket] ToolReturnPart: Could not resolve tool_call_id %s, pending keys: %s",
                tool_call_id,
                list(turn_state.pending_tool_calls.keys()),
            )

    if not result_sent:
        for pending_id, pending_info in sorted(
            turn_state.pending_tool_calls.items(),
            key=lambda item: abs(item[1].get("part_index", 9999) - part_index),
        ):
            if abs(pending_info.get("part_index", 9999) - part_index) <= 3:
                pending_info["result"] = tool_content
                tool_name = pending_info.get("tool_name", "unknown")
                start_time = pending_info.get("start_time", time_module.time())
                duration_ms = (time_module.time() - start_time) * 1000
                group_id = resolve_tool_group_id(
                    turn_state=turn_state,
                    logger=logger,
                    tool_id=pending_id,
                    pending_info=pending_info,
                    fallback_group_id=turn_state.current_tool_group_id,
                    tool_name=tool_name,
                    source="tool_return_proximity",
                )
                logger.info(
                    "[WebSocket] ToolReturnPart: Sending result (by proximity) for %s (id: %s)",
                    tool_name,
                    pending_id,
                )
                await send_typed_tool_lifecycle(
                    ServerToolResult(
                        tool_id=pending_id,
                        tool_name=tool_name,
                        result=tool_content,
                        success=True,
                        duration_ms=duration_ms,
                        timestamp=time_module.time(),
                        session_id=session_id,
                        agent_name=agent_name or "code-puppy",
                        model_name=model_name or "unknown",
                        tool_group_id=group_id,
                    )
                )
                result_sent = True
                break

    if not result_sent:
        logger.warning(
            "[WebSocket] ToolReturnPart: Could NOT send result! tool_call_id=%s, "
            "turn_state.pending_tool_calls=%s, part_index=%s",
            tool_call_id,
            list(turn_state.pending_tool_calls.keys()),
            part_index,
        )

    turn_state.active_parts[part_index] = {
        "id": f"tool-return-{part_index}",
        "type": "tool_return",
        "tool_call_id": tool_call_id,
        "content": tool_content,
    }
    return True


def accumulate_tool_call_part_delta(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    delta_obj: Any,
) -> bool:
    """Append ``ToolCallPartDelta.args_delta`` to the matching active part."""
    args_delta = _extract_attr_or_key(delta_obj, "args_delta") or ""
    if not args_delta or part_index not in turn_state.active_parts:
        return False

    part_info = turn_state.active_parts[part_index]
    if part_info.get("type") != "tool_call":
        return False

    part_info["args_buffer"] = part_info.get("args_buffer", "") + args_delta
    return True


async def finish_tool_call_part(
    *,
    turn_state: WebSocketTurnState,
    part_index: int,
    part_info: dict[str, Any],
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed_tool_lifecycle: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> bool:
    """Emit the deferred ``tool_call`` once streamed args are complete."""
    tool_name = part_info.get("tool_name", "unknown")
    tool_id = part_info.get("id", str(uuid.uuid4())[:8])
    tool_args_str = part_info.get("args_buffer", "") or part_info.get("args", "")
    start_time = part_info.get("start_time", time_module.time())
    raw_tool_call_id = part_info.get("raw_tool_call_id")

    try:
        args_dict = json.loads(tool_args_str) if tool_args_str else {}
    except (json.JSONDecodeError, TypeError):
        args_dict = {}

    logger.debug("[WebSocket] Sending tool_call (args complete): %s", tool_name)

    if turn_state.current_tool_group_id is None:
        turn_state.current_tool_group_id = f"tg-{str(uuid.uuid4())[:8]}"

    await send_typed_tool_lifecycle(
        ServerToolCall(
            tool_id=tool_id,
            tool_name=tool_name,
            args=args_dict,
            timestamp=time_module.time(),
            session_id=session_id,
            agent_name=agent_name,
            model_name=model_name,
            tool_group_id=turn_state.current_tool_group_id,
        )
    )

    turn_state.pending_tool_calls[tool_id] = {
        "tool_name": tool_name,
        "start_time": start_time,
        "part_index": part_index,
        "raw_tool_call_id": raw_tool_call_id,
        "status_only_sent": False,
        "result": None,
        "tool_group_id": turn_state.current_tool_group_id,
    }
    if raw_tool_call_id:
        turn_state.tool_id_aliases[raw_tool_call_id] = tool_id
    if turn_state.current_tool_group_id:
        turn_state.tool_group_ids[tool_id] = turn_state.current_tool_group_id

    turn_state.current_tool_name = None
    turn_state.active_parts.pop(part_index, None)
    return True


async def send_status_only_pending_tool_results(
    *,
    turn_state: WebSocketTurnState,
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> None:
    """Emit status-only placeholder results before assistant text resumes."""
    for tool_id, tool_info in list(turn_state.pending_tool_calls.items()):
        if tool_info.get("status_only_sent"):
            continue
        duration_ms = (time_module.time() - tool_info["start_time"]) * 1000
        logger.debug(
            "[WebSocket] Sending status-only tool_result for: %s (duration: %.1fms)",
            tool_info["tool_name"],
            duration_ms,
        )
        await send_typed(
            ServerToolResult(
                tool_id=tool_id,
                result={"_status": "completed", "_pending_full_result": True},
                tool_name=tool_info["tool_name"],
                success=True,
                duration_ms=duration_ms,
                timestamp=time_module.time(),
                session_id=session_id,
                agent_name=agent_name,
                model_name=model_name,
                tool_group_id=resolve_tool_group_id(
                    turn_state=turn_state,
                    logger=logger,
                    tool_id=tool_id,
                    pending_info=tool_info,
                    fallback_group_id=turn_state.current_tool_group_id,
                    tool_name=tool_info.get("tool_name"),
                    source="status_only_result",
                ),
            )
        )
        tool_info["status_only_sent"] = True


def resolve_pending_tool_id(
    *,
    turn_state: WebSocketTurnState,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
) -> str | None:
    """Resolve canonical frontend tool_id for a backend tool call reference."""
    if tool_call_id and tool_call_id in turn_state.pending_tool_calls:
        return tool_call_id

    if tool_call_id:
        for pending_id, pending_info in turn_state.pending_tool_calls.items():
            if pending_info.get("raw_tool_call_id") == tool_call_id:
                return pending_id

    if tool_name:
        for pending_id, pending_info in turn_state.pending_tool_calls.items():
            if pending_info.get("tool_name") == tool_name:
                return pending_id

    return None


def resolve_tool_group_id(
    *,
    turn_state: WebSocketTurnState,
    logger: Any,
    tool_id: str | None = None,
    pending_info: dict[str, Any] | None = None,
    fallback_group_id: str | None = None,
    tool_name: str | None = None,
    source: str = "unknown",
) -> str:
    """Return a non-empty ``tool_group_id`` for tool lifecycle frames."""
    group_id = None
    if pending_info is not None:
        group_id = pending_info.get("tool_group_id")

    if not group_id and tool_id:
        group_id = turn_state.tool_group_ids.get(tool_id)

    if not group_id and fallback_group_id:
        group_id = fallback_group_id

    if not group_id:
        group_id = turn_state.current_tool_group_id

    if not group_id:
        raw_hint = tool_id or tool_name or "unknown"
        stable_hint = (
            re.sub(r"[^a-z0-9_-]", "-", raw_hint.lower())[:24].strip("-") or "unknown"
        )
        group_id = f"tg-fallback-{stable_hint}-{str(uuid.uuid4())[:6]}"
        logger.warning(
            "[ws] Synthesized missing tool_group_id for source=%s tool_id=%s tool_name=%s",
            source,
            tool_id,
            tool_name,
        )

    if tool_id:
        turn_state.tool_group_ids[tool_id] = group_id
        if pending_info is not None:
            pending_info["tool_group_id"] = group_id
        elif tool_id in turn_state.pending_tool_calls:
            turn_state.pending_tool_calls[tool_id]["tool_group_id"] = group_id

    if turn_state.current_tool_group_id is None:
        turn_state.current_tool_group_id = group_id

    return group_id


def _extract_attr_or_key(obj: Any, name: str) -> Any:
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def _coerce_tool_content(tool_content: Any, logger: Any) -> Any:
    if not tool_content or isinstance(
        tool_content,
        (str, dict, list, int, float, bool, type(None)),
    ):
        return tool_content

    try:
        if hasattr(tool_content, "model_dump"):
            return tool_content.model_dump()
        if hasattr(tool_content, "dict"):
            return tool_content.dict()
        if hasattr(tool_content, "__dict__"):
            return tool_content.__dict__
        return str(tool_content)
    except Exception as exc:  # pragma: no cover - defensive parity branch
        logger.debug("[WebSocket] Could not serialize tool result: %s", exc)
        return str(tool_content)
