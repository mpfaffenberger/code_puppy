"""Fable 5.1 progress-update thinking display quirks.

Fable 5.1 emits short progress updates between tool calls as ``thinking``
blocks. With the default ``thinking.display: "omitted"`` they arrive empty and
long agentic turns look silent. ``display: "updates"`` (behind the
``thinking-display-updates-2026-08-18`` beta header) surfaces them as text
while reasoning stays hidden.
"""

import json
from unittest.mock import patch

import pytest

from code_puppy import config as cp_config
from code_puppy.claude_cache_client import (
    THINKING_DISPLAY_UPDATES_BETA,
    ClaudeCacheAsyncClient,
    _enforce_thinking_display_summary,
)
from code_puppy.command_line.model_settings_defs import (
    SETTING_DEFINITIONS,
    _get_setting_choices,
    _supports_setting,
)
from code_puppy.model_utils import (
    THINKING_DISPLAY_CHOICES,
    get_anthropic_thinking_display_choices,
    resolve_anthropic_thinking_payload,
    should_use_anthropic_thinking_updates,
    supports_adaptive_thinking,
)


class TestShouldUseThinkingUpdates:
    @pytest.mark.parametrize(
        "alias, actual_model_id, expected",
        [
            ("claude-fable-5-1", None, True),
            ("claude-fable-5.1", None, True),
            ("claude-5-1-fable", None, True),
            # The alias doesn't contain the tag, but the actual_model_id does
            ("fable", "claude-fable-5-1", True),
            # Fable 5 (no minor) gets summarized, not updates
            ("claude-fable-5", None, False),
            ("claude-sonnet-5", None, False),
            ("gpt-4o", None, False),
        ],
        ids=[
            "fable_5_1_dashed",
            "fable_5_1_dotted",
            "five_1_fable",
            "via_actual_model_id",
            "fable_5_not_updates",
            "sonnet_5_not_updates",
            "unknown_model",
        ],
    )
    def test_predicate(self, alias, actual_model_id, expected):
        assert (
            should_use_anthropic_thinking_updates(
                alias, actual_model_id=actual_model_id
            )
            is expected
        )

    def test_fable_5_1_still_counts_as_adaptive(self):
        # The "fable-5" adaptive tag must keep matching the 5.1 IDs, or the
        # payload below silently downgrades to classic enabled+budget shape.
        assert supports_adaptive_thinking("claude-fable-5-1") is True
        assert supports_adaptive_thinking("claude-fable-5.1") is True


class TestResolveThinkingPayloadForFable:
    @pytest.mark.parametrize("mode", ["enabled", "adaptive"])
    def test_fable_5_1_gets_updates_display(self, mode):
        result = resolve_anthropic_thinking_payload(
            mode,
            budget_tokens=1024,
            model_name="claude-fable-5-1",
            actual_model_id=None,
        )
        assert result == {"type": "adaptive", "display": "updates"}

    def test_fable_5_keeps_summarized_display(self):
        result = resolve_anthropic_thinking_payload(
            "adaptive",
            budget_tokens=1024,
            model_name="claude-fable-5",
            actual_model_id=None,
        )
        assert result == {"type": "adaptive", "display": "summarized"}

    def test_disabled_still_omits_payload(self):
        result = resolve_anthropic_thinking_payload(
            "off",
            budget_tokens=1024,
            model_name="claude-fable-5-1",
            actual_model_id=None,
        )
        assert result is None

    @pytest.mark.parametrize(
        "thinking_display, expected",
        [
            ("summarized", "summarized"),
            ("updates", "updates"),
            (None, "updates"),
            # Not an offered choice -> model default, never forwarded raw.
            ("omitted", "updates"),
            ("bogus", "updates"),
        ],
        ids=["summarized", "updates", "unset", "omitted_rejected", "garbage"],
    )
    def test_fable_5_1_honors_thinking_display_setting(
        self, thinking_display, expected
    ):
        result = resolve_anthropic_thinking_payload(
            "adaptive",
            budget_tokens=1024,
            model_name="claude-fable-5-1",
            actual_model_id=None,
            thinking_display=thinking_display,
        )
        assert result == {"type": "adaptive", "display": expected}

    def test_thinking_display_ignored_on_non_updates_model(self):
        # Fable 5 offers no display choice; a stray setting must not leak in.
        result = resolve_anthropic_thinking_payload(
            "adaptive",
            budget_tokens=1024,
            model_name="claude-fable-5",
            actual_model_id=None,
            thinking_display="updates",
        )
        assert result == {"type": "adaptive", "display": "summarized"}


class TestThinkingDisplayChoices:
    def test_fable_5_1_offers_updates_and_summarized(self):
        assert get_anthropic_thinking_display_choices("claude-fable-5-1") == (
            "updates",
            "summarized",
        )

    def test_choices_via_actual_model_id(self):
        assert get_anthropic_thinking_display_choices(
            "fable", actual_model_id="claude-fable-5-1"
        ) == ("updates", "summarized")

    @pytest.mark.parametrize("alias", ["claude-fable-5", "claude-opus-5", "gpt-4o"])
    def test_no_choices_elsewhere(self, alias):
        assert get_anthropic_thinking_display_choices(alias) == ()

    def test_default_is_first_choice(self):
        # resolve_anthropic_thinking_payload falls back to choices[0]; keep
        # "updates" in front or the default silently flips.
        assert THINKING_DISPLAY_CHOICES[0] == "updates"


