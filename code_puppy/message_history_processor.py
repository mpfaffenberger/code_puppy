import json
import math
import queue
from typing import List

from pydantic_ai.messages import ModelMessage, ToolCallPart, ToolReturnPart

from code_puppy.config import (
    get_expected_output_tokens,
    get_max_input_tokens_per_request,
    get_message_history_limit,
)
from code_puppy.tools.common import console


def message_history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:
    """
    Compact message history to fit within an estimated token budget while preserving context.

    Strategy:
    - Token-aware compaction using configurable per-request input budget.
    - Reserve configurable output tokens for the assistant reply.
    - Always keep the first message (system prompt).
    - Keep a secondary cap by message count (message_history_limit).
    - Maintain tool call/return pairs when possible (drop unmatched at the boundary).
    """
    if not messages:
        return messages

    # Configuration: message count cap and token budgets
    max_messages = get_message_history_limit()
    max_input_tokens = get_max_input_tokens_per_request()
    reserved_output_tokens = get_expected_output_tokens()
    # Ensure a sensible minimum budget for inputs
    token_budget = max(512, max_input_tokens - reserved_output_tokens)

    # Helper: estimate tokens for a list of ModelMessage(s)
    def estimate_tokens_for_messages(msgs: List[ModelMessage]) -> int:
        chars = 0
        for m in msgs:
            for part in getattr(m, "parts", []) or []:
                # Prefer explicit textual fields
                text_val = None
                for attr in ("content", "text"):
                    v = getattr(part, attr, None)
                    if isinstance(v, str):
                        text_val = v
                        break
                if text_val is not None:
                    chars += len(text_val)
                    continue
                # Tool calls/returns may have structured args; count roughly
                try:
                    if hasattr(part, "args") and part.args is not None:
                        chars += len(json.dumps(part.args, ensure_ascii=False))
                except Exception:
                    pass
        # Heuristic: ~4 chars per token
        return max(1, math.ceil(chars / 4))

    # Always keep the system message
    system_msg = messages[0]
    selected_reversed: List[ModelMessage] = []

    remaining_budget = token_budget - estimate_tokens_for_messages([system_msg])
    remaining_count = max_messages - 1

    # Short-circuit: if count is already within limit and tokens fit, keep all
    if len(messages) <= max_messages and (
        estimate_tokens_for_messages(messages) <= token_budget
    ):
        return messages

    # Take the most recent messages that fit in token budget and count cap
    for msg in reversed(messages[1:]):
        if remaining_count <= 0:
            break
        est = estimate_tokens_for_messages([msg])
        if est <= remaining_budget:
            selected_reversed.append(msg)
            remaining_budget -= est
            remaining_count -= 1
        else:
            # Stop when the next (older) message would not fit, keeping contiguity
            break

    # Reconstruct in chronological order: system, then the reversed selection
    result = [system_msg]
    for m in reversed(selected_reversed):
        result.append(m)

    # Maintain tool call/return pairing: drop unmatched boundary messages
    tool_call_parts = set()
    tool_return_parts = set()
    for item in result:
        for part in getattr(item, "parts", []) or []:
            if hasattr(part, "tool_call_id") and part.tool_call_id:
                if isinstance(part, ToolCallPart):
                    tool_call_parts.add(part.tool_call_id)
                if isinstance(part, ToolReturnPart):
                    tool_return_parts.add(part.tool_call_id)

    mismatched_ids = (tool_call_parts.union(tool_return_parts)) - (
        tool_call_parts.intersection(tool_return_parts)
    )

    final_result = []
    if mismatched_ids:
        for msg in result:
            has_mismatch = False
            for part in getattr(msg, "parts", []) or []:
                if hasattr(part, "tool_call_id") and part.tool_call_id in mismatched_ids:
                    has_mismatch = True
                    break
            if not has_mismatch:
                final_result.append(msg)
    else:
        final_result = result

    # Log compaction summary when truncation occurs
    if len(final_result) < len(messages):
        console.print(
            f"Compacted history to ~{token_budget} input tokens and {max_messages} msgs: "
            f"kept {len(final_result)}/{len(messages)}"
        )

    return final_result