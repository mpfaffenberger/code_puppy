"""Tests for suppressing Anthropic unsupported-sampling-parameter noise.

Some Claude models (e.g. Fable 5) reject sampling params like temperature;
pydantic-ai drops them and warns on every request. We fix this two ways:

1. Root cause: ``make_model_settings`` consults pydantic-ai's model profile
   (``anthropic_disallows_sampling_settings``) and never puts sampling params
   into settings for those models.
2. Backstop: a narrowly-scoped warnings filter installed by
   ``pydantic_patches`` swallows the exact warning message if it ever fires.
"""

import warnings
from unittest.mock import patch

from code_puppy import pydantic_patches
from code_puppy.model_factory import ModelFactory, make_model_settings
from code_puppy.model_utils import anthropic_disallows_sampling_settings

SAMPLING_PARAMS = ("temperature", "top_p", "top_k")

WARNING_MESSAGE = (
    "Sampling parameters ['temperature'] are not supported by "
    "'claude-fable-5'. These settings will be ignored."
)


def _build_settings(model_key: str, model_configs: dict, effective: dict):
    with (
        patch.object(ModelFactory, "load_config", return_value=model_configs),
        patch(
            "code_puppy.config.get_effective_model_settings",
            return_value=effective,
        ),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
    ):
        return make_model_settings(model_key)


class TestProfileHelper:
    """anthropic_disallows_sampling_settings mirrors pydantic-ai's profile."""

    def test_fable_disallows_sampling(self):
        assert anthropic_disallows_sampling_settings("claude-fable-5") is True

    def test_classic_claude_allows_sampling(self):
        assert anthropic_disallows_sampling_settings("claude-sonnet-4-5") is False

    def test_alias_checked_via_actual_model_id(self):
        # Alias alone says nothing; the real API id decides.
        assert (
            anthropic_disallows_sampling_settings("my-fable-alias", "claude-fable-5")
            is True
        )

    def test_non_anthropic_name_allows_sampling(self):
        assert anthropic_disallows_sampling_settings("gpt-5") is False


class TestMakeModelSettingsSampling:
    """Sampling params never enter settings for no-sampling Claude models."""

    def test_no_sampling_model_gets_no_sampling_params(self):
        model_configs = {
            "anthropic-fable": {"type": "anthropic", "name": "claude-fable-5"}
        }
        settings = _build_settings(
            "anthropic-fable",
            model_configs,
            # Even a configured temperature/top_p must be stripped.
            {"temperature": 0.7, "top_p": 0.9},
        )
        for param in SAMPLING_PARAMS:
            assert param not in settings, f"{param} should not be sent to fable"

    def test_normal_claude_keeps_configured_temperature(self):
        model_configs = {
            "anthropic-sonnet": {"type": "anthropic", "name": "claude-sonnet-4-5"}
        }
        settings = _build_settings(
            "anthropic-sonnet", model_configs, {"temperature": 0.3}
        )
        assert settings["temperature"] == 0.3

    def test_normal_claude_defaults_temperature_to_one(self):
        # Extended thinking requires temperature=1.0 when nothing is set.
        model_configs = {
            "anthropic-sonnet": {"type": "anthropic", "name": "claude-sonnet-4-5"}
        }
        settings = _build_settings("anthropic-sonnet", model_configs, {})
        assert settings["temperature"] == 1.0


class TestWarningsBackstop:
    """The warnings filter swallows exactly the pydantic-ai message shape."""

    def test_filter_suppresses_exact_message(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert pydantic_patches.patch_silence_anthropic_sampling_warnings()
            warnings.warn(WARNING_MESSAGE, UserWarning, stacklevel=2)
        assert caught == []

    def test_filter_suppresses_other_params_and_models(self):
        message = (
            "Sampling parameters ['temperature', 'top_p', 'top_k'] are not "
            "supported by 'claude-mythos-9'. These settings will be ignored."
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_anthropic_sampling_warnings()
            warnings.warn(message, UserWarning, stacklevel=2)
        assert caught == []

    def test_filter_leaves_other_user_warnings_alone(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pydantic_patches.patch_silence_anthropic_sampling_warnings()
            warnings.warn("Something else entirely", UserWarning, stacklevel=2)
        assert len(caught) == 1
        assert str(caught[0].message) == "Something else entirely"
