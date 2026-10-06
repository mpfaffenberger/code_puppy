from unittest.mock import patch

import pytest

from code_puppy.model_factory import ModelFactory, make_model_settings

# Profile flags pydantic-ai gates reasoning.mode/context, ``include`` and the
# sampling-param stripping on. It infers them by model-name prefix, so newer
# families (gpt-6+) need them set explicitly.
_REASONING_PROFILE_KEYS = (
    "openai_responses_supports_reasoning_mode",
    "openai_responses_supports_reasoning_context",
    "openai_supports_encrypted_reasoning_content",
    "openai_supports_reasoning",
    "openai_reasoning_enabled_by_default",
    "openai_supports_reasoning_effort_none",
)


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
    for key in _REASONING_PROFILE_KEYS:
        assert profile[key] is True


@pytest.mark.parametrize(
    ("config_key", "underlying"),
    [
        ("openai-gpt-6", "gpt-6"),
        ("openai-gpt-6.1", "gpt-6.1"),
        ("codex-gpt-6-astra", "gpt-6-astra"),
        ("my-alias", "gpt-6.1"),
    ],
)
def test_gpt6_family_profile_enables_reasoning_fields(config_key, underlying):
    """GPT-6+ is newer than 5.6, so it needs the same profile gates.

    The settings path already emits ``openai_reasoning_context``/``mode`` for
    these models; without matching profile flags pydantic-ai would drop them.
    """
    from code_puppy.model_factory import _thinking_tags_profile

    profile = _thinking_tags_profile(config_key, {"name": underlying})

    assert profile is not None
    for key in _REASONING_PROFILE_KEYS:
        assert profile[key] is True


def test_gpt6_profile_matches_on_config_key_when_name_missing():
    from code_puppy.model_factory import _thinking_tags_profile

    profile = _thinking_tags_profile("openai-gpt-6", {})

    assert profile is not None
    for key in _REASONING_PROFILE_KEYS:
        assert profile[key] is True


@pytest.mark.parametrize(
    ("config_key", "config"),
    [
        # Regression guards: the gate must stay at >= 5.6.
        ("some-alias", {"name": "gpt-5.5"}),
        ("some-alias", {"name": "gpt-5.4"}),
        ("some-alias", {"name": "gpt-4o"}),
        ("some-alias", {"name": "o3"}),
        # The underlying name wins: an alias must not flag another backend.
        ("gpt-6-proxy", {"name": "claude-sonnet-4"}),
        ("gpt-5.6-foo", {"name": "o3"}),
        # Malformed ``name`` values never match and never raise.
        ("some-alias", {"name": None}),
        ("some-alias", {"name": ""}),
        ("some-alias", {"name": 123}),
    ],
)
def test_profile_flags_are_not_applied_to_non_56_plus_models(config_key, config):
    from code_puppy.model_factory import _thinking_tags_profile

    assert _thinking_tags_profile(config_key, config) is None


_SAMPLING_SETTINGS = {"temperature": 0.2, "top_p": 0.9}


def _capture_request(api: str, underlying: str, model_settings: dict):
    """Run one agent turn against a mock transport.

    Returns the JSON request body and the "Sampling parameters" warnings
    pydantic-ai emitted, so tests can pin what actually reaches the wire.
    """
    import asyncio
    import json
    import warnings

    import httpx
    from openai import AsyncOpenAI
    from pydantic_ai import Agent
    from pydantic_ai.exceptions import ModelHTTPError
    from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.model_factory import _strict_openai_profile, _thinking_tags_profile

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(400, json={"error": {"message": "stop", "type": "x"}})

    provider = OpenAIProvider(
        openai_client=AsyncOpenAI(
            api_key="test-key",
            base_url="https://proxy.example.com/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            max_retries=0,
        )
    )
    config = {"name": underlying}
    if api == "responses":
        model = OpenAIResponsesModel(
            model_name=underlying,
            provider=provider,
            profile=_thinking_tags_profile("my-model", config),
        )
    else:
        model = OpenAIChatModel(
            model_name=underlying,
            provider=provider,
            profile=_strict_openai_profile("my-model", config),
        )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        with pytest.raises(ModelHTTPError):
            asyncio.run(Agent(model, model_settings=model_settings).run("hi"))
    sampling_warnings = [w for w in caught if "Sampling parameters" in str(w.message)]
    return captured, sampling_warnings


@pytest.mark.parametrize("underlying", ["gpt-6", "gpt-6.1", "gpt-5.6-luna"])
def test_responses_request_body_honors_reasoning_settings(underlying):
    """What actually goes on the wire for a reasoning model with our profile.

    Pins the behavior users see in /model_settings: a non-default
    ``reasoning_context`` reaches the request and ``include`` asks for
    encrypted reasoning. pydantic-ai infers none of this for gpt-6 by name.
    """
    body, _ = _capture_request(
        "responses",
        underlying,
        {
            **_SAMPLING_SETTINGS,
            "openai_reasoning_effort": "high",
            "openai_reasoning_context": "current_turn",
            "openai_reasoning_mode": "standard",
        },
    )

    assert body["reasoning"]["effort"] == "high"
    assert body["reasoning"]["context"] == "current_turn"
    assert body["reasoning"]["mode"] == "standard"
    assert "reasoning.encrypted_content" in body["include"]


@pytest.mark.parametrize("api", ["responses", "chat"])
@pytest.mark.parametrize("underlying", ["gpt-6", "gpt-6.1", "gpt-5.6-luna"])
@pytest.mark.parametrize(
    ("effort", "sampling_sent"),
    [
        # Reasoning off: sampling params are legal and must be kept.
        ("none", True),
        # Reasoning on, or on by default (effort unset): they are stripped.
        ("high", False),
        (None, False),
    ],
)
def test_sampling_params_follow_reasoning_state_like_gpt56(
    api, underlying, effort, sampling_sent
):
    """gpt-6+ must behave exactly like gpt-5.6 on both wire formats.

    The profile flags drive pydantic-ai's sampling-param stripping. This also
    covers Chat Completions models, which receive the same profile through
    ``_strict_openai_profile``.
    """
    settings = dict(_SAMPLING_SETTINGS)
    if effort is not None:
        settings["openai_reasoning_effort"] = effort

    body, sampling_warnings = _capture_request(api, underlying, settings)

    assert ("temperature" in body) is sampling_sent
    assert ("top_p" in body) is sampling_sent
    assert bool(sampling_warnings) is (not sampling_sent)


@pytest.mark.parametrize("underlying", ["gpt-6", "gpt-6.1", "gpt-5.6-luna"])
def test_custom_openai_responses_model_carries_reasoning_profile(underlying):
    """The real Responses model built for custom endpoints must carry the flags.

    pydantic-ai's own name-based inference does not know gpt-6, so without an
    explicit profile the context/mode/``include`` fields are silently dropped.
    """
    config = {
        "my-responses": {
            "type": "custom_openai_responses",
            "name": underlying,
            "custom_endpoint": {
                "url": "https://proxy.example.com/v1",
                "api_key": "test-key",
            },
        }
    }
    model = ModelFactory.get_model("my-responses", config)

    assert type(model).__name__ == "OpenAIResponsesModel"
    for key in _REASONING_PROFILE_KEYS:
        assert model.profile.get(key) is True


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
