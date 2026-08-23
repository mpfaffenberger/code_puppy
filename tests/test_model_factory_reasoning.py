from unittest.mock import patch

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
