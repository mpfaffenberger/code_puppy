"""Pure helpers for message history hashing, token estimation, and pruning.

Extracted from the original ``BaseAgent`` god-class. Everything in here is a
free function with no hidden state. Call sites pass messages (and, where
needed, already-resolved strings / tool dicts) in explicitly.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional, Set

import pydantic
from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage


def stringify_part(part: Any) -> str:
    """Return a stable, timestamp-free string representation of a message part.

    Used for both hashing and token estimation. Ignoring timestamps means two
    otherwise-identical parts emitted at different times collapse to the same
    string, which is exactly what we want for dedup.
    """
    attributes: List[str] = [part.__class__.__name__]

    if hasattr(part, "role") and part.role:
        attributes.append(f"role={part.role}")
    if hasattr(part, "instructions") and part.instructions:
        attributes.append(f"instructions={part.instructions}")

    if hasattr(part, "tool_call_id") and part.tool_call_id:
        attributes.append(f"tool_call_id={part.tool_call_id}")
    if hasattr(part, "tool_name") and part.tool_name:
        attributes.append(f"tool_name={part.tool_name}")

    content = getattr(part, "content", None)
    if content is None:
        attributes.append("content=None")
    elif isinstance(content, str):
        attributes.append(f"content={content}")
    elif isinstance(content, pydantic.BaseModel):
        attributes.append(f"content={json.dumps(content.model_dump(), sort_keys=True)}")
    elif isinstance(content, dict):
        attributes.append(f"content={json.dumps(content, sort_keys=True)}")
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                attributes.append(f"content={item}")
            elif isinstance(item, BinaryContent):
                attributes.append(f"BinaryContent={hash(item.data)}")
    else:
        attributes.append(f"content={repr(content)}")

    return "|".join(attributes)


def hash_message(message: Any) -> int:
    """Stable hash for a ``ModelMessage`` that ignores timestamps."""
    role = getattr(message, "role", None)
    instructions = getattr(message, "instructions", None)
    header_bits: List[str] = []
    if role:
        header_bits.append(f"role={role}")
    if instructions:
        header_bits.append(f"instructions={instructions}")

    part_strings = [stringify_part(part) for part in getattr(message, "parts", [])]
    canonical = "||".join(header_bits + part_strings)
    return hash(canonical)


def estimate_tokens(text: str) -> int:
    """Dirt-simple tiktoken replacement: ``max(1, floor(len(text) / 2.5))``."""
    return max(1, math.floor(len(text) / 2.5))


def estimate_tokens_for_message(message: ModelMessage) -> int:
    """Estimate the number of tokens in a single model message."""
    total = 0
    for part in getattr(message, "parts", []) or []:
        part_str = stringify_part(part)
        if part_str:
            total += estimate_tokens(part_str)
    return max(1, total)


def estimate_context_overhead(
    system_prompt: str,
    pydantic_tools: Optional[Dict[str, Any]],
) -> int:
    """Estimate fixed token overhead for the system prompt + tool definitions.

    The caller is responsible for resolving the system prompt for the active
    model (e.g. via ``prepare_prompt_for_model``). MCP tool overhead is
    deliberately ignored — it was guesswork anyway.

    Args:
        system_prompt: The already-resolved instruction/system prompt string.
        pydantic_tools: The pydantic-ai agent's ``_tools`` dict, or ``None``.

    Returns:
        Estimated total token overhead.
    """
    total = 0
    if system_prompt:
        total += estimate_tokens(system_prompt)

    if not pydantic_tools:
        return total

    for tool_name, tool_func in pydantic_tools.items():
        total += estimate_tokens(tool_name)

        description = getattr(tool_func, "__doc__", None) or ""
        if description:
            total += estimate_tokens(description)

        schema = getattr(tool_func, "schema", None)
        if schema is not None:
            schema_str = json.dumps(schema) if isinstance(schema, dict) else str(schema)
            total += estimate_tokens(schema_str)
        else:
            annotations = getattr(tool_func, "__annotations__", None)
            if annotations:
                total += estimate_tokens(str(annotations))

    return total


# Pydantic-AI has FOUR part kinds that carry a tool_call_id:
#   * tool-call            -> ToolCallPart            (regular tool call)
#   * tool-return          -> ToolReturnPart          (regular tool response)
#   * builtin-tool-call    -> BuiltinToolCallPart     (claude extended-thinking, etc.)
#   * builtin-tool-return  -> BuiltinToolReturnPart   (builtin tool response)
#   * retry-prompt         -> RetryPromptPart         (assistant told to retry; acts as a response)
#
# Treating only `tool-call` / `tool-return` (and ignoring the others) caused
# subtle bugs: e.g. builtin tool calls on Claude Opus were counted as pending
# forever, deferring summarization on every turn.
_TOOL_CALL_PART_KINDS: frozenset[str] = frozenset({"tool-call", "builtin-tool-call"})
_TOOL_RETURN_PART_KINDS: frozenset[str] = frozenset(
    {"tool-return", "builtin-tool-return", "retry-prompt"}
)


def _classify_tool_part(part: object) -> str | None:
    """Return ``"call"``, ``"return"``, or ``None`` for a message part.

    ``None`` means the part doesn't participate in tool_call_id pairing
    (either no id, or an unrelated part kind).
    """
    if getattr(part, "tool_call_id", None) is None:
        return None
    pk = getattr(part, "part_kind", None)
    if pk in _TOOL_CALL_PART_KINDS:
        return "call"
    if pk in _TOOL_RETURN_PART_KINDS:
        return "return"
    return None


def prune_interrupted_tool_calls(
    messages: List[ModelMessage],
) -> List[ModelMessage]:
    """Drop messages participating in mismatched tool_call/tool_return pairs.

    A mismatched ``tool_call_id`` is one that appears only as a call or only
    as a return. The model will reject such histories ("tool_use ids found
    without tool_result blocks"), so we strip them out while preserving order.
    """
    if not messages:
        return messages

    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            kind = _classify_tool_part(part)
            if kind == "call":
                tool_call_ids.add(part.tool_call_id)
            elif kind == "return":
                tool_return_ids.add(part.tool_call_id)

    mismatched = tool_call_ids.symmetric_difference(tool_return_ids)
    if not mismatched:
        return messages

    pruned: List[ModelMessage] = []
    for msg in messages:
        if any(
            getattr(part, "tool_call_id", None) in mismatched
            for part in getattr(msg, "parts", []) or []
        ):
            continue
        pruned.append(msg)
    return pruned


def has_pending_tool_calls(messages: List[ModelMessage]) -> bool:
    """Return True if any tool call is still waiting for its response.

    Recognizes both regular (``tool-call`` / ``tool-return``) and builtin
    (``builtin-tool-call`` / ``builtin-tool-return``) pairings, plus
    ``retry-prompt`` as a valid response form.
    """
    if not messages:
        return False

    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            kind = _classify_tool_part(part)
            if kind == "call":
                tool_call_ids.add(part.tool_call_id)
            elif kind == "return":
                tool_return_ids.add(part.tool_call_id)

    return bool(tool_call_ids - tool_return_ids)


def filter_huge_messages(messages: List[ModelMessage]) -> List[ModelMessage]:
    """Drop individual messages above a 50k-token budget, then prune orphans."""
    filtered = [m for m in messages if estimate_tokens_for_message(m) < 50000]
    return prune_interrupted_tool_calls(filtered)
