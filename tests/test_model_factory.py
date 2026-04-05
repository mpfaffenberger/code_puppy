import os
from unittest.mock import MagicMock, patch

import httpx
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
    assert model.model_name == "gemini-pro"


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


def test_custom_openai_timeout_config(monkeypatch):
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
            "timeout": 600,
        }
    }

    with patch("code_puppy.model_factory.create_async_client") as mock_client:
        mock_client.return_value = httpx.AsyncClient(timeout=600)
        model = ModelFactory.get_model("custom", config)

    mock_client.assert_called_once_with(
        headers={"X-Api-Key": "ok"}, verify=False, timeout=600
    )
    assert model is not None


def test_custom_gemini_timeout_config(monkeypatch):
    monkeypatch.setenv("CUSTOM_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_gemini",
            "name": "gemini",
            "custom_endpoint": {
                "url": "https://fake.url",
                "headers": {"X-Api-Key": "$CUSTOM_API_KEY"},
                "ca_certs_path": False,
                "api_key": "$CUSTOM_API_KEY",
            },
            "timeout": 600,
        }
    }

    with patch("code_puppy.model_factory.create_async_client") as mock_client:
        mock_client.return_value = httpx.AsyncClient(timeout=600)
        model = ModelFactory.get_model("custom", config)

    mock_client.assert_called_once_with(
        headers={"X-Api-Key": "ok"}, verify=False, timeout=600
    )
    assert model is not None


def test_custom_anthropic_timeout_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_anthropic",
            "name": "claude",
            "custom_endpoint": {
                "url": "https://fake.url",
                "headers": {"X-Api-Key": "$OPENAI_API_KEY"},
                "ca_certs_path": False,
                "api_key": "$OPENAI_API_KEY",
            },
            "timeout": 600,
        }
    }

    with (
        patch("code_puppy.model_factory.ClaudeCacheAsyncClient") as mock_client,
        patch("code_puppy.model_factory.make_anthropic_provider") as mock_provider,
        patch("code_puppy.model_factory.AsyncAnthropic") as mock_anthropic,
        patch(
            "code_puppy.model_factory.get_http2", return_value=False
        ) as mock_get_http2,
    ):
        mock_client.return_value = MagicMock()
        mock_provider.return_value = MagicMock()
        mock_anthropic.return_value = MagicMock()
        model = ModelFactory.get_model("custom", config)

    mock_client.assert_called_once_with(
        headers={"X-Api-Key": "ok"},
        verify=False,
        timeout=600,
        http2=False,
    )
    assert model is not None


def test_cerebras_timeout_config(monkeypatch):
    monkeypatch.setenv("CUSTOM_API_KEY", "ok")
    config = {
        "custom": {
            "type": "cerebras",
            "name": "zai-glm-4.7",
            "custom_endpoint": {
                "url": "https://fake.url",
                "headers": {"X-Api-Key": "$CUSTOM_API_KEY"},
                "ca_certs_path": False,
                "api_key": "$CUSTOM_API_KEY",
            },
            "timeout": 600,
        }
    }

    with patch("code_puppy.model_factory.create_async_client") as mock_client:
        mock_client.return_value = httpx.AsyncClient(timeout=600)
        model = ModelFactory.get_model("custom", config)

    mock_client.assert_called_once_with(
        headers={"X-Api-Key": "ok", "X-Cerebras-3rd-Party-Integration": "code-puppy"},
        verify=False,
        model_name="cerebras",
        timeout=600,
    )
    assert model is not None


def test_anthropic_missing_api_key(monkeypatch):
    config = {"anthropic": {"type": "anthropic", "name": "claude-v2"}}
    if "ANTHROPIC_API_KEY" in os.environ:
        monkeypatch.delenv("ANTHROPIC_API_KEY")
    with patch("code_puppy.model_factory.emit_warning") as mock_warn:
        model = ModelFactory.get_model("anthropic", config)
        assert model is None
        mock_warn.assert_called_once()


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


def test_extra_models_json_decode_error(tmp_path, monkeypatch):
    # Create a temporary extra_models.json file with invalid JSON
    extra_models_file = tmp_path / "extra_models.json"
    extra_models_file.write_text("{ invalid json content }")

    # Patch the EXTRA_MODELS_FILE path to point to our temporary file
    from code_puppy.model_factory import ModelFactory

    monkeypatch.setattr(
        "code_puppy.model_factory.EXTRA_MODELS_FILE", str(extra_models_file)
    )

    # This should not raise an exception despite the invalid JSON
    config = ModelFactory.load_config()

    # The config should still be loaded, just without the extra models
    assert isinstance(config, dict)
    assert len(config) > 0


def test_extra_models_exception_handling(tmp_path, monkeypatch, caplog):
    # Create a temporary extra_models.json file that will raise a general exception
    extra_models_file = tmp_path / "extra_models.json"
    # Create a directory with the same name to cause an OSError when trying to read it
    extra_models_file.mkdir()

    # Patch the EXTRA_MODELS_FILE path
    from code_puppy.model_factory import ModelFactory

    monkeypatch.setattr(
        "code_puppy.model_factory.EXTRA_MODELS_FILE", str(extra_models_file)
    )

    # This should not raise an exception despite the error
    with caplog.at_level("WARNING"):
        config = ModelFactory.load_config()

    # The config should still be loaded
    assert isinstance(config, dict)
    assert len(config) > 0

    # Check that warning was logged
    assert "Failed to load extra models config" in caplog.text


def test_custom_timeout_invalid_values():
    """Test that invalid timeout values are rejected."""
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "gpt-4",
            "custom_endpoint": {
                "url": "https://api.example.com/v1",
                "api_key": "$API_KEY",
            },
        }
    }

    # Test invalid timeout values that should be rejected as non-numeric
    invalid_non_numeric = ["abc", True]
    for invalid_timeout in invalid_non_numeric:
        config["custom"]["custom_endpoint"]["timeout"] = invalid_timeout
        with pytest.raises(
            ValueError, match="Custom endpoint timeout must be a number"
        ):
            ModelFactory.get_model("custom", config)

    # Test invalid numeric values (zero or negative)
    invalid_numeric = [0, -1]
    for invalid_timeout in invalid_numeric:
        config["custom"]["custom_endpoint"]["timeout"] = invalid_timeout
        with pytest.raises(
            ValueError, match="Custom endpoint timeout must be greater than zero"
        ):
            ModelFactory.get_model("custom", config)


def test_custom_timeout_precedence(monkeypatch):
    """Test that top-level timeout takes precedence over custom_endpoint.timeout."""
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "gpt-4",
            "timeout": 300,  # Top-level timeout
            "custom_endpoint": {
                "url": "https://api.example.com/v1",
                "api_key": "$OPENAI_API_KEY",
                "timeout": 600,  # Custom endpoint timeout (should be ignored)
            },
        }
    }

    with patch("code_puppy.model_factory.create_async_client") as mock_client:
        mock_client.return_value = httpx.AsyncClient(timeout=300)
        model = ModelFactory.get_model("custom", config)

    # Should use top-level timeout (300), not custom_endpoint timeout (600)
    mock_client.assert_called_once_with(
        headers={},
        verify=None,
        timeout=300,
    )
    assert model is not None
