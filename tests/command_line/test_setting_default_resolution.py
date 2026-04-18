"""Tests for per-model default resolution in the model settings menu.

Locks in the behavior that ``extended_thinking`` defaults to ``"adaptive"``
for Opus 4-6/4-7 models and ``"enabled"`` for other Anthropic models, so
the TUI display (and "reset to default") agrees with what the runtime
model_factory actually sends to Anthropic.
"""

from code_puppy.command_line.model_settings_menu import (
    SETTING_DEFINITIONS,
    _get_setting_default,
)


class TestExtendedThinkingDefault:
    """Extended thinking is the one setting with per-model defaults."""

    def test_opus_4_7_defaults_to_adaptive(self):
        assert (
            _get_setting_default("extended_thinking", "claude-opus-4-7") == "adaptive"
        )

    def test_opus_4_7_alternate_naming_defaults_to_adaptive(self):
        assert (
            _get_setting_default("extended_thinking", "anthropic-4-7-opus-latest")
            == "adaptive"
        )

    def test_opus_4_6_defaults_to_adaptive(self):
        assert (
            _get_setting_default("extended_thinking", "claude-opus-4-6") == "adaptive"
        )

    def test_older_claude_defaults_to_enabled(self):
        assert _get_setting_default("extended_thinking", "claude-opus-4-5") == "enabled"
        assert (
            _get_setting_default("extended_thinking", "claude-3-5-sonnet-20241022")
            == "enabled"
        )

    def test_no_model_falls_back_to_static_default(self):
        # When model is unknown, defer to the static SETTING_DEFINITIONS default.
        assert _get_setting_default("extended_thinking", None) == "enabled"

    def test_static_default_matches_non_opus_default(self):
        # Sanity check: the static fallback in SETTING_DEFINITIONS matches
        # get_default_extended_thinking's non-Opus-4-6/4-7 return value, so
        # no surprises when a user has no model selected.
        static_default = SETTING_DEFINITIONS["extended_thinking"]["default"]
        assert static_default == "enabled"


class TestOtherSettingsDefaultsUnchanged:
    """Non-extended_thinking settings still use the static defaults."""

    def test_temperature_default_is_none_regardless_of_model(self):
        assert _get_setting_default("temperature", "claude-opus-4-7") is None
        assert _get_setting_default("temperature", None) is None

    def test_reasoning_effort_default(self):
        assert _get_setting_default("reasoning_effort", "gpt-5") == "medium"

    def test_budget_tokens_default(self):
        assert _get_setting_default("budget_tokens", "claude-opus-4-7") == 10000

    def test_unknown_setting_returns_none(self):
        assert _get_setting_default("does_not_exist", "claude-opus-4-7") is None
