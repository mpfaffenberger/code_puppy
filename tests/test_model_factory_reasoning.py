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
