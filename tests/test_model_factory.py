import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

from code_puppy.model_factory import ModelFactory, make_model_settings

TEST_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../code_puppy/models.json")


def test_ollama_load_model():
    config = ModelFactory.load_config()

    # Skip test if 'ollama-llama2' model is not in config
    if "ollama-llama2" not in config:
        pytest.skip("Model 'ollama-llama2' not found in configuration, skipping test.")

    model = ModelFactory.get_model("ollama-llama2", config)
    assert hasattr(model, "_provider")
    assert model.model_name == "llama2"
    assert "chat" in dir(model), "OllamaModel must have a .chat method!"


def test_anthropic_load_model():
    config = ModelFactory.load_config()
    if "anthropic-test" not in config:
        pytest.skip("Model 'anthropic-test' not found in configuration, skipping test.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY not set in environment, skipping test.")

    model = ModelFactory.get_model("anthropic-test", config)
    assert hasattr(model, "_provider")
    assert hasattr(model._provider, "_client")
    # Note: Do not make actual Anthropic network calls in CI, just validate instantiation.


def test_anthropic_cache_settings_use_native_ttls():
    """Anthropic settings configure native cache breakpoints for each path."""
    model_configs = {
        "anthropic-test": {
            "type": "anthropic",
            "name": "claude-sonnet-4-5",
        },
        "claude-code-test": {
            "type": "claude_code",
            "name": "claude-opus-4-7",
        },
    }

    with (
        patch.object(ModelFactory, "load_config", return_value=model_configs),
        patch("code_puppy.config.get_custom_model_settings", return_value={}),
    ):
        api_key_settings = make_model_settings("anthropic-test")
        oauth_settings = make_model_settings("claude-code-test")

    cache_fields = (
        "anthropic_cache_instructions",
        "anthropic_cache_tool_definitions",
        "anthropic_cache_messages",
    )
    assert {field: api_key_settings[field] for field in cache_fields} == {
        field: True for field in cache_fields
    }
    assert {field: oauth_settings[field] for field in cache_fields} == {
        field: "1h" for field in cache_fields
    }


@pytest.mark.parametrize(
    ("model_key", "config"),
    [
        ("not-there", {"foo": {"type": "openai", "name": "bar"}}),
        ("bad", {"bad": {"type": "doesnotexist", "name": "fake"}}),
    ],
)
def test_missing_model_or_unsupported_type(model_key, config):
    with pytest.raises(ValueError):
        ModelFactory.get_model(model_key, config)


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


@pytest.mark.parametrize(
    ("model_key", "config"),
    [
        (
            "custom",
            {
                "custom": {
                    "type": "custom_openai",
                    "name": "mycust",
                    "custom_endpoint": {"headers": {}},
                }
            },
        ),
        (
            "x",
            {
                "x": {
                    "type": "custom_anthropic",
                    "name": "ya",
                    "custom_endpoint": {"headers": {}},
                }
            },
        ),
    ],
)
def test_custom_endpoint_missing_url(model_key, config):
    with pytest.raises(ValueError):
        ModelFactory.get_model(model_key, config)


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
    assert hasattr(model, "_provider")


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
    assert hasattr(model._provider, "base_url")


