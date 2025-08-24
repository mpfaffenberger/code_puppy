import os

import pytest

from code_puppy.model_factory import ModelFactory

TEST_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../code_puppy/models.json")


def test_ollama_load_model():
    config = ModelFactory.load_config()

    # Skip test if 'ollama-llama2' model is not in config
    if "ollama-llama2" not in config:
        pytest.skip("Model 'ollama-llama2' not found in configuration, skipping test.")

    model = ModelFactory.get_model("ollama-llama2", config)
    assert hasattr(model, "provider")
    assert model.provider.model_name == "llama2"
    assert "chat" in dir(model), "OllamaModel must have a .chat method!"


def test_anthropic_load_model():
    config = ModelFactory.load_config()
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
                "ca_certs_path": False,
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
