"""Tests for code_puppy.agents.run_stats: TTFT + gen-speed timing.

Covers both the ``AgentRunStats`` state container and the three callback
hooks that drive it (agent_run_start / stream_event / agent_run_end).
"""

import time

import pytest

from code_puppy.agents.run_stats import (
    AgentRunStats,
    _estimate_tokens,
    _on_agent_run_end,
    _on_agent_run_start,
    _on_stream_event,
)
from code_puppy.tools.subagent_context import subagent_context


@pytest.fixture(autouse=True)
def _reset_stats():
    """Ensure every test starts with a completely clean slate."""
    AgentRunStats.reset_cycle_state()
    AgentRunStats.reset_conversation_stats()
    yield
    AgentRunStats.reset_cycle_state()
    AgentRunStats.reset_conversation_stats()


# ---------------------------------------------------------------------------
# AgentRunStats state-machine tests
# ---------------------------------------------------------------------------


def test_initial_conversation_stats_are_none():
    avg_ttft, avg_gen = AgentRunStats.get_conversation_stats()
    assert avg_ttft is None
    assert avg_gen is None


def test_format_conversation_stats_empty():
    assert AgentRunStats.format_conversation_stats(None, None) == ""


def test_format_conversation_stats_both():
    out = AgentRunStats.format_conversation_stats(0.85, 72.3)
    # Note the space before 's' -- intentional, so Rich's number highlighter
    # can match the full decimal (digit must be followed by a non-word char).
    assert "avg TTFT 0.85 s" in out
    assert "avg TG 72.3 t/s" in out
    assert "|" in out


def test_format_conversation_stats_only_ttft():
    out = AgentRunStats.format_conversation_stats(0.42, None)
    assert out == "avg TTFT 0.42 s"


def test_format_conversation_stats_ttft_value_is_highlighter_friendly():
    """Confirm Rich's ReprHighlighter matches the full decimal value."""
    from rich.highlighter import ReprHighlighter
    from rich.text import Text

    out = AgentRunStats.format_conversation_stats(1.53, 86.4)
    text = Text(out)
    ReprHighlighter().highlight(text)
    # Both decimal values should appear as 'repr.number' spans in full.
    matched_substrings = {text.plain[s.start : s.end] for s in text.spans}
    assert "1.53" in matched_substrings
    assert "86.4" in matched_substrings


def test_record_output_tokens_marks_first_token_time():
    AgentRunStats.mark_request_start()
    assert AgentRunStats._first_token_time == 0.0
    AgentRunStats.record_output_tokens(5)
    assert AgentRunStats._first_token_time > 0.0
    assert AgentRunStats._output_tokens == 5


def test_record_output_tokens_ignores_zero_or_negative():
    AgentRunStats.mark_request_start()
    AgentRunStats.record_output_tokens(0)
    AgentRunStats.record_output_tokens(-3)
    assert AgentRunStats._first_token_time == 0.0
    assert AgentRunStats._output_tokens == 0


def test_record_output_tokens_anchors_start_if_missing():
    """If mark_request_start wasn't called, record defensively anchors."""
    AgentRunStats.reset_cycle_state()
    AgentRunStats.record_output_tokens(10)
    assert AgentRunStats._stream_start_time > 0.0
    assert AgentRunStats._first_token_time > 0.0


def test_snapshot_cycle_into_aggregates_folds_and_resets():
    AgentRunStats.mark_request_start()
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)

    AgentRunStats.snapshot_cycle_into_aggregates()

    # Per-cycle state wiped clean.
    assert AgentRunStats._first_token_time == 0.0
    assert AgentRunStats._stream_start_time == 0.0
    assert AgentRunStats._output_tokens == 0
    # Last-known + conversation totals populated.
    assert AgentRunStats._last_ttft_seconds > 0
    assert AgentRunStats._last_gen_tps > 0
    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens == 100
    assert AgentRunStats._total_gen_seconds > 0


def test_snapshot_with_no_first_token_records_nothing():
    AgentRunStats.mark_request_start()  # never recorded any tokens
    AgentRunStats.snapshot_cycle_into_aggregates()
    assert AgentRunStats._last_ttft_seconds == 0.0
    assert AgentRunStats._last_gen_tps == 0.0
    assert AgentRunStats._ttft_sample_count == 0


def test_reset_cycle_preserves_conversation_aggregates():
    AgentRunStats.mark_request_start()
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)
    AgentRunStats.snapshot_cycle_into_aggregates()
    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens == 50

    AgentRunStats.reset_cycle_state()
    assert AgentRunStats._ttft_sample_count == 1  # preserved
    assert AgentRunStats._total_output_tokens == 50  # preserved


def test_reset_conversation_clears_aggregates():
    AgentRunStats._total_ttft_seconds = 1.0
    AgentRunStats._ttft_sample_count = 3
    AgentRunStats._total_output_tokens = 500
    AgentRunStats._total_gen_seconds = 5.0
    AgentRunStats.reset_conversation_stats()
    assert AgentRunStats._total_ttft_seconds == 0.0
    assert AgentRunStats._ttft_sample_count == 0
    assert AgentRunStats._total_output_tokens == 0
    assert AgentRunStats._total_gen_seconds == 0.0


def test_get_conversation_stats_includes_live_cycle():
    """A live cycle's stats should fold into the averages too."""
    # Finished cycle
    AgentRunStats.mark_request_start()
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(100)
    AgentRunStats.snapshot_cycle_into_aggregates()

    # Live cycle
    AgentRunStats.mark_request_start()
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(100)

    avg_ttft, avg_gen = AgentRunStats.get_conversation_stats()
    assert avg_ttft is not None and avg_ttft > 0
    assert avg_gen is not None and avg_gen > 0
    assert AgentRunStats._ttft_sample_count == 1  # only cycle 1 in totals yet


