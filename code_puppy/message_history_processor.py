import json
import queue
from typing import Any, List, Set, Tuple

import pydantic
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
    ToolCallPart,
    ToolCallPartDelta,
    ToolReturn,
    ToolReturnPart,
)

from code_puppy.config import (
    get_model_name,
    get_protected_token_count,
    get_compaction_threshold,
    get_compaction_strategy,
)
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.model_factory import ModelFactory
from code_puppy.state_management import (
    add_compacted_message_hash,
    get_compacted_message_hashes,
    get_message_history,
    hash_message,
    set_message_history,
)
from code_puppy.summarization_agent import run_summarization_sync

# Protected tokens are now configurable via get_protected_token_count()
# Default is 50000 but can be customized in ~/.code_puppy/puppy.cfg


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
    Estimate the number of tokens in a message using len(message) - 4.
    Simple and fast replacement for tiktoken.
    """
    total_tokens = 0

    for part in message.parts:
        part_str = stringify_message_part(part)
        if part_str:
            total_tokens += len(part_str)

    return int(max(1, total_tokens) / 4)


def filter_huge_messages(messages: List[ModelMessage]) -> List[ModelMessage]:
    if not messages:
        return []

    # Never drop the system prompt, even if it is extremely large.
    system_message, *rest = messages
    filtered_rest = [
        m for m in rest if estimate_tokens_for_message(m) < 50000
    ]
    return [system_message] + filtered_rest


def _is_tool_call_part(part: Any) -> bool:
    if isinstance(part, (ToolCallPart, ToolCallPartDelta)):
        return True

    part_kind = (getattr(part, "part_kind", "") or "").replace("_", "-")
    if part_kind == "tool-call":
        return True

    has_tool_name = getattr(part, "tool_name", None) is not None
    has_args = getattr(part, "args", None) is not None
    has_args_delta = getattr(part, "args_delta", None) is not None

    return bool(has_tool_name and (has_args or has_args_delta))


def _is_tool_return_part(part: Any) -> bool:
    if isinstance(part, (ToolReturnPart, ToolReturn)):
        return True

    part_kind = (getattr(part, "part_kind", "") or "").replace("_", "-")
    if part_kind in {"tool-return", "tool-result"}:
        return True

    if getattr(part, "tool_call_id", None) is None:
        return False

    has_content = getattr(part, "content", None) is not None
    has_content_delta = getattr(part, "content_delta", None) is not None
    return bool(has_content or has_content_delta)


def split_messages_for_protected_summarization(
    messages: List[ModelMessage],
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """
    Split messages into two groups: messages to summarize and protected recent messages.

    Returns:
        Tuple of (messages_to_summarize, protected_messages)

    The protected_messages are the most recent messages that total up to the configured protected token count.
    The system message (first message) is always protected.
    All other messages that don't fit in the protected zone will be summarized.
    """
    if len(messages) <= 1:  # Just system message or empty
        return [], messages

    # Always protect the system message (first message)
    system_message = messages[0]
    system_tokens = estimate_tokens_for_message(system_message)

    if len(messages) == 1:
        return [], messages

    # Get the configured protected token count
    protected_tokens_limit = get_protected_token_count()

    # Calculate tokens for messages from most recent backwards (excluding system message)
    protected_messages = []
    protected_token_count = system_tokens  # Start with system message tokens

    # Go backwards through non-system messages to find protected zone
    for i in range(len(messages) - 1, 0, -1):  # Stop at 1, not 0 (skip system message)
        message = messages[i]
        message_tokens = estimate_tokens_for_message(message)

        # If adding this message would exceed protected tokens, stop here
        if protected_token_count + message_tokens > protected_tokens_limit:
            break

        protected_messages.append(message)
        protected_token_count += message_tokens

    # Messages that were added while scanning backwards are currently in reverse order.
    # Reverse them to restore chronological ordering, then prepend the system prompt.
    protected_messages.reverse()
    protected_messages.insert(0, system_message)

    # Messages to summarize are everything between the system message and the
    # protected tail zone we just constructed.
    protected_start_idx = max(1, len(messages) - (len(protected_messages) - 1))
    messages_to_summarize = messages[1:protected_start_idx]

    emit_info(
        f"🔒 Protecting {len(protected_messages)} recent messages ({protected_token_count} tokens, limit: {protected_tokens_limit})"
    )
    emit_info(f"📝 Summarizing {len(messages_to_summarize)} older messages")

    return messages_to_summarize, protected_messages


def deduplicate_tool_returns(messages: List[ModelMessage]) -> List[ModelMessage]:
    """
    Remove duplicate tool returns while preserving the first occurrence for each tool_call_id.

    This function identifies tool-return parts that share the same tool_call_id and
    removes duplicates, keeping only the first return for each id. This prevents
    conversation corruption from duplicate tool_result blocks.
    """
    if not messages:
        return messages

    seen_tool_returns: Set[str] = set()
    deduplicated: List[ModelMessage] = []
    removed_count = 0

    for msg in messages:
        if not hasattr(msg, "parts") or not msg.parts:
            deduplicated.append(msg)
            continue

        filtered_parts = []
        msg_had_duplicates = False

        for part in msg.parts:
            tool_call_id = getattr(part, "tool_call_id", None)
            if tool_call_id and _is_tool_return_part(part):
                if tool_call_id in seen_tool_returns:
                    msg_had_duplicates = True
                    removed_count += 1
                    continue
                seen_tool_returns.add(tool_call_id)
            filtered_parts.append(part)

        if not filtered_parts:
            continue

        if msg_had_duplicates:
            new_msg = type(msg)(parts=filtered_parts)
            for attr_name in dir(msg):
                if (
                    not attr_name.startswith("_")
                    and attr_name != "parts"
                    and hasattr(msg, attr_name)
                ):
                    try:
                        setattr(new_msg, attr_name, getattr(msg, attr_name))
                    except (AttributeError, TypeError):
                        pass
            deduplicated.append(new_msg)
        else:
            deduplicated.append(msg)

    if removed_count > 0:
        emit_warning(f"Removed {removed_count} duplicate tool-return part(s)")

    return deduplicated


def summarize_messages(
    messages: List[ModelMessage], with_protection: bool = True
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """
    Summarize messages while protecting recent messages up to PROTECTED_TOKENS.

    Returns:
        Tuple of (compacted_messages, summarized_source_messages)
        where compacted_messages always preserves the original system message
        as the first entry.
    """
    messages_to_summarize: List[ModelMessage]
    protected_messages: List[ModelMessage]

    if with_protection:
        messages_to_summarize, protected_messages = (
            split_messages_for_protected_summarization(messages)
        )
    else:
        messages_to_summarize = messages[1:] if messages else []
        protected_messages = messages[:1]

    if not messages:
        return [], []

    system_message = messages[0]

    if not messages_to_summarize:
        # Nothing to summarize, so just return the original sequence
        return prune_interrupted_tool_calls(messages), []

    instructions = (
        "The input will be a log of Agentic AI steps that have been taken"
        " as well as user queries, etc. Summarize the contents of these steps."
        " The high level details should remain but the bulk of the content from tool-call"
        " responses should be compacted and summarized. For example if you see a tool-call"
        " reading a file, and the file contents are large, then in your summary you might just"
        " write: * used read_file on space_invaders.cpp - contents removed."
        "\n Make sure your result is a bulleted list of all steps and interactions."
        "\n\nNOTE: This summary represents older conversation history. Recent messages are preserved separately."
    )

    try:
        new_messages = run_summarization_sync(
            instructions, message_history=messages_to_summarize
        )

        if not isinstance(new_messages, list):
            emit_warning(
                "Summarization agent returned non-list output; wrapping into message request"
            )
            new_messages = [ModelRequest([TextPart(str(new_messages))])]

        compacted: List[ModelMessage] = [system_message] + list(new_messages)

        # Drop the system message from protected_messages because we already included it
        protected_tail = [msg for msg in protected_messages if msg is not system_message]

        compacted.extend(protected_tail)

        return prune_interrupted_tool_calls(compacted), messages_to_summarize
    except Exception as e:
        emit_error(f"Summarization failed during compaction: {e}")
        return messages, []  # Return original messages on failure


def summarize_message(message: ModelMessage) -> ModelMessage:
    try:
        # If the message looks like a system/instructions message, skip summarization
        instructions = getattr(message, "instructions", None)
        if instructions:
            return message
        # If any part is a tool call, skip summarization
        for part in message.parts:
            if isinstance(part, ToolCallPart) or getattr(part, "tool_name", None):
                return message
        # Build prompt from textual content parts
        content_bits: List[str] = []
        for part in message.parts:
            s = stringify_message_part(part)
            if s:
                content_bits.append(s)
        if not content_bits:
            return message
        prompt = "Please summarize the following user message:\n" + "\n".join(
            content_bits
        )
        output_text = run_summarization_sync(prompt)
        summarized = ModelRequest([TextPart(output_text)])
        return summarized
    except Exception as e:
        emit_error(f"Summarization failed: {e}")
        return message


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    model_configs = ModelFactory.load_config()
    model_name = get_model_name()

    # Get context length from model config
    model_config = model_configs.get(model_name, {})
    context_length = model_config.get("context_length", 128000)  # Default value

    # Reserve 10% of context for response
    return int(context_length)


def prune_interrupted_tool_calls(messages: List[ModelMessage]) -> List[ModelMessage]:
    """
    Remove any messages that participate in mismatched tool call sequences.

    A mismatched tool call id is one that appears in a ToolCall (model/tool request)
    without a corresponding tool return, or vice versa. We preserve original order
    and only drop messages that contain parts referencing mismatched tool_call_ids.
    """
    if not messages:
        return messages

    tool_call_ids: Set[str] = set()
    tool_return_ids: Set[str] = set()

    # First pass: collect ids for calls vs returns
    for msg in messages:
        for part in getattr(msg, "parts", []) or []:
            tool_call_id = getattr(part, "tool_call_id", None)
            if not tool_call_id:
                continue

            if _is_tool_call_part(part) and not _is_tool_return_part(part):
                tool_call_ids.add(tool_call_id)
            elif _is_tool_return_part(part):
                tool_return_ids.add(tool_call_id)

    mismatched: Set[str] = tool_call_ids.symmetric_difference(tool_return_ids)
    if not mismatched:
        return messages

    pruned: List[ModelMessage] = []
    dropped_count = 0
    for msg in messages:
        has_mismatched = False
        for part in getattr(msg, "parts", []) or []:
            tcid = getattr(part, "tool_call_id", None)
            if tcid and tcid in mismatched:
                has_mismatched = True
                break
        if has_mismatched:
            dropped_count += 1
            continue
        pruned.append(msg)

    if dropped_count:
        emit_warning(
            f"Pruned {dropped_count} message(s) with mismatched tool_call_id pairs"
        )
    return pruned


def message_history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:
    cleaned_history = prune_interrupted_tool_calls(
        deduplicate_tool_returns(messages)
    )

    total_current_tokens = sum(
        estimate_tokens_for_message(msg) for msg in cleaned_history
    )

    model_max = get_model_context_length()

    proportion_used = total_current_tokens / model_max if model_max else 0

    # Check if we're in TUI mode and can update the status bar
    from code_puppy.state_management import get_tui_app_instance, is_tui_mode

    if is_tui_mode():
        tui_app = get_tui_app_instance()
        if tui_app:
            try:
                # Update the status bar instead of emitting a chat message
                status_bar = tui_app.query_one("StatusBar")
                status_bar.update_token_info(
                    total_current_tokens, model_max, proportion_used
                )
            except Exception as e:
                emit_error(e)
                # Fallback to chat message if status bar update fails
                emit_info(
                    f"\n[bold white on blue] Tokens in context: {total_current_tokens}, total model capacity: {model_max}, proportion used: {proportion_used:.2f} [/bold white on blue] \n",
                    message_group="token_context_status",
                )
        else:
            # Fallback if no TUI app instance
            emit_info(
                f"\n[bold white on blue] Tokens in context: {total_current_tokens}, total model capacity: {model_max}, proportion used: {proportion_used:.2f} [/bold white on blue] \n",
                message_group="token_context_status",
            )
    else:
        # Non-TUI mode - emit to console as before
        emit_info(
            f"\n[bold white on blue] Tokens in context: {total_current_tokens}, total model capacity: {model_max}, proportion used: {proportion_used:.2f} [/bold white on blue] \n"
        )
    # Get the configured compaction threshold
    compaction_threshold = get_compaction_threshold()

    # Get the configured compaction strategy
    compaction_strategy = get_compaction_strategy()

    if proportion_used > compaction_threshold:
        filtered_history = filter_huge_messages(cleaned_history)

        if compaction_strategy == "truncation":
            protected_tokens = get_protected_token_count()
            result_messages = truncation(filtered_history, protected_tokens)
            summarized_messages: List[ModelMessage] = []
        else:
            result_messages, summarized_messages = summarize_messages(
                filtered_history
            )

        final_token_count = sum(
            estimate_tokens_for_message(msg) for msg in result_messages
        )
        # Update status bar with final token count if in TUI mode
        if is_tui_mode():
            tui_app = get_tui_app_instance()
            if tui_app:
                try:
                    status_bar = tui_app.query_one("StatusBar")
                    status_bar.update_token_info(
                        final_token_count, model_max, final_token_count / model_max
                    )
                except Exception:
                    emit_info(
                        f"Final token count after processing: {final_token_count}",
                        message_group="token_context_status",
                    )
            else:
                emit_info(
                    f"Final token count after processing: {final_token_count}",
                    message_group="token_context_status",
                )
        else:
            emit_info(f"Final token count after processing: {final_token_count}")
        set_message_history(result_messages)
        for m in summarized_messages:
            add_compacted_message_hash(hash_message(m))
        return result_messages

    set_message_history(cleaned_history)
    return cleaned_history


def truncation(
    messages: List[ModelMessage], protected_tokens: int
) -> List[ModelMessage]:
    emit_info("Truncating message history to manage token usage")
    result = [messages[0]]  # Always keep the first message (system prompt)
    num_tokens = 0
    stack = queue.LifoQueue()

    # Put messages in reverse order (most recent first) into the stack
    # but break when we exceed protected_tokens
    for idx, msg in enumerate(reversed(messages[1:])):  # Skip the first message
        num_tokens += estimate_tokens_for_message(msg)
        if num_tokens > protected_tokens:
            break
        stack.put(msg)

    # Pop messages from stack to get them in chronological order
    while not stack.empty():
        result.append(stack.get())

    result = prune_interrupted_tool_calls(result)
    return result


def message_history_accumulator(messages: List[Any]):
    existing_history = list(get_message_history())
    seen_hashes = {hash_message(message) for message in existing_history}
    compacted_hashes = get_compacted_message_hashes()

    for message in messages:
        message_hash = hash_message(message)
        if message_hash in seen_hashes or message_hash in compacted_hashes:
            continue
        existing_history.append(message)
        seen_hashes.add(message_hash)

    updated_history = message_history_processor(existing_history)
    set_message_history(updated_history)
    return updated_history
