"""Tests for Opus 4.7 wire-level thinking.display='summary' enforcement.

The Opus 4.7 family requires ``display: "summarized"`` alongside
``type: "adaptive"`` in the thinking dict, otherwise the API rejects the
request. We enforce this at the wire level in the claude cache client so
it's guaranteed regardless of how upstream model settings are built.
"""

from __future__ import annotations

import json

from code_puppy.claude_cache_client import (
    ClaudeCacheAsyncClient,
    _enforce_thinking_display_summary,
    _inject_cache_control_in_payload,
    _model_requires_thinking_summary,
)


class TestModelRequiresThinkingSummary:
    def test_opus_4_7_canonical(self):
        assert _model_requires_thinking_summary("claude-opus-4-7") is True

    def test_opus_4_7_with_prefix_and_suffix(self):
        assert (
            _model_requires_thinking_summary("anthropic-claude-opus-4-7-latest") is True
        )

    def test_reversed_naming(self):
        assert _model_requires_thinking_summary("claude-4-7-opus-20250701") is True

    def test_case_insensitive(self):
        assert _model_requires_thinking_summary("Claude-Opus-4-7") is True

    def test_opus_4_6_returns_false(self):
        assert _model_requires_thinking_summary("claude-opus-4-6") is False

    def test_sonnet_returns_false(self):
        assert _model_requires_thinking_summary("claude-sonnet-4-5") is False

    def test_none_returns_false(self):
        assert _model_requires_thinking_summary(None) is False

    def test_empty_string_returns_false(self):
        assert _model_requires_thinking_summary("") is False


class TestEnforceThinkingDisplaySummary:
    def test_adds_display_summary_for_opus_4_7(self):
        payload = {"model": "claude-opus-4-7", "thinking": {"type": "adaptive"}}
        changed = _enforce_thinking_display_summary(payload)
        assert changed is True
        assert payload["thinking"]["display"] == "summarized"

    def test_preserves_other_thinking_fields(self):
        payload = {
            "model": "claude-opus-4-7",
            "thinking": {"type": "adaptive", "budget_tokens": 8000},
        }
        _enforce_thinking_display_summary(payload)
        assert payload["thinking"]["type"] == "adaptive"
        assert payload["thinking"]["budget_tokens"] == 8000
        assert payload["thinking"]["display"] == "summarized"

    def test_no_op_when_already_set(self):
        payload = {
            "model": "claude-opus-4-7",
            "thinking": {"type": "adaptive", "display": "summarized"},
        }
        changed = _enforce_thinking_display_summary(payload)
        assert changed is False
        assert payload["thinking"]["display"] == "summarized"

    def test_no_op_for_non_opus_4_7(self):
        payload = {"model": "claude-opus-4-6", "thinking": {"type": "adaptive"}}
        changed = _enforce_thinking_display_summary(payload)
        assert changed is False
        assert "display" not in payload["thinking"]

    def test_no_op_when_no_thinking_dict(self):
        payload = {"model": "claude-opus-4-7"}
        changed = _enforce_thinking_display_summary(payload)
        assert changed is False
        assert "thinking" not in payload

    def test_no_op_when_thinking_not_a_dict(self):
        # thinking might be e.g. a string or list in weird serialization paths
        payload = {"model": "claude-opus-4-7", "thinking": "adaptive"}
        changed = _enforce_thinking_display_summary(payload)
        assert changed is False

    def test_no_op_for_non_dict_payload(self):
        assert _enforce_thinking_display_summary(None) is False
        assert _enforce_thinking_display_summary([]) is False
        assert _enforce_thinking_display_summary("nope") is False


class TestInjectCacheControlInPayloadEnforcesSummary:
    def test_payload_path_adds_display_summary(self):
        payload = {
            "model": "claude-opus-4-7",
            "thinking": {"type": "adaptive"},
            "messages": [{"role": "user", "content": "hi"}],
        }
        _inject_cache_control_in_payload(payload)
        assert payload["thinking"]["display"] == "summarized"

    def test_payload_path_skips_non_opus_4_7(self):
        payload = {
            "model": "claude-sonnet-4-5",
            "thinking": {"type": "adaptive"},
            "messages": [{"role": "user", "content": "hi"}],
        }
        _inject_cache_control_in_payload(payload)
        assert "display" not in payload["thinking"]


class TestWireBytesInjectionEnforcesSummary:
    def test_bytes_path_adds_display_summary(self):
        body = json.dumps(
            {
                "model": "claude-opus-4-7",
                "thinking": {"type": "adaptive"},
                "messages": [{"role": "user", "content": "hi"}],
            }
        ).encode("utf-8")

        result = ClaudeCacheAsyncClient._inject_cache_control(body)
        assert result is not None, "expected body to be modified"
        data = json.loads(result.decode("utf-8"))
        assert data["thinking"]["display"] == "summarized"

    def test_bytes_path_no_op_for_non_matching_model(self):
        # No cache_control targets, no matching model, no modification at all.
        body = json.dumps(
            {
                "model": "claude-opus-4-6",
                "thinking": {"type": "adaptive"},
            }
        ).encode("utf-8")

        result = ClaudeCacheAsyncClient._inject_cache_control(body)
        # Either no modification (None) or, if cache targets existed, the
        # thinking dict should be untouched.
        if result is not None:
            data = json.loads(result.decode("utf-8"))
            assert "display" not in data["thinking"]

    def test_bytes_path_triggers_modification_even_without_cache_targets(self):
        # The only thing worth modifying here is the thinking.display field.
        # Make sure we still rewrite the body (returning bytes, not None) when
        # the display fix is the only change.
        body = json.dumps(
            {
                "model": "claude-opus-4-7",
                "thinking": {"type": "adaptive"},
            }
        ).encode("utf-8")

        result = ClaudeCacheAsyncClient._inject_cache_control(body)
        assert result is not None
        data = json.loads(result.decode("utf-8"))
        assert data["thinking"]["display"] == "summarized"