# ---------------------------------------------------------------------------
# Token estimator tests
# ---------------------------------------------------------------------------


def test_estimate_tokens_empty():
    assert _estimate_tokens("") == 0
    assert _estimate_tokens(None) == 0


def test_estimate_tokens_minimum_one():
    assert _estimate_tokens("a") == 1


def test_estimate_tokens_2_5_chars_per_token():
    assert _estimate_tokens("a" * 10) == 4  # floor(10/2.5)


# ---------------------------------------------------------------------------
# Callback hook tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_agent_run_start_marks_t0():
    assert AgentRunStats._stream_start_time == 0.0
    await _on_agent_run_start("agent", "model")
    assert AgentRunStats._stream_start_time > 0.0


@pytest.mark.asyncio
async def test_on_agent_run_start_skipped_in_subagent():
    with subagent_context("retriever"):
        await _on_agent_run_start("agent", "model")
    assert AgentRunStats._stream_start_time == 0.0


@pytest.mark.asyncio
async def test_on_stream_event_part_start_with_text_records():
    await _on_agent_run_start("agent", "model")

    from pydantic_ai.messages import TextPart

    part = TextPart(content="hello world from the puppy")
    await _on_stream_event("part_start", {"part": part})

    assert AgentRunStats._first_token_time > 0.0
    assert AgentRunStats._output_tokens > 0


@pytest.mark.asyncio
async def test_on_stream_event_part_delta_with_text_records():
    await _on_agent_run_start("agent", "model")

    from pydantic_ai.messages import TextPartDelta

    delta = TextPartDelta(content_delta="streaming chunk of text")
    await _on_stream_event("part_delta", {"delta": delta})

    assert AgentRunStats._first_token_time > 0.0
    assert AgentRunStats._output_tokens > 0


@pytest.mark.asyncio
async def test_on_stream_event_thinking_delta_records():
    await _on_agent_run_start("agent", "model")

    from pydantic_ai.messages import ThinkingPartDelta

    delta = ThinkingPartDelta(content_delta="hmm thinking about this")
    await _on_stream_event("part_delta", {"delta": delta})

    assert AgentRunStats._first_token_time > 0.0
    assert AgentRunStats._output_tokens > 0


@pytest.mark.asyncio
async def test_on_stream_event_tool_call_delta_records():
    await _on_agent_run_start("agent", "model")

    from pydantic_ai.messages import ToolCallPartDelta

    delta = ToolCallPartDelta(args_delta='{"file": "foo.py"}')
    await _on_stream_event("part_delta", {"delta": delta})

    assert AgentRunStats._first_token_time > 0.0
    assert AgentRunStats._output_tokens > 0


@pytest.mark.asyncio
async def test_on_stream_event_ignores_empty_content():
    await _on_agent_run_start("agent", "model")

    from pydantic_ai.messages import TextPartDelta

    delta = TextPartDelta(content_delta="")
    await _on_stream_event("part_delta", {"delta": delta})

    assert AgentRunStats._first_token_time == 0.0
    assert AgentRunStats._output_tokens == 0


@pytest.mark.asyncio
async def test_on_stream_event_skipped_in_subagent():
    await _on_agent_run_start("agent", "model")
    initial_tokens = AgentRunStats._output_tokens

    with subagent_context("retriever"):
        from pydantic_ai.messages import TextPartDelta

        delta = TextPartDelta(content_delta="subagent talk shouldn't leak")
        await _on_stream_event("part_delta", {"delta": delta})

    assert AgentRunStats._output_tokens == initial_tokens


@pytest.mark.asyncio
async def test_on_stream_event_handles_non_dict_event_data():
    """Defensive: callback must not crash on weird payloads."""
    await _on_stream_event("part_start", "not a dict")
    await _on_stream_event("part_start", None)


@pytest.mark.asyncio
async def test_on_agent_run_end_folds_into_aggregates():
    await _on_agent_run_start("agent", "model")
    time.sleep(0.05)

    from pydantic_ai.messages import TextPartDelta

    delta = TextPartDelta(content_delta="some response text")
    await _on_stream_event("part_delta", {"delta": delta})

    await _on_agent_run_end("agent", "model")

    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens > 0
    assert AgentRunStats._total_gen_seconds > 0
    # Per-cycle state wiped clean.
    assert AgentRunStats._first_token_time == 0.0
    assert AgentRunStats._stream_start_time == 0.0


@pytest.mark.asyncio
async def test_on_agent_run_end_skipped_in_subagent():
    await _on_agent_run_start("agent", "model")
    time.sleep(0.02)
    AgentRunStats.record_output_tokens(10)

    with subagent_context("retriever"):
        await _on_agent_run_end("subagent", "model")

    assert AgentRunStats._ttft_sample_count == 0


@pytest.mark.asyncio
async def test_full_cycle_with_multiple_model_calls():
    """Within one agent run there can be multiple model calls; TTFT measured ONCE."""
    from pydantic_ai.messages import TextPartDelta

    await _on_agent_run_start("agent", "model")  # T0
    time.sleep(0.05)

    # First model call's first token.
    delta1 = TextPartDelta(content_delta="first response")
    await _on_stream_event("part_delta", {"delta": delta1})
    first_token_t = AgentRunStats._first_token_time
    assert first_token_t > 0

    # Subsequent deltas should NOT reset first-token time.
    time.sleep(0.05)
    delta2 = TextPartDelta(content_delta="more output after tool result")
    await _on_stream_event("part_delta", {"delta": delta2})
    assert AgentRunStats._first_token_time == first_token_t

    await _on_agent_run_end("agent", "model")
    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens > 0
