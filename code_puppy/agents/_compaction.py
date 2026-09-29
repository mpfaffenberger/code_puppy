"""Message history compaction — delegated to pydantic-ai-harness.

Code Puppy used to carry ~600 lines of hand-rolled compaction: protected-split
safety, role-alternation repair for Anthropic, same-role merging, framing
requests, a dedicated summarization sub-agent with its own thread pool... All
of that now lives in ``pydantic_ai_harness.compaction``, whose strategies
preserve tool-call/tool-return pairing and provider ordering for us.

The capability itself (``HistoryCompaction``) is now *pure* and lives in
``code_puppy.capabilities.compaction``, staged for upstreaming: it takes
its state through the ``CompactionStore`` protocol, its policy through
injected callables, and reports exclusively through the ``compaction.*``
capability-event family (pydantic-ai #7794). The application-side
listeners live in ``code_puppy.events.bridge``.

What remains here is the Code Puppy-specific glue:

  * ``build_compaction_strategy`` — config → ``FallbackCompaction`` wiring
    (summarize first, slide the window when summarization fails);
  * ``CodePuppyCompactionStore`` — the store adapter over an agent;
  * ``build_history_compaction`` — dependency injection for the pure
    capability (config getters bound late so monkeypatching works);
  * the legacy ``compact()`` / ``HistoryCompaction(agent)`` shims.

Manual ``/compact`` and ``/truncate`` drive the same strategies through the
harness's ``compact_now`` (see ``run_compaction_sync``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, List, Optional, Set, Tuple

from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAPIError,
    UsageLimitExceeded,
)
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model
from pydantic_ai.tools import RunContext
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
from code_puppy.capabilities.compaction import (
    HistoryCompaction as PureHistoryCompaction,
)
from code_puppy.capabilities.compaction import (
    strip_empty_thinking_parts,
)
from code_puppy.config import (
    get_compaction_strategy,
    get_compaction_threshold,
    get_model_context_length,
    get_protected_token_count,
    get_summarization_model_name,
)
from code_puppy.messaging import emit_warning

# Kept importable at module level for the context-indicator plugin, which
# monkeypatches ``_compaction.update_spinner_context`` — the event bridge
# routes spinner updates through this name so the patch keeps working.
from code_puppy.messaging.spinner import (  # noqa: F401
    format_context_info,
    update_spinner_context,
)

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
# Capability wiring (Code Puppy → pure capability)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CodePuppyCompactionStore:
    """`CompactionStore` adapter over a Code Puppy agent.

    The only place the pure ``HistoryCompaction`` capability's state
    contract meets Code Puppy's agent attributes.
    """

    agent: Any

    def get_history(self) -> List[ModelMessage]:
        return self.agent._message_history

    def replace_history(self, messages: List[ModelMessage]) -> None:
        self.agent._message_history = messages

    def compacted_hashes(self) -> Set[str]:
        return self.agent._compacted_message_hashes

    def model_max_tokens(self) -> int:
        return self.agent._get_model_context_length()

    def context_overhead(self) -> int:
        return self.agent._estimate_context_overhead()

    def model_name(self) -> Optional[str]:
        if self.agent is None:
            return None
        try:
            return self.agent.get_model_name()
        except Exception:
            return None

    def identity(self) -> Tuple[Optional[str], Optional[str]]:
        return (
            getattr(self.agent, "name", None),
            getattr(self.agent, "session_id", None),
        )


def _take_forced_compaction_request() -> bool:
    from code_puppy.messaging.pause_controller import get_pause_controller

    return get_pause_controller().take_compaction_request()


def build_history_compaction(agent: Any) -> PureHistoryCompaction:
    """Build the pure ``HistoryCompaction`` capability wired to Code Puppy.

    All Code Puppy specifics are injected here; the capability itself has
    no knowledge of Code Puppy and reports through the ``compaction.*``
    capability-event family, which ``CapabilityEventBridge`` translates
    into legacy callbacks/spinner/messaging.

    Config getters are referenced late (through this module's globals) so
    tests and plugins that monkeypatch ``_compaction.get_compaction_*``
    keep working.
    """
    return PureHistoryCompaction(
        store=CodePuppyCompactionStore(agent),
        strategy_factory=lambda: build_compaction_strategy(),
        strategy_name=lambda: get_compaction_strategy(),
        compaction_threshold=lambda: get_compaction_threshold(),
        token_estimator=estimate_tokens_for_message,
        message_hasher=hash_message,
        history_sanitizer=sanitize_tool_call_ids,
        force_poll=_take_forced_compaction_request,
    )


def HistoryCompaction(agent: Any) -> PureHistoryCompaction:  # noqa: N802
    """Backwards-compatible constructor-shaped factory.

    Historical call sites (and tests) built ``HistoryCompaction(agent)``
    directly; the capability is now pure and dependency-injected, so this
    factory performs the Code Puppy wiring.
    """
    return build_history_compaction(agent)


# Preserve the historical class-level API surface on the factory shim.
HistoryCompaction.get_serialization_name = (  # type: ignore[attr-defined]
    PureHistoryCompaction.get_serialization_name
)


# ---------------------------------------------------------------------------
# Legacy direct-call compaction (tests + non-capability callers)
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
    """Measure + compact ``messages`` directly (legacy signature).

    Thin wrapper over the pure capability's ``measure_and_compact`` so
    there is exactly one compaction driver. Observation (spinner,
    pre-compact hooks, failure messaging) rides the ``compaction.*``
    events, which only dispatch when ``ctx`` belongs to a live run.
    """
    capability = build_history_compaction(agent)
    return await capability.measure_and_compact(
        ctx,
        messages,
        model_max=model_max,
        context_overhead=context_overhead,
        force=force,
    )


# Re-exported for backwards compatibility (tests import these from here).
_strip_empty_thinking_parts = strip_empty_thinking_parts
