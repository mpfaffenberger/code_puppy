"""Regression tests for the claude-sonnet-5-5 forced tool_choice workaround.

pydantic-ai 2.51.0 (our pinned version) correctly excludes claude-opus-5-5
from forced tool_choice ("any"/"tool") support, but claude-sonnet-5-5 has
the identical issue and wasn't covered until pydantic-ai 2.52.0. Its
profile source confirms both models were tested and are both affected:

    # `claude-opus-5-5` returns a 400 for both shapes where
    # `claude-opus-5` returns 200, and likewise `claude-sonnet-5-5`
    # where `claude-sonnet-5` returns 200.

At least WMTLLMGATEWAY (and possibly Anthropic's API directly, per the
comment above) rejects forced tool_choice for claude-sonnet-5-5 with:

    [HTTP 400] tool_choice: type "tool" and "any" are not supported for
    this model.

Until we bump past pydantic-ai 2.52.0, code_puppy.model_utils.
anthropic_forced_tool_choice_unsupported and code_puppy.model_factory.
forced_tool_choice_profile patch the gap locally. See the docstrings on
those two functions for the full story.
"""

import os
from unittest.mock import patch

from code_puppy.model_factory import ModelFactory, forced_tool_choice_profile
from code_puppy.model_utils import anthropic_forced_tool_choice_unsupported


class TestAnthropicForcedToolChoiceUnsupported:
    def test_sonnet_5_5_is_flagged(self):
        assert anthropic_forced_tool_choice_unsupported("sonnet", "claude-sonnet-5-5")

    def test_sonnet_5_5_is_flagged_by_alias_alone(self):
        # actual_model_id is optional; callers sometimes only have the alias.
        assert anthropic_forced_tool_choice_unsupported("claude-sonnet-5-5")

    def test_is_case_insensitive(self):
        assert anthropic_forced_tool_choice_unsupported("sonnet", "Claude-Sonnet-5-5")

    def test_sonnet_5_is_not_flagged(self):
        # Only the 5.5 point release is affected -- claude-sonnet-5 (no
        # trailing "-5") returns 200 per pydantic-ai's own test notes.
        assert not anthropic_forced_tool_choice_unsupported("sonnet", "claude-sonnet-5")

    def test_opus_5_5_is_not_flagged_here(self):
        # pydantic-ai 2.51.0 already excludes claude-opus-5-5 natively --
        # our denylist should stay minimal and not duplicate what
        # pydantic-ai already gets right.
        assert not anthropic_forced_tool_choice_unsupported("opus", "claude-opus-5-5")

    def test_unrelated_model_is_not_flagged(self):
        assert not anthropic_forced_tool_choice_unsupported("opus", "claude-opus-4-8")

    def test_no_actual_model_id_falls_back_to_model_name(self):
        assert not anthropic_forced_tool_choice_unsupported("gpt-5")


class TestForcedToolChoiceProfile:
    def test_returns_override_for_sonnet_5_5(self):
        profile = forced_tool_choice_profile("sonnet", {"name": "claude-sonnet-5-5"})
        assert profile is not None
        assert profile["anthropic_supports_forced_tool_choice"] is False

    def test_returns_none_for_unaffected_model(self):
        assert forced_tool_choice_profile("sonnet", {"name": "claude-sonnet-5"}) is None

    def test_returns_none_for_opus_5_5(self):
        # pydantic-ai already handles this one; we shouldn't build a
        # (harmless but redundant) override profile for it.
        assert forced_tool_choice_profile("opus", {"name": "claude-opus-5-5"}) is None

    def test_falls_back_to_model_name_when_config_has_no_name(self):
        profile = forced_tool_choice_profile("claude-sonnet-5-5", {})
        assert profile is not None
        assert profile["anthropic_supports_forced_tool_choice"] is False


class TestGetModelWiring:
    """End-to-end: ModelFactory.get_model must actually apply the override."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_model_anthropic_sonnet_5_5_gets_override(self):
        config = {
            "sonnet-5-5": {"type": "anthropic", "name": "claude-sonnet-5-5"},
        }
        model = ModelFactory.get_model("sonnet-5-5", config)
        assert model is not None
        assert model.profile.get("anthropic_supports_forced_tool_choice") is False

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_model_anthropic_unaffected_model_is_untouched(self):
        config = {
            "sonnet-5": {"type": "anthropic", "name": "claude-sonnet-5"},
        }
        model = ModelFactory.get_model("sonnet-5", config)
        assert model is not None
        assert model.profile.get("anthropic_supports_forced_tool_choice") is True
