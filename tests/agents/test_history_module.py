"""Tests for code_puppy.agents._history — pure helper functions.

These replace a pile of coverage-chasing tests of BaseAgent internals from
before the Phase-1..3 refactor. They test the public-ish surface of the new
``_history`` module directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from code_puppy.agents._history import (
    estimate_context_overhead,
    estimate_tokens,
    estimate_tokens_for_message,
    filter_huge_messages,
    has_pending_tool_calls,
    hash_message,
    prune_interrupted_tool_calls,
    stringify_part,
)

# ---- estimate_tokens --------------------------------------------------------


class TestEstimateTokens:
    def test_simple_text(self):
        # "hello world" -> 11 chars / 2.5 = 4
        assert estimate_tokens("hello world") == 4

    def test_empty_string_returns_at_least_one(self):
        assert estimate_tokens("") == 1

    def test_single_char(self):
        # 1 / 2.5 = 0 -> floor -> clamped to 1
        assert estimate_tokens("a") == 1

    def test_large_text_formula(self):
        text = "x" * 250
        # 250 / 2.5 = 100
        assert estimate_tokens(text) == 100

    @pytest.mark.parametrize(
        "length,expected", [(1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (6, 2), (10, 4)]
    )
    def test_formula_precision(self, length, expected):
        assert estimate_tokens("x" * length) == expected


# ---- stringify_part ---------------------------------------------------------


class TestStringifyPart:
    def test_text_part(self):
        part = TextPart(content="hello")
        result = stringify_part(part)
        assert "TextPart" in result
        assert "content=hello" in result

    def test_tool_call_part(self):
        part = ToolCallPart(
            tool_name="read_file", args={"path": "x"}, tool_call_id="abc"
        )
        result = stringify_part(part)
        assert "ToolCallPart" in result
        assert "tool_name=read_file" in result
        assert "tool_call_id=abc" in result

    def test_tool_return_part(self):
        part = ToolReturnPart(
            tool_name="read_file", content="file data", tool_call_id="abc"
        )
        result = stringify_part(part)
        assert "ToolReturnPart" in result
        assert "tool_call_id=abc" in result
        assert "content=file data" in result

    def test_binary_content_hashed_not_embedded(self):
        part = MagicMock()
        part.__class__.__name__ = "FakePart"
        part.role = None
        part.instructions = None
        part.tool_call_id = None
        part.tool_name = None
        part.content = [BinaryContent(data=b"abc123", media_type="image/png")]
        result = stringify_part(part)
        assert "BinaryContent=" in result
        assert "abc123" not in result  # raw bytes must NOT leak into the hash string

    def test_none_content(self):
        part = MagicMock()
        part.__class__.__name__ = "EmptyPart"
        part.role = None
        part.instructions = None
        part.tool_call_id = None
        part.tool_name = None
        part.content = None
        assert "content=None" in stringify_part(part)


# ---- hash_message -----------------------------------------------------------


class TestHashMessage:
    def test_same_content_same_hash(self):
        a = ModelRequest([TextPart("hello")])
        b = ModelRequest([TextPart("hello")])
        assert hash_message(a) == hash_message(b)

    def test_different_content_different_hash(self):
        a = ModelRequest([TextPart("hello")])
        b = ModelRequest([TextPart("world")])
        assert hash_message(a) != hash_message(b)

    def test_stable_across_calls(self):
        msg = ModelResponse([TextPart("stable")])
        assert hash_message(msg) == hash_message(msg)


# ---- estimate_tokens_for_message -------------------------------------------


class TestEstimateTokensForMessage:
    def test_single_text_part(self):
        msg = ModelRequest([TextPart("hello")])
        assert estimate_tokens_for_message(msg) >= 1

    def test_multiple_parts_sums(self):
        small = ModelRequest([TextPart("hi")])
        big = ModelRequest([TextPart("hello"), TextPart("world " * 100)])
        assert estimate_tokens_for_message(big) > estimate_tokens_for_message(small)

    def test_empty_parts_minimum_one(self):
        msg = MagicMock()
        msg.parts = []
        assert estimate_tokens_for_message(msg) == 1


# ---- estimate_context_overhead ---------------------------------------------


class TestEstimateContextOverhead:
    def test_empty_prompt_and_no_tools(self):
        assert estimate_context_overhead("", None) == 0

    def test_prompt_only(self):
        assert estimate_context_overhead("hello world hello world", None) > 0

    def test_tools_add_overhead(self):
        def fake_tool():
            """Does a thing."""

        fake_tool.__annotations__ = {"return": str}
        tools = {"fake_tool": fake_tool}
        with_tools = estimate_context_overhead("prompt", tools)
        without = estimate_context_overhead("prompt", None)
        assert with_tools > without

    def test_none_tools_ok(self):
        assert estimate_context_overhead("prompt", None) > 0


# ---- prune_interrupted_tool_calls ------------------------------------------


class TestPruneInterruptedToolCalls:
    def test_empty_list(self):
        assert prune_interrupted_tool_calls([]) == []

    def test_no_tool_calls_passthrough(self):
        msgs = [ModelRequest([TextPart("hi")])]
        assert prune_interrupted_tool_calls(msgs) == msgs

    def test_matched_pair_preserved(self):
        call = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="1")])
        ret = ModelRequest(
            [ToolReturnPart(tool_name="x", content="ok", tool_call_id="1")]
        )
        result = prune_interrupted_tool_calls([call, ret])
        assert result == [call, ret]

    def test_orphan_call_dropped(self):
        call = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="1")])
        result = prune_interrupted_tool_calls([call])
        assert result == []

    def test_orphan_return_dropped(self):
        ret = ModelRequest(
            [ToolReturnPart(tool_name="x", content="ok", tool_call_id="1")]
        )
        result = prune_interrupted_tool_calls([ret])
        assert result == []


# ---- has_pending_tool_calls -------------------------------------------------


class TestHasPendingToolCalls:
    def test_empty(self):
        assert has_pending_tool_calls([]) is False

    def test_matched_pair_no_pending(self):
        call = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="1")])
        ret = ModelRequest(
            [ToolReturnPart(tool_name="x", content="ok", tool_call_id="1")]
        )
        assert has_pending_tool_calls([call, ret]) is False

    def test_unmatched_call_is_pending(self):
        call = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="1")])
        assert has_pending_tool_calls([call]) is True


# ---- filter_huge_messages ---------------------------------------------------


class TestFilterHugeMessages:
    def test_empty(self):
        assert filter_huge_messages([]) == []

    def test_small_messages_kept(self):
        msgs = [ModelRequest([TextPart("hi")]), ModelRequest([TextPart("bye")])]
        assert filter_huge_messages(msgs) == msgs

    def test_giant_message_dropped(self):
        small = ModelRequest([TextPart("hi")])
        giant = ModelRequest([TextPart("x" * 200000)])  # ~80k estimated tokens
        result = filter_huge_messages([small, giant])
        assert small in result
        assert giant not in result

    def test_orphaned_tool_calls_also_pruned(self):
        small = ModelRequest([TextPart("hi")])
        orphan = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="1")])
        result = filter_huge_messages([small, orphan])
        assert small in result
        assert orphan not in result


# ---- REGRESSION: builtin-tool parts + retry-prompt classification -----------


class TestToolPartClassification:
    """Regression tests for the Opus-4.7 builtin-tool-call deferral bug.

    Symptom: Users on Claude Opus 4.7 (extended thinking / builtin tools)
    would see 'Summarization deferred: pending tool call(s) detected' fire
    on every turn, with history growing unbounded. Root cause: both
    has_pending_tool_calls() and prune_interrupted_tool_calls() only knew
    about tool-call/tool-return, ignoring the builtin-* pair and
    retry-prompt. The unified _classify_tool_part() helper fixes this.
    """

    def test_builtin_tool_call_and_return_are_paired(self):
        """builtin-tool-call matched with builtin-tool-return = no pending."""
        from pydantic_ai.messages import (
            BuiltinToolCallPart,
            BuiltinToolReturnPart,
        )

        call = ModelResponse(
            [BuiltinToolCallPart(tool_name="web_search", args={}, tool_call_id="b1")]
        )
        ret = ModelResponse(
            [
                BuiltinToolReturnPart(
                    tool_name="web_search", content="result", tool_call_id="b1"
                )
            ]
        )
        # Key assertion: pairing is recognized
        assert has_pending_tool_calls([call, ret]) is False, (
            "builtin-tool-call + builtin-tool-return should pair up; "
            "if they don't, compaction will defer forever on Opus-4.7"
        )

    def test_orphan_builtin_tool_call_detected_as_pending(self):
        """An orphaned builtin-tool-call should register as pending."""
        from pydantic_ai.messages import BuiltinToolCallPart

        call = ModelResponse(
            [BuiltinToolCallPart(tool_name="web_search", args={}, tool_call_id="b1")]
        )
        assert has_pending_tool_calls([call]) is True

    def test_retry_prompt_counts_as_response(self):
        """retry-prompt carries the failed call's tool_call_id and acts as a
        response. A tool_call + retry_prompt pair should NOT be pending."""
        from pydantic_ai.messages import RetryPromptPart

        call = ModelResponse([ToolCallPart(tool_name="x", args={}, tool_call_id="r1")])
        retry = ModelRequest(
            [RetryPromptPart(content="retry please", tool_call_id="r1")]
        )
        assert has_pending_tool_calls([call, retry]) is False, (
            "retry-prompt should satisfy the pairing — otherwise retried "
            "tools trigger permanent compaction deferrals"
        )

    def test_prune_preserves_paired_builtin_tools(self):
        """prune_interrupted_tool_calls must keep matched builtin tool pairs."""
        from pydantic_ai.messages import (
            BuiltinToolCallPart,
            BuiltinToolReturnPart,
        )

        call = ModelResponse(
            [BuiltinToolCallPart(tool_name="web_search", args={}, tool_call_id="b1")]
        )
        ret = ModelResponse(
            [
                BuiltinToolReturnPart(
                    tool_name="web_search", content="result", tool_call_id="b1"
                )
            ]
        )
        result = prune_interrupted_tool_calls([call, ret])
        assert call in result
        assert ret in result

    def test_prune_drops_orphan_builtin_tool_call(self):
        from pydantic_ai.messages import BuiltinToolCallPart

        text_msg = ModelRequest([TextPart("hi")])
        orphan = ModelResponse(
            [BuiltinToolCallPart(tool_name="web_search", args={}, tool_call_id="b1")]
        )
        result = prune_interrupted_tool_calls([text_msg, orphan])
        assert text_msg in result
        assert orphan not in result

    def test_prune_drops_orphan_builtin_tool_return(self):
        """Symmetric case: orphan builtin-tool-return should be dropped too."""
        from pydantic_ai.messages import BuiltinToolReturnPart

        text_msg = ModelRequest([TextPart("hi")])
        orphan = ModelResponse(
            [
                BuiltinToolReturnPart(
                    tool_name="web_search", content="result", tool_call_id="b1"
                )
            ]
        )
        result = prune_interrupted_tool_calls([text_msg, orphan])
        assert text_msg in result
        assert orphan not in result
