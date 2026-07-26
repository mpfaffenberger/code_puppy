"""Tests for ``code_puppy.model_utils.resolve_anthropic_thinking_payload``.

Ground truth (verified against puppy-backend.walmart.com/anthropic on real
Claude endpoints, 2026-07-01):

* Classic Claude (Sonnet 4.5 and earlier, Haiku, etc.) accepts
  ``{"type": "enabled", "budget_tokens": N}`` and ``{"type": "disabled"}``.
  Sending ``"adaptive"`` yields HTTP 400
  ``Input tag 'adaptive' found using 'type' does not match any of the expected
  tags: 'disabled', 'enabled'``.
* Adaptive-supporting Claude (Opus 4.6/4.7/4.8, Sonnet 4.6, Sonnet 5, Fable 5)
  accepts ``{"type": "adaptive"}`` (optionally with ``"display": "summarized"``
  and/or ``output_config.effort``). Sending ``"enabled"`` yields HTTP 400
  ``"thinking.type.enabled" is not supported for this model. Use adaptive.``

The helper's job is to translate Code Puppy's internal thinking mode
(``"enabled"`` / ``"adaptive"`` / ``"off"`` / ``"disabled"``) into whichever
of those two wire shapes the target model actually accepts.
"""

from __future__ import annotations

import pytest

from code_puppy.model_utils import resolve_anthropic_thinking_payload


class TestClassicModelsGetEnabledShape:
    """Classic Claude models (Sonnet 4.5 and earlier) want type:enabled."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "claude-4-5-sonnet",
            "claude-sonnet-4-5",
            "claude-3-5-sonnet",
            "claude-4-5-haiku",
        ],
    )
    @pytest.mark.parametrize("mode", ["enabled", "adaptive"])
    def test_classic_models_always_get_enabled_shape(self, model_name, mode):
        payload = resolve_anthropic_thinking_payload(
            mode,
            budget_tokens=10000,
            model_name=model_name,
            actual_model_id=None,
        )
        assert payload is not None
        assert payload["type"] == "enabled"
        assert payload["budget_tokens"] == 10000
        assert "display" not in payload


class TestAdaptiveModelsGetAdaptiveShape:
    """Adaptive-supporting Claude models want type:adaptive."""

    @pytest.mark.parametrize(
        "model_name",
        [
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-5-sonnet",
            "claude-fable-5",
        ],
    )
    @pytest.mark.parametrize("mode", ["enabled", "adaptive"])
    def test_adaptive_models_always_get_adaptive_shape(self, model_name, mode):
        payload = resolve_anthropic_thinking_payload(
            mode,
            budget_tokens=10000,
            model_name=model_name,
            actual_model_id=None,
        )
        assert payload is not None
        assert payload["type"] == "adaptive"
        # budget_tokens is meaningless on adaptive and must NOT be included
        assert "budget_tokens" not in payload

    def test_summary_display_added_for_opus_4_7(self):
        payload = resolve_anthropic_thinking_payload(
            "adaptive",
            budget_tokens=8000,
            model_name="claude-opus-4-7",
            actual_model_id=None,
        )
        assert payload == {"type": "adaptive", "display": "summarized"}

    def test_summary_display_added_for_sonnet_5(self):
        payload = resolve_anthropic_thinking_payload(
            "enabled",
            budget_tokens=8000,
            model_name="claude-sonnet-5",
            actual_model_id=None,
        )
        assert payload == {"type": "adaptive", "display": "summarized"}

    def test_summary_display_not_added_for_opus_4_6(self):
        payload = resolve_anthropic_thinking_payload(
            "adaptive",
            budget_tokens=8000,
            model_name="claude-opus-4-6",
            actual_model_id=None,
        )
        assert payload == {"type": "adaptive"}

    def test_uses_actual_model_id_for_adaptive_detection(self):
        # Bedrock-style alias where only actual_model_id reveals the family.
        payload = resolve_anthropic_thinking_payload(
            "enabled",
            budget_tokens=10000,
            model_name="my-custom-alias",
            actual_model_id="us.anthropic.claude-opus-4-7",
        )
        assert payload is not None
        assert payload["type"] == "adaptive"
        assert payload["display"] == "summarized"


class TestOffAndUnknownModesReturnNone:
    """Anything that isn't a documented 'thinking on' mode must return None."""

    @pytest.mark.parametrize(
        "mode",
        ["off", "disabled", "", "nonsense", "true", None],
    )
    @pytest.mark.parametrize(
        "model_name",
        ["claude-opus-4-7", "claude-sonnet-4-5", "claude-3-5-sonnet"],
    )
    def test_returns_none_for_off_and_unknown(self, mode, model_name):
        payload = resolve_anthropic_thinking_payload(
            mode,
            budget_tokens=10000,
            model_name=model_name,
            actual_model_id=None,
        )
        assert payload is None


class TestNoWireLeaks:
    """Fuzz-style: no combination should ever produce a wire-invalid type."""

    def test_every_combination_produces_a_wire_valid_type_or_none(self):
        modes = ["enabled", "adaptive", "off", "disabled", "unknown", "", None]
        models = [
            "claude-4-5-sonnet",
            "claude-sonnet-4-5",
            "claude-3-5-sonnet",
            "claude-opus-4-6",
            "claude-opus-4-7",
            "claude-opus-4-8",
            "claude-sonnet-5",
            "claude-fable-5",
        ]
        for mode in modes:
            for model in models:
                payload = resolve_anthropic_thinking_payload(
                    mode,
                    budget_tokens=10000,
                    model_name=model,
                    actual_model_id=None,
                )
                if payload is None:
                    continue
                assert payload["type"] in ("enabled", "adaptive", "disabled"), (
                    f"leak: mode={mode!r} model={model!r} "
                    f"produced type={payload['type']!r}"
                )
                # Regression assertion tied to the reporter's exact error:
                # never mix adaptive on a classic-only model, and vice versa.
                is_adaptive_model = model in {
                    "claude-opus-4-6",
                    "claude-opus-4-7",
                    "claude-opus-4-8",
                    "claude-sonnet-5",
                    "claude-fable-5",
                }
                expected_type = "adaptive" if is_adaptive_model else "enabled"
                assert payload["type"] == expected_type, (
                    f"routing bug: mode={mode!r} model={model!r} "
                    f"produced type={payload['type']!r} but expected {expected_type!r}"
                )
