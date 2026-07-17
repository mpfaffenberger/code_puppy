"""Callback registration for frontend event emission.

This module registers callbacks for various agent events and emits them
to subscribed WebSocket handlers via the emitter module.

Session channel
---------------
None of the emit-sites below pass an explicit ``session_id`` to
``emit_event``.  Instead they rely on the implicit fallback to
``code_puppy.plugins.frontend_emitter.session_context.current_emitter_session_id`` -- so any embedder (e.g. a
WebSocket backend handling multiple sessions concurrently) just needs
to set the ContextVar at the start of an agent run and every event
emitted by mist during that run will be tagged with the
correct session_id automatically.  No imports from
``code_puppy.api.*`` are added here; the contract is purely through
the ContextVar primitive in ``code_puppy.plugins.frontend_emitter.session_context``.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from code_puppy.callbacks import register_callback
from code_puppy.plugins.frontend_emitter.emitter import emit_event

logger = logging.getLogger(__name__)


# Maximum serialized size we allow for a structured tool-args payload
# before we fall back to a truncated string representation.  Chosen to
# fit comfortably in a typical 16-64 KB WebSocket frame after JSON
# wrapping while still being large enough to carry real file paths,
# small code snippets, and config blobs verbatim.
_MAX_ARGS_SERIALIZED_BYTES = 4096

# Maximum length for the textual representation we attach when a value
# can't be JSON-serialised or exceeds the size cap above.
_MAX_ARGS_TRUNCATED_STR = 4000


async def on_pre_tool_call(
    tool_name: str, tool_args: Dict[str, Any], context: Any = None
) -> None:
    """Emit an event when a tool call starts.

    Args:
        tool_name: Name of the tool being called.
        tool_args: Arguments being passed to the tool.
        context: Optional context data for the tool call.
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
        tool_name: Name of the tool that was called.
        tool_args: Arguments that were passed to the tool.
        result: The result returned by the tool.
        duration_ms: Execution time in milliseconds.
        context: Optional context data for the tool call.
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
        event_type: Type of the streaming event.
        event_data: Data associated with the event.
        agent_session_id: Optional session ID of the agent emitting the
            event.  This is a *callback-supplied* identifier from the
            agent layer; it is independent of the WebSocket-session
            ContextVar used by the emitter and is preserved verbatim
            inside the event payload.
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
        *args: Positional arguments from the invoke_agent callback.
        **kwargs: Keyword arguments from the invoke_agent callback.
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


# ─── sanitizers ─────────────────────────────────────────────────────────