class TestThinkingDisplayModelSetting:
    """The /model_settings menu offers Thinking Display only for Fable 5.1."""

    def test_setting_definition_matches_wire_choices(self):
        setting = SETTING_DEFINITIONS["thinking_display"]
        assert setting["type"] == "choice"
        assert setting["choices"] == list(THINKING_DISPLAY_CHOICES)
        assert setting["default"] == "updates"
        assert _get_setting_choices("thinking_display", None) == list(
            THINKING_DISPLAY_CHOICES
        )

    @pytest.mark.parametrize(
        "model_name, expected",
        [
            ("claude-fable-5-1", True),
            ("claude-code-claude-fable-5-1-long", True),
            ("claude-fable-5", False),
            ("claude-code-claude-opus-4-8-long", False),
            ("gpt-5", False),
        ],
    )
    def test_supported_by_model_name(self, model_name, expected):
        mock_config = {model_name: {}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert (
                cp_config.model_supports_setting(model_name, "thinking_display")
                is expected
            )

    def test_supported_via_underlying_name(self):
        # Alias says nothing; the config's real model ID does.
        mock_config = {"fable": {"name": "claude-fable-5-1"}}
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value=mock_config,
        ):
            assert cp_config.model_supports_setting("fable", "thinking_display")

    def test_oauth_entry_without_explicit_supported_settings_entry(self):
        # Claude Code OAuth entries carry an explicit supported_settings list
        # that predates this setting; identity detection must still win.
        models_config = {
            "claude-code-claude-fable-5-1-long": {
                "name": "claude-fable-5-1",
                "supported_settings": ["temperature", "extended_thinking"],
            }
        }
        assert _supports_setting(
            "claude-code-claude-fable-5-1-long", "thinking_display", models_config
        )


class TestSummaryEnforcementRespectsUpdates:
    def test_updates_survives_on_fable_5_1(self):
        payload = {
            "model": "claude-fable-5-1",
            "thinking": {"type": "adaptive", "display": "updates"},
        }
        assert _enforce_thinking_display_summary(payload) is False
        assert payload["thinking"]["display"] == "updates"

    def test_updates_clobbered_on_non_updates_model(self):
        # Fable 5 requires summarized and doesn't support updates; a stray
        # "updates" display gets coerced back like any other bad value.
        payload = {
            "model": "claude-fable-5",
            "thinking": {"type": "adaptive", "display": "updates"},
        }
        assert _enforce_thinking_display_summary(payload) is True
        assert payload["thinking"]["display"] == "summarized"

    def test_missing_display_still_coerced_to_summarized(self):
        payload = {
            "model": "claude-fable-5-1",
            "thinking": {"type": "adaptive"},
        }
        assert _enforce_thinking_display_summary(payload) is True
        assert payload["thinking"]["display"] == "summarized"


class TestEnsureThinkingUpdatesBeta:
    @staticmethod
    def _body(display):
        return json.dumps(
            {
                "model": "claude-fable-5-1",
                "thinking": {"type": "adaptive", "display": display},
            }
        ).encode("utf-8")

    def test_adds_beta_when_body_requests_updates(self):
        headers = {}
        modified = ClaudeCacheAsyncClient._ensure_thinking_updates_beta(
            headers, self._body("updates")
        )
        assert modified is True
        assert headers["anthropic-beta"] == THINKING_DISPLAY_UPDATES_BETA

    def test_appends_to_existing_betas(self):
        headers = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}
        assert ClaudeCacheAsyncClient._ensure_thinking_updates_beta(
            headers, self._body("updates")
        )
        betas = headers["anthropic-beta"].split(",")
        assert "oauth-2025-04-20" in betas
        assert "interleaved-thinking-2025-05-14" in betas
        assert THINKING_DISPLAY_UPDATES_BETA in betas

    def test_idempotent(self):
        headers = {"anthropic-beta": THINKING_DISPLAY_UPDATES_BETA}
        assert (
            ClaudeCacheAsyncClient._ensure_thinking_updates_beta(
                headers, self._body("updates")
            )
            is False
        )
        assert headers["anthropic-beta"] == THINKING_DISPLAY_UPDATES_BETA

    @pytest.mark.parametrize(
        "body",
        [None, b"", b"not json", json.dumps({"model": "claude-fable-5-1"}).encode()],
        ids=["none", "empty", "invalid_json", "no_thinking"],
    )
    def test_no_change_without_updates_display(self, body):
        headers = {}
        assert (
            ClaudeCacheAsyncClient._ensure_thinking_updates_beta(headers, body) is False
        )
        assert "anthropic-beta" not in headers

    def test_summarized_display_does_not_add_beta(self):
        headers = {}
        assert (
            ClaudeCacheAsyncClient._ensure_thinking_updates_beta(
                headers, self._body("summarized")
            )
            is False
        )
        assert "anthropic-beta" not in headers
