"""Anthropic thinking policy in model_utils (adaptive, defaults, summaries, payload).

Moved from the mirrored aws_bedrock plugin tests: these exercise core
``code_puppy.model_utils`` only, so core owns them.
"""

import pytest


class TestSupportsAdaptiveThinking:
    """Test the shared supports_adaptive_thinking helper."""

    @pytest.mark.parametrize(
        "alias, actual_model_id, expected",
        [
            ("claude-opus-4-7", None, True),
            ("claude-opus-4-6", None, True),
            ("claude-sonnet-4-6", None, True),
            ("claude-opus-5", None, True),
            ("claude-5-opus", None, True),
            ("claude-4.5-opus", None, False),
            ("claude-haiku-4-5", None, False),
            # The alias doesn't contain the tag, but the actual_model_id does
            ("bedrock-opus", "us.anthropic.claude-opus-4-7", True),
            ("gpt-4o", None, False),
        ],
        ids=[
            "opus_4_7_by_alias",
            "opus_4_6_by_alias",
            "sonnet_4_6_by_alias",
            "opus_5_by_alias",
            "five_opus_by_alias",
            "opus_4_5_minor_version_not_adaptive",
            "haiku_not_adaptive",
            "bedrock_opus_via_actual_model_id",
            "unknown_model",
        ],
    )
    def test_supports_adaptive_thinking(self, alias, actual_model_id, expected):
        from code_puppy.model_utils import supports_adaptive_thinking

        assert (
            supports_adaptive_thinking(alias, actual_model_id=actual_model_id)
            is expected
        )


class TestGetDefaultExtendedThinking:
    """Test get_default_extended_thinking uses the shared helper."""

    def test_adaptive_for_opus(self):
        from code_puppy.model_utils import get_default_extended_thinking

        assert get_default_extended_thinking("claude-opus-4-7") == "adaptive"

    def test_enabled_for_haiku(self):
        from code_puppy.model_utils import get_default_extended_thinking

        assert get_default_extended_thinking("claude-haiku-4-5") == "enabled"

    def test_adaptive_via_actual_model_id(self):
        from code_puppy.model_utils import get_default_extended_thinking

        result = get_default_extended_thinking(
            "bedrock-opus", actual_model_id="us.anthropic.claude-opus-4-6-v1:0"
        )
        assert result == "adaptive"


class TestShouldUseThinkingSummary:
    """Test should_use_anthropic_thinking_summary."""

    def test_true_for_opus_4_7(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert should_use_anthropic_thinking_summary("claude-opus-4-7") is True

    def test_false_for_opus_4_6(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert should_use_anthropic_thinking_summary("claude-opus-4-6") is False

    def test_true_via_actual_model_id(self):
        from code_puppy.model_utils import should_use_anthropic_thinking_summary

        assert (
            should_use_anthropic_thinking_summary(
                "bedrock-opus", actual_model_id="us.anthropic.claude-opus-4-7"
            )
            is True
        )


class TestResolveAnthropicThinkingPayload:
    """Opus 5 must always resolve to the adaptive wire shape."""

    @pytest.mark.parametrize(
        "mode, expected",
        [
            ("enabled", {"type": "adaptive", "display": "summarized"}),
            ("adaptive", {"type": "adaptive", "display": "summarized"}),
            ("disabled", None),
        ],
        ids=["enabled_coerced_to_adaptive", "adaptive_passthrough", "disabled_omits"],
    )
    @pytest.mark.parametrize("alias", ["claude-opus-5", "claude-5-opus"])
    def test_opus_5_payload(self, alias, mode, expected):
        from code_puppy.model_utils import resolve_anthropic_thinking_payload

        result = resolve_anthropic_thinking_payload(
            mode, budget_tokens=1024, model_name=alias, actual_model_id=None
        )
        assert result == expected
