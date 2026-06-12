"""Tests for code_puppy.agents.run_stats: TTFT + gen-speed timing.

Covers both the ``AgentRunStats`` state container and the callback
hooks that drive it (agent_run_start / stream_event / agent_run_end /
post_tool_call).
"""

import time
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from code_puppy.agents.run_stats import (
    AgentRunStats,
    _estimate_tokens,
    _on_agent_run_end,
    _on_agent_run_start,
    _on_post_tool_call,
    _on_stream_event,
    _render_high_mode_tool_result,
    _stringify_result,
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
    AgentRunStats.record_output_tokens(25)
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(25)
    AgentRunStats.snapshot_cycle_into_aggregates()
    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens == 50

    AgentRunStats.reset_cycle_state()
    assert AgentRunStats._ttft_sample_count == 1  # preserved
    assert AgentRunStats._total_output_tokens == 50  # preserved


def test_single_event_cycle_records_ttft_but_no_gen_sample():
    """One lone stream event gives no inter-event gap, so no TG sample."""
    AgentRunStats.mark_request_start()
    time.sleep(0.02)
    AgentRunStats.record_output_tokens(50)
    AgentRunStats.snapshot_cycle_into_aggregates()
    assert AgentRunStats._ttft_sample_count == 1
    assert AgentRunStats._total_output_tokens == 0
    assert AgentRunStats._total_gen_seconds == 0.0


def test_gen_time_excludes_stalls_between_stream_events(monkeypatch):
    """Gaps wider than the stall threshold (tool runs, follow-up request
    latency) must not inflate the TG denominator.

    Uses a fake clock instead of real sleeps -- on a loaded machine a
    short sleep can overshoot the stall threshold and flake the test.
    """
    clock = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])

    AgentRunStats.mark_request_start()
    AgentRunStats.record_output_tokens(10)  # first token anchors the burst

    clock[0] += 0.5  # normal inter-token gap -- counted
    AgentRunStats.record_output_tokens(10)
    gen_after_burst = AgentRunStats._gen_seconds
    assert gen_after_burst == pytest.approx(0.5)

    # Stall (e.g. tool execution) wider than the threshold -- excluded.
    clock[0] += AgentRunStats._MAX_INTER_EVENT_GAP_SECONDS + 1.0
    AgentRunStats.record_output_tokens(10)
    assert AgentRunStats._gen_seconds == gen_after_burst


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
    AgentRunStats.record_output_tokens(50)
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)
    AgentRunStats.snapshot_cycle_into_aggregates()

    # Live cycle
    AgentRunStats.mark_request_start()
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)
    time.sleep(0.05)
    AgentRunStats.record_output_tokens(50)

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
    time.sleep(0.02)
    delta2 = TextPartDelta(content_delta="and a bit more of it")
    await _on_stream_event("part_delta", {"delta": delta2})

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


# ---------------------------------------------------------------------------
# High-mode tool result rendering (_on_post_tool_call)
# ---------------------------------------------------------------------------


