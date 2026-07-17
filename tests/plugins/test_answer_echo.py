"""Tests for the ``answer_echo`` plugin.

The plugin's job is small but easy to get wrong — a one-line-per-question
echo of ``ask_user_question`` answers to scrollback after the alt-screen TUI
exits. It must:

- be a no-op for any tool that isn't ``ask_user_question``
- render multi-question answers as ``Q1 → A; Q2 → A``
- surface cancellations / timeouts / errors as a single dim line
- swallow any exception so echo never breaks the agent
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from code_puppy.plugins.answer_echo.register_callbacks import (
    _build_summary,
    _emit,
    _format_selection,
    _on_post_tool_call,
    _terminal_outcome_line,
    _truncate,
)


# ----------------------------- helpers -------------------------------------


def _answer(header: str, selected: list[str], other_text: str | None = None):
    return SimpleNamespace(
        question_header=header,
        selected_options=selected,
        other_text=other_text,
    )


def _result(answers, *, cancelled=False, timed_out=False, error=None):
    return SimpleNamespace(
        answers=answers,
        cancelled=cancelled,
        timed_out=timed_out,
        error=error,
    )


# ----------------------------- formatters ----------------------------------


class TestFormatSelection:
    def test_single_choice(self):
        a = _answer("Database", ["PostgreSQL"])
        assert _format_selection(a) == "PostgreSQL"

    def test_multi_choice_joined_with_comma(self):
        a = _answer("Stack", ["React", "Vue"])
        assert _format_selection(a) == "React, Vue"

    def test_other_text_replaces_label(self):
        a = _answer("Stack", [], other_text="Svelte + Astro")
        assert "Svelte + Astro" in _format_selection(a)
        assert "Other:" in _format_selection(a)

    def test_other_text_appended_after_labels(self):
        a = _answer("Stack", ["React"], other_text="plus Vue")
        formatted = _format_selection(a)
        # both should be present, in order: label then Other
        assert formatted.index("React") < formatted.index("Other:")

    def test_empty_returns_marker(self):
        assert _format_selection(None) == "(no selection)"
        assert _format_selection(_answer("Q", [], None)) == "(no selection)"


class TestBuildSummary:
    def test_single_question(self):
        result = _result([_answer("Database", ["PostgreSQL"])])
        assert _build_summary(result) == "Database → PostgreSQL"

    def test_multi_question_joined_with_semicolon(self):
        result = _result(
            [
                _answer("Database", ["PostgreSQL"]),
                _answer("Cache", ["Redis"]),
            ]
        )
        assert _build_summary(result) == "Database → PostgreSQL; Cache → Redis"

    def test_long_header_is_truncated(self):
        long_header = "x" * 200
        result = _result([_answer(long_header, ["Yes"])])
        summary = _build_summary(result)
        assert len(summary) < 200 + 50
        assert summary.endswith("Yes")

    def test_empty_answers_returns_empty(self):
        assert _build_summary(_result([])) == ""

    def test_truncates_at_200_chars(self):
        # Build a result whose formatted summary clearly exceeds 200 chars
        answers = [
            _answer(f"Question {i}", [f"Answer {i} " + "x" * 30]) for i in range(8)
        ]
        result = _result(answers)
        summary = _build_summary(result)
        assert len(summary) <= 200

    def test_other_text_appears_in_summary(self):
        result = _result([_answer("Name", [], other_text="Bob")])
        summary = _build_summary(result)
        assert "Name" in summary
        assert "Bob" in summary


class TestTerminalOutcomeLine:
    def test_cancelled(self):
        r = _result([], cancelled=True)
        line = _terminal_outcome_line(r)
        assert "cancelled" in line.lower()

    def test_timed_out(self):
        r = _result([], timed_out=True)
        line = _terminal_outcome_line(r)
        assert "timed" in line.lower()

    def test_error(self):
        r = _result([], error="boom")
        line = _terminal_outcome_line(r)
        assert "boom" in line

    def test_success_returns_empty(self):
        r = _result([_answer("Q", ["A"])])
        assert _terminal_outcome_line(r) == ""


class TestTruncate:
    def test_short_unchanged(self):
        assert _truncate("hello", 60) == "hello"

    def test_long_truncated_with_ellipsis(self):
        out = _truncate("x" * 100, 10)
        assert len(out) <= 10
        assert out.endswith("…")

    def test_collapses_whitespace(self):
        assert _truncate("  a   b  \n c ", 60) == "a b c"

    def test_handles_none(self):
        assert _truncate(None, 60) == ""


# ----------------------------- handler --------------------------------------


class TestOnPostToolCall:
    @pytest.mark.asyncio
    async def test_other_tool_is_noop(self):
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="read_file",
                tool_args={},
                result=SimpleNamespace(),
                duration_ms=10,
            )
        emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_emits_summary(self):
        result = _result(
            [
                _answer("Database", ["PostgreSQL"]),
                _answer("Cache", ["Redis"]),
            ]
        )
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )
        # _emit called once with the summary text, not dim
        emit.assert_called_once()
        args, kwargs = emit.call_args
        text, *_ = args
        assert "Database" in text and "Cache" in text
        assert text.startswith("▸")
        assert not kwargs.get("dim")

    @pytest.mark.asyncio
    async def test_cancelled_emits_dim(self):
        result = _result([], cancelled=True)
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )
        emit.assert_called_once()
        args, kwargs = emit.call_args
        assert "cancelled" in args[0].lower()
        assert kwargs.get("dim") is True

    @pytest.mark.asyncio
    async def test_timed_out_emits_dim(self):
        result = _result([], timed_out=True)
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )
        emit.assert_called_once()
        assert "timed" in emit.call_args.args[0].lower()

    @pytest.mark.asyncio
    async def test_error_emits_dim(self):
        result = _result([], error="Bad payload")
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )
        emit.assert_called_once()
        assert "Bad payload" in emit.call_args.args[0]

    @pytest.mark.asyncio
    async def test_non_typed_result_skipped(self):
        """Duck-typed result without `answers` attribute should not crash
        and should not emit (we don't know how to format it)."""
        result = SimpleNamespace(cancelled=False)  # no .answers
        with patch("code_puppy.plugins.answer_echo.register_callbacks._emit") as emit:
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )
        emit.assert_not_called()

    @pytest.mark.asyncio
    async def test_unrelated_exception_swallowed(self):
        """If formatting raises (e.g. weird result type), the handler must
        not propagate — echo is a UX nicety, never a correctness requirement."""
        result = _result([_answer("Q", ["A"])])
        with patch(
            "code_puppy.plugins.answer_echo.register_callbacks._build_summary",
            side_effect=RuntimeError("boom"),
        ):
            # Must not raise
            await _on_post_tool_call(
                tool_name="ask_user_question",
                tool_args={},
                result=result,
                duration_ms=10,
            )


class TestEmitFallback:
    def test_emit_uses_emit_info_when_available(self):
        with patch("code_puppy.messaging.emit_info") as emit_info:
            _emit("hello")
        emit_info.assert_called_once_with("hello")

    def test_emit_uses_dim_markup(self):
        with patch("code_puppy.messaging.emit_info") as emit_info:
            _emit("hello", dim=True)
        emit_info.assert_called_once()
        # the markup is wrapped in [dim]...[/dim]
        assert "[dim]hello[/dim]" in emit_info.call_args.args[0]

    def test_emit_empty_string_noop(self):
        with patch("code_puppy.messaging.emit_info") as emit_info:
            _emit("")
        emit_info.assert_not_called()

    def test_emit_falls_back_to_stderr_when_bus_unavailable(self):
        # Simulate the message bus itself raising — echo must still write
        # somewhere rather than silently lose the line.
        import io

        buf = io.StringIO()
        with patch(
            "code_puppy.messaging.emit_info", side_effect=RuntimeError("bus down")
        ):
            with patch("sys.stderr", buf):
                _emit("hello world")
        assert "hello world" in buf.getvalue()
