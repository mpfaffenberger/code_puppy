import json
import queue
from typing import Any, List, Set, Tuple, Union

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
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    return current_agent.stringify_message_part(part)


def estimate_tokens_for_message(message: ModelMessage) -> int:
    """
    Estimate the number of tokens in a message using len(message) - 4.
    Simple and fast replacement for tiktoken.
    """
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    return current_agent.estimate_tokens_for_message(message)


def filter_huge_messages(messages: List[ModelMessage]) -> List[ModelMessage]:
    if not messages:
        return []

    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    # Never drop the system prompt, even if it is extremely large.
    system_message, *rest = messages
    filtered_rest = [
        m for m in rest if current_agent.estimate_tokens_for_message(m) < 50000
    ]
    return [system_message] + filtered_rest


def _is_tool_call_part(part: Any) -> bool:
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    return current_agent._is_tool_call_part(part)


def _is_tool_return_part(part: Any) -> bool:
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    return current_agent._is_tool_return_part(part)


def split_messages_for_protected_summarization(
    messages: List[ModelMessage], with_protection: bool = True
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
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    system_tokens = current_agent.estimate_tokens_for_message(system_message)

    if not with_protection:
        # If not protecting, summarize everything except the system message
        return messages[1:], [system_message]

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
        message_tokens = current_agent.estimate_tokens_for_message(message)

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


def run_summarization_sync(
    instructions: str,
    message_history: List[ModelMessage],
) -> Union[List[ModelMessage], str]:
    """
    Run summarization synchronously using the configured summarization agent.
    This is exposed as a global function so tests can mock it.
    """
    from code_puppy.summarization_agent import run_summarization_sync as _run_summarization_sync
    return _run_summarization_sync(instructions, message_history)


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
    if not messages:
        return [], []

    # Split messages into those to summarize and those to protect
    messages_to_summarize, protected_messages = split_messages_for_protected_summarization(
        messages, with_protection
    )

    # If nothing to summarize, return the original list
    if not messages_to_summarize:
        return prune_interrupted_tool_calls(messages), []

    # Get the system message (always the first message)
    system_message = messages[0]

    # Instructions for the summarization agent
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
        # Use the global function so tests can mock it
        new_messages = run_summarization_sync(
            instructions, message_history=messages_to_summarize
        )

        if not isinstance(new_messages, list):
            emit_warning(
                "Summarization agent returned non-list output; wrapping into message request"
            )
            new_messages = [ModelRequest([TextPart(str(new_messages))])]

        # Construct compacted messages: system message + new summarized messages + protected tail
        compacted: List[ModelMessage] = [system_message] + list(new_messages)

        # Drop the system message from protected_messages because we already included it
        protected_tail = [msg for msg in protected_messages if msg is not system_message]

        compacted.extend(protected_tail)

        return prune_interrupted_tool_calls(compacted), messages_to_summarize
    except Exception as e:
        emit_error(f"Summarization failed during compaction: {e}")
        return messages, []  # Return original messages on failure


def summarize_message(message: ModelMessage) -> ModelMessage:
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    return current_agent.summarize_message(message)


def get_model_context_length() -> int:
    """
    Get the context length for the currently configured model from models.json
    """
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    return current_agent.get_model_context_length()


def prune_interrupted_tool_calls(messages: List[ModelMessage]) -> List[ModelMessage]:
    """
    Remove any messages that participate in mismatched tool call sequences.

    A mismatched tool call id is one that appears in a ToolCall (model/tool request)
    without a corresponding tool return, or vice versa. We preserve original order
    and only drop messages that contain parts referencing mismatched tool_call_ids.
    """
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    return current_agent.prune_interrupted_tool_calls(messages)


def message_history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:
    # Get current agent to use its methods
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    cleaned_history = current_agent.prune_interrupted_tool_calls(messages)

    total_current_tokens = sum(
        current_agent.estimate_tokens_for_message(msg) for msg in cleaned_history
    )

    model_max = current_agent.get_model_context_length()

    proportion_used = total_current_tokens / model_max if model_max else 0

    # Check if we're in TUI mode and can update the status bar
    from code_puppy.tui_state import get_tui_app_instance, is_tui_mode

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
        filtered_history = current_agent.filter_huge_messages(cleaned_history)

        if compaction_strategy == "truncation":
            protected_tokens = get_protected_token_count()
            result_messages = truncation(filtered_history, protected_tokens)
            summarized_messages: List[ModelMessage] = []
        else:
            result_messages, summarized_messages = summarize_messages(
                filtered_history
            )

        final_token_count = sum(
            current_agent.estimate_tokens_for_message(msg) for msg in result_messages
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
            add_compacted_message_hash(current_agent.hash_message(m))
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
    
    # Get current agent to use its method
    from code_puppy.agents.agent_manager import get_current_agent_config
    current_agent = get_current_agent_config()
    
    seen_hashes = {current_agent.hash_message(message) for message in existing_history}
    compacted_hashes = get_compacted_message_hashes()

    for message in messages:
        message_hash = current_agent.hash_message(message)
        if message_hash in seen_hashes or message_hash in compacted_hashes:
            continue
        existing_history.append(message)
        seen_hashes.add(message_hash)

    updated_history = message_history_processor(existing_history)
    set_message_history(updated_history)
    return updated_history