@pytest.mark.parametrize(
    ("env_var", "model_type", "model_name"),
    [
        ("OPENAI_API_KEY", "custom_openai", "cust"),
        ("CUSTOM_API_KEY", "custom_gemini", "gemini"),
    ],
)
def test_custom_timeout_config(monkeypatch, env_var, model_type, model_name):
    monkeypatch.setenv(env_var, "ok")
    config = {
        "custom": {
            "type": model_type,
            "name": model_name,
            "custom_endpoint": {
                "url": "https://fake.url",
                "headers": {"X-Api-Key": "$" + env_var},
                "ca_certs_path": False,
                "api_key": "$" + env_var,
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


# --- Regression tests: 'System message must be at the beginning.' after auto-compact.
# Strict OpenAI-compatible backends (SGLang, vLLM) reject >1 leading system
# message. After SummarizingCompaction the wire format has two: the
# compaction-summary SystemPromptPart + the agent's per-turn
# instruction_parts. The profile must set
# openai_chat_supports_multiple_system_messages=False so pydantic-ai's
# _merge_leading_system_messages joins them into one.


def test_custom_openai_merges_system_messages(monkeypatch):
    """custom_openai defaults to merging leading system messages."""
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "qwen-sglang",
            "custom_endpoint": {
                "url": "https://fake.url",
                "api_key": "$OPENAI_API_KEY",
            },
        }
    }
    model = ModelFactory.get_model("custom", config)
    assert model is not None
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is False


def test_custom_openai_multiple_system_messages_override(monkeypatch):
    """Users can opt out with ``supports_multiple_system_messages: true``."""
    monkeypatch.setenv("OPENAI_API_KEY", "ok")
    config = {
        "custom": {
            "type": "custom_openai",
            "name": "qwen-sglang",
            "supports_multiple_system_messages": True,
            "custom_endpoint": {
                "url": "https://fake.url",
                "api_key": "$OPENAI_API_KEY",
            },
        }
    }
    model = ModelFactory.get_model("custom", config)
    assert model is not None
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is True


def test_custom_openai_explicit_false_stays_false():
    """A JSON ``false`` (Python ``False``) correctly produces ``False``."""
    from code_puppy.model_factory import _strict_openai_profile

    profile = _strict_openai_profile("m", {"supports_multiple_system_messages": False})
    assert profile.get("openai_chat_supports_multiple_system_messages") is False


def test_openrouter_merges_system_messages(monkeypatch):
    """OpenRouter routes to various backends, so merge by default too."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "ok")
    config = {
        "or": {
            "type": "openrouter",
            "name": "openai/test-model",
        },
    }
    model = ModelFactory.get_model("or", config)
    assert model is not None
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is False


def test_cerebras_profile_has_both_flags(monkeypatch):
    """Cerebras keeps strict-tool-def=False AND gains system-message merge."""
    monkeypatch.setenv("CEREBRAS_API_KEY", "ok")
    config = {
        "cb": {
            "type": "cerebras",
            "name": "llama-4-scout",
        },
    }
    model = ModelFactory.get_model("cb", config)
    assert model is not None
    assert model.profile.get("openai_supports_strict_tool_definition") is False
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is False


def test_zai_coding_merges_system_messages(monkeypatch):
    """ZAI coding endpoint gets the same safe default."""
    monkeypatch.setenv("ZAI_API_KEY", "ok")
    config = {
        "zai": {
            "type": "zai_coding",
            "name": "glm-4.6",
        },
    }
    model = ModelFactory.get_model("zai", config)
    assert model is not None
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is False


def test_zai_api_merges_system_messages(monkeypatch):
    """ZAI API endpoint gets the same safe default (symmetry with zai_coding)."""
    monkeypatch.setenv("ZAI_API_KEY", "ok")
    config = {
        "zai": {
            "type": "zai_api",
            "name": "glm-4.6",
        },
    }
    model = ModelFactory.get_model("zai", config)
    assert model is not None
    assert model.profile.get("openai_chat_supports_multiple_system_messages") is False


def test_strict_openai_profile_helper():
    """_strict_openai_profile merges thinking tags + multiple-system-messages setting."""
    from code_puppy.model_factory import _strict_openai_profile
    from pydantic_ai.profiles.openai import OpenAIModelProfile

    # Default: merge is on (False means merge)
    profile = _strict_openai_profile("test-model", {})
    assert profile.get("openai_chat_supports_multiple_system_messages") is False

    # Override via config
    profile = _strict_openai_profile(
        "test-model", {"supports_multiple_system_messages": True}
    )
    assert profile.get("openai_chat_supports_multiple_system_messages") is True

    # Extra profile settings are preserved alongside the merge flag
    extra = OpenAIModelProfile(openai_supports_strict_tool_definition=False)
    profile = _strict_openai_profile("test-model", {}, extra=extra)
    assert profile.get("openai_supports_strict_tool_definition") is False
    assert profile.get("openai_chat_supports_multiple_system_messages") is False

    # Thinking-tags config + extra + merge flag all coexist (cerebras-style triple-merge)
    profile = _strict_openai_profile(
        "minimax-m3",
        {"provider": "lilac", "name": "minimax-m3"},
        extra=OpenAIModelProfile(openai_supports_strict_tool_definition=False),
    )
    assert profile.get("openai_chat_supports_multiple_system_messages") is False
    assert profile.get("openai_supports_strict_tool_definition") is False
    # Unconditional: the lilac/minimax-m3 config must resolve custom thinking
    # tags, and they must survive the extra-merge.
    from code_puppy.model_utils import get_thinking_tags

    expected_tags = get_thinking_tags(
        "minimax-m3", {"provider": "lilac", "name": "minimax-m3"}
    )
    assert expected_tags is not None
    assert profile["thinking_tags"] == expected_tags


def test_strict_openai_profile_rejects_non_bool():
    """A non-bool ``supports_multiple_system_messages`` fails fast with TypeError.

    A JSON string like ``"false"`` would otherwise silently invert the user's
    intent (it is truthy); ``bool()``-coercion is no cure since
    ``bool("false")`` is ``True``.
    """
    from code_puppy.model_factory import _strict_openai_profile

    with pytest.raises(TypeError, match="must be a JSON boolean"):
        _strict_openai_profile("m", {"supports_multiple_system_messages": "false"})


@pytest.mark.asyncio
async def test_wire_format_merges_leading_system_messages():
    """Integration test: after compaction, the wire format has exactly one system message.

    This directly proves the bug is fixed — two leading SystemPromptParts +
    instruction_parts produce one merged system message on the wire, not two.
    """
    import httpx
    from pydantic_ai.messages import (
        InstructionPart,
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        TextPart,
        UserPromptPart,
    )
    from pydantic_ai.models import ModelRequestParameters
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from code_puppy.model_factory import _strict_openai_profile

    async with httpx.AsyncClient(base_url="http://localhost:30000") as client:
        provider = OpenAIProvider(api_key="dummy", http_client=client)
        model = OpenAIChatModel(
            model_name="qwen-sglang",
            provider=provider,
            profile=_strict_openai_profile("qwen-sglang", {}),
        )

        # Simulate a post-compaction history: summary + preserved turns
        messages = [
            ModelRequest(
                parts=[SystemPromptPart(content="[compaction-summary] Previous work.")]
            ),
            ModelRequest(parts=[UserPromptPart(content="What is 2+2?")]),
            ModelResponse(parts=[TextPart(content="4")], model_name="qwen-sglang"),
            ModelRequest(
                parts=[UserPromptPart(content="continue")],
                instructions="You are a helpful assistant.",
            ),
        ]

        prepared = model.prepare_messages(messages, None)
        mrp = ModelRequestParameters(
            function_tools=[],
            output_mode="text",
            output_object=None,
            output_tools=[],
            instruction_parts=[InstructionPart(content="You are a helpful assistant.")],
        )
        openai_messages = await model._map_messages(prepared, mrp, model_settings=None)

    system_roles = [m for m in openai_messages if m.get("role") == "system"]
    assert len(system_roles) == 1, (
        f"Expected exactly 1 system message after merge, got {len(system_roles)}"
    )
    content = system_roles[0].get("content", "")
    assert "[compaction-summary]" in content
    assert "You are a helpful assistant." in content


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
        patch("code_puppy.model_factory.get_http2", return_value=False),
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


@pytest.mark.parametrize(
    ("model_key", "config"),
    [
        (
            "az1",
            {
                "az1": {
                    "type": "azure_openai",
                    "name": "az",
                    "api_version": "2023",
                    "api_key": "val",
                }
            },
        ),
        (
            "az2",
            {
                "az2": {
                    "type": "azure_openai",
                    "name": "az",
                    "azure_endpoint": "foo",
                    "api_key": "val",
                }
            },
        ),
        (
            "az3",
            {
                "az3": {
                    "type": "azure_openai",
                    "name": "az",
                    "azure_endpoint": "foo",
                    "api_version": "1.0",
                }
            },
        ),
    ],
)
def test_azure_missing_field(model_key, config):
    with pytest.raises(ValueError):
        ModelFactory.get_model(model_key, config)


def test_extra_models_json_decode_error(tmp_path, monkeypatch):
    # Create a temporary extra_models.json file with invalid JSON
    extra_models_file = tmp_path / "extra_models.json"
    extra_models_file.write_text("{ invalid json content }")
    base_config = {"base-model": {"type": "openai", "name": "base"}}

    # Use an explicit base config: bundled models.json may intentionally be empty.
    monkeypatch.setattr(
        "code_puppy.model_factory.callbacks.get_callbacks", lambda phase: [object()]
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.callbacks.on_load_model_config",
        lambda: [base_config.copy()],
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.EXTRA_MODELS_FILE", str(extra_models_file)
    )

    # Invalid extra JSON should be ignored without discarding the base config.
    config = ModelFactory.load_config()

    assert config["base-model"] == base_config["base-model"]


def test_extra_models_exception_handling(tmp_path, monkeypatch, caplog):
    # Create a directory where a JSON file is expected to force an OSError.
    extra_models_file = tmp_path / "extra_models.json"
    extra_models_file.mkdir()
    base_config = {"base-model": {"type": "openai", "name": "base"}}

    # Use an explicit base config: bundled models.json may intentionally be empty.
    monkeypatch.setattr(
        "code_puppy.model_factory.callbacks.get_callbacks", lambda phase: [object()]
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.callbacks.on_load_model_config",
        lambda: [base_config.copy()],
    )
    monkeypatch.setattr(
        "code_puppy.model_factory.EXTRA_MODELS_FILE", str(extra_models_file)
    )

    with caplog.at_level("WARNING"):
        config = ModelFactory.load_config()

    assert config["base-model"] == base_config["base-model"]
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
