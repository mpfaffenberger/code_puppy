"""Regression tests for stringify_part() ToolCallPart.args handling.

Regression: estimate_tokens_for_message() undercounted ~5x on tool-heavy
sessions because stringify_part() hit the ``content=None`` branch for every
ToolCallPart (which has no .content field, only .args), silently discarding
all argument bytes.  This caused compaction to never fire: the estimate sat
at ~20% of the real context usage while the model was actually at ~98%.

These tests assert that:
1. stringify_part() serializes ToolCallPart.args (not silently drops them).
2. estimate_tokens_for_message() scales with large tool-call arg payloads.
3. Tool-call messages in a realistic wedge-scenario history contribute
   tokens proportional to their arg payload.
4. List content items of non-str/non-Binary types are not silently dropped.
"""

from __future__ import annotations

import json
import math

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)

from code_puppy.agents._history import (
    estimate_tokens_for_message,
    stringify_part,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_call(tool_name: str, args: str, tool_call_id: str) -> ToolCallPart:
    return ToolCallPart(tool_name=tool_name, args=args, tool_call_id=tool_call_id)


def _make_tool_return(
    tool_name: str, content: str, tool_call_id: str
) -> ToolReturnPart:
    return ToolReturnPart(
        tool_name=tool_name, content=content, tool_call_id=tool_call_id
    )


# ---------------------------------------------------------------------------
# Fix 1: ToolCallPart.args must appear in stringify_part output
# ---------------------------------------------------------------------------


class TestStringifyPartToolCallArgs:
    def test_args_not_discarded_as_content_none(self):
        """Before fix: stringify_part hit 'content=None' for ToolCallPart,
        silently dropping all args.  After fix: 'args=...' must be present."""
        part = _make_tool_call(
            "read_file",
            json.dumps({"file_path": "/some/long/path/to/source_file.py"}),
            "tc_001",
        )
        result = stringify_part(part)
        assert "content=None" not in result, (
            "stringify_part must NOT treat ToolCallPart.args as missing content"
        )
        assert "args=" in result, "stringify_part must include 'args=' for ToolCallPart"

    def test_args_content_is_captured(self):
        """The serialized args string must contain the actual payload text."""
        payload = {
            "command": "grep -r 'estimate_tokens' /repo/code_puppy",
            "cwd": "/repo",
        }
        part = _make_tool_call("agent_run_shell_command", json.dumps(payload), "tc_002")
        result = stringify_part(part)
        # Key fragments from the payload must survive stringification.
        assert "estimate_tokens" in result
        assert "agent_run_shell_command" in result

    def test_large_args_produce_proportional_string(self):
        """A 10KB args payload must produce a stringified output >> 10 chars.

        Before the fix, all tool calls produced ~70-char strings regardless
        of args size.  After the fix, the string length must scale with args.
        """
        large_args = json.dumps({"data": "x" * 10_000})
        part = _make_tool_call("write_file", large_args, "tc_003")
        result = stringify_part(part)
        assert len(result) > 1_000, (
            f"stringify_part output ({len(result)} chars) should scale with "
            f"large args ({len(large_args)} chars)"
        )

    def test_small_vs_large_args_estimate_differs_significantly(self):
        """Token estimate for a large-args tool call must be >> small-args call."""
        small_args = json.dumps({"file_path": "/a.py"})
        large_args = json.dumps({"file_path": "/a.py", "content": "x" * 50_000})

        small_part = _make_tool_call("write_file", small_args, "tc_small")
        large_part = _make_tool_call("write_file", large_args, "tc_large")

        small_msg = ModelResponse(parts=[small_part])
        large_msg = ModelResponse(parts=[large_part])

        small_est = estimate_tokens_for_message(small_msg)
        large_est = estimate_tokens_for_message(large_msg)

        # Large args (50KB extra) must produce substantially more tokens.
        assert large_est > small_est * 5, (
            f"Large-args message ({large_est} tok) should be >>5x small-args "
            f"({small_est} tok); args content must be counted"
        )

    def test_truncated_args_does_not_raise(self):
        """Truncated / invalid JSON in args must not crash stringify_part.

        This is the secondary failure mode: a truncated
        tool-call arg wedges the session permanently because args_as_dict()
        raises.  stringify_part must handle it gracefully.
        """
        truncated = (
            '{"file_path": "/some/file.py", "content": "partial...'  # no closing
        )
        part = _make_tool_call("write_file", truncated, "tc_trunc")
        # Must not raise — we want the safe fallback path
        result = stringify_part(part)
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Fix 1: estimate_tokens_for_message scales with tool-call args
# ---------------------------------------------------------------------------


class TestEstimateTokensToolCallScaling:
    def test_tool_call_tokens_scale_with_args_size(self):
        """Regression: tool-call args were not counted.

        A session's ToolCallParts collectively had ~100KB of args that the
        old estimator attributed zero tokens to.  The estimate must scale.
        """
        # 50KB args (realistic for a large write_file or shell command output)
        big_args = json.dumps({"content": "a" * 50_000})
        part = _make_tool_call("write_file", big_args, "tc_big")
        msg = ModelResponse(parts=[part])
        tokens = estimate_tokens_for_message(msg)

        # 50KB / 2.5 chars-per-token ≈ 20,000 tokens.  We allow generous
        # slack (50%) — the exact ratio doesn't matter, but the order of
        # magnitude must be right.
        min_expected = math.floor(len(big_args) / 2.5) // 2  # 50% of ideal
        assert tokens >= min_expected, (
            f"Token estimate {tokens} is too low for {len(big_args)}-char args "
            f"(expected >= {min_expected})"
        )

    def test_realistic_wedge_session_counts_tool_call_args(self):
        """Simulate the tail of the wedged session from the bug report.

        Repeated write_file calls carry multi-KB args; each is followed by a
        multi-KB write_file return.  The invariant under test: the ToolCallPart
        messages on their own must contribute tokens proportional to their
        arg payload.  Before the fix each call collapsed to a ~70-char
        ``content=None`` string (~30 tokens), so this assertion fails on the
        buggy code regardless of how large the returns are.
        """
        n_rounds = 20
        args_chars = 0
        call_msgs = []
        return_msgs = []
        for i in range(n_rounds):
            args = json.dumps(
                {"file_path": f"/repo/src/module_{i}.py", "content": "y" * 5_000}
            )
            args_chars += len(args)
            call_msgs.append(
                ModelResponse(
                    parts=[_make_tool_call("write_file", args, f"tc_{i:03d}")]
                )
            )
            return_msgs.append(
                ModelRequest(
                    parts=[
                        _make_tool_return(
                            "write_file", "# " + "x" * 8_000, f"tc_{i:03d}"
                        )
                    ]
                )
            )

        call_tokens = sum(estimate_tokens_for_message(m) for m in call_msgs)
        return_tokens = sum(estimate_tokens_for_message(m) for m in return_msgs)

        # ~100KB of args at the chars/2.5 heuristic is ~40k tokens; allow 50%
        # slack.  The buggy code produced ~20 * 30 = ~600 tokens here.
        min_call_tokens = math.floor(args_chars / 2.5) // 2
        assert call_tokens >= min_call_tokens, (
            f"Tool-call messages estimated at {call_tokens} tok for "
            f"{args_chars} chars of args (expected >= {min_call_tokens}); "
            "ToolCallPart.args is being dropped"
        )
        # Args are comparable in size to returns, so they must not be dwarfed
        # by them (pre-fix: calls were <2% of the total).
        assert call_tokens > 0.3 * return_tokens


# ---------------------------------------------------------------------------
# Fix 2: list content items of unknown type must not be silently dropped
# ---------------------------------------------------------------------------


class TestStringifyPartListContent:
    def test_dict_items_in_list_content_not_silently_dropped(self):
        """Non-str, non-Binary items in list content must produce output."""

        class _FakePart:
            content = [{"key": "value", "nested": {"x": 1}}, "plain string"]
            tool_call_id = None
            tool_name = None
            role = None
            instructions = None
            # No .args field so we go through the content branch

        part = _FakePart()
        result = stringify_part(part)
        # Dict items fall through to the repr() branch; plain strings pass through.
        assert "content={'key': 'value', 'nested': {'x': 1}}" in result
        assert "content=plain string" in result

    def test_unknown_type_in_list_content_uses_repr(self):
        """Items of unexpected type get repr()'d rather than silently dropped."""

        class _Sentinel:
            def __repr__(self):
                return "<sentinel_object>"

        class _FakePart:
            content = [_Sentinel()]
            tool_call_id = None
            tool_name = None
            role = None
            instructions = None

        part = _FakePart()
        result = stringify_part(part)
        assert "<sentinel_object>" in result, (
            "Unknown list-content items must appear via repr(), not be silently dropped"
        )


# ---------------------------------------------------------------------------
# Sanity: ToolReturnPart (content, not args) still works correctly
# ---------------------------------------------------------------------------


class TestStringifyPartToolReturn:
    def test_tool_return_content_unchanged(self):
        """ToolReturnPart.content must still be captured (regression guard)."""
        file_content = "def foo():\n    return 42\n" * 200  # ~5KB
        part = _make_tool_return("read_file", file_content, "tc_ret_001")
        result = stringify_part(part)
        # The bulk of the file content must appear.
        assert "def foo" in result
        assert len(result) > len(file_content) * 0.9  # not significantly truncated


# ---------------------------------------------------------------------------
# A part carrying BOTH .args and .content must contribute both
# ---------------------------------------------------------------------------


class TestStringifyPartArgsAndContent:
    def test_part_with_args_and_content_counts_both(self):
        class _FakePart:
            args = '{"path": "/x.py"}'
            content = "returned file body"
            tool_call_id = None
            tool_name = None
            role = None
            instructions = None

        result = stringify_part(_FakePart())
        assert 'args={"path": "/x.py"}' in result
        assert "content=returned file body" in result

    def test_tool_call_part_has_no_spurious_content_marker(self):
        part = _make_tool_call("read_file", '{"file_path": "/a.py"}', "tc_nc")
        result = stringify_part(part)
        assert 'args={"file_path": "/a.py"}' in result
        assert "content=" not in result

    def test_part_without_args_or_content_keeps_content_none(self):
        class _Bare:
            tool_call_id = None
            tool_name = None
            role = None
            instructions = None

        assert "content=None" in stringify_part(_Bare())
