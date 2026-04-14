"""Tests for Azure content-filter false-positive detection and auto-retry.

Covers:
  - ``is_content_filter_response`` pattern matching (positive & negative)
  - ``on_result_check_content_filter`` callback return values
  - Integration with the ``agent_run_result`` hook contract
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelResponse, TextPart

from code_puppy.plugins.walmart_specific.content_filter_retry import (
    CONTENT_FILTER_RETRY_DELAY,
    CONTENT_FILTER_RETRY_PROMPT,
    _MAX_REFUSAL_LENGTH,
    _REFUSAL_PATTERNS,
    is_content_filter_response,
    on_result_check_content_filter,
)


# ---------------------------------------------------------------------------
# is_content_filter_response — detection tests
# ---------------------------------------------------------------------------


class TestIsContentFilterResponse:
    """Unit tests for the detection heuristic."""

    @pytest.mark.parametrize(
        "text",
        [
            "I'm sorry, but I cannot assist with that request.",
            "I'm sorry, but I can't assist with that.",
            "I'm sorry, but I cannot help with that.",
            "I'm sorry, but I can't help with that request.",
            "I cannot assist with that request.",
            "Sorry, but I can't help with that.",
            "I'm not able to assist with that.",
            "I'm unable to help with that request.",
            "  I'm sorry, but I cannot assist with that.  ",  # whitespace
            "I'M SORRY, BUT I CANNOT ASSIST WITH THAT REQUEST.",  # uppercase
        ],
    )
    def test_detects_known_refusal_patterns(self, text: str):
        assert is_content_filter_response(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            # Legitimate short responses that should NOT trigger
            "Hello! How can I help you today?",
            "Sure, I'd be happy to help with that.",
            "Here's the code you requested.",
            "",
            # None value
            None,
            # Long response that happens to contain the phrase buried inside
            "Here's a 500-word essay. " * 20
            + "I'm sorry, but I cannot assist with that."
            + " More text follows. " * 10,
        ],
    )
    def test_ignores_non_filter_responses(self, text):
        assert is_content_filter_response(text) is False

    def test_length_boundary(self):
        """Responses longer than _MAX_REFUSAL_LENGTH are never matched."""
        base = "I'm sorry, but I cannot assist with that."
        padded_at_limit = base + " " * (_MAX_REFUSAL_LENGTH - len(base))
        assert len(padded_at_limit.strip()) <= _MAX_REFUSAL_LENGTH
        assert is_content_filter_response(padded_at_limit) is True

        # One char over → no match
        padded_over = base + "x" * (_MAX_REFUSAL_LENGTH - len(base) + 1)
        assert is_content_filter_response(padded_over) is False

    def test_all_patterns_are_lowercase(self):
        """Invariant: every pattern string is already lowercased."""
        for p in _REFUSAL_PATTERNS:
            assert p == p.lower(), f"Pattern should be lowercase: {p!r}"


# ---------------------------------------------------------------------------
# on_result_check_content_filter — callback tests
# ---------------------------------------------------------------------------


def _make_result(
    output: str | None,
    *,
    all_messages=None,
    new_messages=None,
):
    """Build a lightweight stand-in for a pydantic-ai RunResult."""
    return SimpleNamespace(
        output=output,
        all_messages=(lambda: all_messages or []),
        new_messages=(lambda: new_messages or []),
    )



def _make_model_response(text: str | None = None, *, finish_reason=None):
    parts = [TextPart(text)] if text is not None else []
    return ModelResponse(parts=parts, finish_reason=finish_reason)


class TestOnResultCheckContentFilter:
    """Tests for the ``agent_run_result`` callback implementation."""

    def test_returns_none_for_normal_response(self):
        result = _make_result("Here's your code!")
        rv = on_result_check_content_filter(result, "test-agent", "gpt-5.4")
        assert rv is None

    def test_returns_retry_dict_for_filtered_response(self):
        result = _make_result(
            "I'm sorry, but I cannot assist with that request."
        )
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ):
            rv = on_result_check_content_filter(
                result, "test-agent", "gpt-5.4"
            )

        assert isinstance(rv, dict)
        assert rv["retry"] is True
        assert rv["prompt"] == CONTENT_FILTER_RETRY_PROMPT
        assert rv["delay"] == CONTENT_FILTER_RETRY_DELAY

    def test_returns_none_for_empty_output(self):
        result = _make_result("")
        rv = on_result_check_content_filter(result, "test-agent", "gpt-5.4")
        assert rv is None

    def test_returns_none_for_none_output(self):
        result = SimpleNamespace(output=None)
        rv = on_result_check_content_filter(result, "test-agent", "gpt-5.4")
        assert rv is None

    def test_returns_none_for_missing_output_attr(self):
        result = SimpleNamespace(data="something")
        rv = on_result_check_content_filter(result, "test-agent", "gpt-5.4")
        assert rv is None

    def test_emits_warning_on_detection(self):
        result = _make_result(
            "I'm sorry, but I cannot assist with that request."
        )
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ) as mock_warn:
            on_result_check_content_filter(result, "test-agent", "gpt-5.4")

        mock_warn.assert_called_once()
        assert "content filter" in mock_warn.call_args[0][0].lower()

    def test_detects_refusal_in_model_response_messages(self):
        result = _make_result(
            None,
            all_messages=[
                _make_model_response(
                    "I'm sorry, but I cannot assist with that request."
                )
            ],
        )
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ):
            rv = on_result_check_content_filter(
                result, "test-agent", "gpt-5.4"
            )

        assert isinstance(rv, dict)
        assert rv["retry"] is True

    def test_detects_content_filter_finish_reason_without_text(self):
        result = _make_result(
            None,
            new_messages=[_make_model_response(None, finish_reason="content_filter")],
        )
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ):
            rv = on_result_check_content_filter(
                result, "test-agent", "gpt-5.4"
            )

        assert isinstance(rv, dict)
        assert rv["retry"] is True

    def test_does_not_warn_for_normal_response(self):
        result = _make_result("All good!")
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ) as mock_warn:
            on_result_check_content_filter(result, "test-agent", "gpt-5.4")

        mock_warn.assert_not_called()


# ---------------------------------------------------------------------------
# Hook contract tests — verify the dict shape matches base_agent expectations
# ---------------------------------------------------------------------------


class TestHookContract:
    """Ensure the callback return value matches what _run_with_result_hooks expects."""

    def test_retry_dict_has_required_keys(self):
        result = _make_result(
            "I'm sorry, but I cannot assist with that request."
        )
        with patch(
            "code_puppy.plugins.walmart_specific.content_filter_retry.emit_warning"
        ):
            rv = on_result_check_content_filter(
                result, "test-agent", "gpt-5.4"
            )

        # base_agent checks: isinstance(r, dict) and r.get("retry")
        assert isinstance(rv, dict)
        assert "retry" in rv
        assert rv["retry"] is True

        # base_agent reads: .get("prompt", "Please continue.")
        assert isinstance(rv["prompt"], str)
        assert len(rv["prompt"]) > 0

        # base_agent reads: .get("delay", 1.0)
        assert isinstance(rv["delay"], (int, float))
        assert rv["delay"] > 0

    def test_none_return_does_not_trigger_retry(self):
        """base_agent skips retry when callback returns None."""
        result = _make_result("Perfectly normal response.")
        rv = on_result_check_content_filter(result, "test-agent", "gpt-5.4")
        assert rv is None
