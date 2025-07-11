

import os
import json
import tempfile
from unittest.mock import patch, Mock

import pytest
import httpx

from code_puppy.model_factory import ModelFactory

TEST_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../code_puppy/models.json")


def test_ollama_load_model():
    config = ModelFactory.load_config(TEST_CONFIG_PATH)

    # Skip test if 'ollama-llama2' model is not in config
    if "ollama-llama2" not in config:
        pytest.skip("Model 'ollama-llama2' not found in configuration, skipping test.")

    model = ModelFactory.get_model("ollama-llama2", config)
    assert hasattr(model, "provider")
    assert model.provider.model_name == "llama2"
    assert "chat" in dir(model), "OllamaModel must have a .chat method!"


def test_anthropic_load_model():
    config = ModelFactory.load_config(TEST_CONFIG_PATH)
    if "anthropic-test" not in config:
        pytest.skip("Model 'anthropic-test' not found in configuration, skipping test.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set in environment, skipping test.")

    model = ModelFactory.get_model("anthropic-test", config)
    assert hasattr(model, "provider")
    assert hasattr(model.provider, "anthropic_client")
    # Note: Do not make actual Anthropic network calls in CI, just validate instantiation.


def test_missing_model():
    config = {"foo": {"type": "openai", "name": "bar"}}
    with pytest.raises(ValueError):
        ModelFactory.get_model("not-there", config)


def test_unsupported_type():
    config = {"bad": {"type": "doesnotexist", "name": "fake"}}
    with pytest.raises(ValueError):
        ModelFactory.get_model("bad", config)


def test_env_var_reference_azure(monkeypatch):
    monkeypatch.setenv("AZ_URL", "https://mock-endpoint.openai.azure.com")
    monkeypatch.setenv("AZ_VERSION", "2023-05-15")
    monkeypatch.setenv("AZ_KEY", "supersecretkey")
    config = {
        "azmodel": {
            "type": "azure_openai",
            "name": "az",
            "azure_endpoint": "$AZ_URL",
            "api_version": "$AZ_VERSION",
            "api_key": "$AZ_KEY",
        }
    }
    model = ModelFactory.get_model("azmodel", config)
    assert model.client is not None


def test_custom_endpoint_missing_url():
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "mycust",
            "custom_endpoint": {"headers": {}},
        }
    }
    with pytest.raises(ValueError):
        ModelFactory.get_model("custom", config)


# Additional tests for coverage
def test_get_custom_config_missing_custom_endpoint():
    from code_puppy.model_factory import get_custom_config

    with pytest.raises(ValueError):
        get_custom_config({})


def test_get_custom_config_missing_url():
    from code_puppy.model_factory import get_custom_config

    config = {"custom_endpoint": {"headers": {}}}
    with pytest.raises(ValueError):
        get_custom_config(config)


def test_gemini_load_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-value")
    config = {"gemini": {"type": "gemini", "name": "gemini-pro"}}
    model = ModelFactory.get_model("gemini", config)
    assert model is not None
    assert hasattr(model, "provider")


def test_openai_load_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    config = {"openai": {"type": "openai", "name": "fake-openai-model"}}
    model = ModelFactory.get_model("openai", config)
    assert model is not None
    assert hasattr(model, "provider")


def test_custom_openai_happy(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "cust",
            "custom_endpoint": {
                "url": "https://fake.url",
                "headers": {"X-Api-Key": "$OPENAI_API_KEY"},
                "ca_certs_path": "false",
                "api_key": "$OPENAI_API_KEY",
            },
        }
    }
    model = ModelFactory.get_model("custom", config)
    assert model is not None
    assert hasattr(model.provider, "base_url")


def test_anthropic_missing_api_key(monkeypatch):
    config = {"anthropic": {"type": "anthropic", "name": "claude-v2"}}
    if "ANTHROPIC_API_KEY" in os.environ:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(ValueError):
        ModelFactory.get_model("anthropic", config)


def test_azure_missing_endpoint():
    config = {
        "az1": {
            "type": "azure_openai",
            "name": "az",
            "api_version": "2023",
            "api_key": "val",
        }
    }
    with pytest.raises(ValueError):
        ModelFactory.get_model("az1", config)


