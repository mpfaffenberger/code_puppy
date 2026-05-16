"""Tests for the /prune custom-command plugin."""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

try:
    from pydantic_ai.messages import ThinkingPart  # type: ignore
except ImportError:  # pragma: no cover — older pydantic-ai versions
    ThinkingPart = None  # type: ignore[assignment]

try:
    from pydantic_ai.messages import RetryPromptPart  # type: ignore
except ImportError:  # pragma: no cover
    RetryPromptPart = None  # type: ignore[assignment]

from code_puppy.plugins.prune import prune_model
from code_puppy.plugins.prune.prune_menu import PruneMenu
from code_puppy.plugins.prune.prune_model import (
    ContextBudget,
    MessageEntry,
    annotate_context_window,
    build_message_entries,
    classify_tool,
    short_args,
    short_str,
)
from code_puppy.plugins.prune.prune_render import (
    ctx_detail_text,
    ctx_indicator,
    format_args_full,
    render_budget_line,
    render_detail,
    render_legend,
    render_list,
    tokens_str,
)


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────


def _plugin_module():
    return importlib.import_module("code_puppy.plugins.prune.register_callbacks")


def _agent_manager_module(agent: MagicMock) -> SimpleNamespace:
    return SimpleNamespace(get_current_agent=lambda: agent)


def _system_msg() -> ModelRequest:
    return ModelRequest(parts=[SystemPromptPart(content="you are a puppy")])


def _system_plus_user_msg(
    system: str = "you are a puppy", user: str = "first turn"
) -> ModelRequest:
    """How pydantic-ai actually bundles history[0]: system + first user."""
    return ModelRequest(
        parts=[
            SystemPromptPart(content=system),
            UserPromptPart(content=user),
        ]
    )


def _user_msg(text: str = "hi") -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _assistant_text(text: str = "hello human") -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def _assistant_with_thinking(
    text: str = "final answer", thinking: str = "let me think..."
) -> ModelResponse:
    """Build an assistant response with both a thinking part and a text part.

    Skips the test cleanly if the installed pydantic-ai is too old to ship
    ``ThinkingPart`` so the suite remains forwards-compatible.
    """
    if ThinkingPart is None:  # pragma: no cover
        import pytest

        pytest.skip("pydantic-ai version lacks ThinkingPart")
    return ModelResponse(parts=[ThinkingPart(content=thinking), TextPart(content=text)])


def _assistant_with_tool(
    *, text: str | None, tool_name: str, tool_call_id: str, args: str = "{}"
) -> ModelResponse:
    parts = []
    if text is not None:
        parts.append(TextPart(content=text))
    parts.append(
        ToolCallPart(tool_name=tool_name, args=args, tool_call_id=tool_call_id)
    )
    return ModelResponse(parts=parts)


def _tool_return(tool_call_id: str, content: str = "ok") -> ModelRequest:
    return ModelRequest(
        parts=[
            ToolReturnPart(tool_name="t", content=content, tool_call_id=tool_call_id)
        ]
    )


# ───────────────────────────────────────────────────────────────────────────
# prune_model: classifier + string helpers
# ───────────────────────────────────────────────────────────────────────────


class TestClassifyTool:
    def test_write_tool(self):
        assert classify_tool("create_file") == "✎"
        assert classify_tool("replace_in_file") == "✎"
        assert classify_tool("delete_file") == "✎"

    def test_shell_tool(self):
        assert classify_tool("agent_run_shell_command") == "⚡"

    def test_browser_prefix(self):
        assert classify_tool("browser_open") == "🌐"

    def test_terminal_prefix(self):
        assert classify_tool("terminal_run") == "▶"

    def test_unclassified(self):
        assert classify_tool("read_file") == "·"


class TestShortStr:
    def test_none(self):
        assert short_str(None) == ""

    def test_strips_newlines(self):
        assert short_str("foo\nbar\r baz") == "foo bar  baz"

    def test_truncates_with_ellipsis(self):
        result = short_str("x" * 200, limit=20)
        assert len(result) == 20
        assert result.endswith("…")


class TestShortArgs:
    def test_empty(self):
        assert short_args({}) == ""

    def test_basic_join(self):
        out = short_args({"a": 1, "b": 2})
        assert "a=1" in out and "b=2" in out

    def test_truncates_long(self):
        big = {"k1": "x" * 100, "k2": "y" * 100}
        out = short_args(big, limit=30)
        assert len(out) == 30
        assert out.endswith("…")

    def test_caps_at_four_keys(self):
        d = {f"k{i}": i for i in range(10)}
        out = short_args(d)
        # Only first 4 keys make it into the string
        for i in range(4):
            assert f"k{i}=" in out
        assert "k5=" not in out


# ───────────────────────────────────────────────────────────────────────────
# prune_model: build_message_entries
# ───────────────────────────────────────────────────────────────────────────


