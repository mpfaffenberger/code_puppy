"""Tests for code_puppy.agents._compaction (pydantic-ai-harness backed).

Covers:
- build_compaction_strategy() — config → FallbackCompaction wiring
- compact() — trigger math, force path, fallback + failure resilience,
  dropped-hash bookkeeping
- run_compaction_sync() — the sync bridge driving compact_now for /compact
- make_history_processor() — the pydantic-ai processor closure, including
  the ctx-taking calling-convention regression test
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
    build_compaction_strategy,
    compact,
    make_history_processor,
    run_compaction_sync,
)

# ---------- Test fixtures & helpers ------------------------------------------


def _sys_msg(text: str = "system prompt") -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _user_msg(text: str) -> ModelMessage:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str) -> ModelMessage:
    return ModelResponse(parts=[TextPart(content=text)])


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
    """Minimal agent stub satisfying the make_history_processor contract."""

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
    async def test_under_threshold_is_noop(self):
        msgs = _build_long_history(n_turns=2)
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            new_msgs, dropped = await compact(
                agent=None,
                messages=msgs,
                model_max=1_000_000,
                context_overhead=0,
                ctx=_ctx(),
            )
        assert new_msgs is msgs, "under threshold must return the input unchanged"
        assert dropped == []

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


# ---------- make_history_processor() -----------------------------------------


class TestMakeHistoryProcessor:
    def test_closure_takes_run_context(self):
        """REGRESSION: pydantic-ai picks the 2-arg calling convention off the
        first parameter's RunContext annotation. The closure must opt in so
        the live ctx reaches the harness strategies."""
        from pydantic_ai._utils import takes_run_context

        processor = make_history_processor(_FakeAgent())
        assert takes_run_context(processor)

    async def test_merges_new_messages_into_agent_history(self):
        agent = _FakeAgent(model_max=1_000_000)
        m1, m2, m3 = _user_msg("hello"), _assistant_text("hi there"), _user_msg("more")
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await make_history_processor(agent)(_ctx(), [m1, m2, m3])
        assert m1 in agent._message_history
        assert m2 in agent._message_history
        assert m3 in agent._message_history
        assert result == agent._message_history

    async def test_dedupes_by_hash(self):
        agent = _FakeAgent(model_max=1_000_000)
        m1 = _user_msg("hello")
        agent._message_history = [m1]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            await make_history_processor(agent)(_ctx(), [_user_msg("hello")])
        assert len(agent._message_history) == 1

    async def test_last_message_preserved_even_on_compacted_hash_collision(self):
        """A short prompt whose hash was recorded as compacted must still be
        appended when it is the newest incoming message."""
        agent = _FakeAgent(model_max=1_000_000)
        from code_puppy.agents._history import hash_message

        newest = _user_msg("yes")
        agent._compacted_message_hashes.add(hash_message(newest))
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            await make_history_processor(agent)(_ctx(), [_user_msg("yes")])
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
            result = await make_history_processor(agent)(_ctx(), incoming)

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
            await make_history_processor(agent)(
                _ctx(), [_user_msg("yes"), _assistant_text("done")]
            )
        assert len(agent._message_history) == 1  # trailing response popped

    async def test_strips_trailing_model_responses(self):
        agent = _FakeAgent(model_max=1_000_000)
        msgs = [_user_msg("q"), _assistant_text("a"), _assistant_text("trailing")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await make_history_processor(agent)(_ctx(), msgs)
        assert isinstance(result[-1], ModelRequest)

    async def test_strips_empty_thinking_parts(self):
        agent = _FakeAgent(model_max=1_000_000)
        empty_thinking = ModelResponse(parts=[ThinkingPart(content="")])
        msgs = [_user_msg("q"), empty_thinking, _user_msg("q2")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await make_history_processor(agent)(_ctx(), msgs)
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
            result = await make_history_processor(agent)(_ctx(), msgs)
        assert len(result) < len(msgs)
        assert agent._compacted_message_hashes, "dropped hashes must be recorded"

    async def test_noop_under_threshold(self):
        agent = _FakeAgent(model_max=1_000_000)
        # End on a user turn so the trailing-ModelResponse trim is a no-op.
        msgs = _build_long_history(n_turns=3) + [_user_msg("latest")]
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = await make_history_processor(agent)(_ctx(), msgs)
        assert len(result) == len(msgs)
        assert not agent._compacted_message_hashes


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
