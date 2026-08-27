"""History accumulation + compaction as a pure pydantic-ai capability.

Upstreaming staging: this module must not import anything from
``code_puppy``. Application specifics arrive through the
:class:`CompactionStore` protocol and constructor callables; application
side effects leave exclusively through the ``compaction.*`` capability
event family below (pydantic-ai #7794). The Code Puppy glue lives in
``code_puppy.agents._compaction`` and the app-side listeners in
``code_puppy.events.bridge``.

Event design follows the audit rules: events carry domain truth that
generic framework events cannot reconstruct (the actual context-usage
measurement the trigger used, the compaction decision, the committed
outcome), and decision/boundary events dispatch inline so listeners run
before the operation proceeds.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Protocol, Set, Tuple

from pydantic_ai import CapabilityEvent
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.messages import ModelMessage, ModelResponse, ThinkingPart
from pydantic_ai.models import ModelRequestContext
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage

COMPACTION_NAMESPACE = "compaction"

# ---------------------------------------------------------------------------
# Typed capability events (namespace: ``compaction``)
# ---------------------------------------------------------------------------


@dataclass(kw_only=True)
class HistoryProcessingStartedEvent(
    CapabilityEvent, namespace=COMPACTION_NAMESPACE, dispatch="inline"
):
    """History processing is about to begin for a model request.

    Inline: this marks a mutation boundary — listeners that want a
    consistent pre-merge view of the durable history must run before the
    capability starts mutating it.
    """

    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    history_count: int = 0
    """Messages in the durable history before merging."""
    incoming_count: int = 0
    """Messages arriving with this model request."""


@dataclass(kw_only=True)
class ContextUsageMeasuredEvent(CapabilityEvent, namespace=COMPACTION_NAMESPACE):
    """The context-usage measurement the compaction trigger actually used.

    Domain truth unavailable from generic events: token estimates are
    application-calibrated and include schema/system-prompt overhead.
    """

    total_tokens: int
    model_max_tokens: int
    proportion_used: float
    phase: str = "pre"
    """``'pre'`` (before a potential compaction) or ``'post'`` (after)."""


@dataclass(kw_only=True)
class BeforeCompactionEvent(
    CapabilityEvent, namespace=COMPACTION_NAMESPACE, dispatch="inline"
):
    """Compaction is about to run. Inline decision event: listeners may
    :meth:`cancel` before history is mutated."""

    strategy: str
    message_count: int
    total_tokens: int
    agent_name: Optional[str] = None
    forced: bool = False
    """True when a mid-run ``/compact`` requested this compaction."""
    cancelled: bool = False
    cancel_reason: Optional[str] = None

    def cancel(self, reason: Optional[str] = None) -> None:
        """Cancel the pending compaction; history is left untouched."""
        self.cancelled = True
        self.cancel_reason = reason


@dataclass(kw_only=True)
class CompactionCompletedEvent(CapabilityEvent, namespace=COMPACTION_NAMESPACE):
    """A compaction committed to the durable history."""

    messages_before: int
    messages_after: int
    total_tokens_before: int
    total_tokens_after: int
    dropped_count: int
    forced: bool = False


@dataclass(kw_only=True)
class CompactionFailedEvent(CapabilityEvent, namespace=COMPACTION_NAMESPACE):
    """Compaction raised; the run continues with the uncompacted history."""

    error_type: str
    error_message: str


@dataclass(kw_only=True)
class HistoryProcessingCompletedEvent(
    CapabilityEvent, namespace=COMPACTION_NAMESPACE, dispatch="inline"
):
    """History processing finished; the outbound history is committed.

    Inline for the same boundary reason as
    :class:`HistoryProcessingStartedEvent`: listeners observe the
    committed state before the model request proceeds.
    """

    agent_name: Optional[str] = None
    session_id: Optional[str] = None
    history_count: int = 0
    messages_added: int = 0
    messages_filtered: int = 0


# ---------------------------------------------------------------------------
# Application state protocol
# ---------------------------------------------------------------------------


class CompactionStore(Protocol):
    """Durable conversation state owned by the application.

    ``get_history`` returns the *live* list — the capability merges new
    messages into it in place, then commits the processed result with
    ``replace_history``. ``compacted_hashes`` is likewise the live set
    used to suppress re-accumulation of compacted-away messages.
    """

    def get_history(self) -> List[ModelMessage]: ...

    def replace_history(self, messages: List[ModelMessage]) -> None: ...

    def compacted_hashes(self) -> Set[str]: ...

    def model_max_tokens(self) -> int: ...

    def context_overhead(self) -> int: ...

    def model_name(self) -> Optional[str]: ...

    def identity(self) -> Tuple[Optional[str], Optional[str]]:
        """``(agent_name, session_id)`` for event attribution."""
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def strip_empty_thinking_parts(
    messages: List[ModelMessage],
) -> Tuple[List[ModelMessage], int]:
    """Remove empty ThinkingParts without discarding replay signatures."""

    def _strippable(p: Any) -> bool:
        return isinstance(p, ThinkingPart) and not p.content and not p.signature

    cleaned: List[ModelMessage] = []
    filtered_count = 0
    for msg in messages:
        parts = list(msg.parts)
        if len(parts) == 1 and _strippable(parts[0]):
            filtered_count += 1
            continue
        if any(_strippable(p) for p in parts):
            msg = dataclasses.replace(
                msg,
                parts=[p for p in parts if not _strippable(p)],
            )
            if not msg.parts:
                filtered_count += 1
                continue
        cleaned.append(msg)
    return cleaned, filtered_count


async def _safe_emit(ctx: RunContext[Any], event: Any) -> Any:
    """Emit an event, tolerating synthetic contexts with no event stream.

    Compaction must never die because observation plumbing is absent
    (tests drive hooks with bare contexts; ``compact_now`` runs outside a
    live run). Decision events therefore *fail open*: when emission is
    impossible the operation proceeds as if no listener objected.
    """
    try:
        return await ctx.emit_event(event)
    except Exception:
        return event


# ---------------------------------------------------------------------------
# The capability
# ---------------------------------------------------------------------------


@dataclass
class HistoryCompaction(AbstractCapability[Any]):
    """First-class capability owning in-run history accumulation + compaction.

    Overrides ``before_model_request`` — the exact seam the generic
    ``ProcessHistory`` capability uses internally — so registration order
    against neighbouring capabilities (steer injection, response clamp)
    is preserved. On every model request it:

      1. Emits :class:`HistoryProcessingStartedEvent` (inline).
      2. Merges incoming messages not already in the durable history
         (always keeping the newest message despite hash collisions).
      3. Measures context usage and emits :class:`ContextUsageMeasuredEvent`.
      4. Over threshold (or forced): emits :class:`BeforeCompactionEvent`
         (inline, cancellable) then runs the injected strategy; emits
         :class:`CompactionCompletedEvent` / :class:`CompactionFailedEvent`.
      5. Records dropped-message hashes for dedup.
      6. Strips empty ThinkingParts; trims trailing ModelResponses;
         applies the injected sanitizer.
      7. Commits via ``store.replace_history`` and emits
         :class:`HistoryProcessingCompletedEvent` (inline).

    All application knowledge is injected; this class has no imports
    from, and no knowledge of, any host application.
    """

    store: CompactionStore
    """Durable history + accounting owned by the application."""

    strategy_factory: Callable[[], Any]
    """Builds the compaction strategy (e.g. a harness ``FallbackCompaction``)."""

    strategy_name: Callable[[], str]
    """Human-readable name of the configured strategy, for events."""

    compaction_threshold: Callable[[], float]
    """Proportion of the context window that triggers compaction."""

    token_estimator: Callable[[ModelMessage, Optional[str]], int]
    """Estimates tokens for one message, given the active model name."""

    message_hasher: Callable[[ModelMessage], str]
    """Stable content hash used for merge dedup + dropped tracking."""

    history_sanitizer: Optional[Callable[[List[ModelMessage]], List[ModelMessage]]] = (
        None
    )
    """Optional final-pass sanitizer (e.g. tool_call_id normalization)."""

    force_poll: Optional[Callable[[], bool]] = None
    """Polled once per request; True forces compaction (mid-run ``/compact``).

    The callable owns one-shot semantics (take-and-clear), not this class.
    """

    async def before_model_request(
        self,
        ctx: RunContext[Any],
        request_context: ModelRequestContext,
    ) -> ModelRequestContext:
        """Replace the outbound messages with the compacted durable history."""
        request_context.messages = await self._process(ctx, request_context.messages)
        return request_context

    async def _process(
        self, ctx: RunContext[Any], messages: List[ModelMessage]
    ) -> List[ModelMessage]:
        store = self.store
        agent_name, session_id = store.identity()
        history = store.get_history()
        compacted_hashes = store.compacted_hashes()

        await _safe_emit(
            ctx,
            HistoryProcessingStartedEvent(
                agent_name=agent_name,
                session_id=session_id,
                history_count=len(history),
                incoming_count=len(messages),
            ),
        )

        existing_hashes = {self.message_hasher(m) for m in history}
        messages_added = 0
        last_idx = len(messages) - 1
        for i, msg in enumerate(messages):
            h = self.message_hasher(msg)
            if h in existing_hashes:
                continue
            # Always keep the newest message even on hash collision — short
            # prompts like "yes"/"1" can collide and get silently dropped.
            if i == last_idx or h not in compacted_hashes:
                history.append(msg)
                messages_added += 1

        force = bool(self.force_poll()) if self.force_poll is not None else False
        new_history, dropped = await self.measure_and_compact(
            ctx,
            history,
            model_max=store.model_max_tokens(),
            context_overhead=store.context_overhead(),
            force=force,
        )
        for m in dropped:
            compacted_hashes.add(self.message_hasher(m))

        cleaned, filtered_count = strip_empty_thinking_parts(new_history)

        # Ensure history ends with a ModelRequest — otherwise Anthropic etc.
        # reject it with a "prefill" error.
        while cleaned and isinstance(cleaned[-1], ModelResponse):
            cleaned.pop()

        if self.history_sanitizer is not None:
            cleaned = self.history_sanitizer(cleaned)

        store.replace_history(cleaned)

        await _safe_emit(
            ctx,
            HistoryProcessingCompletedEvent(
                agent_name=agent_name,
                session_id=session_id,
                history_count=len(cleaned),
                messages_added=messages_added,
                messages_filtered=len(messages) - messages_added + filtered_count,
            ),
        )
        return cleaned

    async def measure_and_compact(
        self,
        ctx: RunContext[Any],
        messages: List[ModelMessage],
        *,
        model_max: int,
        context_overhead: int,
        force: bool = False,
    ) -> Tuple[List[ModelMessage], List[ModelMessage]]:
        """Measure context usage and compact when over threshold (or forced).

        Returns ``(new_messages, dropped_messages)``. On any compaction
        failure the original messages come back untouched — the run must
        always survive a failed compaction.
        """
        model_name = self.store.model_name()
        message_tokens = sum(self.token_estimator(m, model_name) for m in messages)
        total_tokens = message_tokens + context_overhead
        proportion_used = total_tokens / model_max if model_max else 0.0

        await _safe_emit(
            ctx,
            ContextUsageMeasuredEvent(
                total_tokens=total_tokens,
                model_max_tokens=model_max,
                proportion_used=proportion_used,
                phase="pre",
            ),
        )

        if not force and proportion_used <= self.compaction_threshold():
            return messages, []

        decision = await _safe_emit(
            ctx,
            BeforeCompactionEvent(
                strategy=self.strategy_name(),
                message_count=len(messages),
                total_tokens=total_tokens,
                agent_name=self.store.identity()[0],
                forced=force,
            ),
        )
        if decision.cancelled:
            return messages, []

        try:
            strategy = self.strategy_factory()
            # pydantic-ai-harness#528: shared usage + default request_limit=50
            # kills the summary past 50 parent requests. Detach the ledger,
            # fold it back. Synthetic contexts that aren't dataclasses (or
            # carry no usage) run the strategy against the original ctx.
            run_usage = getattr(ctx, "usage", None)
            if run_usage is not None and dataclasses.is_dataclass(ctx):
                summary_usage = RunUsage()
                strategy_ctx = dataclasses.replace(ctx, usage=summary_usage)
                try:
                    result = await strategy.compact(list(messages), strategy_ctx)
                finally:
                    run_usage.incr(summary_usage)
            else:
                result = await strategy.compact(list(messages), ctx)
        except Exception as e:
            await _safe_emit(
                ctx,
                CompactionFailedEvent(
                    error_type=type(e).__name__, error_message=str(e)
                ),
            )
            return messages, []

        result_hashes = {self.message_hasher(m) for m in result}
        dropped = [m for m in messages if self.message_hasher(m) not in result_hashes]

        # Parity with the historical implementation: the post-compaction
        # measurement reports message tokens only (no overhead term).
        final_token_count = sum(self.token_estimator(m, model_name) for m in result)
        await _safe_emit(
            ctx,
            ContextUsageMeasuredEvent(
                total_tokens=final_token_count,
                model_max_tokens=model_max,
                proportion_used=final_token_count / model_max if model_max else 0.0,
                phase="post",
            ),
        )
        await _safe_emit(
            ctx,
            CompactionCompletedEvent(
                messages_before=len(messages),
                messages_after=len(result),
                total_tokens_before=total_tokens,
                total_tokens_after=final_token_count,
                dropped_count=len(dropped),
                forced=force,
            ),
        )
        return result, dropped

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        """Not spec-serializable: holds live application state and callables."""
        return None