class TestBuildMessageEntries:
    def test_filters_system_prompt(self):
        history = [_system_msg(), _user_msg("hello")]
        entries = build_message_entries(history)
        assert len(entries) == 1
        assert entries[0].role == "user"
        assert entries[0].history_index == 1

    def test_user_message_classification(self):
        entries = build_message_entries([_system_msg(), _user_msg("ping")])
        assert entries[0].role == "user"
        assert "ping" in entries[0].full_text

    def test_assistant_text_only(self):
        history = [_system_msg(), _assistant_text("hi there")]
        entries = build_message_entries(history)
        assert entries[0].role == "assistant"
        assert entries[0].tool_calls == []

    def test_assistant_with_tool_call(self):
        history = [
            _system_msg(),
            _assistant_with_tool(
                text="running cmd",
                tool_name="agent_run_shell_command",
                tool_call_id="tc1",
                args='{"command": "ls"}',
            ),
            _tool_return("tc1"),
        ]
        entries = build_message_entries(history)
        # assistant + tool-return (system filtered out)
        assert len(entries) == 2
        assistant = entries[0]
        assert assistant.role == "assistant"
        assert len(assistant.tool_calls) == 1
        tc = assistant.tool_calls[0]
        assert tc.tool_call_id == "tc1"
        assert tc.icon == "⚡"
        assert tc.has_return is True  # back-linked from the return message

    def test_system_plus_user_bundle_gets_system_role(self):
        """pydantic-ai bundles the system prompt with the first user
        message into one ModelRequest. That bundle must be labeled
        ``system`` — never ``user`` — so the menu doesn't pretend it's a
        normal prunable message.
        """
        history = [_system_plus_user_msg(system="you are", user="do stuff")]
        entries = build_message_entries(history)
        assert len(entries) == 1
        assert entries[0].role == "system"
        # Preview should highlight the USER content (what a human cares
        # about scanning), not the system blob.
        assert "do stuff" in entries[0].preview

    def test_pure_system_message_still_filtered(self):
        """A message containing ONLY a system prompt (no user/tool parts)
        is still hidden — there's nothing to display.
        """
        history = [_system_msg(), _user_msg("hi")]
        entries = build_message_entries(history)
        assert len(entries) == 1
        assert entries[0].role == "user"

    def test_synthesizes_system_entry_from_agent_when_missing(self):
        """Code Puppy sends the system prompt via pydantic-ai's instructions
        field rather than as a SystemPromptPart, so raw history doesn't
        contain it. The menu must synthesize one from the agent's
        ``get_full_system_prompt()`` so the user can see what's always
        in context.
        """
        agent = MagicMock()
        agent.get_full_system_prompt.return_value = "You are Rowsdower"
        history = [_user_msg("hi"), _assistant_text("hello!")]
        entries = build_message_entries(history, agent)
        assert entries[0].role == "system"
        assert entries[0].history_index < 0  # sentinel — not a real slot
        assert entries[0].in_context is True  # always in context
        assert "Rowsdower" in entries[0].full_text
        # The two real entries follow.
        assert entries[1].role == "user"
        assert entries[2].role == "assistant"

    def test_does_not_synthesize_system_when_already_present(self):
        """When raw history already advertises a system role (e.g. a
        system+user bundle), don't double up with a synthetic one.
        """
        agent = MagicMock()
        agent.get_full_system_prompt.return_value = "You are Rowsdower"
        history = [_system_plus_user_msg(), _assistant_text("hi")]
        entries = build_message_entries(history, agent)
        sys_entries = [e for e in entries if e.role == "system"]
        assert len(sys_entries) == 1
        # And the one that's there is the REAL one (positive history_index),
        # not the synthetic.
        assert sys_entries[0].history_index >= 0

    def test_no_agent_means_no_synthetic_system_entry(self):
        """When called without an agent (e.g. legacy callers, tests),
        nothing is synthesized — preserves backward-compatible behavior.
        """
        history = [_user_msg("hi")]
        entries = build_message_entries(history)
        assert all(e.role != "system" for e in entries)

    def test_synthetic_system_entry_skips_when_prompt_empty(self):
        agent = MagicMock()
        agent.get_full_system_prompt.return_value = ""
        history = [_user_msg("hi")]
        entries = build_message_entries(history, agent)
        assert all(e.role != "system" for e in entries)

    def test_synthetic_system_entry_skips_when_agent_raises(self):
        agent = MagicMock()
        agent.get_full_system_prompt.side_effect = RuntimeError("nope")
        history = [_user_msg("hi")]
        # Must not propagate — the menu should degrade gracefully.
        entries = build_message_entries(history, agent)
        assert all(e.role != "system" for e in entries)


class TestThinkingPartExtraction:
    """ThinkingPart instances live inside ModelResponse and represent the
    model's chain-of-thought. We surface them in the detail pane (so the
    user can see what the agent was reasoning about) without burying the
    actual response in the preview line.
    """

    def test_thinking_is_collected_into_segments(self):
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="because", thinking="hmm reason 1"),
        ]
        entries = build_message_entries(history)
        asst = entries[-1]
        assert asst.thinking_segments == ["hmm reason 1"]

    def test_preview_excludes_thinking_content(self):
        """The preview line should show the user-facing answer, not
        chain-of-thought noise.
        """
        history = [
            _user_msg("why"),
            _assistant_with_thinking(
                text="short answer", thinking="REALLY LONG INTERNAL MONOLOGUE"
            ),
        ]
        entries = build_message_entries(history)
        asst = entries[-1]
        assert "short answer" in asst.preview
        assert "INTERNAL MONOLOGUE" not in asst.preview

    def test_full_text_includes_thinking_under_fenced_section(self):
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="answer", thinking="reasoning"),
        ]
        entries = build_message_entries(history)
        asst = entries[-1]
        # The detail pane reads full_text, so both must be there with the
        # thinking content clearly fenced for the user.
        assert "answer" in asst.full_text
        assert "[thinking]" in asst.full_text
        assert "reasoning" in asst.full_text

    def test_brain_icon_set_when_thinking_present_and_no_tool_calls(self):
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="a", thinking="b"),
        ]
        entries = build_message_entries(history)
        assert entries[-1].icon == "🧠"

    def test_tool_call_icon_wins_over_thinking_icon(self):
        """Tool calls communicate what the turn DID — that should keep its
        priority over the chain-of-thought marker.
        """
        if ThinkingPart is None:  # pragma: no cover
            import pytest

            pytest.skip("pydantic-ai version lacks ThinkingPart")
        history = [
            _user_msg("do it"),
            ModelResponse(
                parts=[
                    ThinkingPart(content="plan"),
                    TextPart(content="ok"),
                    ToolCallPart(tool_name="shell", args="{}", tool_call_id="tc1"),
                ]
            ),
        ]
        entries = build_message_entries(history)
        # Whatever classify_tool('shell') returns, NOT the brain.
        assert entries[-1].icon != "🧠"
        assert entries[-1].thinking_segments == ["plan"]

    def test_no_thinking_means_no_segments_and_no_brain(self):
        history = [_user_msg("hi"), _assistant_text("hello")]
        entries = build_message_entries(history)
        assert entries[-1].thinking_segments == []
        assert entries[-1].icon != "🧠"


