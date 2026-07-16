"""Tests for ``code_puppy.plugins.prune.prune_model``.

Covers the data layer: string/arg helpers, tool classifier, the
``MessageEntry`` lock invariant, ``build_message_entries`` parsing of
pydantic-ai history (incl. thinking + retry-prompt parts), and
``annotate_context_window`` budget bookkeeping.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
)

from code_puppy.plugins.prune.prune_model import (
    MessageEntry,
    annotate_context_window,
    build_message_entries,
    classify_tool,
    short_args,
    short_str,
)

from ._helpers import (
    RetryPromptPart,
    ThinkingPart,
    _assistant_text,
    _assistant_with_thinking,
    _assistant_with_tool,
    _system_msg,
    _system_plus_user_msg,
    _tool_return,
    _user_msg,
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
# prune_model: MessageEntry.is_locked invariant
# ───────────────────────────────────────────────────────────────────────────


class TestMessageEntryIsLocked:
    """The lock invariant fires on content (role == "system"), not
    position. ``build_message_entries`` already assigns ``role='system'``
    to any entry carrying a ``SystemPromptPart`` — including pydantic-
    ai's bundled system+user request at ``history[0]`` — so the bundle
    stays locked while a pure first-user message is now prunable.
    """

    def test_role_system_is_locked(self):
        entry = MessageEntry(history_index=5, role="system", preview="x", full_text="x")
        assert entry.is_locked is True

    def test_history_index_0_with_user_role_is_now_prunable(self):
        """Non-Anthropic transports put a plain UserPromptPart at
        history[0]; users must be allowed to prune it. Previously this
        was locked by a position-based check.
        """
        entry = MessageEntry(history_index=0, role="user", preview="x", full_text="x")
        assert entry.is_locked is False

    def test_regular_user_entry_is_not_locked(self):
        entry = MessageEntry(history_index=3, role="user", preview="x", full_text="x")
        assert entry.is_locked is False

    def test_assistant_entry_is_not_locked(self):
        entry = MessageEntry(
            history_index=1, role="assistant", preview="x", full_text="x"
        )
        assert entry.is_locked is False

    def test_history_index_0_with_system_role_remains_locked(self):
        """Anthropic-style: pydantic-ai bundles SystemPromptPart +
        UserPromptPart at history[0] and build_message_entries tags it
        ``role='system'``. The bundle must stay locked.
        """
        entry = MessageEntry(history_index=0, role="system", preview="x", full_text="x")
        assert entry.is_locked is True


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

    def test_no_synthetic_system_entry_is_injected(self):
        """build_message_entries must never invent a synthetic sys row.

        Earlier versions accepted an ``agent`` argument and synthesised a
        sys row from ``agent.get_full_system_prompt()``, which produced a
        duplicate at index 1 whenever the first user message already had
        the system prompt folded into it (e.g. claude-code OAuth). The
        agent argument is gone entirely now — the bug is impossible by
        construction — but we keep this regression test to lock in the
        "no synthetic sys row" contract.
        """
        history = [_user_msg("hi"), _assistant_text("hello!")]
        entries = build_message_entries(history)
        # No synthetic system row at the top — just the real history.
        assert all(e.role != "system" for e in entries)
        assert entries[0].role == "user"
        assert entries[1].role == "assistant"

    def test_real_system_role_from_history_is_preserved(self):
        """When raw history contains a bundled system+user ModelRequest, the
        real sys entry is kept (and is the only sys entry — no synthetic).
        """
        history = [_system_plus_user_msg(), _assistant_text("hi")]
        entries = build_message_entries(history)
        sys_entries = [e for e in entries if e.role == "system"]
        assert len(sys_entries) == 1
        # And it's the REAL one (positive history_index), not synthetic.
        assert sys_entries[0].history_index >= 0


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

    def test_thinking_segments_captured_alongside_text(self):
        history = [
            _user_msg("why"),
            _assistant_with_thinking(text="a", thinking="b"),
        ]
        entries = build_message_entries(history)
        assert entries[-1].thinking_segments == ["b"]

    def test_thinking_segments_captured_alongside_tool_calls(self):
        """Even when an assistant turn fires tool calls, the chain-of-
        thought content must still be captured so the detail pane can
        surface it.
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
        assert entries[-1].thinking_segments == ["plan"]
        assert entries[-1].tool_calls  # tool calls preserved too

    def test_no_thinking_means_no_segments(self):
        history = [_user_msg("hi"), _assistant_text("hello")]
        entries = build_message_entries(history)
        assert entries[-1].thinking_segments == []


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
        from types import SimpleNamespace

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
