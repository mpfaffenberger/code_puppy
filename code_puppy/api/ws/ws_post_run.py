"""Helpers for post-run WebSocket outcome resolution.

This module extracts the response/error/cancelled/no-result decision tree from
chat_handler.py while leaving the caller in charge of exact WebSocket send
ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from code_puppy.api.ws.response_frames import (
    build_error_response_frames,
    has_streamed_content,
    parse_api_error,
)
from code_puppy.api.ws.schemas import ServerError


@dataclass(slots=True)
class PostRunResolution:
    """Resolved post-run state for one completed agent turn."""

    cancelled: bool = False
    error_frames: list[dict[str, Any]] | None = None
    no_result_error: ServerError | None = None
    response_text: str = ""
    tokens_used: dict[str, Any] | None = None
    thinking_text: str = ""


def resolve_post_run_resolution(
    *,
    result: Any,
    turn_state: Any,
    agent: Any,
    session_id: str,
    logger: Any,
) -> PostRunResolution:
    """Resolve post-turn response/error/cancelled state without sending frames."""
    if turn_state.agent_error == "cancelled":
        return PostRunResolution(cancelled=True)

    if turn_state.agent_error is not None:
        logger.debug(
            "[WS:%s] turn_state.agent_error -> sending frame(s) to client. type=%s",
            session_id,
            type(turn_state.agent_error).__name__,
        )
        return PostRunResolution(
            error_frames=build_error_response_frames(
                turn_state.agent_error,
                turn_state.collected_text,
                session_id,
            )
        )

    has_nonempty_stream = has_streamed_content(turn_state.collected_text)
    logger.debug(
        "[WS:%s] post-run: result_is_none=%s collected_chunks=%d has_nonempty_stream=%s",
        session_id,
        result is None,
        len(turn_state.collected_text),
        has_nonempty_stream,
    )

    if result is None and not has_nonempty_stream:
        logger.warning(
            "[WS:%s] Agent task completed with result=None and no streamed text; treating as error.",
            session_id,
        )
        parsed_error = parse_api_error(
            RuntimeError(
                "Agent run failed (no result returned). Check server logs for the underlying exception."
            )
        )
        return PostRunResolution(
            no_result_error=ServerError(
                error=parsed_error["user_message"],
                error_type=parsed_error["error_type"],
                technical_details=parsed_error["technical_details"],
                action_required=parsed_error.get("action_required"),
                session_id=session_id,
            )
        )

    response_text = extract_response_text(
        result=result,
        collected_text=turn_state.collected_text,
        agent=agent,
        logger=logger,
    )
    tokens_used = extract_token_usage(result=result, agent=agent)
    thinking_text = (
        ""
        if getattr(turn_state, "b1_streaming_used", False)
        else extract_thinking_text(agent=agent, logger=logger)
    )

    return PostRunResolution(
        response_text=response_text,
        tokens_used=tokens_used,
        thinking_text=thinking_text,
    )


def extract_response_text(
    *, result: Any, collected_text: list[str], agent: Any, logger: Any
) -> str:
    """Extract the final assistant response text using the existing priority order."""
    response_text = ""

    if has_streamed_content(collected_text):
        response_text = "".join(collected_text)
        logger.debug(f"Using collected streaming text ({len(response_text)} chars)")
    elif result:
        if hasattr(result, "output"):
            response_text = str(result.output) if result.output else "(Empty response)"
            logger.debug(f"Using result.output ({len(response_text)} chars)")
        elif hasattr(result, "data"):
            response_text = str(result.data) if result.data else "(Empty response)"
            logger.debug(f"Using result.data ({len(response_text)} chars)")
    elif agent:
        messages = agent.get_message_history()
        for msg in reversed(messages):
            if (
                hasattr(msg, "role")
                and msg.role == "assistant"
                and hasattr(msg, "content")
            ):
                response_text = str(msg.content)
                logger.debug(f"Using message history ({len(response_text)} chars)")
                break

    if not response_text:
        response_text = "Agent returned no response"

    return response_text


def extract_token_usage(*, result: Any, agent: Any) -> dict[str, Any] | None:
    """Extract token usage from result metadata or estimate from history."""
    tokens_used = None
    if result:
        if hasattr(result, "usage"):
            usage = result.usage
            if usage:
                tokens_used = {
                    "input_tokens": getattr(usage, "input_tokens", None)
                    or getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None)
                    or getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
        elif hasattr(result, "_usage"):
            usage = result._usage
            if usage:
                tokens_used = {
                    "input_tokens": getattr(usage, "input_tokens", None)
                    or getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None)
                    or getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }

    if not tokens_used and agent:
        try:
            history = agent.get_message_history()
            total_estimated = sum(
                agent.estimate_tokens_for_message(msg) for msg in history
            )
            tokens_used = {
                "total_tokens": total_estimated,
                "estimated": True,
            }
        except Exception:
            pass

    return tokens_used


def extract_thinking_text(*, agent: Any, logger: Any) -> str:
    """Extract thinking content from the last response-like history message."""
    thinking_text = ""
    if agent:
        try:
            history = agent.get_message_history()
            logger.debug(
                "[Thinking Debug] Checking history for thinking parts, %s messages",
                len(history) if history else 0,
            )
            if history:
                for i, msg in enumerate(reversed(history)):
                    msg_type = type(msg).__name__
                    logger.debug(
                        "[Thinking Debug] Message %s: type=%s, has_parts=%s",
                        i,
                        msg_type,
                        hasattr(msg, "parts"),
                    )
                    if "Response" in msg_type and hasattr(msg, "parts"):
                        logger.debug(
                            "[Thinking Debug] Found Response with %s parts",
                            len(msg.parts),
                        )
                        for j, part in enumerate(msg.parts):
                            part_type = type(part).__name__
                            part_content_preview = (
                                str(getattr(part, "content", ""))[:100]
                                if hasattr(part, "content")
                                else "N/A"
                            )
                            logger.debug(
                                "[Thinking Debug] Part %s: type=%s, content_preview=%s",
                                j,
                                part_type,
                                part_content_preview,
                            )
                            if "Thinking" in part_type and hasattr(part, "content"):
                                thinking_text = part.content
                                logger.debug(
                                    "[Thinking Debug] Found thinking content: %s chars",
                                    len(thinking_text),
                                )
                                break
                        if thinking_text:
                            break
        except Exception as e:
            logger.warning(f"Could not extract thinking content: {e}")
            import traceback

            logger.warning(traceback.format_exc())

    if not thinking_text:
        logger.debug("[Thinking Debug] No thinking content found in message history")

    return thinking_text


__all__ = [
    "PostRunResolution",
    "extract_response_text",
    "extract_thinking_text",
    "extract_token_usage",
    "resolve_post_run_resolution",
]