class TestRetryPromptPart:
    """pydantic-ai emits a RetryPromptPart when the model's tool call args
    fail validation. It carries ``tool_call_id`` + ``tool_name`` and is the
    tool-side response to a bad call. The prune plugin must treat it like
    a ToolReturnPart so:
      - the parent tool call shows ``has_return=True`` (no orphan warning)
      - the message classifies as ``tool-return`` (not ``unknown``)
      - the validation error surfaces in the detail pane with a clear label
    """

    def _retry_msg(self, tool_name: str, tool_call_id: str, error: str):
        if RetryPromptPart is None:  # pragma: no cover
            import pytest

            pytest.skip("pydantic-ai version lacks RetryPromptPart")
        return ModelRequest(
            parts=[
                RetryPromptPart(
                    content=error,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                )
            ]
        )

    def test_retry_prompt_classifies_as_tool_return(self):
        history = [
            _user_msg("do it"),
            _assistant_with_tool(
                text=None, tool_name="shell", tool_call_id="tc1", args="{}"
            ),
            self._retry_msg("shell", "tc1", "validation error"),
        ]
        entries = build_message_entries(history)
        retry_entry = entries[-1]
        assert retry_entry.role == "tool-return"
        assert retry_entry.is_pure_tool_return is True
        assert "tc1" in retry_entry.tool_return_ids

    def test_retry_prompt_marks_parent_tool_call_has_return(self):
        history = [
            _user_msg("do it"),
            _assistant_with_tool(
                text=None, tool_name="shell", tool_call_id="tc1", args="{}"
            ),
            self._retry_msg("shell", "tc1", "oops"),
        ]
        entries = build_message_entries(history)
        asst = entries[1]
        assert asst.tool_calls[0].has_return is True

    def test_retry_prompt_label_in_full_text(self):
        history = [
            _user_msg("do it"),
            _assistant_with_tool(
                text=None, tool_name="shell", tool_call_id="tc1", args="{}"
            ),
            self._retry_msg("shell", "tc1", "bad args"),
        ]
        entries = build_message_entries(history)
        retry_entry = entries[-1]
        assert "retry-prompt" in retry_entry.full_text
        assert "shell" in retry_entry.full_text
        assert "bad args" in retry_entry.full_text

    def test_tool_return_message_flagged(self):
        history = [_system_msg(), _tool_return("tc-orphan")]
        entries = build_message_entries(history)
        assert len(entries) == 1
        assert entries[0].role == "tool-return"
        assert entries[0].is_pure_tool_return is True


# ───────────────────────────────────────────────────────────────────────────
# prune_model: annotate_context_window
# ───────────────────────────────────────────────────────────────────────────


class TestAnnotateContextWindow:
    def test_no_estimator_returns_unavailable(self):
        agent = SimpleNamespace()  # no estimate_tokens_for_message
        entries = [MessageEntry(history_index=1, role="user", preview="", full_text="")]
        budget = annotate_context_window(entries, [_system_msg(), _user_msg()], agent)
        assert budget.available is False
        assert all(e.tokens is None for e in entries)

    def test_fills_tokens_and_in_context(self):
        agent = MagicMock()
        agent.estimate_tokens_for_message.side_effect = lambda m: 10
        agent._get_model_context_length.return_value = 100
        agent._estimate_context_overhead.return_value = 20

        history = [_system_msg(), _user_msg("a"), _assistant_text("b")]
        entries = build_message_entries(history)
        budget = annotate_context_window(entries, history, agent)

        assert budget.available is True
        assert budget.context_length == 100
        assert budget.overhead_tokens == 20
        assert budget.out_of_context_messages == 0
        assert budget.out_of_context_tokens == 0
        for e in entries:
            assert e.tokens == 10
            # available = 100 - 20 = 80; two entries × 10 each fit easily
            assert e.in_context is True
        # used_tokens reflects in-context only (both fit, sum = 20)
        assert budget.used_tokens == 20
        # percent never exceeds 100
        assert budget.percent_used is not None
        assert budget.percent_used <= 100.0

    def test_marks_out_of_context_when_budget_blown(self):
        agent = MagicMock()
        # Each message reports a big count; budget can fit only the newest.
        agent.estimate_tokens_for_message.side_effect = lambda m: 60
        agent._get_model_context_length.return_value = 100
        agent._estimate_context_overhead.return_value = 20  # available = 80

        history = [_system_msg(), _user_msg("a"), _assistant_text("b")]
        entries = build_message_entries(history)
        annotate_context_window(entries, history, agent)

        # newest fits (60 ≤ 80), oldest does NOT (60+60 > 80)
        assert entries[-1].in_context is True
        assert entries[0].in_context is False

    def test_used_tokens_counts_only_in_context_not_overflow(self):
        """When history exceeds the budget, used_tokens reports only what
        actually fits — percent_used must never exceed 100%.
        """
        agent = MagicMock()
        agent.estimate_tokens_for_message.side_effect = lambda m: 60
        agent._get_model_context_length.return_value = 100
        agent._estimate_context_overhead.return_value = 20  # available = 80

        # Three messages × 60 = 180 tokens but only 80 fits.
        history = [
            _system_msg(),
            _user_msg("old"),
            _assistant_text("mid"),
            _user_msg("new"),
        ]
        entries = build_message_entries(history)
        budget = annotate_context_window(entries, history, agent)

        # Only the newest entry fits (60 ≤ 80; next would be 120 > 80).
        assert budget.used_tokens == 60
        assert budget.out_of_context_tokens == 120  # 2 × 60
        assert budget.out_of_context_messages == 2
        # percent stays bounded: (60 + 20) / 100 = 80%
        assert budget.percent_used == 80.0

    def test_system_message_is_always_in_context(self):
        """Even when the budget is blown, the system bundle must stay in.
        It is the agent's identity and is sent on every turn.
        """
        agent = MagicMock()
        # System takes a huge chunk; user messages are small but the
        # combination far exceeds the budget.
        token_map = {0: 9000, 1: 100, 2: 100, 3: 100}

        def _estimate(msg):
            for idx, m in enumerate(history):
                if m is msg:
                    return token_map.get(idx, 0)
            return 0

        agent.estimate_tokens_for_message.side_effect = _estimate
        agent._get_model_context_length.return_value = 10000
        agent._estimate_context_overhead.return_value = 500  # avail = 500

        history = [
            _system_plus_user_msg(),
            _assistant_text("a"),
            _user_msg("b"),
            _assistant_text("c"),
        ]
        entries = build_message_entries(history)
        annotate_context_window(entries, history, agent)

        sys_entry = next(e for e in entries if e.role == "system")
        assert sys_entry.in_context is True

    def test_system_tokens_reserved_before_others_compete(self):
        """System tokens come off the top of the budget so other messages
        only get whatever's left.
        """
        agent = MagicMock()
        # context=200, overhead=0, system=100 → only 100 left for others.
        # Two non-system messages of 60 each: one fits, the other doesn't.
        token_map = {0: 100, 1: 60, 2: 60}

        def _estimate(msg):
            for idx, m in enumerate(history):
                if m is msg:
                    return token_map.get(idx, 0)
            return 0

        agent.estimate_tokens_for_message.side_effect = _estimate
        agent._get_model_context_length.return_value = 200
        agent._estimate_context_overhead.return_value = 0

        history = [
            _system_plus_user_msg(),
            _user_msg("older"),
            _assistant_text("newest"),
        ]
        entries = build_message_entries(history)
        annotate_context_window(entries, history, agent)

        sys_entry, older, newest = entries
        assert sys_entry.in_context is True
        assert newest.in_context is True
        assert older.in_context is False

    def test_in_context_is_contiguous_tail_even_with_size_outliers(self):
        """Once a message overflows the budget, every OLDER message must also
        be marked out — even if it would individually fit. Real context
        windows are tail-truncated, not bin-packed.
        """
        agent = MagicMock()
        # Three messages, oldest-to-newest: small, HUGE, small.
        # Without the contiguous-tail rule, the huge middle one would be
        # marked out but the small oldest one would slip back in.
        token_map = {0: 10, 1: 10, 2: 10000, 3: 10}

        def _estimate(msg):
            # idx 0 is the system prompt — return any value; it'll be filtered.
            for idx, m in enumerate(history):
                if m is msg:
                    return token_map.get(idx, 0)
            return 0

        agent.estimate_tokens_for_message.side_effect = _estimate
        agent._get_model_context_length.return_value = 100
        agent._estimate_context_overhead.return_value = 0  # available = 100

        history = [
            _system_msg(),
            _user_msg("small old"),  # idx 1, 10 tokens
            _assistant_text("giant"),  # idx 2, 10000 tokens — won't fit
            _user_msg("small new"),  # idx 3, 10 tokens — fits as newest
        ]
        entries = build_message_entries(history)
        annotate_context_window(entries, history, agent)

        # entries are in history order: small-old, giant, small-new
        small_old, giant, small_new = entries
        assert small_new.in_context is True  # newest, fits
        assert giant.in_context is False  # blew the budget
        # CRUCIAL: small_old must ALSO be False even though 10 tokens fits
        # alone — once we overflow, everything older is out.
        assert small_old.in_context is False

    def test_estimator_exception_keeps_tokens_none(self):
        agent = MagicMock()
        agent.estimate_tokens_for_message.side_effect = RuntimeError("nope")
        agent._get_model_context_length.return_value = 100
        agent._estimate_context_overhead.return_value = 0

        history = [_system_msg(), _user_msg("a")]
        entries = build_message_entries(history)
        annotate_context_window(entries, history, agent)
        assert entries[0].tokens is None


