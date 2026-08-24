"""Tests for the pure setting-choice logic in model_settings_defs.py.

_get_setting_choices() used to live inline in model_settings_menu.py; the
termflow refactor moved it here as a standalone pure function. These tests
cover the OpenAI reasoning_effort dynamic-choice detection specifically --
see model_utils.get_openai_reasoning_effort_choices for the source of truth
on which choices each OpenAI model family actually supports.
"""

from code_puppy.command_line.model_settings_defs import _get_setting_choices


class TestGetSettingChoicesReasoningEffort:
    def test_gpt_5_6_offers_max(self):
        catalog = {"my-5.6": {"name": "gpt-5.6"}}
        choices = _get_setting_choices("reasoning_effort", "my-5.6", catalog)
        assert "max" in choices
        assert "xhigh" in choices

    def test_plain_gpt_5_excludes_xhigh_and_max(self):
        catalog = {"my-5": {"name": "gpt-5"}}
        choices = _get_setting_choices("reasoning_effort", "my-5", catalog)
        assert "xhigh" not in choices
        assert "max" not in choices
        assert "none" in choices and "high" in choices

    def test_o_series_gets_low_medium_high(self):
        catalog = {"o3-mini": {"name": "o3-mini"}}
        choices = _get_setting_choices("reasoning_effort", "o3-mini", catalog)
        assert set(choices) == {"low", "medium", "high"}

    def test_fixed_effort_model_has_no_choices(self):
        catalog = {"o1-mini": {"name": "o1-mini"}}
        choices = _get_setting_choices("reasoning_effort", "o1-mini", catalog)
        assert choices == []

    def test_alias_fallback_via_catalog_name(self):
        """extra_models.json-style aliases: catalog key doesn't match any
        OpenAI family token, but the underlying \"name\" does."""
        catalog = {"acme-reasoner": {"name": "o3"}}
        choices = _get_setting_choices("reasoning_effort", "acme-reasoner", catalog)
        assert set(choices) == {"low", "medium", "high"}

    def test_explicit_catalog_flags_can_widen_a_recognized_model(self):
        catalog = {
            "my-5": {
                "name": "gpt-5",
                "supports_xhigh_reasoning": True,
                "supports_max_reasoning": True,
            }
        }
        choices = _get_setting_choices("reasoning_effort", "my-5", catalog)
        assert "xhigh" in choices
        assert "max" in choices

    def test_unrecognized_model_falls_back_to_legacy_flags(self):
        """A model get_openai_reasoning_effort_choices doesn't recognize at
        all still gets the old opt-in-flag behavior, not a hard failure."""
        catalog = {"some-custom-model": {"name": "some-custom-model"}}
        choices = _get_setting_choices("reasoning_effort", "some-custom-model", catalog)
        assert "xhigh" not in choices
        assert "max" not in choices

    def test_advertised_catalog_choices_take_precedence(self):
        catalog = {
            "my-5": {"name": "gpt-5", "setting_choices": {"reasoning_effort": ["low"]}}
        }
        choices = _get_setting_choices("reasoning_effort", "my-5", catalog)
        assert choices == ["low"]
