"""Tests for ``code_puppy.agents._diagnostics`` (issue #296).

We don't want to boot the whole agent runtime just to check that an exception
renders with all of its signal intact, so these tests hit the helpers
directly and capture the text passed to ``emit_info``.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_puppy.agents._diagnostics import (
    _emit_exception_chain,
    _emit_useful_attrs,
    _needs_deep_diagnostics,
    emit_exception_diagnostics,
)

try:
    from builtins import BaseExceptionGroup  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - 3.10 only
    BaseExceptionGroup = Exception  # type: ignore[misc,assignment]


class _FakeAPIError(Exception):
    """Stand-in for a provider SDK error with useful attrs."""

    def __init__(self, message, *, body=None, response=None):
        super().__init__(message)
        self.body = body
        self.response = response


def _rendered_lines(calls) -> str:
    """Join all emitted payloads into one searchable string."""
    pieces = []
    for call in calls:
        payload = call.args[0] if call.args else call.kwargs.get("message")
        if payload is None:
            continue
        # rich.text.Text renders via its plain attribute; strings render as-is.
        pieces.append(getattr(payload, "plain", str(payload)))
    return "\n".join(pieces)


class TestCheapPath:
    def test_plain_runtime_error_emits_summary_and_skips_deep_block(self):
        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            with patch("code_puppy.agents._diagnostics.log_error") as mock_log:
                emit_exception_diagnostics(RuntimeError("boom"), group_id="g1")

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "Unexpected error: boom" in rendered
        assert "Diagnostic detail" not in rendered
        assert "Sub-exception" not in rendered
        mock_log.assert_called_once()

    def test_log_failure_does_not_propagate(self):
        with patch("code_puppy.agents._diagnostics.emit_info"):
            with patch(
                "code_puppy.agents._diagnostics.log_error",
                side_effect=OSError("disk full"),
            ):
                # Must not raise.
                emit_exception_diagnostics(RuntimeError("boom"), group_id="g2")

    def test_emit_info_failure_does_not_propagate(self):
        with patch(
            "code_puppy.agents._diagnostics.emit_info",
            side_effect=RuntimeError("display dead"),
        ):
            with patch("code_puppy.agents._diagnostics.log_error"):
                emit_exception_diagnostics(RuntimeError("boom"), group_id="g3")


class TestDeepPath:
    def test_trigger_phrase_enables_deep_diagnostics(self):
        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            with patch("code_puppy.agents._diagnostics.log_error"):
                emit_exception_diagnostics(
                    RuntimeError("output validation failed: schema mismatch"),
                    group_id="g",
                )

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "Diagnostic detail" in rendered
        assert "Exception type: RuntimeError" in rendered

    def test_base_exception_group_unrolls_leaves_with_attrs(self):
        if BaseExceptionGroup is Exception:
            pytest.skip("Python 3.10 lacks BaseExceptionGroup")

        leaf1 = _FakeAPIError(
            "provider blew up",
            body={"message": "try again"},
        )
        leaf2 = _FakeAPIError(
            "also blew up",
            body={"message": "rate limited"},
        )
        group = BaseExceptionGroup("agent task group failed", [leaf1, leaf2])

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            with patch("code_puppy.agents._diagnostics.log_error"):
                emit_exception_diagnostics(group, group_id="g")

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "Sub-exception 1" in rendered
        assert "Sub-exception 2" in rendered
        assert "provider blew up" in rendered
        assert "also blew up" in rendered
        # Useful attributes should surface on each leaf.
        assert "body:" in rendered
        assert "try again" in rendered
        assert "rate limited" in rendered

    def test_chained_cause_is_shown(self):
        try:
            try:
                raise ValueError("bad schema")
            except ValueError as cause:
                raise RuntimeError("output validation retries exhausted") from cause
        except RuntimeError as exc:
            caught = exc

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            with patch("code_puppy.agents._diagnostics.log_error"):
                emit_exception_diagnostics(caught, group_id="g")

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "cause" in rendered
        assert "ValueError" in rendered
        assert "bad schema" in rendered

    def test_group_leaf_cap_truncates_and_reports_overflow(self):
        if BaseExceptionGroup is Exception:
            pytest.skip("Python 3.10 lacks BaseExceptionGroup")

        leaves = [RuntimeError(f"err {i}") for i in range(15)]
        group = BaseExceptionGroup("too many", leaves)

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            with patch("code_puppy.agents._diagnostics.log_error"):
                emit_exception_diagnostics(group, group_id="g")

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "Sub-exception 10" in rendered
        assert "Sub-exception 11" not in rendered
        assert "5 more sub-exception(s) omitted" in rendered


class TestHelpers:
    def test_emit_useful_attrs_skips_missing_and_empty(self):
        exc = _FakeAPIError("msg", body=None)

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            _emit_useful_attrs(exc, "g", indent="  ")

        # Only ``message`` is set (via ``Exception.__init__``'s args); body/response/etc are None.
        rendered = _rendered_lines(mock_emit.call_args_list)
        # Our USEFUL_ATTRS check uses getattr(obj, 'message', None). Exception
        # doesn't set .message, so nothing should emit here.
        assert rendered == ""

    def test_emit_useful_attrs_renders_set_attrs(self):
        exc = _FakeAPIError(
            "ignored",
            body={"error": "rate limited"},
            response="HTTP 429",
        )

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            _emit_useful_attrs(exc, "g", indent="  ")

        rendered = _rendered_lines(mock_emit.call_args_list)
        assert "body:" in rendered
        assert "rate limited" in rendered
        assert "response:" in rendered
        assert "HTTP 429" in rendered

    def test_emit_chain_handles_cycles(self):
        a = RuntimeError("a")
        b = RuntimeError("b")
        # Intentionally create a cycle via __cause__.
        a.__cause__ = b
        b.__cause__ = a

        with patch("code_puppy.agents._diagnostics.emit_info") as mock_emit:
            # Should not loop forever.
            _emit_exception_chain(a, "g", max_depth=10)

        # At most one new emission before we bail on the cycle.
        assert len(mock_emit.call_args_list) <= 2

    def test_needs_deep_diagnostics_detects_triggers(self):
        assert _needs_deep_diagnostics(
            RuntimeError("output validation retries exceeded")
        )
        assert _needs_deep_diagnostics(RuntimeError("blah retries blah"))
        assert not _needs_deep_diagnostics(RuntimeError("plain boom"))

    def test_needs_deep_diagnostics_detects_exception_groups(self):
        if BaseExceptionGroup is Exception:
            pytest.skip("Python 3.10 lacks BaseExceptionGroup")
        group = BaseExceptionGroup("bundle", [ValueError("x")])
        assert _needs_deep_diagnostics(group)
