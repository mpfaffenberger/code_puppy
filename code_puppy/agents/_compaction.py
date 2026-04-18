"""Message history compaction (truncation + summarization).

Replaces the old ``message_history_processor`` / ``message_history_accumulator``
pair from ``BaseAgent``. All logic here is free-function; the one stateful
entry point is ``make_history_processor(agent)`` which returns a closure that
pydantic-ai wires in as its ``history_processors`` callback.

The delayed-compaction globals and the retry-after-tool-calls plumbing from
the original god-class are **gone**. If compaction can't run safely right now
(pending tool calls + summarization strategy), we just skip it this cycle and
let the next ``history_processor`` invocation handle it.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, List, Set, Tuple

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
)

from code_puppy.agents._history import (
    estimate_tokens_for_message,
    filter_huge_messages,
    has_pending_tool_calls,
    hash_message,
    prune_interrupted_tool_calls,
)
from code_puppy.callbacks import (
    on_message_history_processor_end,
    on_message_history_processor_start,
)
from code_puppy.config import (
    get_compaction_strategy,
    get_compaction_threshold,
    get_protected_token_count,
)
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.messaging.spinner import SpinnerBase, update_spinner_context
from code_puppy.summarization_agent import SummarizationError, run_summarization_sync

_SUMMARIZATION_INSTRUCTIONS = (
    "The input will be a log of Agentic AI steps that have been taken"
    " as well as user queries, etc. Summarize the contents of these steps."
    " The high level details should remain but the bulk of the content from tool-call"
    " responses should be compacted and summarized. For example if you see a tool-call"
    " reading a file, and the file contents are large, then in your summary you might just"
    " write: * used read_file on space_invaders.cpp - contents removed."
    "\n Make sure your result is a bulleted list of all steps and interactions."
    "\n\nNOTE: This summary represents older conversation history. "
    "Recent messages are preserved separately."
)


def _find_safe_split_index(messages: List[ModelMessage], initial_split_idx: int) -> int:
    """Adjust split index so we never sever a tool_call from its tool_return."""
    if initial_split_idx <= 1:
        return initial_split_idx

    protected_tool_return_ids: Set[str] = set()
    for msg in messages[initial_split_idx:]:
        for part in getattr(msg, "parts", []) or []:
            if getattr(part, "part_kind", None) == "tool-return":
                tcid = getattr(part, "tool_call_id", None)
                if tcid:
                    protected_tool_return_ids.add(tcid)

    if not protected_tool_return_ids:
        return initial_split_idx

    adjusted_idx = initial_split_idx
    # Walk backwards; never cross the system message at index 0.
    for i in range(initial_split_idx - 1, 0, -1):
        msg = messages[i]
        has_match = False
        for part in getattr(msg, "parts", []) or []:
            if getattr(part, "part_kind", None) == "tool-call":
                tcid = getattr(part, "tool_call_id", None)
                if tcid and tcid in protected_tool_return_ids:
                    has_match = True
                    break
        if has_match:
            adjusted_idx = i
        else:
            # Tool calls and their returns are adjacent — first miss ends it.
            break

    return adjusted_idx


def split_for_protected_summarization(
    messages: List[ModelMessage],
    protected_tokens: int,
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """Split messages into (to_summarize, protected) groups.

    The system message (index 0) is always protected. Starting from the most
    recent message, we accumulate messages into the protected zone until we
    hit ``protected_tokens``. Everything in-between becomes summarization
    fodder. The split point is adjusted to keep tool_call/tool_return pairs
    together.
    """
    if len(messages) <= 1:
        return [], messages

    system_message = messages[0]
    system_tokens = estimate_tokens_for_message(system_message)

    protected_messages: List[ModelMessage] = []
    running_tokens = system_tokens

    for i in range(len(messages) - 1, 0, -1):
        msg_tokens = estimate_tokens_for_message(messages[i])
        if running_tokens + msg_tokens > protected_tokens:
            break
        protected_messages.append(messages[i])
        running_tokens += msg_tokens

    protected_messages.reverse()
    protected_messages.insert(0, system_message)

    protected_start_idx = max(1, len(messages) - (len(protected_messages) - 1))
    protected_start_idx = _find_safe_split_index(messages, protected_start_idx)
    messages_to_summarize = messages[1:protected_start_idx]

    emit_info(
        f"🔒 Protecting {len(protected_messages)} recent messages "
        f"({running_tokens} tokens, limit: {protected_tokens})"
    )
    emit_info(f"📝 Summarizing {len(messages_to_summarize)} older messages")

    return messages_to_summarize, protected_messages


def truncate(messages: List[ModelMessage], protected_tokens: int) -> List[ModelMessage]:
    """Drop middle messages, keeping system prompt, optional thinking, and recent tail."""
    import queue

    if not messages:
        return messages

    emit_info("Truncating message history to manage token usage")
    result: List[ModelMessage] = [messages[0]]

    # Preserve the 2nd message if it's an extended-thinking context.
    skip_second = False
    if len(messages) > 1:
        second_msg = messages[1]
        if any(isinstance(part, ThinkingPart) for part in second_msg.parts):
            result.append(second_msg)
            skip_second = True

    start_idx = 2 if skip_second else 1
    messages_to_scan = messages[start_idx:]

    num_tokens = 0
    stack: "queue.LifoQueue[ModelMessage]" = queue.LifoQueue()
    for msg in reversed(messages_to_scan):
        num_tokens += estimate_tokens_for_message(msg)
        if num_tokens > protected_tokens:
            break
        stack.put(msg)

    while not stack.empty():
        result.append(stack.get())

    return prune_interrupted_tool_calls(result)


def summarize(
    messages: List[ModelMessage],
    protected_tokens: int,
    with_protection: bool = True,
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """Summarize older messages, preserving the protected recent tail.

    Returns ``(compacted_messages, summarized_source_messages)``. On failure
    we log a warning and return ``(messages, [])`` so the run continues.
    """
    if not messages:
        return [], []

    if with_protection:
        messages_to_summarize, protected_messages = split_for_protected_summarization(
            messages, protected_tokens
        )
    else:
        messages_to_summarize = messages[1:]
        protected_messages = messages[:1]

    system_message = messages[0]

    if not messages_to_summarize:
        return prune_interrupted_tool_calls(messages), []

    try:
        pruned = prune_interrupted_tool_calls(messages_to_summarize)
        if not pruned:
            return prune_interrupted_tool_calls(messages), []

        new_messages = run_summarization_sync(
            _SUMMARIZATION_INSTRUCTIONS, message_history=pruned
        )

        if not isinstance(new_messages, list):
            emit_warning(
                "Summarization agent returned non-list output; wrapping into message request"
            )
            new_messages = [ModelRequest([TextPart(str(new_messages))])]

        compacted: List[ModelMessage] = [system_message] + list(new_messages)
        compacted.extend(msg for msg in protected_messages if msg is not system_message)
        return prune_interrupted_tool_calls(compacted), messages_to_summarize
    except (SummarizationError, Exception) as e:
        error_type = type(e).__name__
        emit_error(f"Compaction failed: [{error_type}] {e}")
        if isinstance(e, SummarizationError) and e.original_error:
            emit_warning(
                f"💡 Tip: Underlying error was {type(e.original_error).__name__}. "
                "Consider using '/set compaction_strategy=truncation' as a fallback."
            )
        return messages, []


def compact(
    agent: Any,
    messages: List[ModelMessage],
    model_max: int,
    context_overhead: int,
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """Unified compaction entrypoint. Replaces ``message_history_processor``.

    Args:
        agent: The owning agent (only used to satisfy the no-delayed-compaction
            invariant — kept for future hook points).
        messages: Current message history (already accumulated by the caller).
        model_max: Effective model context window in tokens.
        context_overhead: Estimated overhead for system prompt + tool schemas.

    Returns:
        ``(new_messages, dropped_messages_for_hash_tracking)``.
    """
    del agent  # reserved for future hooks; no state needed right now

    message_tokens = sum(estimate_tokens_for_message(m) for m in messages)
    total_tokens = message_tokens + context_overhead
    proportion_used = total_tokens / model_max if model_max else 0.0

    context_summary = SpinnerBase.format_context_info(
        total_tokens, model_max, proportion_used
    )
    update_spinner_context(context_summary)

    threshold = get_compaction_threshold()
    if proportion_used <= threshold:
        return messages, []

    strategy = get_compaction_strategy()

    protected_tokens = get_protected_token_count()
    filtered = filter_huge_messages(messages)

    # filter_huge_messages() already runs prune_interrupted_tool_calls(),
    # so by this point any orphaned tool_call / tool_return pairs (from
    # cancelled runs, Ctrl-C interrupts, etc.) have been stripped out. The
    # check below only trips on a genuine mid-execution state, which
    # shouldn't happen when the history_processor is invoked — but we keep
    # it as a defensive safety net.
    #
    # Previously this check ran on the raw `messages` list, which meant a
    # single orphaned tool_call (e.g., from one cancelled command weeks ago)
    # would defer summarization forever, letting history grow unbounded.
    if strategy == "summarization" and has_pending_tool_calls(filtered):
        emit_warning(
            "⚠️  Summarization deferred: pending tool call(s) detected "
            "after pruning orphans. Will retry on next invocation.",
            message_group="token_context_status",
        )
        return messages, []

    if strategy == "truncation":
        result_messages = truncate(filtered, protected_tokens)
        result_hashes = {hash_message(m) for m in result_messages}
        summarized_messages = [
            m for m in filtered if hash_message(m) not in result_hashes
        ]
    else:
        result_messages, summarized_messages = summarize(filtered, protected_tokens)

    final_token_count = sum(estimate_tokens_for_message(m) for m in result_messages)
    final_summary = SpinnerBase.format_context_info(
        final_token_count,
        model_max,
        final_token_count / model_max if model_max else 0.0,
    )
    update_spinner_context(final_summary)

    return result_messages, summarized_messages


def _strip_empty_thinking_parts(
    messages: List[ModelMessage],
) -> Tuple[List[ModelMessage], int]:
    """Remove empty ThinkingParts; drop messages rendered empty by removal."""
    cleaned: List[ModelMessage] = []
    filtered_count = 0
    for msg in messages:
        parts = list(msg.parts)
        if (
            len(parts) == 1
            and isinstance(parts[0], ThinkingPart)
            and not parts[0].content
        ):
            filtered_count += 1
            continue
        if any(isinstance(p, ThinkingPart) and not p.content for p in parts):
            msg = dataclasses.replace(
                msg,
                parts=[
                    p
                    for p in parts
                    if not (isinstance(p, ThinkingPart) and not p.content)
                ],
            )
            if not msg.parts:
                filtered_count += 1
                continue
        cleaned.append(msg)
    return cleaned, filtered_count


def make_history_processor(agent: Any) -> Callable[..., List[ModelMessage]]:
    """Build the pydantic-ai ``history_processors`` callback for ``agent``.

    The returned closure:
      1. Fires ``on_message_history_processor_start``.
      2. Merges any incoming messages not already in ``agent._message_history``
         (preserving the last-message regardless of compacted-hash collisions).
      3. Runs ``compact(...)`` if we're over threshold.
      4. Records dropped-message hashes in ``agent._compacted_message_hashes``.
      5. Strips empty ThinkingParts.
      6. Trims trailing ModelResponse messages so history ends with a ModelRequest.
      7. Fires ``on_message_history_processor_end``.

    Agent contract (Phase 3 will enforce on ``BaseAgent``):
      - ``agent._message_history: list``
      - ``agent._compacted_message_hashes: set``
      - ``agent._get_model_context_length() -> int``
      - ``agent._estimate_context_overhead() -> int``
      - ``agent.name`` / ``agent.session_id`` (optional)
    """

    def history_processor(messages: List[ModelMessage]) -> List[ModelMessage]:
        # pydantic-ai picks 1-arg vs 2-arg processor by inspecting the first
        # parameter's type annotation (must be ``RunContext`` for 2-arg form).
        # We don't need ctx, so we use the 1-arg form.
        history: List[ModelMessage] = agent._message_history
        compacted_hashes: Set[int] = agent._compacted_message_hashes

        on_message_history_processor_start(
            agent_name=getattr(agent, "name", None),
            session_id=getattr(agent, "session_id", None),
            message_history=list(history),
            incoming_messages=list(messages),
        )

        existing_hashes = {hash_message(m) for m in history}
        messages_added = 0
        last_idx = len(messages) - 1
        for i, msg in enumerate(messages):
            h = hash_message(msg)
            if h in existing_hashes:
                continue
            # Always keep the last (newest) message, even if its hash collides
            # with a previously compacted one — short prompts like "yes"/"1"
            # can collide and get silently dropped otherwise.
            if i == last_idx or h not in compacted_hashes:
                history.append(msg)
                messages_added += 1

        new_history, dropped = compact(
            agent,
            history,
            agent._get_model_context_length(),
            agent._estimate_context_overhead(),
        )
        agent._message_history = new_history
        for m in dropped:
            compacted_hashes.add(hash_message(m))

        cleaned, filtered_count = _strip_empty_thinking_parts(agent._message_history)

        # Ensure history ends with a ModelRequest — otherwise Anthropic etc.
        # reject it with a "prefill" error.
        while cleaned and isinstance(cleaned[-1], ModelResponse):
            cleaned.pop()

        agent._message_history = cleaned

        on_message_history_processor_end(
            agent_name=getattr(agent, "name", None),
            session_id=getattr(agent, "session_id", None),
            message_history=list(cleaned),
            messages_added=messages_added,
            messages_filtered=len(messages) - messages_added + filtered_count,
        )

        return cleaned

    return history_processor
