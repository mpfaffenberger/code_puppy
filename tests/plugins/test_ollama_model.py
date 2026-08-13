"""Tests for the Ollama model plugin."""

import asyncio
from unittest.mock import patch

import httpx

from code_puppy.plugins.ollama.register_callbacks import create_ollama_model


def _client(**kwargs):
    return httpx.AsyncClient(**kwargs)


@patch(
    "code_puppy.plugins.ollama.register_callbacks.create_async_client",
    side_effect=_client,
)
def test_custom_endpoint_accepts_timeout_from_get_custom_config(mock_client):
    """A custom Ollama endpoint should instantiate with the current config shape."""
    model_config = {
        "type": "ollama",
        "name": "qwen3:4b",
        "custom_endpoint": {
            "url": "https://ollama.example.com/v1",
            "api_key": "ollama",
        },
    }

    model = create_ollama_model("ollama-qwen3", model_config, {})

    assert model is not None
    assert model.model_name == "qwen3:4b"
    assert str(model._provider.base_url).rstrip("/") == "https://ollama.example.com/v1"
    mock_client.assert_called_once_with(headers={}, verify=None)
    asyncio.run(model._provider._client.close())


@patch(
    "code_puppy.plugins.ollama.register_callbacks.create_async_client",
    side_effect=_client,
)
def test_custom_endpoint_passes_headers_and_tls_config(mock_client):
    """Custom endpoint headers and certificate settings remain supported."""
    model_config = {
        "type": "ollama",
        "name": "qwen3:4b",
        "custom_endpoint": {
            "url": "https://ollama.example.com/v1",
            "headers": {"X-Test": "value"},
            "ca_certs_path": False,
            "api_key": "ollama",
        },
    }

    model = create_ollama_model("ollama-qwen3", model_config, {})

    assert model is not None
    mock_client.assert_called_once_with(headers={"X-Test": "value"}, verify=False)
    asyncio.run(model._provider._client.close())


@patch(
    "code_puppy.plugins.ollama.register_callbacks.create_async_client",
    side_effect=_client,
)
def test_local_endpoint_uses_ollama_defaults(mock_client, monkeypatch):
    """Local Ollama configurations should not require a custom endpoint."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)

    model = create_ollama_model(
        "ollama-qwen3", {"type": "ollama", "name": "qwen3:4b"}, {}
    )

    assert model is not None
    assert str(model._provider.base_url).rstrip("/") == "http://localhost:11434/v1"
    mock_client.assert_called_once_with(headers={}, verify=None)
    asyncio.run(model._provider._client.close())
