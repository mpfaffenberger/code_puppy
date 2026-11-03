"""Shared helpers for extracting display fields from pydantic-ai ModelMessages.

Used by the SQLite persistence helpers and session_context.py.
Must not import from seeder.py or session_context.py to avoid circular imports.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PART_TYPE_TEXT = {"TextPart", "UserPromptPart", "SystemPromptPart"}
_PART_TYPE_THINKING = {"ThinkingPart"}


def get_role(msg: Any) -> str:
    """Map a ModelMessage to a DB role string."""
    kind = getattr(msg, "kind", None)
    if kind == "request":
        return "user"
    if kind == "response":
        return "assistant"
    return "system"


def extract_content(msg: Any) -> str:
    """Extract human-readable text from a ModelMessage's parts."""
    parts = getattr(msg, "parts", [])
    texts = []
    for part in parts:
        if type(part).__name__ in _PART_TYPE_TEXT:
            c = getattr(part, "content", "")
            if isinstance(c, str) and c.strip():
                texts.append(c)
    return "\n".join(texts)


def extract_thinking(msg: Any) -> Optional[str]:
    """Extract extended thinking text from a ModelResponse's parts."""
    parts = getattr(msg, "parts", [])
    texts = [
        getattr(p, "content", "")
        for p in parts
        if type(p).__name__ in _PART_TYPE_THINKING
        and isinstance(getattr(p, "content", ""), str)
    ]
    joined = "\n".join(t for t in texts if t)
    return joined or None


def get_message_timestamp(msg: Any) -> Optional[str]:
    """Return the message's own timestamp as an ISO string, or None."""
    ts = getattr(msg, "timestamp", None)
    if ts is None:
        return None
    try:
        return ts.isoformat()
    except Exception:
        return str(ts)


def pydantic_json_for_message(msg: Any) -> Optional[str]:
    """Serialise a single ModelMessage to a JSON string via ModelMessagesTypeAdapter.

    Stores as a single-element list: `[msg_json]`.
    Deserialise with: `ModelMessagesTypeAdapter.validate_json(s)[0]`

    Returns None if serialisation fails for unsupported historical message shapes.
    """
    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ModelMessagesTypeAdapter.dump_json([msg]).decode("utf-8")
    except Exception as exc:
        logger.debug("pydantic_json serialisation failed: %s", exc)
        return None


_PART_TYPE_TOOL_CALL = {"ToolCallPart"}
# Extended set of tool return part type names for runtime compatibility
# Different versions of pydantic-ai and streaming may use different class names
_PART_TYPE_TOOL_RETURN = {"ToolReturnPart", "ToolReturn", "RetryPromptPart"}


def extract_tool_calls(msg: Any) -> list[dict[str, Any]]:
    """Extract ToolCallPart entries from a ModelResponse.

    Returns list of dicts: {id, name, args_dict}
    """
    import uuid

    parts = getattr(msg, "parts", [])
    result = []
    for part in parts:
        if type(part).__name__ not in _PART_TYPE_TOOL_CALL:
            continue
        args = getattr(part, "args", {})
        if hasattr(args, "model_dump"):
            args = args.model_dump()
        elif hasattr(args, "__dict__"):
            args = dict(args.__dict__)
        result.append(
            {
                "id": getattr(part, "tool_call_id", "") or str(uuid.uuid4()),
                "name": getattr(part, "tool_name", "unknown"),
                "args": args,
            }
        )
    return result


def _is_tool_return_like(part: Any) -> bool:
    """Check if a part is a tool return using duck-typing.

    Handles various runtime representations:
    - ToolReturnPart (standard pydantic-ai)
    - ToolReturn (streaming/runtime variant)
    - Any object with tool_call_id + (content or return_value)
    """
    class_name = type(part).__name__

    # Fast path: known class names
    if class_name in _PART_TYPE_TOOL_RETURN:
        return True

    # Duck-typing fallback: must have tool_call_id and some result content
    has_tool_call_id = hasattr(part, "tool_call_id") and getattr(
        part, "tool_call_id", None
    )
    has_content = hasattr(part, "content") or hasattr(part, "return_value")

    return bool(has_tool_call_id and has_content)


def _extract_tool_return_data(part: Any) -> dict[str, Any]:
    """Extract tool return data from a part using multiple field strategies.

    Handles different field naming conventions:
    - content (ToolReturnPart)
    - return_value (some runtime variants)
    - result (potential future variants)
    """
    import json

    # Get the result content - try multiple field names
    raw_content = None
    for field in ("content", "return_value", "result"):
        if hasattr(part, field):
            raw_content = getattr(part, field, None)
            if raw_content is not None:
                break

    # Parse JSON if string, otherwise use as-is
    if raw_content is None:
        result_val = None
    elif isinstance(raw_content, str):
        try:
            result_val = json.loads(raw_content)
        except (json.JSONDecodeError, TypeError):
            result_val = raw_content
    else:
        result_val = raw_content

    # Get tool name - try multiple field names
    tool_name = "unknown"
    for field in ("tool_name", "name"):
        if hasattr(part, field):
            name = getattr(part, field, None)
            if name:
                tool_name = name
                break

    return {
        "id": getattr(part, "tool_call_id", "") or "",
        "name": tool_name,
        "result": result_val,
    }


def extract_tool_returns(msg: Any) -> list[dict[str, Any]]:
    """Extract tool return entries from a ModelRequest.

    Returns list of dicts: {id, name, result}

    Handles multiple runtime representations:
    - ToolReturnPart (standard pydantic-ai)
    - ToolReturn (streaming variant)
    - Duck-typed objects with tool_call_id + content/return_value

    This extended compatibility ensures tool results are persisted to SQLite
    regardless of which pydantic-ai version or streaming mode is in use.
    """
    parts = getattr(msg, "parts", [])
    result = []

    for part in parts:
        if not _is_tool_return_like(part):
            continue

        try:
            data = _extract_tool_return_data(part)
            if data["id"]:  # Only add if we have a valid tool_call_id
                result.append(data)
            else:
                logger.debug(
                    "Skipping tool return with empty tool_call_id: %s",
                    type(part).__name__,
                )
        except Exception as exc:
            logger.warning(
                "Failed to extract tool return from %s: %s", type(part).__name__, exc
            )

    return result
