"""Tests for code_puppy.agents._compaction (pydantic-ai-harness backed).

Covers:
- build_compaction_strategy() — config → FallbackCompaction wiring
- compact() — trigger math, force path, fallback + failure resilience,
  dropped-hash bookkeeping
- run_compaction_sync() — the sync bridge driving compact_now for /compact
- HistoryCompaction — the pydantic-ai capability, exercised through its real
  before_model_request seam plus a TestModel-backed Agent.run() dispatch test
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import patch

import pytest
from opentelemetry.trace import NoOpTracer
from pydantic_ai.exceptions import ModelHTTPError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from pydantic_ai_harness.compaction import (
    FallbackCompaction,
    SlidingWindowCompaction,
    SummarizingCompaction,
)

from code_puppy.agents import _compaction
from code_puppy.agents._compaction import (
    HistoryCompaction,
    build_compaction_strategy,
    compact,
    run_compaction_sync,
)

# ---------- Test fixtures & helpers ------------------------------------------


def _sys_msg(text: str = "system prompt") -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _user_msg(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


class _IdentityStrategy:
    async def compact(self, messages, ctx):
        return messages


def _tool_call(tool_name: str, args: dict, call_id: str) -> ModelMessage:
    return ModelResponse(
        parts=[ToolCallPart(tool_name=tool_name, args=args, tool_call_id=call_id)]
    )


def _tool_return(tool_name: str, content: str, call_id: str) -> ModelMessage:
    return ModelRequest(
        parts=[
            ToolReturnPart(
                tool_name=tool_name,
                content=content,
                tool_call_id=call_id,
            )
        ]
    )


def _build_long_history(
    n_turns: int = 20, payload_chars: int = 400
) -> List[ModelMessage]:
    """Build a realistic tool-heavy message history with paired calls/returns."""
    payload = "x" * payload_chars
    msgs: List[ModelMessage] = [_sys_msg("You are a helpful test agent.")]
    for i in range(n_turns):
        msgs.append(_user_msg(f"user question {i}: {payload}"))
        call_id = f"call_{i}"
        msgs.append(_tool_call("read_file", {"path": f"/tmp/file_{i}.txt"}, call_id))
        msgs.append(_tool_return("read_file", f"contents {i}: {payload}", call_id))
        msgs.append(_assistant_text(f"answer {i}"))
    return msgs


def _ctx(model: Any = None, usage: RunUsage | None = None) -> RunContext[Any]:
    """A minimal RunContext, mirroring the one compact_now fabricates."""
    return RunContext[Any](
        deps=None,
        model=model if model is not None else TestModel(),
        usage=usage if usage is not None else RunUsage(),
        tracer=NoOpTracer(),
    )


def _summary_model(marker: str = "SUMMARY") -> FunctionModel:
    def _fn(messages: List[ModelMessage], info: AgentInfo) -> ModelResponse:
        return ModelResponse(parts=[TextPart(content=marker)])

    return FunctionModel(_fn)


def _exploding_model() -> FunctionModel:
    def _fn(messages: List[ModelMessage], info: AgentInfo) -> ModelResponse:
        raise ModelHTTPError(
            status_code=500, model_name="exploding", body="summarizer exploded"
        )

    return FunctionModel(_fn)


def _orphan_tool_ids(messages: List[ModelMessage]) -> tuple[set, set]:
    calls = {
        p.tool_call_id
        for m in messages
        for p in m.parts
        if getattr(p, "part_kind", "") == "tool-call"
    }
    rets = {
        p.tool_call_id
        for m in messages
        for p in m.parts
        if getattr(p, "part_kind", "") == "tool-return"
    }
    return calls - rets, rets - calls


class _FakeAgent:
    """Minimal agent stub satisfying the HistoryCompaction agent contract."""

    def __init__(
        self,
        model_max: int = 10_000,
        overhead: int = 500,
        name: str = "fake-agent",
    ):
        self.name = name
        self._message_history: List[ModelMessage] = []
        self._compacted_message_hashes: set = set()
        self._model_max = model_max
        self._overhead = overhead
        self.session_id = None

    def _get_model_context_length(self) -> int:
        return self._model_max

    def _estimate_context_overhead(self) -> int:
        return self._overhead


# ---------- build_compaction_strategy() --------------------------------------


class TestBuildCompactionStrategy:
    def test_truncation_config_builds_sliding_only_chain(self):
        with patch.multiple(
            _compaction,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 1234,
            get_compaction_threshold=lambda: 0.85,
            get_model_context_length=lambda: 100_000,
        ):
            strategy = build_compaction_strategy()

        assert isinstance(strategy, FallbackCompaction)
        assert len(strategy.fallback_chain) == 1
        (sliding,) = strategy.fallback_chain
        assert isinstance(sliding, SlidingWindowCompaction)
        assert sliding.keep_tokens == 1234
        assert sliding.max_tokens == 85_000

    def test_summarization_config_builds_two_wave_chain(self):
        with patch.multiple(
            _compaction,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 2000,
            get_compaction_threshold=lambda: 0.5,
            get_model_context_length=lambda: 200_000,
            _summarizer_model=lambda: TestModel(),
        ):
            strategy = build_compaction_strategy()

        assert isinstance(strategy, FallbackCompaction)
        summarizer, sliding = strategy.fallback_chain
        assert isinstance(summarizer, SummarizingCompaction)
        assert isinstance(sliding, SlidingWindowCompaction)
        assert summarizer.keep_tokens == 2000
        assert sliding.keep_tokens == 2000
        assert summarizer.max_tokens == 100_000
        # pydantic-ai-harness#528: UsageLimitExceeded must trigger fallback so
        # truncation still saves runs past pydantic-ai's default request cap.
        assert UsageLimitExceeded in strategy.fallback_on

    def test_unavailable_summarizer_model_degrades_to_sliding_only(self):
        def _boom():
            raise RuntimeError("no such model")

        with patch.multiple(
            _compaction,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 2000,
            get_compaction_threshold=lambda: 0.5,
            get_model_context_length=lambda: 200_000,
            _summarizer_model=_boom,
        ):
            strategy = build_compaction_strategy()

        assert len(strategy.fallback_chain) == 1
        assert isinstance(strategy.fallback_chain[0], SlidingWindowCompaction)

    def test_explicit_protected_tokens_override(self):
        with patch.multiple(
            _compaction,
            get_compaction_strategy=lambda: "truncation",
            get_compaction_threshold=lambda: 0.85,
            get_model_context_length=lambda: 100_000,
        ):
            strategy = build_compaction_strategy(protected_tokens=777)
        assert strategy.fallback_chain[0].keep_tokens == 777


# ---------- compact() --------------------------------------------------------


class TestCompact:
    async def test_summarization_reports_protected_and_older_messages(self):
        msgs = [_user_msg("system"), _user_msg("old"), _user_msg("recent")]

        with (
            patch.multiple(
                _compaction,
                get_compaction_strategy=lambda: "summarization",
                get_protected_token_count=lambda: 2,
                estimate_tokens_for_message=lambda message, model_name: 1,
                build_compaction_strategy=lambda: _IdentityStrategy(),
            ),
            patch.object(_compaction, "emit_info") as emit_info,
        ):
            await compact(None, msgs, 100, 0, _ctx(), force=True)

        assert [call.args[0] for call in emit_info.call_args_list] == [
            "\U0001f512 Protecting 2 recent messages (2 tokens, limit: 2)",
            "\U0001f4dd Summarizing 1 older messages",
        ]

    async def test_truncation_reports_history_management(self):
        msgs = [_user_msg("old"), _user_msg("recent")]

        with (
            patch.multiple(
                _compaction,
                get_compaction_strategy=lambda: "truncation",
                build_compaction_strategy=lambda: _IdentityStrategy(),
            ),
            patch.object(_compaction, "emit_info") as emit_info,
        ):
            await compact(None, msgs, 100, 0, _ctx(), force=True)

        emit_info.assert_called_once_with(
            "Truncating message history to manage token usage"
        )

    async def test_under_threshold_is_noop(self):
        msgs = _build_long_history(n_turns=2)
        with (
            patch.object(_compaction, "get_compaction_threshold", return_value=0.95),
            patch.object(_compaction, "emit_info") as emit_info,
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=1_000_000,
                context_overhead=0,
                ctx=_ctx(),
            )
        assert new_msgs is msgs, "under threshold must return the input unchanged"
        assert dropped == []
        emit_info.assert_not_called()

    async def test_force_bypasses_threshold(self):
        msgs = _build_long_history(n_turns=20)
        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.95,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 1_000_000,
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=1_000_000,
                context_overhead=0,
                ctx=_ctx(),
                force=True,
            )

        assert len(new_msgs) < len(msgs)
        assert dropped

    async def test_over_threshold_truncation_strategy(self):
        msgs = _build_long_history(n_turns=20)
        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.1,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(),
            )
        assert len(new_msgs) < len(msgs)
        assert len(dropped) > 0
        # The opening user turn survives (SlidingWindowCompaction preserves it).
        assert new_msgs[0].parts[0].content == msgs[0].parts[0].content
        # No severed tool pairs.
        orphan_calls, orphan_returns = _orphan_tool_ids(new_msgs)
        assert not orphan_calls and not orphan_returns

    async def test_summarization_path_invokes_summarizer(self):
        """compact() routes to SummarizingCompaction; its output lands in
        history and dropped messages are recorded for hash tracking."""
        msgs = _build_long_history(n_turns=20)

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
            _summarizer_model=lambda: _summary_model("HARNESS_SUMMARY"),
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(),
            )

        assert len(new_msgs) < len(msgs)
        assert any(
            "HARNESS_SUMMARY" in str(getattr(p, "content", ""))
            for m in new_msgs
            for p in m.parts
        ), "summarizer output missing from result"
        assert len(dropped) > 0

    async def test_summarization_failure_falls_back_to_sliding_window(self):
        """If the summary model call fails with an API error, FallbackCompaction
        must advance to SlidingWindowCompaction rather than leaving history
        unbounded — the whole reason the chain exists."""
        msgs = _build_long_history(n_turns=20)

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
            _summarizer_model=_exploding_model,
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(),
            )

        assert len(new_msgs) < len(msgs), (
            "Sliding-window fallback should have shrunk the history"
        )
        assert len(dropped) > 0, "dropped messages must be recorded for hash tracking"
        orphan_calls, orphan_returns = _orphan_tool_ids(new_msgs)
        assert not orphan_calls and not orphan_returns

    async def test_summarization_succeeds_past_default_request_cap(self):
        """REGRESSION (harness#528): summarization must survive >50 parent
        requests via the detached ledger, and still bill the parent."""
        msgs = _build_long_history(n_turns=20)
        parent_usage = RunUsage(requests=60)

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
            _summarizer_model=lambda: _summary_model("HARNESS_SUMMARY"),
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(usage=parent_usage),
            )

        assert len(new_msgs) < len(msgs)
        assert any(
            "HARNESS_SUMMARY" in str(getattr(p, "content", ""))
            for m in new_msgs
            for p in m.parts
        ), "summary call must not be rejected by the parent's request count"
        assert parent_usage.requests == 61, (
            "the summary request must fold back into the parent's accounting"
        )
        assert len(dropped) > 0
        orphan_calls, orphan_returns = _orphan_tool_ids(new_msgs)
        assert not orphan_calls and not orphan_returns

    async def test_unexpected_strategy_error_returns_input_unchanged(self):
        """A non-API failure must never kill the run: compact() eats it and
        returns the original history for this cycle."""
        msgs = _build_long_history(n_turns=20)

        class _Broken:
            async def compact(self, messages, ctx):
                raise RuntimeError("programming error in strategy")

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
            build_compaction_strategy=lambda *a, **kw: _Broken(),
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(),
            )

        assert new_msgs is msgs
        assert dropped == []

    async def test_orphan_tool_calls_are_pruned_not_blocking(self):
        """REGRESSION: an orphaned tool_call from a cancelled run must neither
        block compaction nor leak into the compacted output."""
        msgs = _build_long_history(n_turns=20)
        orphan = _tool_call("read_file", {"path": "/cancelled.txt"}, "orphan_ctrl_c")
        msgs = [msgs[0], orphan] + msgs[1:]

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
        ):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=10_000,
                context_overhead=0,
                ctx=_ctx(),
            )

        assert len(new_msgs) < len(msgs)
        orphan_calls, orphan_returns = _orphan_tool_ids(new_msgs)
        assert not orphan_calls and not orphan_returns


# ---------- run_compaction_sync() --------------------------------------------


class TestRunCompactionSync:
    def test_runs_without_a_running_loop(self):
        msgs = _build_long_history(n_turns=10)
        out = run_compaction_sync(
            SlidingWindowCompaction(max_messages=1, keep_tokens=500),
            msgs,
            model=TestModel(),
        )
        assert len(out) < len(msgs)

    async def test_runs_from_inside_a_running_loop(self):
        """Command handlers may fire while the UI loop is live — the bridge
        must hop to a worker thread rather than deadlock."""
        msgs = _build_long_history(n_turns=10)
        out = run_compaction_sync(
            SlidingWindowCompaction(max_messages=1, keep_tokens=500),
            msgs,
            model=TestModel(),
        )
        assert len(out) < len(msgs)

    def test_input_list_is_not_mutated(self):
        msgs = _build_long_history(n_turns=10)
        snapshot = list(msgs)
        run_compaction_sync(
            SlidingWindowCompaction(max_messages=1, keep_tokens=500),
            msgs,
            model=TestModel(),
        )
        assert msgs == snapshot


# ---------- HistoryCompaction -------------------------------------------------


async def _fire(agent: Any, messages: List[ModelMessage]) -> List[ModelMessage]:
    """Drive the capability through its REAL seam — before_model_request —
    exactly as pydantic-ai's capability chain does, and hand back the
    (possibly replaced) outbound message list."""
    from types import SimpleNamespace

    request_context = SimpleNamespace(messages=messages)
    out = await HistoryCompaction(agent).before_model_request(_ctx(), request_context)
    return out.messages


class TestHistoryCompaction:
    def test_not_spec_serializable(self):
        """The capability holds a live agent reference — it must opt out of
        spec serialization like ProcessHistory does."""
        assert HistoryCompaction.get_serialization_name() is None

    async def test_before_model_request_replaces_outbound_messages(self):
        """Parity with ProcessHistory: the seam must REPLACE
        request_context.messages with the processed history, not append."""
        from types import SimpleNamespace

        agent = _FakeAgent(model_max=1_000_000)
        request_context = SimpleNamespace(messages=[_user_msg("hello")])
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            out = await HistoryCompaction(agent).before_model_request(
                _ctx(), request_context
            )
        assert out is request_context
        # Identity, not just equality: the processed durable history object
        # itself becomes the outbound list — replace, never append.
        assert out.messages is agent._message_history

    async def test_merges_new_messages_into_agent_history(self):
        agent = _FakeAgent(model_max=1_000_000)
        m1, m2, m3 = _user_msg("hello"), _assistant_text("hi there"), _user_msg("more")
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await _fire(agent, [m1, m2, m3])
        assert m1 in agent._message_history
        assert m2 in agent._message_history
        assert m3 in agent._message_history
        assert result == agent._message_history

    async def test_dedupes_by_hash(self):
        agent = _FakeAgent(model_max=1_000_000)
        m1 = _user_msg("hello")
        agent._message_history = [m1]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            await _fire(agent, [_user_msg("hello")])
        assert len(agent._message_history) == 1

    async def test_last_message_preserved_even_on_compacted_hash_collision(self):
        """A short prompt whose hash was recorded as compacted must still be
        appended when it is the newest incoming message."""
        agent = _FakeAgent(model_max=1_000_000)
        from code_puppy.agents._history import hash_message

        newest = _user_msg("yes")
        agent._compacted_message_hashes.add(hash_message(newest))
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            await _fire(agent, [_user_msg("yes")])
        assert len(agent._message_history) == 1

    async def test_repeated_user_prompt_is_not_dropped_as_duplicate(self):
        """A second "yes" answering a different question must survive.

        Hashes are timestamp-independent, so a repeated short prompt hashes
        identically to the earlier one. Treating that as a duplicate dropped
        the turn, and the trailing-ModelResponse pop then removed the previous
        assistant answer as well, so the model lost both sides of the exchange.
        """
        agent = _FakeAgent(model_max=1_000_000)
        agent._message_history = [_user_msg("yes"), _assistant_text("Deleting it now.")]
        incoming = [
            _user_msg("yes"),
            _assistant_text("Deleting it now."),
            _user_msg("yes"),
        ]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await HistoryCompaction(agent)._process(_ctx(), incoming)

        user_turns = [m for m in result if isinstance(m, ModelRequest)]
        assert len(user_turns) == 2, "the second 'yes' was dropped"
        assert any(isinstance(m, ModelResponse) for m in result), (
            "the earlier assistant answer was destroyed by the trailing pop"
        )

    async def test_resent_history_with_no_new_turn_still_dedupes(self):
        """Guard the other direction: an identical resend must not grow history."""
        agent = _FakeAgent(model_max=1_000_000)
        agent._message_history = [_user_msg("yes"), _assistant_text("done")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            await HistoryCompaction(agent)._process(
                _ctx(), [_user_msg("yes"), _assistant_text("done")]
            )
        assert len(agent._message_history) == 1  # trailing response popped

    async def test_strips_trailing_model_responses(self):
        agent = _FakeAgent(model_max=1_000_000)
        msgs = [_user_msg("q"), _assistant_text("a"), _assistant_text("trailing")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await _fire(agent, msgs)
        assert isinstance(result[-1], ModelRequest)

    async def test_strips_empty_thinking_parts(self):
        agent = _FakeAgent(model_max=1_000_000)
        empty_thinking = ModelResponse(parts=[ThinkingPart(content="")])
        msgs = [_user_msg("q"), empty_thinking, _user_msg("q2")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await _fire(agent, msgs)
        assert empty_thinking not in result

    async def test_triggers_compaction_over_threshold(self):
        agent = _FakeAgent(model_max=10_000, overhead=0)
        msgs = _build_long_history(n_turns=20)
        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.1,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
            get_model_context_length=lambda: 10_000,
        ):
            result = await _fire(agent, msgs)
        assert len(result) < len(msgs)
        assert agent._compacted_message_hashes, "dropped hashes must be recorded"

    async def test_noop_under_threshold(self):
        agent = _FakeAgent(model_max=1_000_000)
        # End on a user turn so the trailing-ModelResponse trim is a no-op.
        msgs = _build_long_history(n_turns=3) + [_user_msg("latest")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await _fire(agent, msgs)
        assert len(result) == len(msgs)
        assert not agent._compacted_message_hashes

    async def test_agent_run_dispatches_through_capability_chain(self):
        """End-to-end: a real pydantic-ai Agent wired with the capability must
        dispatch it on every model request — the user prompt lands in the
        owning agent's durable message history via the real chain, and the
        model receives exactly the processed history the capability built."""
        from pydantic_ai import Agent as PydanticAgent

        fake = _FakeAgent(model_max=1_000_000)
        seen: List[List[ModelMessage]] = []

        def _capture(messages: List[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append(list(messages))
            return ModelResponse(parts=[TextPart(content="ok")])

        pyd_agent = PydanticAgent(
            model=FunctionModel(_capture),
            output_type=str,
            capabilities=[HistoryCompaction(fake)],
        )
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await pyd_agent.run("hello capability")
        assert any(
            any(
                getattr(p, "content", None) == "hello capability"
                for p in getattr(m, "parts", [])
            )
            for m in fake._message_history
        ), "user prompt must be merged into the durable history via the chain"
        # The wire request carried the capability's processed durable history
        # — not the raw incoming list.
        assert seen and seen[0] == fake._message_history
        assert result.output == "ok"


# ---------- FallbackCompaction wiring sanity ---------------------------------


class TestFallbackChainIntegration:
    async def test_fallback_chain_end_to_end(self):
        """Exploding summarizer + healthy sliding window: the chain must land
        on the window and still respect pairing + first-message retention."""
        msgs = _build_long_history(n_turns=20)
        strategy = FallbackCompaction(
            fallback_chain=[
                SummarizingCompaction(
                    model=_exploding_model(), max_tokens=1, keep_tokens=500
                ),
                SlidingWindowCompaction(max_tokens=1, keep_tokens=500),
            ]
        )
        out = await strategy.compact(list(msgs), _ctx())
        assert len(out) < len(msgs)
        orphan_calls, orphan_returns = _orphan_tool_ids(out)
        assert not orphan_calls and not orphan_returns

    async def test_fallback_chain_reraises_when_all_fail(self):
        strategy = FallbackCompaction(
            fallback_chain=[
                SummarizingCompaction(
                    model=_exploding_model(), max_tokens=1, keep_tokens=500
                ),
            ]
        )
        with pytest.raises(ModelHTTPError):
            await strategy.compact(_build_long_history(n_turns=20), _ctx())
