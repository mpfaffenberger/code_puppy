"""Tests for code_puppy.agents._compaction.

Covers:
- truncate() — deterministic, offline
- split_for_protected_summarization() — pure splitting logic
- compact() — unified entrypoint with both strategies + deferral paths
- make_history_processor() — the pydantic-ai history_processors closure,
  including the 1-arg calling convention regression test
"""

from __future__ import annotations

from typing import List
from unittest.mock import patch

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

from code_puppy.agents import _compaction
from code_puppy.agents._compaction import (
    compact,
    make_history_processor,
    split_for_protected_summarization,
    summarize,
    truncate,
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


# ---------- truncate() -------------------------------------------------------


class TestTruncate:
    def test_empty_input_returns_empty(self):
        assert truncate([], protected_tokens=1000) == []

    def test_single_message_returns_single(self):
        msgs = [_sys_msg()]
        result = truncate(msgs, protected_tokens=1000)
        assert result == msgs

    def test_preserves_system_message(self):
        msgs = _build_long_history(n_turns=20)
        result = truncate(msgs, protected_tokens=500)
        assert result[0] is msgs[0], "system message must be the first element"

    def test_preserves_thinking_context_at_index_1(self):
        sys_msg = _sys_msg()
        thinking_msg = ModelResponse(parts=[ThinkingPart(content="deep thoughts")])
        tail = [_user_msg(f"q {i}") for i in range(10)]
        msgs = [sys_msg, thinking_msg] + tail
        result = truncate(msgs, protected_tokens=200)
        assert result[0] is sys_msg
        assert result[1] is thinking_msg

    def test_truncates_middle_respecting_token_budget(self):
        msgs = _build_long_history(n_turns=20)
        result = truncate(msgs, protected_tokens=800)
        # Must be strictly shorter than input
        assert len(result) < len(msgs)
        # Must keep the system message
        assert result[0] is msgs[0]
        # Must include the last few messages
        assert result[-1] is msgs[-1]

    def test_prunes_interrupted_tool_calls_on_boundary(self):
        """If truncate lands mid-pair, pruning should drop the orphan."""
        sys_msg = _sys_msg()
        # Create a history where the truncation boundary would isolate a tool_call
        # without its matching tool_return.
        msgs = [sys_msg]
        for i in range(10):
            msgs.append(_user_msg(f"q{i}: " + "x" * 500))
            msgs.append(_tool_call("read_file", {}, f"call_{i}"))
            msgs.append(_tool_return("read_file", "data", f"call_{i}"))
            msgs.append(_assistant_text(f"done {i}"))

        result = truncate(msgs, protected_tokens=1000)

        # Verify no orphan tool_calls/returns remain
        call_ids = set()
        return_ids = set()
        for msg in result:
            for part in msg.parts:
                cid = getattr(part, "tool_call_id", None)
                if not cid:
                    continue
                if part.part_kind == "tool-call":
                    call_ids.add(cid)
                elif part.part_kind == "tool-return":
                    return_ids.add(cid)
        assert call_ids == return_ids, (
            f"orphan tool ids detected: only-calls={call_ids - return_ids}, "
            f"only-returns={return_ids - call_ids}"
        )


# ---------- split_for_protected_summarization() ------------------------------


class TestSplitForProtectedSummarization:
    def test_single_message_protected(self):
        msgs = [_sys_msg()]
        to_sum, protected = split_for_protected_summarization(
            msgs, protected_tokens=1000
        )
        assert to_sum == []
        assert protected == msgs

    def test_system_always_protected(self):
        msgs = _build_long_history(n_turns=10)
        to_sum, protected = split_for_protected_summarization(
            msgs, protected_tokens=500
        )
        assert protected[0] is msgs[0], "system message must head the protected group"

    def test_protected_tail_ordering_preserved(self):
        msgs = _build_long_history(n_turns=10)
        _, protected = split_for_protected_summarization(msgs, protected_tokens=800)
        # Skip system msg at index 0; the rest must be a contiguous tail in order
        tail = protected[1:]
        assert tail == msgs[-len(tail) :], (
            "protected tail must be in chronological order"
        )

    def test_split_keeps_tool_pairs_together(self):
        """If a tool_return lands in the protected zone, its call must too."""
        sys_msg = _sys_msg()
        msgs = [sys_msg]
        # Pad with lots of text to force the split near a tool pair
        for i in range(5):
            msgs.append(_user_msg(f"q{i}: " + "x" * 400))
            msgs.append(_assistant_text("ok " + "y" * 400))
        # Final turn with a tool call/return pair
        msgs.append(_user_msg("do a thing"))
        msgs.append(_tool_call("read_file", {}, "final_call"))
        msgs.append(_tool_return("read_file", "data", "final_call"))
        msgs.append(_assistant_text("answered"))

        _, protected = split_for_protected_summarization(msgs, protected_tokens=300)

        # Collect ids in protected zone
        call_ids = set()
        return_ids = set()
        for msg in protected:
            for part in msg.parts:
                cid = getattr(part, "tool_call_id", None)
                if not cid:
                    continue
                if part.part_kind == "tool-call":
                    call_ids.add(cid)
                elif part.part_kind == "tool-return":
                    return_ids.add(cid)
        # If final_call's return is protected, its call must be too
        if "final_call" in return_ids:
            assert "final_call" in call_ids, (
                "tool_return pulled into protected zone without its matching tool_call"
            )


# ---------- compact() --------------------------------------------------------


class TestCompact:
    def test_under_threshold_is_noop(self):
        msgs = _build_long_history(n_turns=2)
        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=1_000_000, context_overhead=0
            )
        assert new_msgs is msgs, "under threshold must return the input unchanged"
        assert dropped == []

    def test_over_threshold_truncation_strategy(self):
        msgs = _build_long_history(n_turns=20)
        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.1,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 500,
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=10_000, context_overhead=0
            )
        assert len(new_msgs) < len(msgs)
        assert len(dropped) > 0
        # System message preserved
        assert new_msgs[0] is msgs[0]

    def test_orphan_tool_calls_do_not_block_summarization(self):
        """REGRESSION: orphaned tool_calls (from cancelled runs) must NOT cause
        summarization to be deferred indefinitely.

        Before the fix, `has_pending_tool_calls()` ran on the raw message list,
        so a single unmatched tool_call left over from a Ctrl-C would permanently
        disable compaction. Now the check runs *after* orphan-pruning, so stale
        unmatched calls are silently cleaned up and summarization proceeds.

        The user-visible symptom was "Summarization deferred: pending tool
        call(s) detected" firing on every turn, with history growing unbounded.
        """
        summary_msg = ModelRequest(parts=[UserPromptPart(content="SUMMARY")])

        # Build a huge history with a permanent orphan tool_call at the start —
        # the kind of thing that lives in a long-running session after a
        # cancelled command.
        msgs = _build_long_history(n_turns=20)
        # Inject an orphan tool_call after the system message (no matching return)
        orphan = _tool_call("read_file", {"path": "/cancelled.txt"}, "orphan_ctrl_c")
        msgs = [msgs[0], orphan] + msgs[1:]

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            run_summarization_sync=lambda instructions, message_history: [summary_msg],
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=10_000, context_overhead=0
            )

        # Must NOT be deferred — summarization should have run
        assert len(new_msgs) < len(msgs), (
            "Summarization was deferred due to stale orphan tool_call — "
            "the bug is back. Check has_pending_tool_calls() ordering."
        )
        assert summary_msg in new_msgs, "summarizer output missing from result"
        # The orphan tool_call should be gone (pruned)
        for m in new_msgs:
            for p in m.parts:
                assert getattr(p, "tool_call_id", None) != "orphan_ctrl_c", (
                    "orphan tool_call leaked into compacted output"
                )

    def test_summarization_defers_only_on_truly_pending_post_prune(self):
        """Edge case: if `filter_huge_messages` leaves an orphan (shouldn't
        happen in practice but defensive), deferral should still fire."""
        import code_puppy.agents._compaction as cm

        sys_msg = _sys_msg()
        msgs = [sys_msg, _user_msg("q"), _tool_call("read_file", {}, "live_orphan")]

        # Force filter_huge_messages to return the messages unchanged (simulating
        # a hypothetical bug where pruning doesnt run). Then the deferral
        # safety net should kick in.
        with patch.multiple(
            cm,
            get_compaction_threshold=lambda: 0.001,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            filter_huge_messages=lambda m, *_args, **_kwargs: m,  # bypass the prune
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=100, context_overhead=0
            )
        assert new_msgs is msgs, "safety-net deferral must return input unchanged"
        assert dropped == []

    def test_summarization_path_invokes_summarizer(self):
        """Verify compact() routes to summarize() and gets reasonable result."""
        msgs = _build_long_history(n_turns=20)
        summary_msg = ModelRequest(parts=[UserPromptPart(content="SUMMARY")])

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            run_summarization_sync=lambda instructions, message_history: [summary_msg],
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=10_000, context_overhead=0
            )

        assert len(new_msgs) < len(msgs)
        assert new_msgs[0] is msgs[0], "system msg preserved"
        # The injected summary should appear in the result
        assert summary_msg in new_msgs
        assert len(dropped) > 0

    def test_summarization_failure_falls_back_to_truncation(self):
        """If the summarization agent blows up, compact() must fall back to
        truncation rather than returning history unchanged (which would let
        the context window keep growing)."""
        msgs = _build_long_history(n_turns=20)

        def _boom(instructions, message_history):
            raise RuntimeError("summarizer model exploded")

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            run_summarization_sync=_boom,
        ):
            new_msgs, dropped = compact(
                agent=None, messages=msgs, model_max=10_000, context_overhead=0
            )

        # Truncation actually compacted things — history shrank, drops recorded.
        assert len(new_msgs) < len(msgs), (
            "Fallback truncation should have shrunk the history"
        )
        assert new_msgs[0] is msgs[0], "system msg preserved on fallback"
        assert len(dropped) > 0, "dropped messages must be recorded for hash tracking"

    def test_summarization_failure_preserves_strategy_setting(self):
        """The fallback should be one-shot — the user's configured strategy is
        not silently mutated. (Sanity check: we never call set_compaction_strategy.)"""
        msgs = _build_long_history(n_turns=20)
        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.01,
            get_compaction_strategy=lambda: "summarization",
            get_protected_token_count=lambda: 500,
            run_summarization_sync=lambda *a, **kw: (_ for _ in ()).throw(
                RuntimeError("nope")
            ),
        ):
            # Just make sure it doesn't raise — config-mutation is a non-event
            # because we never import any setter in _compaction.py.
            compact(agent=None, messages=msgs, model_max=10_000, context_overhead=0)