# ───────────────────────────────────────────────────────────────────────────
# prune_render
# ───────────────────────────────────────────────────────────────────────────


class TestCtxIndicator:
    def test_in_context(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=True
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "●"

    def test_out_of_context(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=False
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "○"

    def test_unknown(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=None
        )
        glyph, _style = ctx_indicator(e)
        assert glyph == "·"


class TestTokensStr:
    def test_none(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", tokens=None
        )
        assert tokens_str(e) == ""

    def test_value(self):
        e = MessageEntry(
            history_index=1, role="user", preview="", full_text="", tokens=42
        )
        assert tokens_str(e) == "~42t"


class TestFormatArgsFull:
    def test_empty_uses_fallback(self):
        assert format_args_full({}, "fb") == ["fb"]
        assert format_args_full({}, "") == ["<no args>"]

    def test_non_dict_falls_back(self):
        assert format_args_full([1, 2, 3], "fb") == ["fb"]  # type: ignore[arg-type]

    def test_inline_scalars(self):
        out = format_args_full({"a": 1, "b": "short"}, "")
        assert out == ["a: 1", "b: short"]

    def test_multiline_string_block_scalar(self):
        out = format_args_full({"code": "line1\nline2"}, "")
        assert out[0] == "code: |"
        assert "line1" in out[1]
        assert "line2" in out[2]

    def test_nested_dict_recurses(self):
        out = format_args_full({"outer": {"inner": "val"}}, "")
        assert out[0] == "outer:"
        # Nested key indented under the parent
        assert any("inner: val" in line for line in out[1:])

    def test_list_renders_with_dash(self):
        out = format_args_full({"items": [1, 2, 3]}, "")
        assert out[0] == "items:"
        assert any(line.lstrip().startswith("- 1") for line in out[1:])


class TestRenderBudgetLine:
    def test_unavailable(self):
        b = ContextBudget(available=False)
        out = render_budget_line(b)
        assert "unavailable" in out[0][1]

    def test_green_under_70(self):
        b = ContextBudget(
            used_tokens=10, overhead_tokens=10, context_length=100, available=True
        )  # 20% used
        out = render_budget_line(b)
        # Style is "fg:ansigreen" (matches C_FOOTER_OK)
        assert out[0][0] == prune_model.C_FOOTER_OK

    def test_yellow_70_to_90(self):
        b = ContextBudget(
            used_tokens=40, overhead_tokens=40, context_length=100, available=True
        )  # 80%
        out = render_budget_line(b)
        assert out[0][0] == prune_model.C_FOOTER_PREVIEW

    def test_red_over_90(self):
        b = ContextBudget(
            used_tokens=50, overhead_tokens=45, context_length=100, available=True
        )  # 95%
        out = render_budget_line(b)
        assert out[0][0] == prune_model.C_SHELL

    def test_shows_overflow_when_messages_dont_fit(self):
        b = ContextBudget(
            used_tokens=70,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=500,
            out_of_context_messages=3,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        assert "out of context" in flat
        assert "500" in flat
        assert "3 older" in flat
        # Must not imply messages are destroyed.
        assert "dropped" not in flat.lower()
        assert "removed" not in flat.lower()

    def test_overflow_is_on_its_own_line(self):
        """Long overflow line shouldn't crowd the main context counter."""
        b = ContextBudget(
            used_tokens=70,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=12345,
            out_of_context_messages=9,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        # Two newlines total: one after the main line, one after overflow.
        assert flat.count("\n") == 2
        # The overflow segment must come AFTER a newline (own line).
        main_line, _, rest = flat.partition("\n")
        assert "older msg" not in main_line
        assert "older msg" in rest

    def test_hides_overflow_when_everything_fits(self):
        b = ContextBudget(
            used_tokens=30,
            overhead_tokens=10,
            context_length=100,
            out_of_context_tokens=0,
            out_of_context_messages=0,
            available=True,
        )
        flat = "".join(text for _style, text in render_budget_line(b))
        assert "overflow" not in flat


# ───────────────────────────────────────────────────────────────────────────
# PruneMenu state (no live TTY)
# ───────────────────────────────────────────────────────────────────────────


def _menu_with_history():
    """Build a PruneMenu over a small but representative history."""
    history = [
        _system_msg(),
        _user_msg("step 1"),
        _assistant_with_tool(
            text="running tests",
            tool_name="agent_run_shell_command",
            tool_call_id="tc1",
            args='{"command": "pytest"}',
        ),
        _tool_return("tc1"),
        _user_msg("step 2"),
        _assistant_with_tool(
            text="writing file",
            tool_name="create_file",
            tool_call_id="tc2",
            args='{"file_path": "x.py"}',
        ),
        _tool_return("tc2"),
    ]
    entries = build_message_entries(history)
    return PruneMenu(entries=entries, preview_only=False), entries, history


class TestPruneMenuInit:
    def test_rejects_empty_entries(self):
        with pytest.raises(ValueError):
            PruneMenu(entries=[], preview_only=False)

    def test_pure_tool_returns_hidden_from_rows(self):
        menu, entries, _ = _menu_with_history()
        # Tool-return messages should not have a "message" row; they live
        # underneath their parent's tool-call rows.
        message_rows = [r for r in menu.rows if r.kind == "message"]
        assert all(not entries[r.message_idx].is_pure_tool_return for r in message_rows)

    def test_rows_include_tool_calls(self):
        menu, _, _ = _menu_with_history()
        tool_rows = [r for r in menu.rows if r.kind == "tool_call"]
        assert {r.tool_call_id for r in tool_rows} == {"tc1", "tc2"}

    def test_rows_are_ordered_newest_first(self):
        """The newest message must be at the top of the list (row 0) so
        the cursor lands on the most recent context first."""
        menu, entries, _ = _menu_with_history()
        message_rows = [r for r in menu.rows if r.kind == "message"]
        # History indices on message rows should strictly decrease (newest
        # → oldest) because pure-tool-return entries are filtered out.
        history_idx_seq = [entries[r.message_idx].history_index for r in message_rows]
        assert history_idx_seq == sorted(history_idx_seq, reverse=True)

    def test_tool_calls_stay_below_their_parent_message(self):
        """Reversal applies to messages, not to the tool-call list inside
        a single message — those stay in invocation order under their
        parent row."""
        menu, _, _ = _menu_with_history()
        # For each tool_call row, walk backwards until we hit a message
        # row. That message row must be the parent (same message_idx).
        for i, row in enumerate(menu.rows):
            if row.kind != "tool_call":
                continue
            j = i - 1
            while j >= 0 and menu.rows[j].kind != "message":
                j -= 1
            assert j >= 0, f"tool_call row at index {i} has no parent"
            assert menu.rows[j].message_idx == row.message_idx


class TestPruneMenuSelection:
    def test_toggle_message_adds_and_removes(self):
        menu, _, _ = _menu_with_history()
        # Cursor on a message row by construction (first row is message)
        first_msg_row = next(i for i, r in enumerate(menu.rows) if r.kind == "message")
        menu.cursor = first_msg_row
        menu._toggle_current()
        assert menu.rows[first_msg_row].message_idx in menu.selected_messages
        menu._toggle_current()
        assert menu.rows[first_msg_row].message_idx not in menu.selected_messages

    def test_toggle_message_clears_child_tool_calls(self):
        menu, _, _ = _menu_with_history()
        # Find the assistant message with tool calls + one of its tool-call rows
        tc_row_idx = next(i for i, r in enumerate(menu.rows) if r.kind == "tool_call")
        tc_row = menu.rows[tc_row_idx]
        # Pre-select the tool call directly
        menu.selected_tool_calls.add((tc_row.message_idx, tc_row.tool_call_id))
        # Now toggle the parent message
        parent_row_idx = next(
            i
            for i, r in enumerate(menu.rows)
            if r.kind == "message" and r.message_idx == tc_row.message_idx
        )
        menu.cursor = parent_row_idx
        menu._toggle_current()
        assert tc_row.message_idx in menu.selected_messages
        # Tool-call selection was wiped
        assert not any(m == tc_row.message_idx for (m, _) in menu.selected_tool_calls)

    def test_toggle_tool_call_noop_when_parent_selected(self):
        menu, _, _ = _menu_with_history()
        tc_row_idx = next(i for i, r in enumerate(menu.rows) if r.kind == "tool_call")
        tc_row = menu.rows[tc_row_idx]
        menu.selected_messages.add(tc_row.message_idx)
        menu.cursor = tc_row_idx
        before = set(menu.selected_tool_calls)
        menu._toggle_current()
        assert menu.selected_tool_calls == before

    def test_toggle_tool_call_adds_and_removes(self):
        menu, _, _ = _menu_with_history()
        tc_row_idx = next(i for i, r in enumerate(menu.rows) if r.kind == "tool_call")
        tc_row = menu.rows[tc_row_idx]
        menu.cursor = tc_row_idx
        menu._toggle_current()
        assert (tc_row.message_idx, tc_row.tool_call_id) in menu.selected_tool_calls
        menu._toggle_current()
        assert (tc_row.message_idx, tc_row.tool_call_id) not in menu.selected_tool_calls

    def test_system_row_is_not_toggleable(self):
        """Pressing space on a system row must be a no-op so the user
        cannot accidentally select the agent's identity for removal.
        """
        history = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        budget = ContextBudget()
        menu = PruneMenu(entries=entries, preview_only=False, budget=budget)
        # Find the system row's index and put cursor on it.
        sys_row_idx = next(
            i
            for i, r in enumerate(menu.rows)
            if r.kind == "message" and menu.entries[r.message_idx].role == "system"
        )
        menu.cursor = sys_row_idx
        menu._toggle_current()
        # System message_idx must NOT appear in selected_messages.
        sys_msg_idx = menu.rows[sys_row_idx].message_idx
        assert sys_msg_idx not in menu.selected_messages

    def test_select_all_skips_system_rows(self):
        history = [
            _system_plus_user_msg(),
            _assistant_text("hi"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries, preview_only=False)
        menu._select_all()
        # Find system entry's msg_idx — it must be excluded.
        sys_msg_idx = next(i for i, e in enumerate(menu.entries) if e.role == "system")
        assert sys_msg_idx not in menu.selected_messages

    def test_select_all_clears_individual_tool_call_selections(self):
        menu, _, _ = _menu_with_history()
        tc_row = next(r for r in menu.rows if r.kind == "tool_call")
        menu.selected_tool_calls.add((tc_row.message_idx, tc_row.tool_call_id))
        menu._select_all()
        assert menu.selected_tool_calls == set()
        assert menu.selected_messages  # at least one message selected

    def test_clear_all(self):
        menu, _, _ = _menu_with_history()
        menu.selected_messages.add(0)
        menu.selected_tool_calls.add((0, "tc1"))
        menu._clear_all()
        assert menu.selected_messages == set()
        assert menu.selected_tool_calls == set()

    def test_row_is_checked_implied(self):
        menu, _, _ = _menu_with_history()
        tc_row = next(r for r in menu.rows if r.kind == "tool_call")
        menu.selected_messages.add(tc_row.message_idx)
        checked, implied = menu._row_is_checked(tc_row)
        assert checked is True and implied is True

    def test_selection_has_side_effects_via_message(self):
        menu, _, _ = _menu_with_history()
        # Both tool calls in our fixture are side-effecting (shell + write).
        # Selecting any assistant message should trip the flag.
        msg_row = next(
            r
            for r in menu.rows
            if r.kind == "message" and menu.entries[r.message_idx].tool_calls
        )
        menu.selected_messages.add(msg_row.message_idx)
        assert menu._selection_has_side_effects() is True

    def test_selection_has_side_effects_via_tool_call(self):
        menu, _, _ = _menu_with_history()
        tc_row = next(r for r in menu.rows if r.kind == "tool_call")
        menu.selected_tool_calls.add((tc_row.message_idx, tc_row.tool_call_id))
        assert menu._selection_has_side_effects() is True


class TestPruneMenuBuildSelection:
    def test_maps_message_idx_to_history_index(self):
        menu, entries, _ = _menu_with_history()
        first_msg_row = next(r for r in menu.rows if r.kind == "message")
        menu.selected_messages.add(first_msg_row.message_idx)
        sel = menu._build_selection()
        assert (
            entries[first_msg_row.message_idx].history_index
            in sel.history_indices_to_drop
        )

    def test_tool_call_ids_passed_through(self):
        menu, _, _ = _menu_with_history()
        tc_row = next(r for r in menu.rows if r.kind == "tool_call")
        menu.selected_tool_calls.add((tc_row.message_idx, tc_row.tool_call_id))
        sel = menu._build_selection()
        assert tc_row.tool_call_id in sel.tool_call_ids_to_drop


# ───────────────────────────────────────────────────────────────────────────
# Plugin command handlers
# ───────────────────────────────────────────────────────────────────────────


class TestCustomCommand:
    def test_custom_help_lists_prune(self):
        entries = dict(_plugin_module()._custom_help())
        assert "prune" in entries

    def test_handle_custom_command_ignores_others(self):
        assert _plugin_module()._handle_custom_command("/nope", "nope") is None


# ───────────────────────────────────────────────────────────────────────────
# _collect_removed_tool_call_ids
# ───────────────────────────────────────────────────────────────────────────


class TestCollectRemovedToolCallIds:
    def test_includes_explicit_ids(self):
        mod = _plugin_module()
        ids = mod._collect_removed_tool_call_ids([], set(), {"a", "b"})
        assert ids == {"a", "b"}

    def test_pulls_tool_call_ids_from_dropped_messages(self):
        mod = _plugin_module()
        history = [
            _system_msg(),
            _assistant_with_tool(
                text=None, tool_name="create_file", tool_call_id="tc-x"
            ),
        ]
        ids = mod._collect_removed_tool_call_ids(history, {1}, set())
        assert ids == {"tc-x"}

    def test_unions_both_sources(self):
        mod = _plugin_module()
        history = [
            _system_msg(),
            _assistant_with_tool(
                text=None, tool_name="create_file", tool_call_id="tc-x"
            ),
        ]
        ids = mod._collect_removed_tool_call_ids(history, {1}, {"tc-explicit"})
        assert ids == {"tc-x", "tc-explicit"}

    def test_ignores_out_of_range(self):
        mod = _plugin_module()
        ids = mod._collect_removed_tool_call_ids([_system_msg()], {99}, set())
        assert ids == set()


# ───────────────────────────────────────────────────────────────────────────
# _filter_message_parts
# ───────────────────────────────────────────────────────────────────────────


class TestFilterMessageParts:
    def test_response_drops_matching_tool_call(self):
        mod = _plugin_module()
        msg = ModelResponse(
            parts=[
                TextPart(content="kept"),
                ToolCallPart(tool_name="t", args="{}", tool_call_id="drop-me"),
            ]
        )
        new_msg, n_calls, n_returns = mod._filter_message_parts(msg, {"drop-me"}, set())
        assert n_calls == 1
        assert n_returns == 0
        assert new_msg is not None
        assert all(not isinstance(p, ToolCallPart) for p in new_msg.parts)

    def test_response_collapses_when_empty(self):
        mod = _plugin_module()
        msg = ModelResponse(
            parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="drop-me")]
        )
        new_msg, n_calls, _ = mod._filter_message_parts(msg, {"drop-me"}, set())
        assert new_msg is None
        assert n_calls == 1

    def test_request_drops_matching_tool_return(self):
        mod = _plugin_module()
        msg = _tool_return("ret-id")
        new_msg, _, n_returns = mod._filter_message_parts(msg, set(), {"ret-id"})
        assert n_returns == 1
        assert new_msg is None  # collapsed

    def test_no_drops_returns_original(self):
        mod = _plugin_module()
        msg = _assistant_text("hi")
        new_msg, n_calls, n_returns = mod._filter_message_parts(msg, set(), set())
        assert new_msg is msg
        assert (n_calls, n_returns) == (0, 0)


# ───────────────────────────────────────────────────────────────────────────
# _prune_dangling_tool_fragments
# ───────────────────────────────────────────────────────────────────────────


class TestPruneDanglingToolFragments:
    def test_removes_orphan_return_tail(self):
        mod = _plugin_module()
        system = _system_msg()
        reply = _assistant_text("hi")
        orphan = _tool_return("tc-orphan")
        cleaned, extra = mod._prune_dangling_tool_fragments([system, reply, orphan])
        assert cleaned == [system, reply]
        assert extra == 1

    def test_leaves_matched_call_return_pair_alone(self):
        """prune's pruner is smarter than pop's — paired call/return at the
        tail is NOT dangling, so it stays put."""
        mod = _plugin_module()
        system = _system_msg()
        text = _assistant_text("hi")
        call = ModelResponse(
            parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="tc1")]
        )
        ret = _tool_return("tc1")
        cleaned, extra = mod._prune_dangling_tool_fragments([system, text, call, ret])
        assert cleaned == [system, text, call, ret]
        assert extra == 0

    def test_removes_orphan_tool_call_at_tail(self):
        """A tool call without a matching return IS dangling."""
        mod = _plugin_module()
        system = _system_msg()
        text = _assistant_text("hi")
        orphan_call = ModelResponse(
            parts=[ToolCallPart(tool_name="t", args="{}", tool_call_id="orphan")]
        )
        cleaned, extra = mod._prune_dangling_tool_fragments([system, text, orphan_call])
        assert cleaned == [system, text]
        assert extra == 1

    def test_idempotent_on_clean_history(self):
        mod = _plugin_module()
        history = [_system_msg(), _assistant_text("hi")]
        cleaned, extra = mod._prune_dangling_tool_fragments(history)
        assert cleaned == history
        assert extra == 0


# ───────────────────────────────────────────────────────────────────────────
# _perform_prune end-to-end
# ───────────────────────────────────────────────────────────────────────────


class TestPerformPrune:
    def test_empty_history_emits_warning(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_warning"
            ) as mock_warn,
        ):
            _plugin_module()._perform_prune({1}, set())
        agent.set_message_history.assert_not_called()
        mock_warn.assert_called_once()

    def test_nothing_selected_emits_info(self):
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            _plugin_module()._perform_prune(set(), set())
        agent.set_message_history.assert_not_called()
        mock_info.assert_called_once()

    def test_drops_system_prompt_index_defensively(self):
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            # Caller maliciously asked us to drop index 0 — should be a no-op.
            _plugin_module()._perform_prune({0}, set())
        agent.set_message_history.assert_not_called()
        mock_info.assert_called_once()

    def test_drops_message_and_matching_tool_return(self):
        """Selecting the assistant message should also nuke its return."""
        system = _system_msg()
        user = _user_msg("step 1")
        asst = _assistant_with_tool(
            text=None, tool_name="create_file", tool_call_id="tc1"
        )
        ret = _tool_return("tc1")
        followup = _user_msg("step 2")

        agent = MagicMock()
        agent.get_message_history.return_value = [system, user, asst, ret, followup]

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_success"),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            # Drop the assistant message (index 2). Its tool-return at index 3
            # should be collapsed away as a side effect.
            _plugin_module()._perform_prune({2}, set())

        agent.set_message_history.assert_called_once()
        new_history = agent.set_message_history.call_args[0][0]
        assert new_history == [system, user, followup]

    def test_drops_individual_tool_call_and_its_return(self):
        """Surgical tool-call removal: parent message survives, return goes."""
        system = _system_msg()
        asst = ModelResponse(
            parts=[
                TextPart(content="doing work"),
                ToolCallPart(tool_name="create_file", args="{}", tool_call_id="keep"),
                ToolCallPart(tool_name="create_file", args="{}", tool_call_id="drop"),
            ]
        )
        ret_keep = _tool_return("keep")
        ret_drop = _tool_return("drop")

        agent = MagicMock()
        agent.get_message_history.return_value = [system, asst, ret_keep, ret_drop]

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_success"),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            _plugin_module()._perform_prune(set(), {"drop"})

        new_history = agent.set_message_history.call_args[0][0]
        # System + (assistant with one tool call) + the "keep" return remain.
        assert len(new_history) == 3
        kept_asst = new_history[1]
        kept_tool_call_ids = [
            p.tool_call_id for p in kept_asst.parts if isinstance(p, ToolCallPart)
        ]
        assert kept_tool_call_ids == ["keep"]

    def test_set_history_failure_emits_error(self):
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]
        agent.set_message_history.side_effect = RuntimeError("boom")

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_error"
            ) as mock_error,
        ):
            _plugin_module()._perform_prune({1}, set())

        mock_error.assert_called_once()


