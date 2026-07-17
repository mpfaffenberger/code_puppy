"""Ollama model type handler for OpenAI Chat Completions-compatible endpoints.

Registers the 'ollama' model type so users can connect Mist to local
inference servers (Ollama, LM Studio, vLLM, llama.cpp, etc.) via
~/.mist/extra_models.json.

Minimal config (Ollama on localhost with defaults):
{
    "ollama-qwen3": {
        "type": "ollama",
        "name": "qwen3:30b",
        "context_length": 131072
    }
}

Full config (remote server, same custom_endpoint format as custom_openai):
{
    "lmstudio-codellama": {
        "type": "ollama",
        "name": "codellama:34b",
        "context_length": 16384,
        "custom_endpoint": {
            "url": "http://192.168.1.50:1234/v1",
            "api_key": "$LM_STUDIO_KEY"
        }
    }
}

Note: Mist requires models with strong tool/function calling support.
Models without tool calling will notwork properly.
"""

import logging
import os
from typing import Any

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from code_puppy.callbacks import register_callback
from code_puppy.http_utils import create_async_client
from code_puppy.model_factory import get_custom_config

logger = logging.getLogger(__name__)

# Ollama defaults
_DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
_DEFAULT_OLLAMA_API_KEY = "ollama"


def create_ollama_model(
    model_name: str,
    model_config: dict[str, Any],
    config: dict[str, Any],
) -> OpenAIChatModel | None:
    """Create a model for an OpenAI Chat Completions-compatible endpoint.

    When ``custom_endpoint`` is present in *model_config*, the standard
    ``get_custom_config()`` helper is used (same path as ``custom_openai``
    and ``codex`` model types).

    When ``custom_endpoint`` is absent, sensible Ollama defaults are applied:
    - base URL from ``OLLAMA_HOST`` env var, or ``http://localhost:11434/v1``
    - api_key ``"ollama"`` (required non-empty by OpenAIProvider, not validated by Ollama)

    Args:
        model_name: The config key name of the model.
        model_config: The model's configuration dict.
        config: The full models configuration (unused, kept for API compat).

    Returns:
        OpenAIChatModel instance, or None if creation fails.
    """
    try:
        if "custom_endpoint" in model_config:
            url, headers, verify, api_key = get_custom_config(model_config)
        else:
            # Derive base URL: OLLAMA_HOST env var → default
            ollama_host = os.environ.get("OLLAMA_HOST", "").rstrip("/")
            if ollama_host:
                url = (
                    ollama_host if ollama_host.endswith("/v1") else f"{ollama_host}/v1"
                )
            else:
                url = _DEFAULT_OLLAMA_BASE_URL
            headers = {}
            verify = None
            api_key = _DEFAULT_OLLAMA_API_KEY

        client = create_async_client(headers=headers, verify=verify)

        provider_args: dict[str, Any] = {
            "base_url": url,
            "http_client": client,
        }
        if api_key:
            provider_args["api_key"] = api_key
        else:
            provider_args["api_key"] = _DEFAULT_OLLAMA_API_KEY

        provider = OpenAIProvider(**provider_args)

        actual_model_name = model_config.get("name", model_name)
        model = OpenAIChatModel(actual_model_name, provider=provider)
        model.provider = (
            provider  # Expose for connection-pooling cleanup (project convention)
        )

        logger.info("Created ollama model: %s -> %s", actual_model_name, url)
        return model

    except Exception as e:
        logger.error("Failed to create ollama model '%s': %s", model_name, e)
        return None


def _get_ollama_model_types():
    """Return the ollama model type handler for the register_model_type hook."""
    return [
        {
            "type": "ollama",
            "handler": create_ollama_model,
        },
    ]


register_callback("register_model_type", _get_ollama_model_types)
