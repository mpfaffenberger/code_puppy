import json
import tiktoken

import pydantic
from pydantic_ai.messages import ModelMessage


def get_tokenizer():
    """
    Always use cl100k_base tokenizer regardless of model type.
    This is a simple approach that works reasonably well for most models.
    """
    return tiktoken.get_encoding("cl100k_base")


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
    Estimate the number of tokens in a message using tiktoken with cl100k_base encoding.
    This is more accurate than character-based estimation.
    """
    tokenizer = get_tokenizer()
    total_tokens = 0

    for part in message.parts:
        part_str = stringify_message_part(part)
        if part_str:
            tokens = tokenizer.encode(part_str)
            total_tokens += len(tokens)

    return max(1, total_tokens)