# ───────────────────────────────────────────────────────────────────────────
# _handle_prune_command (dispatch + preview path)
# ───────────────────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────────────────
# Smoke tests for full render paths (mostly to keep coverage honest)
# ───────────────────────────────────────────────────────────────────────────


def _flatten(formatted) -> str:
    """Collapse a prompt_toolkit-style [(style, text), ...] list to a string."""
    return "".join(text for _style, text in formatted)


class TestRenderLegend:
    def test_legend_lists_all_three_glyphs(self):
        flat = "".join(text for _style, text in render_legend())
        assert "●" in flat
        assert "○" in flat
        assert "·" in flat
        assert "in context" in flat
        assert "out of context" in flat

    def test_legend_does_not_falsely_imply_overflow_is_prunable_or_gone(self):
        """Pruning ○ messages doesn't free up budget — they're already
        being skipped by the model. Conversely, they're NOT destroyed:
        if newer messages get pruned, older ○ ones slide back in. The
        legend must convey neither false implication.
        """
        flat = "".join(text for _style, text in render_legend()).lower()
        assert "drop candidate" not in flat
        assert "dropped" not in flat
        assert "removed" not in flat
        assert "gone" not in flat

    def test_legend_uses_in_context_color_for_filled_dot(self):
        out = render_legend()
        green_segments = [seg for seg in out if "●" in seg[1]]
        assert green_segments, "Expected a segment containing the green dot"
        assert green_segments[0][0] == prune_model.C_FOOTER_OK


