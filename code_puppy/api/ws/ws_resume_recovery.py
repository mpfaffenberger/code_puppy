"""Safe one-shot recovery helpers for resumed WebSocket sessions.

When a resumed turn returns ``result=None`` with no streamed text, we can
attempt a bounded recovery by reloading canonical history from SQLite and
trimming obviously incomplete trailing tool-only responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ResumeRecoveryResult:
    """Outcome of a resume recovery attempt."""

    success: bool
    ctx: Any | None = None
    removed_messages: int = 0
    reason: str = ""


def _is_incomplete_tool_only_response(message: Any) -> bool:
    """Return True when a trailing response appears to be tool-incomplete.

    Conservative heuristic:
    - message has ``parts``
    - contains at least one ToolCallPart
    - contains no ToolReturnPart
    - contains no TextPart
    """
    parts = getattr(message, "parts", None)
    if not parts:
        return False

    part_types = {type(part).__name__ for part in parts}
    has_tool_call = "ToolCallPart" in part_types
    has_tool_return = "ToolReturnPart" in part_types
    has_text = "TextPart" in part_types
    return has_tool_call and not has_tool_return and not has_text


def sanitize_trailing_incomplete_tool_history(
    history: list[Any],
) -> tuple[list[Any], int]:
    """Trim incomplete trailing tool-only assistant responses from history."""
    if not history:
        return history, 0

    trimmed = list(history)
    removed = 0
    while trimmed and _is_incomplete_tool_only_response(trimmed[-1]):
        trimmed.pop()
        removed += 1

    return trimmed, removed


async def reload_session_from_sqlite_with_sanitization(
    *,
    session_id: str,
    logger: Any,
) -> ResumeRecoveryResult:
    """Force a fresh SQLite reload for this session and sanitize trailing history."""
    try:
        # Ensure next load is truly from SQLite canonical state.
        from code_puppy.api.session_context import session_manager

        await session_manager.destroy_session(session_id)
        ctx = await session_manager.load_session(session_id)
        if ctx is None:
            return ResumeRecoveryResult(
                success=False,
                reason="Session not found in SQLite during recovery reload",
            )

        history = ctx.agent.get_message_history() or []
        sanitized, removed = sanitize_trailing_incomplete_tool_history(history)
        if removed > 0:
            try:
                ctx.agent.set_message_history(sanitized)
                logger.warning(
                    "[WS:%s] Resume recovery trimmed %d trailing incomplete tool message(s)",
                    session_id,
                    removed,
                )
            except Exception as exc:
                return ResumeRecoveryResult(
                    success=False,
                    reason=f"Failed to apply sanitized history: {exc}",
                )

        return ResumeRecoveryResult(success=True, ctx=ctx, removed_messages=removed)
    except Exception as exc:
        return ResumeRecoveryResult(success=False, reason=str(exc))


__all__ = [
    "ResumeRecoveryResult",
    "reload_session_from_sqlite_with_sanitization",
    "sanitize_trailing_incomplete_tool_history",
]
