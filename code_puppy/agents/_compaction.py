"""Message history compaction — delegated to pydantic-ai-harness.

Code Puppy used to carry ~600 lines of hand-rolled compaction: protected-split
safety, role-alternation repair for Anthropic, same-role merging, framing
requests, a dedicated summarization sub-agent with its own thread pool... All
of that now lives in ``pydantic_ai_harness.compaction``, whose strategies
preserve tool-call/tool-return pairing and provider ordering for us.

What remains here is the Code Puppy-specific glue:

  * ``build_compaction_strategy`` — config → ``FallbackCompaction`` wiring
    (summarize first, slide the window when summarization fails);
  * the trigger check (``compaction_threshold * model context length``,
    both from ``config.py``), reusing the same token estimates that feed
    the spinner context badge;
  * ``make_history_processor`` — the closure owning the agent's message
    accumulator, dedup hashes, and post-compaction hygiene.

Manual ``/compact`` and ``/truncate`` drive the same strategies through the
harness's ``compact_now`` (see ``run_compaction_sync``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, List, Optional, Set, Tuple

from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAPIError,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart
from pydantic_ai.models import Model
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from pydantic_ai_harness.compaction import (
    FallbackCompaction,
    SlidingWindowCompaction,
    SummarizingCompaction,
    compact_now,
)

from code_puppy.agents._history import (
    estimate_tokens_for_message,
    hash_message,
    sanitize_tool_call_ids,
)
from code_puppy.callbacks import (
    on_message_history_processor_end,
    on_message_history_processor_start,
)
from code_puppy.config import (
    get_compaction_strategy,
    get_compaction_threshold,
    get_model_context_length,
    get_protected_token_count,
    get_summarization_model_name,
)
from code_puppy.messaging import emit_error, emit_success, emit_warning
from code_puppy.messaging.spinner import format_context_info, update_spinner_context

# ---------------------------------------------------------------------------
# Strategy construction
# ---------------------------------------------------------------------------


def _summarizer_model() -> Model:
    """Resolve the configured summarization model through the model factory.

    Honors the ``summarization_model`` config key (falling back to the global
    model), so custom endpoints in ``models.json`` / ``extra_models.json``
    keep working — a bare model-name string would only resolve through
    pydantic-ai's provider registry.
    """
    from code_puppy.model_factory import ModelFactory

    return ModelFactory.get_model(
        get_summarization_model_name(), ModelFactory.load_config()
    )


def build_compaction_strategy(
    protected_tokens: Optional[int] = None,
) -> FallbackCompaction:
    """Build the ``FallbackCompaction`` chain from Code Puppy config.

    First wave is ``SummarizingCompaction`` (skipped entirely when the
    configured strategy is ``truncation``); the fallback is a deterministic
    ``SlidingWindowCompaction``. Both keep ``protected_token_count`` tokens
    of recent tail and trigger at ``compaction_threshold * model context
    length`` — though the trigger is only load-bearing for constructor
    validation, since the chain is always driven directly (by
    :func:`compact` in-run, or ``compact_now`` for ``/compact``) where the
    harness does not consult it.

    The summarizer chain adds ``UsageLimitExceeded`` to ``fallback_on`` so
    truncation still saves the run (see pydantic-ai-harness#528).
    """
    protected = (
        get_protected_token_count() if protected_tokens is None else protected_tokens
    )
    threshold_tokens = int(get_compaction_threshold() * get_model_context_length())
    sliding = SlidingWindowCompaction(
        max_tokens=threshold_tokens, keep_tokens=protected
    )
    if get_compaction_strategy() == "truncation":
        return FallbackCompaction(fallback_chain=[sliding])

    try:
        summarizer = SummarizingCompaction(
            model=_summarizer_model(),
            max_tokens=threshold_tokens,
            keep_tokens=protected,
        )
    except Exception as e:
        emit_warning(
            f"Summarization model unavailable ({type(e).__name__}: {e}); "
            "compacting with the sliding-window fallback only."
        )
        return FallbackCompaction(fallback_chain=[sliding])
    return FallbackCompaction(
        fallback_chain=[summarizer, sliding],
        fallback_on=(ModelAPIError, FallbackExceptionGroup, UsageLimitExceeded),
    )


def resolve_agent_model(agent: Any) -> Model:
    """Return the agent's live pydantic-ai model, building one if needed.

    ``compact_now`` needs a real ``Model`` (or provider-resolvable string);
    Code Puppy model names only resolve through ``ModelFactory``, so a bare
    ``get_model_name()`` string won't do.
    """
    model = getattr(agent, "cur_model", None)
    if model is not None:
        return model
    from code_puppy.model_factory import ModelFactory

    return ModelFactory.get_model(agent.get_model_name(), ModelFactory.load_config())


def run_compaction_sync(strategy: Any, messages: List[ModelMessage], *, model: Model):
    """Drive ``compact_now`` from a sync command handler (no run active).

    Uses ``asyncio.run`` directly when no loop is running; otherwise hops to
    a one-shot worker thread so we never block or re-enter the UI loop.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def _run():
        return asyncio.run(compact_now(strategy, list(messages), model=model))

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(_run).result()


# ---------------------------------------------------------------------------
# In-run compaction
# ---------------------------------------------------------------------------


async def compact(
    agent: Any,
    messages: List[ModelMessage],
    model_max: int,
    context_overhead: int,
    ctx: RunContext[Any],
    *,
    force: bool = False,
) -> Tuple[List[ModelMessage], List[ModelMessage]]:
    """Unified in-run compaction entrypoint.

    Args:
        agent: The owning agent. Used to resolve the active model name so
            token estimates can apply per-model calibration multipliers.
        messages: Current message history (already accumulated by the caller).
        model_max: Effective model context window in tokens.
        context_overhead: Estimated overhead for system prompt + tool schemas.
        ctx: The live pydantic-ai ``RunContext`` — passing it through means
            the summarizer's usage folds into the run's accounting.
        force: Compact regardless of the configured context threshold. Used by
            mid-run ``/compact`` at the next safe model-call boundary.

    Returns:
        ``(new_messages, dropped_messages_for_hash_tracking)``. On any
        compaction failure the original messages come back untouched — the
        run must always survive a failed compaction.
    """
    model_name: Optional[str] = None
    if agent is not None:
        try:
            model_name = agent.get_model_name()
        except Exception:
            model_name = None

    message_tokens = sum(estimate_tokens_for_message(m, model_name) for m in messages)
    total_tokens = message_tokens + context_overhead
    proportion_used = total_tokens / model_max if model_max else 0.0

    update_spinner_context(
        format_context_info(total_tokens, model_max, proportion_used)
    )

    if not force and proportion_used <= get_compaction_threshold():
        return messages, []

    # Fire pre_compact hooks so Claude Code-style PreCompact hooks (and any
    # other plugins) can observe / log compactions. Result is advisory.
    try:
        from code_puppy.callbacks import on_pre_compact

        agent_name = getattr(agent, "name", "unknown") if agent else "unknown"
        await on_pre_compact(
            agent_name, get_compaction_strategy(), len(messages), total_tokens
        )
    except Exception:
        # Hooks must never break compaction.
        pass

    # Oversized-payload guarding is no longer done here: ToolOutputLimits
    # bounds tool returns at production time and ClampOversizedMessages
    # clamps runaway response parts at request time (see _output_limits.py),
    # both wired as pure capabilities in _builder.py.
    try:
        strategy = build_compaction_strategy()
        # pydantic-ai-harness#528: shared usage + default request_limit=50 kills
        # the summary past 50 parent requests. Detach the ledger, fold it back.
        summary_usage = RunUsage()
        strategy_ctx = dataclasses.replace(ctx, usage=summary_usage)
        try:
            result = await strategy.compact(list(messages), strategy_ctx)
        finally:
            ctx.usage.incr(summary_usage)
    except Exception as e:
        emit_error(f"Compaction failed: [{type(e).__name__}] {e}")
        return messages, []

    result_hashes = {hash_message(m) for m in result}
    dropped = [m for m in messages if hash_message(m) not in result_hashes]

    final_token_count = sum(estimate_tokens_for_message(m, model_name) for m in result)
    update_spinner_context(
        format_context_info(
            final_token_count,
            model_max,
            final_token_count / model_max if model_max else 0.0,
        )
    )
    return result, dropped


# ---------------------------------------------------------------------------
# History-processor closure
# ---------------------------------------------------------------------------


def _strip_empty_thinking_parts(
    messages: List[ModelMessage],
) -> Tuple[List[ModelMessage], int]:
    """Remove empty ThinkingParts without discarding replay signatures."""
    cleaned: List[ModelMessage] = []
    filtered_count = 0
    for msg in messages:
        parts = list(msg.parts)
        if (
            len(parts) == 1
            and isinstance(parts[0], ThinkingPart)
            and not parts[0].content
            and not parts[0].signature
        ):
            filtered_count += 1
            continue
        if any(
            isinstance(p, ThinkingPart) and not p.content and not p.signature
            for p in parts
        ):
            msg = dataclasses.replace(
                msg,
                parts=[
                    p
                    for p in parts
                    if not (
                        isinstance(p, ThinkingPart)
                        and not p.content
                        and not p.signature
                    )
                ],
            )
            if not msg.parts:
                filtered_count += 1
                continue
        cleaned.append(msg)
    return cleaned, filtered_count


def make_history_processor(agent: Any) -> Callable[..., Any]:
    """Build the pydantic-ai history-processor callback for ``agent``.

    The returned async closure:
      1. Fires ``on_message_history_processor_start``.
      2. Merges any incoming messages not already in ``agent._message_history``
         (preserving the last-message regardless of compacted-hash collisions).
      3. Runs ``compact(...)`` if we're over threshold (or ``/compact`` forced).
      4. Records dropped-message hashes in ``agent._compacted_message_hashes``.
      5. Strips empty ThinkingParts that carry no replay signature.
      6. Trims trailing ModelResponse messages so history ends with a ModelRequest.
      7. Fires ``on_message_history_processor_end``.

    Agent contract:
      - ``agent._message_history: list``
      - ``agent._compacted_message_hashes: set``
      - ``agent._get_model_context_length() -> int``
      - ``agent._estimate_context_overhead() -> int``
      - ``agent.name`` / ``agent.session_id`` (optional)
    """

    async def history_processor(
        ctx: RunContext[Any], messages: List[ModelMessage]
    ) -> List[ModelMessage]:
        # The RunContext-annotated first parameter opts us into pydantic-ai's
        # 2-arg processor calling convention; the live ctx is handed straight
        # to the harness strategies so summary-call usage lands on the run.
        history: List[ModelMessage] = agent._message_history
        compacted_hashes: Set[str] = agent._compacted_message_hashes

        on_message_history_processor_start(
            agent_name=getattr(agent, "name", None),
            session_id=getattr(agent, "session_id", None),
            message_history=list(history),
            incoming_messages=list(messages),
        )

        existing_hashes = {hash_message(m) for m in history}
        messages_added = 0
        last_idx = len(messages) - 1
        # pydantic-ai hands us the history it knows about plus this turn's new
        # prompt, so being handed more messages than we hold means the last one
        # is genuinely new. Its hash can still collide: hashes are
        # timestamp-independent, so a repeated short prompt like "yes" or "1"
        # hashes identically to the earlier one. Treating that as a duplicate
        # drops the turn, and the trailing-ModelResponse pop below then removes
        # the preceding assistant answer too.
        has_new_turn = len(messages) > len(history)
        for i, msg in enumerate(messages):
            h = hash_message(msg)
            is_new_turn = i == last_idx and has_new_turn
            if h in existing_hashes and not is_new_turn:
                continue
            # Always keep the newest message even on hash collision — short
            # prompts like "yes"/"1" can collide and get silently dropped.
            if is_new_turn or h not in compacted_hashes:
                history.append(msg)
                messages_added += 1

        from code_puppy.messaging.pause_controller import get_pause_controller

        force_compaction = get_pause_controller().take_compaction_request()
        new_history, dropped = await compact(
            agent,
            history,
            agent._get_model_context_length(),
            agent._estimate_context_overhead(),
            ctx,
            force=force_compaction,
        )
        if force_compaction:
            detail = "" if dropped else " History was already minimal."
            emit_success(f"Mid-run compaction complete.{detail}")
        agent._message_history = new_history
        for m in dropped:
            compacted_hashes.add(hash_message(m))

        cleaned, filtered_count = _strip_empty_thinking_parts(agent._message_history)

        # Ensure history ends with a ModelRequest — otherwise Anthropic etc.
        # reject it with a "prefill" error.
        while cleaned and isinstance(cleaned[-1], ModelResponse):
            cleaned.pop()

        # Sanitize tool_call_ids that don't match Anthropic's pattern: stale IDs
        # from Kimi-style providers (dots/colons) cause a 400 after switching to
        # Claude. Cheap no-op when all IDs already conform.
        cleaned = sanitize_tool_call_ids(cleaned)

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
