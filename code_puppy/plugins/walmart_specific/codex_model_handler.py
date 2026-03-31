"""Codex model type handler for the OpenAI Responses API.

This handler creates models that use the ChatGPTCodexAsyncClient,
which properly handles reasoning items required by the Responses API.

Usage in extra_models.json:
{
    "gpt-5.3-codex": {
        "name": "gpt-5.3-codex",
        "type": "codex",
        "custom_endpoint": {
            "url": "http://localhost:8080",
            "api_key": "$puppy_token",
            "headers": {
                "X-Api-Key": "$puppy_token"
            }
        },
        "context_length": 200000
    }
}
"""

import logging
from typing import Any, Dict

from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from code_puppy.chatgpt_codex_client import create_codex_async_client
from code_puppy.model_factory import get_custom_config

logger = logging.getLogger(__name__)


def create_codex_model(
    model_name: str,
    model_config: Dict[str, Any],
    config: Dict[str, Any],
) -> OpenAIResponsesModel | None:
    """Create a codex model using the ChatGPTCodexAsyncClient.

    This handler is registered via the register_model_type callback and
    handles models with type="codex" in their configuration.

    The ChatGPTCodexAsyncClient:
    - Injects required fields (store=false, stream=true)
    - Handles reasoning items properly for the Responses API
    - Converts streaming responses when needed

    Args:
        model_name: The config key name of the model
        model_config: The model's configuration dict
        config: The full models configuration

    Returns:
        OpenAIResponsesModel instance or None if creation fails
    """
    try:
        url, headers, verify, api_key = get_custom_config(model_config)

        # Use the codex client which handles reasoning items
        client = create_codex_async_client(headers=headers, verify=verify)

        provider_args: Dict[str, Any] = {
            "base_url": url,
            "http_client": client,
        }
        if api_key:
            provider_args["api_key"] = api_key

        provider = OpenAIProvider(**provider_args)

        # Use OpenAIResponsesModel for the Responses API
        actual_model_name = model_config.get("name", model_name)
        model = OpenAIResponsesModel(actual_model_name, provider=provider)
        model.provider = provider

        logger.info(f"Created codex model: {actual_model_name} -> {url}")
        return model

    except Exception as e:
        logger.error(f"Failed to create codex model '{model_name}': {e}")
        return None
