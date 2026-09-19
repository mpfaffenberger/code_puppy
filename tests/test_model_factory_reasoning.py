from unittest.mock import patch

import pytest

from code_puppy.model_factory import ModelFactory, make_model_settings


def test_openai_gpt5_alias_uses_responses_reasoning_settings():
    config = {
        "openai-gpt-5.6-luna": {
            "type": "openai",
            "provider": "openai",
            "name": "gpt-5.6-luna",
            "context_length": 1_050_000,
            "supported_settings": [
                "temperature",
                "top_p",
                "reasoning_effort",
                "verbosity",
            ],
        }
    }
    with (
        patch.object(ModelFactory, "load_config", return_value=config),
        patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={},
        ),
    ):
        settings = make_model_settings("openai-gpt-5.6-luna", max_tokens=4096)

    assert settings["openai_reasoning_effort"] == "medium"
    assert settings["openai_reasoning_summary"] == "auto"
    assert settings["openai_reasoning_context"] == "all_turns"
    assert settings["openai_reasoning_mode"] == "standard"
    assert settings["openai_text_verbosity"] == "medium"


def test_gpt56_alias_profile_enables_reasoning_fields():
    """The exact extra-model alias gets the profile gates it needs."""
    from code_puppy.model_factory import _thinking_tags_profile

    profile = _thinking_tags_profile(
        "openai-gpt-5.6-luna",
        {"name": "gpt-5.6-luna"},
    )

    assert profile is not None
    assert profile["openai_responses_supports_reasoning_mode"] is True
    assert profile["openai_responses_supports_reasoning_context"] is True
    assert profile["openai_supports_encrypted_reasoning_content"] is True


def test_alias_keyed_custom_responses_model_gets_reasoning_settings():
    """A config key without "gpt-5" must still match on the underlying name."""
    config = {
        "luna-responses": {
            "type": "custom_openai_responses",
            "name": "gpt-5.6-luna",
            "context_length": 1_050_000,
            "custom_endpoint": {
                "url": "https://api.openai.com/v1",
                "api_key": "$OPENAI_API_KEY",
            },
            "supported_settings": [
                "temperature",
                "top_p",
                "reasoning_effort",
                "verbosity",
            ],
        }
    }
    with (
        patch.object(ModelFactory, "load_config", return_value=config),
        patch(
            "code_puppy.config.get_custom_model_settings",
            return_value={},
        ),
    ):
        settings = make_model_settings("luna-responses", max_tokens=4096)

    assert settings["openai_reasoning_effort"] == "medium"
    assert settings["openai_reasoning_summary"] == "auto"
    assert settings["openai_reasoning_context"] == "all_turns"
    assert settings["openai_reasoning_mode"] == "standard"


# Each case pairs a model type with the settings class its factory builds:
# chatgpt_oauth is always Responses, azure_foundry only for gpt-5 deployments.
_RESPONSES_API_CASES = [
    ("chatgpt_oauth", "gpt-5.2", True),
    ("chatgpt_oauth", "o3", True),
    ("chatgpt_oauth", "codex-mini-latest", True),
    ("azure_foundry_openai", "gpt-5.2", True),
    ("azure_foundry_openai", "o3", False),
    ("azure_foundry_openai", "codex-mini-latest", False),
    ("custom_openai_responses", "o3", True),
    ("custom_openai", "o3", False),
    ("openai", "o3", False),
    ("azure_openai", "o3", False),
]


@pytest.mark.parametrize(
    ("model_type", "name", "expect_responses"), _RESPONSES_API_CASES
)
def test_settings_class_matches_constructed_model(model_type, name, expect_responses):
    """The settings class must follow the wire format the model factory builds.

    An o-series model under ``chatgpt_oauth`` is still a Responses model, so
    emitting Chat settings for it would send the wrong payload shape.
    """
    import pydantic_ai.models.openai as oai

    constructed: list[str] = []
    real_chat = oai.OpenAIChatModelSettings
    real_responses = oai.OpenAIResponsesModelSettings

    def record_chat(*args, **kwargs):
        constructed.append("chat")
        return real_chat(*args, **kwargs)

    def record_responses(*args, **kwargs):
        constructed.append("responses")
        return real_responses(*args, **kwargs)

    config = {"m": {"type": model_type, "name": name}}
    with (
        patch.object(oai, "OpenAIChatModelSettings", record_chat),
        patch.object(oai, "OpenAIResponsesModelSettings", record_responses),
        patch.object(ModelFactory, "load_config", return_value=config),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
    ):
        make_model_settings("m", max_tokens=4096)

    expected = "responses" if expect_responses else "chat"
    assert constructed == [expected]


# Renamed Azure deployments are the risky case: the plugin decides Responses
# vs Chat from the deployment name alone, so these must agree with it exactly.
_AZURE_DEPLOYMENT_CASES = [
    "gpt-5.2",
    "gpt-5-4",
    "prod-gpt5-deploy",
    "my-deployment",
    "o3",
    "GPT-5.2",
]


@pytest.mark.parametrize("deployment_name", _AZURE_DEPLOYMENT_CASES)
def test_azure_foundry_settings_track_the_real_plugin(deployment_name):
    """Pin the azure_foundry mirror to the plugin's actual model choice.

    The plugin keys off the deployment name only, so a renamed gpt-5
    deployment legitimately gets a Chat model. Asserting against the real
    factory means a plugin change breaks this test instead of silently
    desynchronising the settings class from the wire format.
    """
    from unittest.mock import Mock

    from code_puppy.model_factory import _uses_responses_api

    pytest.importorskip("code_puppy_core_plugins.azure_foundry.register_callbacks")
    from code_puppy_core_plugins.azure_foundry.register_callbacks import (
        _create_azure_foundry_openai_model,
    )

    token_provider = Mock()
    token_provider.check_auth_status.return_value = (True, "Valid", "user@test.com")
    token_provider.get_token = Mock(return_value="token123")

    with (
        patch(
            "code_puppy_core_plugins.azure_foundry.register_callbacks.get_token_provider",
            return_value=token_provider,
        ),
        patch("openai.AsyncAzureOpenAI"),
        patch(
            "code_puppy.provider_identity.resolve_provider_identity",
            return_value="azure_foundry_openai",
        ),
        patch("code_puppy.provider_identity.make_openai_provider", return_value=Mock()),
        patch("pydantic_ai.models.openai.OpenAIResponsesModel") as responses_model,
        patch("pydantic_ai.models.openai.OpenAIChatModel"),
    ):
        _create_azure_foundry_openai_model(
            "gpt-5.2",
            {"name": deployment_name, "foundry_resource": "res"},
            {},
        )
        plugin_built_responses = responses_model.called

    config = {"type": "azure_foundry_openai", "name": deployment_name}
    assert _uses_responses_api("gpt-5.2", config) is plugin_built_responses
