import json
import queue
from typing import Any, List, Set, Tuple

import pydantic
from pydantic_ai.messages import ModelMessage, ModelRequest, TextPart, ToolCallPart

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


def estimate_token_count(text: str) -> int:
    """
    Simple token estimation using len(message) - 4.
    This replaces tiktoken with a much simpler approach.
    """
    return max(1, len(text) - 4)


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
            total_tokens += estimate_token_count(part_str)

    return max(1, total_tokens)


def filter_huge_messages(messages: List[ModelMessage]) -> List[ModelMessage]:
    filtered = [m for m in messages if estimate_tokens_for_message(m) < 50000]
    pruned = prune_interrupted_tool_calls(filtered)
    return pruned


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

        protected_messages.insert(0, message)  # Insert at beginning to maintain order
        protected_token_count += message_tokens

    # Add system message at the beginning of protected messages
    protected_messages.insert(0, system_message)

    # Messages to summarize are everything between system message and protected zone
    protected_start_idx = (
        len(messages) - len(protected_messages) + 1
    )  # +1 because system message is protected
    messages_to_summarize = messages[
        1:protected_start_idx
    ]  # Start from 1 to skip system message

    emit_info(
        f"🔒 Protecting {len(protected_messages)} recent messages ({protected_token_count} tokens, limit: {protected_tokens_limit})"
    )
    emit_info(f"📝 Summarizing {len(messages_to_summarize)} older messages")

    return messages_to_summarize, protected_messages


def summarize_messages(
    messages: List[ModelMessage], with_protection=True
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """
    Summarize messages while protecting recent messages up to PROTECTED_TOKENS.

    Returns:
        List of messages: [system_message, summary_of_old_messages, ...protected_recent_messages]
    """
    messages_to_summarize, protected_messages = messages, []
    if with_protection:
        messages_to_summarize, protected_messages = (
            split_messages_for_protected_summarization(messages)
        )

    if not messages_to_summarize:
        # Nothing to summarize, return protected messages as-is
        return protected_messages, messages_to_summarize

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
        # Return: [system_message, summary, ...protected_recent_messages]
        result = new_messages + protected_messages[1:]
        return prune_interrupted_tool_calls(result), messages_to_summarize
    except Exception as e:
        emit_error(f"Summarization failed during compaction: {e}")
        return messages, messages_to_summarize  # Return original messages on failure


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
            # Heuristic: if it's an explicit ToolCallPart or has a tool_name/args,
            # consider it a call; otherwise it's a return/result.
            if part.part_kind == "tool-call":
                tool_call_ids.add(tool_call_id)
            else:
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
    # First, prune any interrupted/mismatched tool-call conversations
    total_current_tokens = sum(estimate_tokens_for_message(msg) for msg in messages)

    model_max = get_model_context_length()

    proportion_used = total_current_tokens / model_max

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
        if compaction_strategy == "truncation":
            # Use truncation instead of summarization
            protected_tokens = get_protected_token_count()
            result_messages = truncation(
                filter_huge_messages(messages), protected_tokens
            )
            summarized_messages = []  # No summarization in truncation mode
        else:
            # Default to summarization
            result_messages, summarized_messages = summarize_messages(
                filter_huge_messages(messages)
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
    return messages


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
    _message_history = get_message_history()
    message_history_hashes = set([hash_message(m) for m in _message_history])
    for msg in messages:
        if (
            hash_message(msg) not in message_history_hashes
            and hash_message(msg) not in get_compacted_message_hashes()
        ):
            _message_history.append(msg)

    # Apply message history trimming using the main processor
    # This ensures we maintain global state while still managing context limits
    message_history_processor(_message_history)
    return get_message_history()
