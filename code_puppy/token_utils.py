import json

import pydantic
from pydantic_ai.messages import ModelMessage


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens using the len/4 heuristic.
    This is a simple approximation that works reasonably well for most text.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def stringify_message_part(part) -> str:
    """
    Convert a message part to a string representation for token estimation or other uses.

    Args:
        part: A message part that may contain content or be a tool call

    Returns:
        String representation of the message part
    """
    result = ""
    if hasattr(part, "part_kind"):
        result += part.part_kind + ": "
    else:
        result += str(type(part)) + ": "

    # Handle content
    if hasattr(part, "content") and part.content:
        # Handle different content types
        if isinstance(part.content, str):
            result = part.content
        elif isinstance(part.content, pydantic.BaseModel):
            result = json.dumps(part.content.model_dump())
        elif isinstance(part.content, dict):
            result = json.dumps(part.content)
        else:
            result = str(part.content)

    # Handle tool calls which may have additional token costs
    # If part also has content, we'll process tool calls separately
    if hasattr(part, "tool_name") and part.tool_name:
        # Estimate tokens for tool name and parameters
        tool_text = part.tool_name
        if hasattr(part, "args"):
            tool_text += f" {str(part.args)}"
        result += tool_text

    return result


def estimate_tokens_for_message(message: ModelMessage) -> int:
    """
    Estimate the number of tokens in a message using the len/4 heuristic.
    This is a simple approximation that works reasonably well for most text.
    """
    total_tokens = 0

    for part in message.parts:
        part_str = stringify_message_part(part)
        if part_str:
            total_tokens += estimate_tokens(part_str)

    return max(1, total_tokens)
