"""Contract tests for the pure HistoryCompaction capability + its events.

Covers the #7794 decoupling contract:

* module purity (no ``code_puppy`` imports in the pure capability),
* typed event registration under the ``compaction`` namespace,
* emission ordering along the processing pipeline,
* inline ``BeforeCompactionEvent`` cancellation (fake and REAL dispatch),
* fail-open emission on synthetic contexts,
* capability_id stamping through pydantic-ai's real capability chain.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from pydantic_ai.capabilities import AbstractCapability, on_event
from pydantic_ai.messages import (
    CAPABILITY_EVENT_TYPES,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from code_puppy.capabilities.compaction import (
    BeforeCompactionEvent,
    CompactionCompletedEvent,
    CompactionFailedEvent,
    ContextUsageMeasuredEvent,
    HistoryCompaction,
    HistoryProcessingCompletedEvent,
    HistoryProcessingStartedEvent,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _user_msg(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


def _history(n: int) -> List[ModelMessage]:
    out: List[ModelMessage] = []
    for i in range(n):
        out.append(_user_msg(f"user turn {i} " + "x" * 200))
        out.append(_assistant(f"assistant turn {i} " + "y" * 200))
    return out


@dataclass
class _Store:
    """In-memory CompactionStore."""

    history: List[ModelMessage] = field(default_factory=list)
    hashes: set = field(default_factory=set)
    model_max: int = 1_000_000
    overhead: int = 0

    def get_history(self):
        return self.history

    def replace_history(self, messages):
        self.history = messages

    def compacted_hashes(self):
        return self.hashes

    def model_max_tokens(self):
        return self.model_max

    def context_overhead(self):
        return self.overhead

    def model_name(self):
        return "test-model"

    def identity(self):
        return ("test-agent", "session-1")


class _DropHalf:
    """Strategy that keeps the second half of the messages."""

    async def compact(self, messages, ctx):
        return list(messages[len(messages) // 2 :])


class _Explode:
    async def compact(self, messages, ctx):
        raise RuntimeError("boom")


class _EmitRecorder:
    """Fake RunContext capturing emitted events; optionally cancels."""

    def __init__(self, cancel_compaction: bool = False):
        self.events: List[Any] = []
        self.cancel_compaction = cancel_compaction

    async def emit_event(self, event):
        self.events.append(event)
        if self.cancel_compaction and isinstance(event, BeforeCompactionEvent):
            event.cancel("recorder said no")
        return event


def _capability(
    store: _Store,
    *,
    strategy: Any = None,
    threshold: float = 0.95,
    force: bool = False,
) -> HistoryCompaction:
    return HistoryCompaction(
        store=store,
        strategy_factory=lambda: strategy or _DropHalf(),
        strategy_name=lambda: "test-strategy",
        compaction_threshold=lambda: threshold,
        token_estimator=lambda m, model_name: 100,
        message_hasher=lambda m: repr(m),
        history_sanitizer=None,
        force_poll=(lambda: force) if force else None,
    )


async def _fire(capability: HistoryCompaction, ctx, messages):
    request_context = SimpleNamespace(messages=messages)
    out = await capability.before_model_request(ctx, request_context)
    return out.messages


# ---------------------------------------------------------------------------
# Purity + registration
# ---------------------------------------------------------------------------


def test_pure_module_has_no_code_puppy_imports():
    """The capability module must be extractable to pydantic-ai-harness
    verbatim: no imports from code_puppy outside its own package."""
    import inspect

    import code_puppy.capabilities.compaction as module

    source = inspect.getsource(module)
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import code_puppy", "from code_puppy")):
            pytest.fail(f"code_puppy import in pure capability module: {stripped!r}")


def test_event_kinds_registered_under_compaction_namespace():
    expected = {
        "compaction.history_processing_started": HistoryProcessingStartedEvent,
        "compaction.context_usage_measured": ContextUsageMeasuredEvent,
        "compaction.before_compaction": BeforeCompactionEvent,
        "compaction.compaction_completed": CompactionCompletedEvent,
        "compaction.compaction_failed": CompactionFailedEvent,
        "compaction.history_processing_completed": HistoryProcessingCompletedEvent,
    }
    for kind, cls in expected.items():
        assert CAPABILITY_EVENT_TYPES.get(kind) is cls
        assert cls(**_minimal_kwargs(cls)).kind == kind


def _minimal_kwargs(cls):
    required = {
        f.name: 0
        for f in dataclasses.fields(cls)
        if f.default is dataclasses.MISSING
        and f.default_factory is dataclasses.MISSING
        and f.name not in ("kind",)
    }
    for name in list(required):
        if name in ("strategy", "error_type", "error_message", "phase"):
            required[name] = "x"
    return required


def test_decision_events_dispatch_inline():
    assert BeforeCompactionEvent.event_dispatch == "inline"
    assert HistoryProcessingStartedEvent.event_dispatch == "inline"
    assert HistoryProcessingCompletedEvent.event_dispatch == "inline"
    # Observe-only events stay at stream position.
    assert ContextUsageMeasuredEvent.event_dispatch == "stream"
    assert CompactionCompletedEvent.event_dispatch == "stream"
    assert CompactionFailedEvent.event_dispatch == "stream"


# ---------------------------------------------------------------------------
# Emission ordering + payloads
# ---------------------------------------------------------------------------


class TestEmission:
    async def test_under_threshold_emits_lifecycle_and_measurement_only(self):
        store = _Store()
        ctx = _EmitRecorder()
        msgs = _history(2) + [_user_msg("latest")]
        await _fire(_capability(store, threshold=0.95), ctx, msgs)

        kinds = [type(e) for e in ctx.events]
        assert kinds == [
            HistoryProcessingStartedEvent,
            ContextUsageMeasuredEvent,
            HistoryProcessingCompletedEvent,
        ]
        usage = ctx.events[1]
        assert usage.phase == "pre"
        assert usage.model_max_tokens == store.model_max
        assert usage.total_tokens == 100 * len(msgs)

    async def test_over_threshold_emits_full_pipeline_in_order(self):
        store = _Store(model_max=1_000)
        ctx = _EmitRecorder()
        msgs = _history(10) + [_user_msg("latest")]
        await _fire(_capability(store, threshold=0.1), ctx, msgs)

        kinds = [type(e) for e in ctx.events]
        assert kinds == [
            HistoryProcessingStartedEvent,
            ContextUsageMeasuredEvent,  # pre
            BeforeCompactionEvent,
            ContextUsageMeasuredEvent,  # post
            CompactionCompletedEvent,
            HistoryProcessingCompletedEvent,
        ]
        before = ctx.events[2]
        assert before.strategy == "test-strategy"
        assert before.agent_name == "test-agent"
        assert not before.forced
        completed = ctx.events[4]
        assert completed.messages_after < completed.messages_before
        assert completed.dropped_count > 0
        assert ctx.events[3].phase == "post"

    async def test_forced_compaction_stamps_forced_flag(self):
        store = _Store()
        ctx = _EmitRecorder()
        msgs = _history(4)
        await _fire(_capability(store, threshold=0.95, force=True), ctx, msgs)
        before = [e for e in ctx.events if isinstance(e, BeforeCompactionEvent)]
        completed = [e for e in ctx.events if isinstance(e, CompactionCompletedEvent)]
        assert before and before[0].forced
        assert completed and completed[0].forced

    async def test_failure_emits_compaction_failed_and_keeps_messages(self):
        store = _Store(model_max=1_000)
        ctx = _EmitRecorder()
        msgs = _history(10)
        capability = _capability(store, strategy=_Explode(), threshold=0.1)
        result = await _fire(capability, ctx, msgs)

        failed = [e for e in ctx.events if isinstance(e, CompactionFailedEvent)]
        assert failed and failed[0].error_type == "RuntimeError"
        assert failed[0].error_message == "boom"
        assert not any(isinstance(e, CompactionCompletedEvent) for e in ctx.events)
        # All original messages survive (modulo trailing-response trim).
        assert len(result) >= len(msgs) - 1
        assert not store.hashes


# ---------------------------------------------------------------------------
# Inline cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    async def test_cancelled_before_compaction_skips_compaction(self):
        store = _Store(model_max=1_000)
        ctx = _EmitRecorder(cancel_compaction=True)
        msgs = _history(10)
        result = await _fire(_capability(store, threshold=0.1), ctx, msgs)

        assert not any(isinstance(e, CompactionCompletedEvent) for e in ctx.events)
        assert len(result) >= len(msgs) - 1
        assert not store.hashes
        before = [e for e in ctx.events if isinstance(e, BeforeCompactionEvent)][0]
        assert before.cancelled and before.cancel_reason == "recorder said no"


# ---------------------------------------------------------------------------
# Fail-open emission
# ---------------------------------------------------------------------------


class TestSafeEmit:
    async def test_synthetic_context_without_emit_event_does_not_break(self):
        """compact_now-style contexts have no event stream; compaction must
        proceed exactly as before, fail-open."""
        store = _Store(model_max=1_000)
        ctx = SimpleNamespace(usage=None)  # no emit_event at all
        msgs = _history(10)
        result = await _fire(_capability(store, threshold=0.1), ctx, msgs)
        assert len(result) < len(msgs)  # compaction still ran


# ---------------------------------------------------------------------------
# Real dispatch through pydantic-ai's capability chain
# ---------------------------------------------------------------------------


@dataclass
class _Listener(AbstractCapability[Any]):
    """Stand-in for the app-side bridge: records events, optionally cancels."""

    seen: List[Any] = field(default_factory=list)
    cancel: bool = False

    @on_event(
        HistoryProcessingStartedEvent,
        ContextUsageMeasuredEvent,
        BeforeCompactionEvent,
        CompactionCompletedEvent,
        CompactionFailedEvent,
        HistoryProcessingCompletedEvent,
    )
    async def _record(self, ctx, event):
        self.seen.append(event)
        if self.cancel and isinstance(event, BeforeCompactionEvent):
            event.cancel("listener veto")

    @classmethod
    def get_serialization_name(cls) -> Optional[str]:
        return None


def _run_agent(capabilities):
    from pydantic_ai import Agent as PydanticAgent

    def _model(messages: List[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content="ok")])

    async def _stream_model(messages: List[ModelMessage], info: AgentInfo):
        # Event dispatch rides the run's event stream, which needs a
        # streaming-capable model.
        yield "ok"

    return PydanticAgent(
        model=FunctionModel(_model, stream_function=_stream_model),
        output_type=str,
        capabilities=capabilities,
    )


class TestRealDispatch:
    async def test_inline_events_reach_listener_capability(self):
        store = _Store()
        store.history = _history(3)
        listener = _Listener()
        agent = _run_agent([_capability(store, threshold=0.95), listener])

        result = await agent.run("hello events")
        assert result.output == "ok"

        kinds = [type(e) for e in listener.seen]
        assert HistoryProcessingStartedEvent in kinds
        assert HistoryProcessingCompletedEvent in kinds
        assert ContextUsageMeasuredEvent in kinds
        # capability_id must be stamped by the emitting capability's run id.
        started = [
            e for e in listener.seen if isinstance(e, HistoryProcessingStartedEvent)
        ][0]
        assert started.capability_id

    async def test_listener_cancellation_through_real_chain(self):
        """A listener capability cancels BeforeCompaction inline; the emitter
        must observe the decision and skip compaction — through pydantic-ai's
        real dispatch, not a fake."""
        store = _Store(model_max=1_000)
        store.history = _history(20)
        n_before = len(store.history)
        listener = _Listener(cancel=True)
        agent = _run_agent([_capability(store, threshold=0.01), listener])

        await agent.run("please compact")

        before = [e for e in listener.seen if isinstance(e, BeforeCompactionEvent)]
        assert before and before[0].cancelled
        assert not any(isinstance(e, CompactionCompletedEvent) for e in listener.seen)
        # History gained the new prompt but was never compacted.
        assert len(store.history) >= n_before
        assert not store.hashes

    async def test_compaction_happens_without_veto_through_real_chain(self):
        store = _Store(model_max=1_000)
        store.history = _history(20)
        n_before = len(store.history)
        listener = _Listener()
        agent = _run_agent([_capability(store, threshold=0.01), listener])

        await agent.run("please compact")

        completed = [
            e for e in listener.seen if isinstance(e, CompactionCompletedEvent)
        ]
        assert completed and completed[0].dropped_count > 0
        assert len(store.history) < n_before
        assert store.hashes