def test_azure_missing_apiversion():
    config = {
        "az2": {
            "type": "azure_openai",
            "name": "az",
            "azure_endpoint": "foo",
            "api_key": "val",
        }
    }
    with pytest.raises(ValueError):
        ModelFactory.get_model("az2", config)


def test_azure_missing_apikey():
    config = {
        "az3": {
            "type": "azure_openai",
            "name": "az",
            "azure_endpoint": "foo",
            "api_version": "1.0",
        }
    }
    with pytest.raises(ValueError):
        ModelFactory.get_model("az3", config)


def test_custom_anthropic_missing_url():
    config = {
        "x": {
            "type": "custom_anthropic",
            "name": "ya",
            "custom_endpoint": {"headers": {}},
        }
    }
    with pytest.raises(ValueError):
        ModelFactory.get_model("x", config)


# Tests for the new remote config fetching functionality
def test_load_config_remote_success():
    """Test successful remote config fetch and local update"""
    remote_config = {"test_model": {"type": "openai", "name": "gpt-4"}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        local_path = f.name
        json.dump({"old_model": {"type": "openai", "name": "gpt-3.5"}}, f)

    try:
        with patch("httpx.Client") as mock_client:
            mock_response = Mock()
            # Clear cache to prevent interference
            ModelFactory.clear_cache()
            # Fix mock response structure to match expected API format
            mock_response.json.return_value = {"config": remote_config}
            mock_response.raise_for_status.return_value = None
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = ModelFactory.load_config(local_path)

            assert result == remote_config

            # Check that local file was updated
            with open(local_path, "r") as f:
                updated_local = json.load(f)
            assert updated_local == remote_config
    finally:
        os.unlink(local_path)


def test_load_config_remote_fail_local_fallback():
    """Test fallback to local config when remote fetch fails"""
    local_config = {"local_model": {"type": "openai", "name": "gpt-3.5"}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        local_path = f.name
        json.dump(local_config, f)

    try:
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = (
                httpx.RequestError("Network error")
            )

            result = ModelFactory.load_config(local_path)

            assert result == local_config
    finally:
        os.unlink(local_path)


def test_load_config_remote_same_as_local():
    """Test that local file is not updated when remote config is same as local"""
    config = {"same_model": {"type": "openai", "name": "gpt-4"}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        local_path = f.name
        json.dump(config, f)

    try:
        with patch("httpx.Client") as mock_client:
            # Clear cache to prevent interference
            ModelFactory.clear_cache()
            mock_response = Mock()
            # Fix mock response structure to match expected API format
            mock_response.json.return_value = {"config": config}  # Same as local
            mock_response.raise_for_status.return_value = None
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = ModelFactory.load_config(local_path)

            assert result == config
    finally:
        os.unlink(local_path)


def test_load_config_no_local_no_remote():
    """Test error when neither remote nor local config is available"""
    non_existent_path = "/tmp/does_not_exist.json"

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = (
            httpx.RequestError("Network error")
        )

        with pytest.raises(FileNotFoundError):
            ModelFactory.load_config(non_existent_path)


def test_load_config_remote_success_no_local_file():
    """Test creating local file when remote fetch succeeds but no local file exists"""
    remote_config = {"new_model": {"type": "openai", "name": "gpt-4"}}

    with tempfile.TemporaryDirectory() as temp_dir:
        local_path = os.path.join(temp_dir, "subdir", "models.json")

        with patch("httpx.Client") as mock_client:
            mock_response = Mock()
            # Clear cache to prevent interference
            ModelFactory.clear_cache()
            # Fix mock response structure to match expected API format
            mock_response.json.return_value = {"config": remote_config}
            mock_response.raise_for_status.return_value = None
            mock_client.return_value.__enter__.return_value.get.return_value = (
                mock_response
            )

            result = ModelFactory.load_config(local_path)

            assert result == remote_config
            assert os.path.exists(local_path)

            with open(local_path, "r") as f:
                saved_config = json.load(f)
            assert saved_config == remote_config


def test_load_config_caching_prevents_redundant_calls():
    """Test that caching prevents redundant network calls for the same config path"""
    # Clear cache to start fresh
    ModelFactory.clear_cache()
    
    remote_config = {"cached_model": {"type": "openai"