class TestRenderListSmoke:
    def test_renders_title_and_rows(self):
        menu, _entries, _ = _menu_with_history()
        out = render_list(menu)
        flat = _flatten(out)
        assert "prune" in flat
        # Each visible message row prefixes its history index.
        assert "user" in flat or "asst" in flat

    def test_renders_legend_under_budget(self):
        menu, _, _ = _menu_with_history()
        flat = _flatten(render_list(menu))
        assert "legend:" in flat
        assert "in context" in flat

    def test_preview_mode_changes_title(self):
        menu, _, _ = _menu_with_history()
        menu.preview_only = True
        flat = _flatten(render_list(menu))
        assert "preview" in flat

    def test_renders_with_selection(self):
        menu, _, _ = _menu_with_history()
        menu.selected_messages.add(
            next(r.message_idx for r in menu.rows if r.kind == "message")
        )
        flat = _flatten(render_list(menu))
        # Footer should reflect the selection count.
        assert "1 message" in flat

    def test_renders_when_viewport_clipped(self):
        """Force hidden-above/below indicators to appear."""
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 1
        menu.cursor = len(menu.rows) - 1
        menu._scroll_into_view()
        flat = _flatten(render_list(menu))
        assert "more above" in flat


class TestRenderDetailSmoke:
    def test_message_detail(self):
        menu, _, _ = _menu_with_history()
        # Cursor on the first message row
        menu.cursor = next(i for i, r in enumerate(menu.rows) if r.kind == "message")
        flat = _flatten(render_detail(menu))
        assert "message" in flat
        assert "history index" in flat

    def test_tool_call_detail(self):
        menu, _, _ = _menu_with_history()
        menu.cursor = next(i for i, r in enumerate(menu.rows) if r.kind == "tool_call")
        flat = _flatten(render_detail(menu))
        assert "tool call" in flat
        # Our fixture's tool calls all have returns, so the warning is absent.
        assert "no matching return" not in flat

    def test_message_detail_surfaces_thinking_block_count(self):
        """When an assistant turn carried thinking content, the metadata
        line should call it out so the user can find it in full_text.
        """
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="answer", thinking="reasoning here"),
        ]
        entries = build_message_entries(history)
        menu = PruneMenu(entries=entries, preview_only=False)
        # Put cursor on the assistant row.
        menu.cursor = next(
            i
            for i, r in enumerate(menu.rows)
            if r.kind == "message" and menu.entries[r.message_idx].role == "assistant"
        )
        flat = _flatten(render_detail(menu))
        assert "thinking block" in flat
        # And the full text section must include the fenced reasoning.
        assert "reasoning here" in flat

    def test_side_effect_warning_when_selected(self):
        menu, _, _ = _menu_with_history()
        # Select an assistant message containing a side-effecting tool call.
        for r in menu.rows:
            if r.kind == "message" and menu.entries[r.message_idx].tool_calls:
                menu.selected_messages.add(r.message_idx)
                menu.cursor = next(i for i, rr in enumerate(menu.rows) if rr is r)
                break
        flat = _flatten(render_detail(menu))
        assert "side-effecting" in flat

    def test_ctx_detail_text_branches(self):
        e_in = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=True
        )
        e_out = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=False
        )
        e_unknown = MessageEntry(
            history_index=1, role="user", preview="", full_text="", in_context=None
        )
        assert "in context" in ctx_detail_text(e_in)
        assert "out of context" in ctx_detail_text(e_out)
        # Out-of-context wording must not imply messages are gone.
        out_lower = ctx_detail_text(e_out).lower()
        assert "dropped" not in out_lower
        assert "removed" not in out_lower
        assert ctx_detail_text(e_unknown) == ""