def _sanitize_args(args: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize tool arguments for safe emission.

    Strategy:
      * Primitives (str / int / float / bool / None) round-trip directly,
        with strings capped at 500 chars.
      * Structured values (list / dict) are JSON-serialised and kept
        verbatim if the serialised form fits within ``_MAX_ARGS_SERIALIZED_BYTES``;
        otherwise replaced by a truncated string representation (NOT the
        opaque ``<list[N]>`` stub the previous implementation produced).
      * Anything that can't be JSON-serialised falls back to ``repr()``,
        capped at ``_MAX_ARGS_TRUNCATED_STR`` chars.

    Args:
        args: The raw tool arguments dict (or any value -- non-dicts are
            normalised to an empty dict for back-compat).

    Returns:
        Sanitized arguments safe for emission over a WebSocket.
    """
    if not isinstance(args, dict):
        return {}

    sanitized: Dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str):
            sanitized[key] = _truncate_string(value, max_length=500)
        elif isinstance(value, bool) or value is None:
            # Note: must check ``bool`` before ``int`` because bool is a subclass of int.
            sanitized[key] = value
        elif isinstance(value, (int, float)):
            sanitized[key] = value
        elif isinstance(value, (list, dict, tuple)):
            sanitized[key] = _preserve_structured(value)
        else:
            # Unknown type: best-effort textual representation.
            try:
                sanitized[key] = _truncate_string(
                    repr(value), max_length=_MAX_ARGS_TRUNCATED_STR
                )
            except Exception:
                sanitized[key] = f"<{type(value).__name__}>"

    return sanitized


def _preserve_structured(value: Any) -> Any:
    """Round-trip a structured value through JSON if it fits within budget.

    Returns the original value (so it serialises naturally downstream)
    when the serialised form is <= ``_MAX_ARGS_SERIALIZED_BYTES`` bytes,
    otherwise a truncated string preview.  This replaces the previous
    behaviour of emitting an opaque ``<list[N]>`` stub.
    """
    try:
        serialised = json.dumps(value, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        # Not JSON-serialisable at all -- fall back to a short repr.
        try:
            return _truncate_string(repr(value), max_length=_MAX_ARGS_TRUNCATED_STR)
        except Exception:
            return f"<{type(value).__name__}>"

    if len(serialised.encode("utf-8")) <= _MAX_ARGS_SERIALIZED_BYTES:
        # Small enough -- return the original Python value so it
        # round-trips cleanly through whatever JSON encoder runs later.
        return value

    # Too big: return a truncated preview string so the consumer at
    # least sees the shape and the first portion of the content.
    return _truncate_string(serialised, max_length=_MAX_ARGS_TRUNCATED_STR)


def _sanitize_event_data(data: Any) -> Any:
    """Sanitize event data for safe emission.

    Special-cased for pydantic-ai delta-style objects:
      * Anything carrying a ``content_delta`` attribute (text streaming)
        is normalised to ``{"type": <class_name>, "content_delta": <str>}``.
      * Anything carrying an ``args_delta`` attribute (tool-call streaming)
        is normalised to ``{"type": <class_name>, "args_delta": <str>,
        "tool_call_id": <id|None>, "tool_name": <name|None>}``.
      * Anything carrying a ``part`` attribute (part_start / part_end
        wrappers) is unwrapped recursively into its part.
      * Plain dicts / lists / scalars retain the previous behaviour
        (capped recursion, capped length).

    Without this normalisation, ``repr()`` of a pydantic-ai delta produces
    something like ``<TextPartDelta>`` and downstream consumers (browsers,
    GUI clients) lose the actual streamed content.

    Args:
        data: The raw event data.

    Returns:
        Sanitized data safe for emission.
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

    # ── pydantic-ai delta extraction ────────────────────────────────
    #
    # We use duck-typing (hasattr) rather than isinstance() so we don't
    # have to import pydantic-ai here and we stay compatible with any
    # future delta subclass that adheres to the same attribute names.

    type_name = type(data).__name__

    # 1. content_delta (TextPartDelta)
    if hasattr(data, "content_delta"):
        content = getattr(data, "content_delta", "")
        return {
            "type": type_name,
            "content_delta": _truncate_string(content, max_length=1000),
        }

    # 2. args_delta (ToolCallPartDelta)
    if hasattr(data, "args_delta"):
        args_delta = getattr(data, "args_delta", "")
        return {
            "type": type_name,
            "args_delta": _truncate_string(args_delta, max_length=1000),
            "tool_call_id": _safe_getattr_str(data, "tool_call_id"),
            "tool_name": _safe_getattr_str(data, "tool_name"),
            "tool_name_delta": _safe_getattr_str(data, "tool_name_delta"),
        }

    # 3. part-wrapping events (PartStartEvent / PartEndEvent / etc.) --
    #    unwrap the inner ``part`` so its content is reachable too.
    if hasattr(data, "part"):
        try:
            inner = _sanitize_event_data(data.part)
        except Exception:
            inner = f"<{type_name}.part>"
        return {"type": type_name, "part": inner}

    # 4. ToolCallPart payloads: preserve structured tool metadata for
    #    downstream stream bridges (/ws/chat typed event parser).
    if hasattr(data, "tool_name") and hasattr(data, "args"):
        return {
            "type": type_name,
            "tool_call_id": _safe_getattr_str(data, "tool_call_id"),
            "tool_name": _safe_getattr_str(data, "tool_name"),
            "args": _sanitize_args(getattr(data, "args", {})),
        }

    # 5. Anything with a usable content/text attribute on the top level
    #    (e.g. fully-formed TextPart, ThinkingPart).
    if hasattr(data, "content"):
        return {
            "type": type_name,
            "content": _truncate_string(getattr(data, "content", ""), max_length=1000),
        }

    return f"<{type_name}>"


def _safe_getattr_str(obj: Any, name: str) -> Optional[str]:
    """Return ``str(getattr(obj, name))`` or ``None`` if missing / failing."""
    try:
        val = getattr(obj, name, None)
        return None if val is None else str(val)
    except Exception:
        return None


def _is_successful_result(result: Any) -> bool:
    """Determine if a tool result indicates success.

    Args:
        result: The tool result.

    Returns:
        True if the result appears successful.
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
        result: The tool result.

    Returns:
        A string summary of the result.
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
    """Truncate a string value if it exceeds ``max_length``.

    Args:
        value: The value to truncate (will be converted to str).
        max_length: Maximum length before truncation.

    Returns:
        Truncated string or ``None`` if value is ``None``.
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