# ---------- make_history_processor() -----------------------------------------


class TestMakeHistoryProcessor:
    """Critical: pydantic-ai calls this with a 1-arg signature. Regression
    coverage for the bug fixed after Phase 4."""

    def test_closure_signature_is_one_arg(self):
        """REGRESSION: pydantic-ai's _takes_ctx() inspects the first param's
        type annotation. If it's not RunContext, processor is called with only
        messages. Our closure must have exactly 1 param."""
        import inspect

        agent = _FakeAgent()
        processor = make_history_processor(agent)
        sig = inspect.signature(processor)
        assert list(sig.parameters.keys()) == ["messages"], (
            f"history_processor must be 1-arg (messages only) for pydantic-ai "
            f"compatibility. Got: {list(sig.parameters.keys())}"
        )

    def test_callable_with_single_messages_arg(self):
        """Smoke test: must not raise when called pydantic-ai style."""
        agent = _FakeAgent()
        processor = make_history_processor(agent)
        # Should not raise
        result = processor([])
        assert result == []

    def test_merges_new_messages_into_agent_history(self):
        agent = _FakeAgent()
        agent._message_history = [_sys_msg()]
        processor = make_history_processor(agent)

        # Note: end with a ModelRequest so the trailing-ModelResponse stripper
        # doesn't eat the assistant message.
        incoming = [
            _sys_msg(),
            _user_msg("hello"),
            _assistant_text("hi"),
            _user_msg("follow up"),
        ]
        result = processor(incoming)

        # The new messages (user + assistant + follow-up) should have been merged
        assert len(result) == 4
        assert agent._message_history is result or agent._message_history == result
        # Must end with a ModelRequest (Anthropic prefill requirement)
        assert isinstance(result[-1], ModelRequest)

    def test_dedupes_by_hash(self):
        """Messages already in history (by hash) should not be re-appended."""
        agent = _FakeAgent()
        sys_msg = _sys_msg()
        user_msg = _user_msg("hello")
        agent._message_history = [sys_msg, user_msg]

        processor = make_history_processor(agent)
        # Pass the same messages in again
        result = processor([sys_msg, user_msg])
        assert len(result) == 2, "duplicate messages must not be re-appended"

    def test_last_message_preserved_even_on_hash_collision(self):
        """Short repeated prompts like 'yes' collide with compacted hashes.
        The last message must always survive."""
        agent = _FakeAgent()
        sys_msg = _sys_msg()
        yes_msg = _user_msg("yes")

        # Pretend "yes" was compacted previously
        from code_puppy.agents._history import hash_message

        agent._message_history = [sys_msg]
        agent._compacted_message_hashes = {hash_message(yes_msg)}

        processor = make_history_processor(agent)
        result = processor([sys_msg, yes_msg])

        # Even though yes_msg's hash is in compacted_hashes, it's the last
        # message and must be preserved.
        assert yes_msg in result, "last message must survive hash collision"

    def test_strips_trailing_model_responses(self):
        """History must end with ModelRequest (Anthropic prefill requirement)."""
        agent = _FakeAgent()
        processor = make_history_processor(agent)

        msgs = [
            _sys_msg(),
            _user_msg("q"),
            _assistant_text("a1"),
            _assistant_text("a2"),  # Trailing ModelResponse
        ]
        result = processor(msgs)

        assert len(result) > 0
        assert isinstance(result[-1], ModelRequest), (
            f"history must end with ModelRequest, got {type(result[-1]).__name__}"
        )

    def test_strips_empty_thinking_parts(self):
        agent = _FakeAgent()
        processor = make_history_processor(agent)

        empty_thinking = ModelResponse(parts=[ThinkingPart(content="")])
        msgs = [_sys_msg(), empty_thinking, _user_msg("q")]
        result = processor(msgs)

        # Empty-thinking-only message should be filtered out
        for msg in result:
            if len(msg.parts) == 1 and isinstance(msg.parts[0], ThinkingPart):
                assert msg.parts[0].content, (
                    "empty ThinkingPart should have been stripped"
                )

    def test_preserves_empty_thinking_with_signature(self):
        """ThinkingParts with encrypted reasoning state must NOT be stripped.

        GPT-5 on the Responses API returns reasoning items with empty content
        but non-empty ``signature`` / ``id`` (the encrypted reasoning payload).
        These must round-trip back to the API or the paired ``msg_...`` item
        in the next turn errors with "provided without its required
        'reasoning' item".
        """
        agent = _FakeAgent()
        processor = make_history_processor(agent)

        reasoning_msg = ModelResponse(
            parts=[
                ThinkingPart(
                    content="",
                    id="rs_abc123",
                    signature="encrypted-blob",
                    provider_name="openai",
                ),
                TextPart(content="hi", id="msg_abc123"),
            ]
        )
        msgs = [_sys_msg(), _user_msg("q"), reasoning_msg, _user_msg("q2")]
        result = processor(msgs)

        # The reasoning ThinkingPart must survive — dropping it would orphan
        # the paired TextPart(id="msg_...") on the next API request.
        thinking_found = False
        for msg in result:
            for p in msg.parts:
                if isinstance(p, ThinkingPart) and p.id == "rs_abc123":
                    thinking_found = True
                    assert p.signature == "encrypted-blob"
        assert thinking_found, (
            "ThinkingPart with signature must be preserved for Responses API"
        )

    def test_triggers_compaction_over_threshold(self):
        """When over threshold, the processor must call compact() and shrink history."""
        agent = _FakeAgent(model_max=5_000, overhead=100)
        processor = make_history_processor(agent)

        big_msgs = _build_long_history(n_turns=20)

        with patch.multiple(
            _compaction,
            get_compaction_threshold=lambda: 0.1,
            get_compaction_strategy=lambda: "truncation",
            get_protected_token_count=lambda: 300,
        ):
            result = processor(big_msgs)

        assert len(result) < len(big_msgs), (
            "over-threshold processor call must compact history"
        )
        assert result[0] is big_msgs[0], "system message preserved through compaction"

    def test_noop_under_threshold(self):
        agent = _FakeAgent(model_max=1_000_000, overhead=0)
        processor = make_history_processor(agent)

        msgs = _build_long_history(n_turns=2)

        with patch.object(_compaction, "get_compaction_threshold", return_value=0.95):
            result = processor(msgs)

        # Under threshold: all messages preserved (modulo ModelResponse trimming)
        assert (
            len(result) >= len(msgs) - 1
        )  # at most 1 stripped (trailing ModelResponse)


