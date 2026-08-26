"""Factory-level coverage for the catalog-provided default fallback chain."""

from unittest.mock import MagicMock, patch

from pydantic_ai.models.openai import OpenAIResponsesModel

from code_puppy.fallback_chain_model import FallbackChainModel
from code_puppy.model_factory import ModelFactory


_CHAIN_CHILDREN = (
    "claude-4-8-opus-long",
    "claude-5-sonnet",
    "gpt-5.6-luna",
)


def _sanitized_catalog() -> dict:
    """Return only the catalog entries needed by the factory smoke test."""
    custom_anthropic = {
        "type": "custom_anthropic",
        "name": "placeholder-anthropic-model",
        "custom_endpoint": {
            "url": "https://sanitized.invalid/v1",
            "headers": {"x-api-key": "$TEST_MODEL_API_KEY"},
            "api_key": "$TEST_MODEL_API_KEY",
            "ca_certs_path": False,
        },
    }
    return {
        "claude-4-8-opus-long": {
            **custom_anthropic,
            "name": "claude-4-8-opus-long",
        },
        "claude-5-sonnet": {
            **custom_anthropic,
            "name": "claude-5-sonnet",
        },
        "gpt-5.6-luna": {
            "type": "codex",
            "name": "gpt-5.6-luna",
            "custom_endpoint": {
                "url": "https://sanitized.invalid/v1",
                "headers": {"authorization": "Bearer $TEST_MODEL_API_KEY"},
                "api_key": "$TEST_MODEL_API_KEY",
                "ca_certs_path": False,
            },
        },
        "default-fallback-chain": {
            "type": "fallback_chain",
            "models": list(_CHAIN_CHILDREN),
        },
    }


def test_factory_resolves_default_alias_with_catalog_child_order():
    """The configured alias must instantiate the real recursive factory path."""
    catalog = _sanitized_catalog()

    with (
        patch.object(ModelFactory, "load_config", return_value=catalog),
        patch(
            "code_puppy.model_factory.get_api_key",
            return_value="test-only-model-key",
        ),
        patch("code_puppy.model_factory.ClaudeCacheAsyncClient"),
        patch("code_puppy.model_factory.AsyncAnthropic"),
        patch(
            "code_puppy.model_factory.make_anthropic_provider",
            return_value=MagicMock(),
        ),
        patch(
            "code_puppy.model_factory.create_async_client",
            return_value=MagicMock(),
        ),
    ):
        model = ModelFactory.get_model("default-fallback-chain", catalog)

    assert set(catalog) == {*_CHAIN_CHILDREN, "default-fallback-chain"}
    assert isinstance(model, FallbackChainModel)
    assert [child.model_name for child in model.models] == list(_CHAIN_CHILDREN)


def test_factory_resolves_codex_catalog_entry_to_responses_model():
    """The Luna child keeps its Codex/Responses API model resolution."""
    catalog = _sanitized_catalog()

    with (
        patch(
            "code_puppy.model_factory.get_api_key", return_value="test-only-model-key"
        ),
        patch(
            "code_puppy.model_factory.create_async_client",
            return_value=MagicMock(),
        ) as create_client,
    ):
        model = ModelFactory.get_model("gpt-5.6-luna", catalog)

    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-5.6-luna"
    create_client.assert_called_once()