class TestPruneMenuViewport:
    def test_scroll_into_view_clamps_top(self):
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 2
        menu.cursor = len(menu.rows) - 1
        menu._scroll_into_view()
        assert menu.viewport_top + menu._visible_rows >= menu.cursor + 1

    def test_scroll_into_view_jumps_up_when_cursor_above(self):
        menu, _, _ = _menu_with_history()
        menu._visible_rows = 2
        menu.viewport_top = 3
        menu.cursor = 0
        menu._scroll_into_view()
        assert menu.viewport_top == 0

    def test_update_display_resets_detail_scroll_on_cursor_move(self):
        menu, _, _ = _menu_with_history()
        menu.detail_scroll = 5
        menu._last_cursor_for_detail = 0
        menu.cursor = 1
        menu._update_display()
        assert menu.detail_scroll == 0


class TestHandlePruneCommand:
    def test_empty_history_bails_out(self):
        agent = MagicMock()
        agent.get_message_history.return_value = []
        agent.get_full_system_prompt.return_value = ""
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_info.assert_called_once()
        assert "no prunable messages" in mock_info.call_args.args[0].lower()

    def test_only_system_entries_bails_out(self):
        """With a non-empty raw history of just a system message, the
        synthetic system row is the only entry — and it's non-prunable —
        so we should bail out gracefully.
        """
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg()]
        agent.get_full_system_prompt.return_value = "you are a puppy"
        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch("code_puppy.plugins.prune.register_callbacks.emit_info") as mock_info,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_info.assert_called_once()

    def test_get_agent_failure_emits_error(self):
        bad_manager = SimpleNamespace(
            get_current_agent=MagicMock(side_effect=RuntimeError("kaboom"))
        )
        with (
            patch.dict(sys.modules, {"code_puppy.agents.agent_manager": bad_manager}),
            patch(
                "code_puppy.plugins.prune.register_callbacks.emit_error"
            ) as mock_error,
        ):
            result = _plugin_module()._handle_custom_command("/prune", "prune")
        assert result is True
        mock_error.assert_called_once()

    def test_preview_flag_parsed(self):
        """`/prune preview` should hit the PruneMenu with preview_only=True."""
        agent = MagicMock()
        agent.get_message_history.return_value = [_system_msg(), _assistant_text("hi")]

        fake_menu_instance = MagicMock()
        fake_menu_instance.run.return_value = None  # user cancels

        with (
            patch.dict(
                sys.modules,
                {"code_puppy.agents.agent_manager": _agent_manager_module(agent)},
            ),
            patch(
                "code_puppy.plugins.prune.prune_menu.PruneMenu",
                return_value=fake_menu_instance,
            ) as mock_menu,
            patch("code_puppy.plugins.prune.register_callbacks.emit_info"),
        ):
            _plugin_module()._handle_custom_command("/prune preview", "prune")

        _args, kwargs = mock_menu.call_args
        assert kwargs.get("preview_only") is True