class TestHighModeToolResult:
    """_render_high_mode_tool_result renders tool output in high mode."""

    def _capture(self, tool_name, result, *, level="high", duration_ms=42.0):
        """Run the renderer and return captured console output."""
        buf = StringIO()
        console = Console(file=buf, force_terminal=False, width=120)
        with (
            patch(
                "code_puppy.config.get_output_level",
                return_value=level,
            ),
            patch(
                "code_puppy.agents.event_stream_handler.get_streaming_console",
                return_value=console,
            ),
        ):
            _render_high_mode_tool_result(tool_name, {}, result, duration_ms)
        buf.seek(0)
        return buf.read()

    def test_renders_in_high_mode(self):
        out = self._capture("list_agents", "x = 1\ny = 2")
        assert "list_agents" in out
        assert "returned" in out
        assert "42 ms" in out
        assert "x = 1" in out
        assert "y = 2" in out

    def test_silent_in_medium_mode(self):
        out = self._capture("list_agents", "x = 1", level="medium")
        assert out == ""

    def test_silent_in_low_mode(self):
        out = self._capture("list_agents", "x = 1", level="low")
        assert out == ""

    def test_long_results_shown_in_full_with_footer(self):
        """High mode never truncates.  Results >50 lines get an info footer."""
        long_result = "\n".join(f"line {i}" for i in range(200))
        out = self._capture("list_agents", long_result)
        # All lines must be present — no truncation in high mode
        assert "line 0" in out
        assert "line 100" in out
        assert "line 199" in out
        # Informational footer (not a gate)
        assert "200 lines" in out
        assert "chars" in out
        # Old truncation indicator must NOT appear
        assert "truncated" not in out

    def test_short_results_no_footer(self):
        """Results under the footer threshold should have no footer."""
        short_result = "\n".join(f"line {i}" for i in range(10))
        out = self._capture("list_agents", short_result)
        assert "line 0" in out
        assert "line 9" in out
        assert "lines," not in out  # no footer

    def test_handles_dict_result(self):
        out = self._capture("list_agents", {"error": "file not found"})
        assert "file not found" in out

    def test_never_crashes(self):
        """Even with pathological input, the renderer must not raise."""
        _render_high_mode_tool_result("tool", {}, None, 0.0)
        _render_high_mode_tool_result("tool", {}, 12345, 0.0)

    # -- invoke_agent / invoke_agent_with_model summary rendering -----------

    def test_invoke_agent_shows_summary_not_repr(self):
        """invoke_agent result should show a compact summary, not raw repr."""
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        result = AgentInvokeOutput(
            response="Hello\nWorld\nMultiline",
            agent_name="test-agent",
            session_id="sess-1",
            model_name="gpt-4",
        )
        out = self._capture("invoke_agent", result)
        # Should contain agent name and char count, NOT raw response body
        assert "test-agent" in out
        assert "OK" in out
        assert "21 chars" in out
        # Must NOT contain the raw response text or escaped newlines
        assert "Hello" not in out
        assert "World" not in out
        assert "Multiline" not in out

    def test_invoke_agent_with_model_shows_summary(self):
        """invoke_agent_with_model gets the same compact treatment."""
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        result = AgentInvokeOutput(
            response="big response" * 100,
            agent_name="code-puppy",
        )
        out = self._capture("invoke_agent_with_model", result)
        assert "code-puppy" in out
        assert "OK" in out
        assert "1,200 chars" in out
        # Raw body must not leak
        assert "big response" not in out

    def test_invoke_agent_error_shows_fail(self):
        """Error sub-agent results should show FAIL status."""
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        result = AgentInvokeOutput(
            response=None,
            agent_name="broken-agent",
            error="Model quota exceeded",
        )
        out = self._capture("invoke_agent", result)
        assert "broken-agent" in out
        assert "FAIL" in out
        # Error message should NOT be dumped (it's in the response payload)
        assert "quota" not in out

    def test_invoke_agent_no_response(self):
        """Sub-agent with None response and no error shows 'no response'."""
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        result = AgentInvokeOutput(
            response=None,
            agent_name="empty-agent",
        )
        out = self._capture("invoke_agent", result)
        assert "empty-agent" in out
        assert "no response" in out

    def test_normal_tool_still_renders_body(self):
        """Non-rendered tools should still render their full result body."""
        out = self._capture("list_agents", "line 1\nline 2\nline 3")
        assert "line 1" in out
        assert "line 2" in out
        assert "line 3" in out

    # -- Tools with rich_renderer (compact summary, no body) ---------------

    def test_rendered_tool_shows_compact_summary(self):
        """Tools in _TOOLS_WITH_RENDERER show duration only, no body."""
        out = self._capture("read_file", "x = 1\ny = 2")
        assert "read_file" in out
        assert "returned" in out
        assert "42 ms" in out
        # Body should NOT appear
        assert "x = 1" not in out
        assert "y = 2" not in out

    def test_grep_shows_compact_summary(self):
        """grep is in _TOOLS_WITH_RENDERER."""
        out = self._capture("grep", "match 1\nmatch 2")
        assert "grep" in out
        assert "returned" in out
        assert "match 1" not in out

    def test_shell_shows_compact_summary(self):
        """agent_run_shell_command is in _TOOLS_WITH_RENDERER."""
        out = self._capture("agent_run_shell_command", "output here")
        assert "agent_run_shell_command" in out
        assert "returned" in out
        assert "output here" not in out

    # -- _stringify_result --------------------------------------------------

    def test_stringify_plain_string(self):
        assert _stringify_result("hello\nworld") == "hello\nworld"

    def test_stringify_dict(self):
        out = _stringify_result({"key": "value", "nested": {"a": 1}})
        assert "\n" in out  # Should be multi-line JSON
        assert '"key"' in out
        assert '"value"' in out

    def test_stringify_list(self):
        out = _stringify_result([1, 2, 3])
        assert "\n" in out
        assert "1" in out

    def test_stringify_pydantic_model(self):
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        result = AgentInvokeOutput(
            response="Hello\nWorld",
            agent_name="test",
        )
        out = _stringify_result(result)
        # Should produce multi-line JSON (real newlines for line splitting)
        assert out.count("\n") > 1
        # Should contain the field names as JSON keys
        assert '"response"' in out
        assert '"agent_name"' in out

    def test_stringify_none(self):
        out = _stringify_result(None)
        assert isinstance(out, str)

    def test_stringify_int(self):
        assert _stringify_result(42) == "42"

    # -- Footer for large structured results --------------------------------

    def test_large_structured_result_shown_in_full_with_footer(self):
        """Structured results are never truncated; large ones get a footer."""
        big_dict = {f"key_{i}": f"value_{i}" for i in range(200)}
        out = self._capture("list_agents", big_dict)
        # No truncation
        assert "truncated" not in out
        # All keys must be present
        assert '"key_0"' in out
        assert '"key_199"' in out
        # Informational footer (>50 lines)
        assert "lines" in out
        assert "chars" in out


@pytest.mark.asyncio
async def test_on_post_tool_call_delegates_to_renderer():
    """_on_post_tool_call should call the render function."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    with (
        patch(
            "code_puppy.config.get_output_level",
            return_value="high",
        ),
        patch(
            "code_puppy.agents.event_stream_handler.get_streaming_console",
            return_value=console,
        ),
    ):
        await _on_post_tool_call("list_files", {"dir": "."}, "found 5 files", 10.0)
    buf.seek(0)
    out = buf.read()
    assert "list_files" in out
    assert "returned" in out
    # list_files is in _TOOLS_WITH_RENDERER, so body should NOT appear
    assert "found 5 files" not in out