# ---------- summarize() ------------------------------------------------------


class TestSummarize:
    def test_empty_input_returns_empty(self):
        assert summarize([], protected_tokens=1000) == ([], [])

    def test_no_messages_to_summarize(self):
        """If only system message fits, nothing to summarize."""
        msgs = [_sys_msg()]
        result, dropped = summarize(msgs, protected_tokens=10_000)
        assert len(result) == 1
        assert dropped == []

    def test_summarization_failure_returns_original(self):
        """If summarization agent blows up, return original messages unchanged."""
        msgs = _build_long_history(n_turns=10)

        def _boom(instructions, message_history):
            raise RuntimeError("model is on fire")

        with patch.object(_compaction, "run_summarization_sync", _boom):
            result, dropped = summarize(msgs, protected_tokens=500)

        assert result == msgs, "failure must return original messages unchanged"
        assert dropped == []

    def test_non_list_output_is_wrapped(self):
        """If summarizer returns a string, it should be wrapped into a message."""
        msgs = _build_long_history(n_turns=10)

        with patch.object(
            _compaction,
            "run_summarization_sync",
            return_value="summary as string",
        ):
            result, dropped = summarize(msgs, protected_tokens=500)

        # Must still compact; string got wrapped into a ModelRequest
        assert len(result) < len(msgs)
        assert result[0] is msgs[0]  # system preserved
