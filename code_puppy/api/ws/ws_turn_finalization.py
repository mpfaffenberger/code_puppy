"""Post-turn WebSocket finalization helpers.

This module owns the stateful orchestration that happens *after* the agent run
completes but *before* persistence/broadcast work begins:

1. Emit B1 tool results before ``stream_end`` when possible.
2. Sync ``result.all_messages()`` onto the agent.
3. Snapshot message history before await points.
4. Emit any remaining tool results from finalized history while suppressing
   duplicates already delivered before ``stream_end``.

The caller remains responsible for the surrounding frame ordering, persistence,
and client/broadcast sends.
"""

from __future__ import annotations

import time as time_module
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from code_puppy.api.ws.schemas import ServerToolResult


@dataclass(slots=True)
class TurnFinalizationResult:
    """Result of post-run history/tool finalization."""

    pre_sent_tool_ids: set[str] = field(default_factory=set)
    history_snapshot: list[Any] = field(default_factory=list)


_SIMPLE_TYPES = (str, dict, list, int, float, bool, type(None))


def _serialize_tool_result(value: Any) -> Any:
    """Coerce tool result content into JSON-ish payloads safely."""
    if isinstance(value, _SIMPLE_TYPES):
        return value
    try:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        if hasattr(value, "__dict__"):
            return value.__dict__
    except Exception:
        pass
    return str(value)


def _iter_tool_returns(messages: Iterable[Any]) -> Iterable[Any]:
    """Yield ToolReturn-like parts from model messages when available."""
    try:
        from pydantic_ai.messages import ToolReturn, ToolReturnPart
    except Exception:
        return []

    parts_found: list[Any] = []
    for msg in messages:
        if not hasattr(msg, "parts"):
            continue
        for part in msg.parts:
            if isinstance(part, (ToolReturnPart, ToolReturn)):
                parts_found.append(part)
    return parts_found


async def emit_pre_stream_end_tool_results(
    *,
    result: Any,
    turn_state: Any,
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed_tool_lifecycle: Callable[[Any], Awaitable[None]],
    logger: Any,
) -> set[str]:
    """Emit B1 tool results before ``stream_end`` and return sent tool IDs."""
    sent_tool_ids: set[str] = set()
    if not result or not hasattr(result, "all_messages"):
        return sent_tool_ids

    try:
        messages = list(result.all_messages())
        for part in _iter_tool_returns(messages):
            tool_name = getattr(part, "tool_name", "unknown")
            raw_tool_id = getattr(part, "tool_call_id", None)
            tool_id = (
                turn_state.tool_id_aliases.get(raw_tool_id, raw_tool_id)
                if raw_tool_id
                else "unknown"
            )
            result_payload = _serialize_tool_result(getattr(part, "content", None))
            logger.warning(
                "[WebSocket] Pre-stream_end tool result: %s (id: %s), content_preview=%s",
                tool_name,
                tool_id,
                str(result_payload)[:100] if result_payload else None,
            )
            await send_typed_tool_lifecycle(
                ServerToolResult(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    result=result_payload,
                    success=True,
                    duration_ms=0,
                    timestamp=time_module.time(),
                    session_id=session_id,
                    agent_name=agent_name,
                    model_name=model_name,
                    tool_group_id=turn_state.tool_group_ids.get(tool_id),
                )
            )
            sent_tool_ids.add(tool_id)
    except Exception as exc:
        logger.warning(
            "Pre-stream_end tool result extraction failed: %s",
            exc,
        )

    return sent_tool_ids


async def finalize_turn_history(
    *,
    result: Any,
    agent: Any,
    turn_state: Any,
    session_id: str,
    agent_name: str,
    model_name: str,
    send_typed: Callable[[Any], Awaitable[None]],
    pre_sent_tool_ids: set[str] | None,
    logger: Any,
) -> TurnFinalizationResult:
    """Sync history from ``result.all_messages()`` and emit remaining tool results."""
    finalized = TurnFinalizationResult(
        pre_sent_tool_ids=set(pre_sent_tool_ids or set()),
        history_snapshot=[],
    )

    if not result or not hasattr(result, "all_messages"):
        return finalized

    try:
        all_msgs = list(result.all_messages())
        if all_msgs:
            agent.set_message_history(all_msgs)
            finalized.history_snapshot = list(agent.get_message_history())
            logger.debug(
                "Updated message history from result.all_messages(): %s messages",
                len(all_msgs),
            )

        try:
            for part in _iter_tool_returns(all_msgs):
                tool_name = getattr(part, "tool_name", "unknown")
                tool_call_id = getattr(part, "tool_call_id", "unknown")
                result_payload = _serialize_tool_result(getattr(part, "content", None))

                if tool_name == "agent_run_shell_command":
                    stdout_val = (
                        result_payload.get("stdout", "N/A")
                        if isinstance(result_payload, dict)
                        else "not dict"
                    )
                    logger.debug(
                        "Extracted shell result: id=%s, stdout=%s",
                        tool_call_id,
                        stdout_val,
                    )

                if tool_call_id in finalized.pre_sent_tool_ids:
                    logger.debug(
                        "[WebSocket] Skipping duplicate tool result (pre-sent): %s",
                        tool_call_id,
                    )
                    continue

                logger.info(
                    "[WebSocket] Sending extracted tool result for %s (id: %s)",
                    tool_name,
                    tool_call_id,
                )
                await send_typed(
                    ServerToolResult(
                        tool_id=tool_call_id,
                        tool_name=tool_name,
                        result=result_payload,
                        success=True,
                        duration_ms=0,
                        timestamp=time_module.time(),
                        session_id=session_id,
                        agent_name=agent_name,
                        model_name=model_name,
                        tool_group_id=turn_state.tool_group_ids.get(tool_call_id),
                    )
                )
        except Exception as exc:
            logger.warning(
                "Could not extract tool results from messages: %s",
                exc,
            )
    except Exception as exc:
        logger.warning(
            "Could not update history from result.all_messages(): %s",
            exc,
        )

    return finalized


__all__ = [
    "TurnFinalizationResult",
    "emit_pre_stream_end_tool_results",
    "finalize_turn_history",
]
