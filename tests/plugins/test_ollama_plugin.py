"""Tests for the Ollama plugin model type handler."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel

from code_puppy.plugins.ollama.register_callbacks import (
    _DEFAULT_OLLAMA_API_KEY,
    _DEFAULT_OLLAMA_BASE_URL,
    _get_ollama_model_types,
    create_ollama_model,
)

MODULE = "code_puppy.plugins.ollama.register_callbacks"


@pytest.fixture
def mock_async_client():
    with patch(f"{MODULE}.create_async_client") as mock:
        mock.return_value = MagicMock()
        yield mock


@pytest.fixture
def mock_get_custom_config():
    with patch(f"{MODULE}.get_custom_config") as mock:
        mock.return_value = (
            "http://remote:8080/v1",
            {"X-Key": "val"},
            None,
            "custom-key",
        )
        yield mock


@pytest.fixture
def mock_provider():
    with patch(f"{MODULE}.OpenAIProvider") as mock:
        mock.return_value = MagicMock()
        yield mock


def test_custom_endpoint_uses_get_custom_config(
    mock_async_client, mock_get_custom_config, mock_provider
):
    model_config = {
        "name": "codellama:34b",
        "custom_endpoint": {
            "url": "http://remote:8080/v1",
            "api_key": "custom-key",
        },
    }
    result = create_ollama_model("my-model", model_config, {})

    mock_get_custom_config.assert_called_once_with(model_config)
    assert isinstance(result, OpenAIChatModel)


def test_no_custom_endpoint_defaults_to_localhost(
    mock_async_client, mock_provider, monkeypatch
):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {"name": "llama3:8b"}
    result = create_ollama_model("my-model", model_config, {})

    assert isinstance(result, OpenAIChatModel)
    # Verify the client was created with empty headers and no verify
    mock_async_client.assert_called_once_with(headers={}, verify=None)


def test_ollama_host_env_appends_v1(mock_async_client, mock_provider, monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://myserver:11434")
    model_config = {"name": "gpt3:30b"}
    create_ollama_model("my-model", model_config, {})

    # Check the provider was called with /v1 appended
    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["base_url"] == "http://myserver:11434/v1"


def test_ollama_host_already_ends_with_v1(
    mock_async_client, mock_provider, monkeypatch
):
    monkeypatch.setenv("OLLAMA_HOST", "http://myserver:11434/v1")
    model_config = {"name": "gpt3:30b"}
    create_ollama_model("my-model", model_config, {})

    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["base_url"] == "http://myserver:11434/v1"


def test_ollama_host_trailing_slash_stripped(
    mock_async_client, mock_provider, monkeypatch
):
    monkeypatch.setenv("OLLAMA_HOST", "http://myserver:11434/")
    model_config = {"name": "gpt3:30b"}
    create_ollama_model("my-model", model_config, {})

    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["base_url"] == "http://myserver:11434/v1"


def test_ollama_host_empty_string_uses_default(
    mock_async_client, mock_provider, monkeypatch
):
    monkeypatch.setenv("OLLAMA_HOST", "")
    model_config = {"name": "llama3:8b"}
    create_ollama_model("my-model", model_config, {})

    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["base_url"] == _DEFAULT_OLLAMA_BASE_URL


def test_returns_open_ai_chat_model_not_responses(
    mock_async_client, mock_provider, monkeypatch
):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {"name": "llama3:8b"}
    result = create_ollama_model("my-model", model_config, {})

    assert isinstance(result, OpenAIChatModel)
    assert not isinstance(result, OpenAIResponsesModel)


def test_provider_is_set_on_model(mock_async_client, mock_provider, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {"name": "llama3:8b"}
    result = create_ollama_model("my-model", model_config, {})

    assert result is not None
    assert hasattr(result, "provider")
    assert result.provider is not None


def test_uses_model_config_name(mock_async_client, mock_provider, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {"name": "gpt3:30b"}
    result = create_ollama_model("config-key", model_config, {})

    assert result is not None
    assert result.model_name == "gpt3:30b"


def test_falls_back_to_model_name_key(mock_async_client, mock_provider, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {}  # No "name" key
    result = create_ollama_model("fallback-name", model_config, {})

    assert result is not None
    assert result.model_name == "fallback-name"


def test_returns_none_on_exception(monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {
        "name": "test",
        "custom_endpoint": {"url": "http://x", "api_key": "k"},
    }
    with patch(f"{MODULE}.get_custom_config", side_effect=RuntimeError("boom")):
        result = create_ollama_model("bad-model", model_config, {})
    assert result is None


def test_get_ollama_model_types_structure():
    result = _get_ollama_model_types()
    assert isinstance(result, list)
    assert len(result) == 1
    entry = result[0]
    assert entry["type"] == "ollama"
    assert callable(entry["handler"])
    assert entry["handler"] is create_ollama_model


def test_api_key_defaults_to_ollama(mock_async_client, mock_provider, monkeypatch):
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    model_config = {"name": "llama3:8b"}
    create_ollama_model("my-model", model_config, {})

    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["api_key"] == _DEFAULT_OLLAMA_API_KEY


def test_api_key_fallback_when_custom_returns_none(mock_async_client, mock_provider):
    with patch(f"{MODULE}.get_custom_config") as mock_gcc:
        mock_gcc.return_value = ("http://x/v1", {}, None, None)
        create_ollama_model(
            "m",
            {"name": "t", "custom_endpoint": {"url": "http://x/v1"}},
            {},
        )

    call_kwargs = mock_provider.call_args[1]
    assert call_kwargs["api_key"] == _DEFAULT_OLLAMA_API_KEY


def test_default_constants():
    assert _DEFAULT_OLLAMA_BASE_URL == "http://localhost:11434/v1"
    assert _DEFAULT_OLLAMA_API_KEY == "ollama"
