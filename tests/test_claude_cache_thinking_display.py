"""Thinking ``display`` / off-switch normalization on outgoing Anthropic bodies.

The API only accepts ``display`` while thinking runs (``adaptive`` /
``enabled``), some models refuse ``type: "disabled"`` in favor of
``"between_tools"``, and Opus 5.5 refuses both, so ``thinking`` is omitted.
"""

import json

import pytest

from code_puppy.claude_cache_client import (
    ClaudeCacheAsyncClient,
    _enforce_thinking_display_summary,
)


@pytest.mark.parametrize(
    ("model", "thinking", "expected"),
    [
        # Classifier shape on a between_tools model: rewritten, no display.
        ("claude-sonnet-5-5", {"type": "disabled"}, {"type": "between_tools"}),
        (
            "claude-sonnet-5-5",
            {"type": "disabled", "display": "summarized"},
            {"type": "between_tools"},
        ),
        (
            "claude-sonnet-5-5",
            {"type": "between_tools", "display": "summarized"},
            {"type": "between_tools"},
        ),
        # Models outside the between_tools family keep "disabled", minus display.
        (
            "claude-sonnet-5",
            {"type": "disabled", "display": "summarized"},
            {"type": "disabled"},
        ),
        (
            "claude-opus-5",
            {"type": "disabled", "display": "summarized"},
            {"type": "disabled"},
        ),
    ],
)
def test_non_thinking_types_never_carry_display(model, thinking, expected):
    payload = {"model": model, "thinking": thinking}

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == expected


@pytest.mark.parametrize(
    "thinking",
    [
        {"type": "disabled"},
        {"type": "disabled", "display": "summarized"},
        {"type": "between_tools"},
    ],
)
def test_omit_thinking_model_drops_off_shapes(thinking):
    payload = {"model": "claude-opus-5-5", "max_tokens": 16, "thinking": thinking}

    assert _enforce_thinking_display_summary(payload) is True
    assert payload == {"model": "claude-opus-5-5", "max_tokens": 16}


@pytest.mark.parametrize(
    ("thinking", "expected"),
    [
        ({"type": "adaptive"}, {"type": "adaptive", "display": "summarized"}),
        (
            {"type": "enabled", "budget_tokens": 1024},
            {"type": "enabled", "budget_tokens": 1024, "display": "summarized"},
        ),
    ],
)
def test_omit_thinking_model_keeps_active_thinking(thinking, expected):
    payload = {"model": "claude-opus-5-5", "thinking": thinking}

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == expected


@pytest.mark.parametrize("thinking_type", ["disabled", "between_tools"])
def test_clean_non_thinking_shape_is_left_alone(thinking_type):
    payload = {"model": "claude-sonnet-5", "thinking": {"type": thinking_type}}

    assert _enforce_thinking_display_summary(payload) is False
    assert payload["thinking"] == {"type": thinking_type}


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-sonnet-5-5"])
def test_adaptive_still_gets_summarized(model):
    payload = {"model": model, "thinking": {"type": "adaptive"}}

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_enabled_display_behavior_unchanged():
    payload = {
        "model": "claude-opus-4-7",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == {
        "type": "enabled",
        "budget_tokens": 1024,
        "display": "summarized",
    }


@pytest.mark.parametrize(
    ("model", "expected_thinking"),
    [
        ("claude-sonnet-5-5", {"type": "between_tools"}),
        ("claude-opus-5-5", None),
    ],
)
def test_body_hook_rewrites_classifier_request(model, expected_thinking):
    body = json.dumps({"model": model, "thinking": {"type": "disabled"}}).encode()

    rewritten = ClaudeCacheAsyncClient._enforce_thinking_display_summary_body(body)

    assert json.loads(rewritten).get("thinking") == expected_thinking
