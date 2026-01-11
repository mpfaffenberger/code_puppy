"""Callback registration for frontend event emission.

This module registers callbacks for various agent events and emits them
to subscribed WebSocket handlers via the emitter module.
"""

import logging
import time
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.plugins.frontend_emitter.emitter import emit_event

logger = logging.getLogger(__name__)


async def on_pre_tool_call(
    tool_name: str, tool_args: Dict[str, Any], context: Any = None
) -> None:
    """Emit an event when a tool call starts.

    Args:
        tool_name: Name of the tool being called
        tool_args: Arguments being passed to the tool
        context: Optional context data for the tool call
    """
    try:
        emit_event(
            "tool_call_start",
            {
                "tool_name": tool_name,
                "tool_args": _sanitize_args(tool_args),
                "start_time": time.time(),
            },
        )
        logger.debug(f"Emitted tool_call_start for {tool_name}")
    except Exception as e:
        logger.error(f"Failed to emit pre_tool_call event: {e}")


async def on_post_tool_call(
    tool_name: str,
    tool_args: Dict[str, Any],
    result: Any,
    duration_ms: float,
    context: Any = None,
) -> None:
    """Emit an event when a tool call completes.

    Args:
        tool_name: Name of the tool that was called
        tool_args: Arguments that were passed to the tool
        result: The result returned by the tool
        duration_ms: Execution time in milliseconds
        context: Optional context data for the tool call
    """
    try:
        emit_event(
            "tool_call_complete",
            {
                "tool_name": tool_name,
                "tool_args": _sanitize_args(tool_args),
                "duration_ms": duration_ms,
                "success": _is_successful_result(result),
                "result_summary": _summarize_result(result),
            },
        )
        logger.debug(
            f"Emitted tool_call_complete for {tool_name} ({duration_ms:.2f}ms)"
        )
    except Exception as e:
        logger.error(f"Failed to emit post_tool_call event: {e}")


async def on_stream_event(
    event_type: str, event_data: Any, agent_session_id: Optional[str] = None
) -> None:
    """Emit streaming events from the agent.

    Args:
        event_type: Type of the streaming event
        event_data: Data associated with the event
        agent_session_id: Optional session ID of the agent emitting the event
    """
    try:
        emit_event(
            "stream_event",
            {
                "event_type": event_type,
                "event_data": _sanitize_event_data(event_data),
                "agent_session_id": agent_session_id,
            },
        )
        logger.debug(f"Emitted stream_event: {event_type}")
    except Exception as e:
        logger.error(f"Failed to emit stream_event: {e}")


async def on_invoke_agent(*args: Any, **kwargs: Any) -> None:
    """Emit an event when an agent is invoked.

    Args:
        *args: Positional arguments from the invoke_agent callback
        **kwargs: Keyword arguments from the invoke_agent callback
    """
    try:
        # Extract relevant info from args/kwargs
        agent_info = {
            "agent_name": kwargs.get("agent_name") or (args[0] if args else None),
            "session_id": kwargs.get("session_id"),
            "prompt_preview": _truncate_string(
                kwargs.get("prompt") or (args[1] if len(args) > 1 else None),
                max_length=200,
            ),
        }
        emit_event("agent_invoked", agent_info)
        logger.debug(f"Emitted agent_invoked: {agent_info.get('agent_name')}")
    except Exception as e:
        logger.error(f"Failed to emit invoke_agent event: {e}")


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize tool arguments for safe emission.

    Truncates large values and removes potentially sensitive data.

    Args:
        args: The raw tool arguments

    Returns:
        Sanitized arguments safe for emission
    """
    if not isinstance(args, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            sanitized[key] = _truncate_string(value, max_length=500)
        elif isinstance(value, (int, float, bool, type(None))):
            sanitized[key] = value
        elif isinstance(value, (list, dict)):
            # Just indicate the type and length for complex types
            sanitized[key] = f"<{type(value).__name__}[{len(value)}]>"
        else:
            sanitized[key] = f"<{type(value).__name__}>"

    return sanitized


def _sanitize_event_data(data: Any) -> Any:
    """Sanitize event data for safe emission.

    Args:
        data: The raw event data

    Returns:
        Sanitized data safe for emission
    """
    if data is None:
        return None

    if isinstance(data, str):
        return _truncate_string(data, max_length=1000)

    if isinstance(data, (int, float, bool)):
        return data

    if isinstance(data, dict):
        return {k: _sanitize_event_data(v) for k, v in list(data.items())[:20]}

    if isinstance(data, (list, tuple)):
        return [_sanitize_event_data(item) for item in data[:20]]

    return f"<{type(data).__name__}>"


def _is_successful_result(result: Any) -> bool:
    """Determine if a tool result indicates success.

    Args:
        result: The tool result

    Returns:
        True if the result appears successful
    """
    if result is None:
        return True  # No result often means success

    if isinstance(result, dict):
        # Check for error indicators
        if result.get("error"):
            return False
        if result.get("success") is False:
            return False
        return True

    if isinstance(result, bool):
        return result

    return True  # Default to success


def _summarize_result(result: Any) -> str:
    """Create a brief summary of a tool result.

    Args:
        result: The tool result

    Returns:
        A string summary of the result
    """
    if result is None:
        return "<no result>"

    if isinstance(result, str):
        return _truncate_string(result, max_length=200)

    if isinstance(result, dict):
        if "error" in result:
            return f"Error: {_truncate_string(str(result['error']), max_length=100)}"
        if "message" in result:
            return _truncate_string(str(result["message"]), max_length=100)
        return f"<dict with {len(result)} keys>"

    if isinstance(result, (list, tuple)):
        return f"<{type(result).__name__}[{len(result)}]>"

    return _truncate_string(str(result), max_length=200)


def _truncate_string(value: Any, max_length: int = 100) -> Optional[str]:
    """Truncate a string value if it exceeds max_length.

    Args:
        value: The value to truncate (will be converted to str)
        max_length: Maximum length before truncation

    Returns:
        Truncated string or None if value is None
    """
    if value is None:
        return None

    s = str(value)
    if len(s) > max_length:
        return s[: max_length - 3] + "..."
    return s


def register() -> None:
    """Register all frontend emitter callbacks."""
    register_callback("pre_tool_call", on_pre_tool_call)
    register_callback("post_tool_call", on_post_tool_call)
    register_callback("stream_event", on_stream_event)
    register_callback("invoke_agent", on_invoke_agent)
    logger.debug("Frontend emitter callbacks registered")


# Auto-register callbacks when this module is imported
register()
