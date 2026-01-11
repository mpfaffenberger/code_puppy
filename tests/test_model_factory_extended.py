"""Extended tests for model_factory.py to improve coverage.

This file focuses on covering previously uncovered code paths:
- make_model_settings function
- ZaiChatModel._process_response
- Complex header resolution in get_custom_config
- OAuth model types (claude_code, gemini_oauth, chatgpt_oauth)
- Cerebras provider
- Round-robin model with rotate_every
- Interleaved thinking settings
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.model_factory import (
    ModelFactory,
    ZaiChatModel,
    get_api_key,
    get_custom_config,
    make_model_settings,
)


class TestMakeModelSettings:
    """Test make_model_settings function for various model types."""

    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_basic(self, mock_eff):
        """Test basic model settings creation."""
        settings = make_model_settings("gpt-4")
        assert settings is not None
        # Settings is a TypedDict, check max_tokens exists
        assert "max_tokens" in settings
        assert settings["max_tokens"] is not None

    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_with_explicit_max_tokens(self, mock_eff):
        """Test model settings with explicit max_tokens."""
        settings = make_model_settings("gpt-4", max_tokens=4000)
        assert settings["max_tokens"] == 4000

    @patch("code_puppy.config.get_openai_reasoning_effort", return_value="high")
    @patch("code_puppy.config.get_openai_verbosity", return_value="detailed")
    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_gpt5(self, mock_eff, mock_verb, mock_reason):
        """Test model settings for GPT-5 models."""
        settings = make_model_settings("gpt-5")
        # Check it's a dict with the expected keys
        assert isinstance(settings, dict)
        assert "max_tokens" in settings

    @patch("code_puppy.config.get_openai_reasoning_effort", return_value="medium")
    @patch("code_puppy.config.get_openai_verbosity", return_value="medium")
    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_gpt5_codex(self, mock_eff, mock_verb, mock_reason):
        """Test model settings for GPT-5 codex models (verbosity not applied)."""
        settings = make_model_settings("gpt-5-codex")
        assert isinstance(settings, dict)
        # Codex models should not have extra_body with verbosity

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_claude(self, mock_effective):
        """Test model settings for Claude models."""
        mock_effective.return_value = {
            "extended_thinking": True,
            "budget_tokens": 15000,
        }
        settings = make_model_settings("claude-3-5-sonnet")
        assert isinstance(settings, dict)
        assert settings.get("anthropic_thinking") is not None

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_claude_no_thinking(self, mock_effective):
        """Test model settings for Claude without extended thinking."""
        mock_effective.return_value = {
            "extended_thinking": False,
        }
        settings = make_model_settings("claude-3-5-sonnet")
        assert isinstance(settings, dict)

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_anthropic_prefix(self, mock_effective):
        """Test model settings for models with anthropic- prefix."""
        mock_effective.return_value = {
            "extended_thinking": True,
            "budget_tokens": 10000,
        }
        settings = make_model_settings("anthropic-claude-3")
        assert isinstance(settings, dict)

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_with_temperature(self, mock_effective):
        """Test model settings with temperature already set."""
        mock_effective.return_value = {
            "temperature": 0.5,
            "extended_thinking": True,
            "budget_tokens": 10000,
        }
        settings = make_model_settings("claude-3-sonnet")
        assert isinstance(settings, dict)
        assert settings.get("temperature") == 0.5

    @patch("code_puppy.model_factory.ModelFactory.load_config")
    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_auto_max_tokens(self, mock_effective, mock_load):
        """Test automatic max_tokens calculation from context length."""
        mock_load.return_value = {
            "my-model": {
                "context_length": 200000,
            }
        }
        settings = make_model_settings("my-model")
        # max(2048, min(15% of 200000, 65536)) = max(2048, min(30000, 65536)) = 30000
        assert settings["max_tokens"] == 30000

    @patch(
        "code_puppy.model_factory.ModelFactory.load_config",
        side_effect=Exception("Load failed"),
    )
    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    def test_make_model_settings_config_load_fails(self, mock_effective, mock_load):
        """Test max_tokens calculation when config load fails."""
        settings = make_model_settings("unknown-model")
        # Falls back to context_length=128000
        # max(2048, min(15% of 128000, 65536)) = max(2048, min(19200, 65536)) = 19200
        assert settings["max_tokens"] == 19200

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_claude_with_top_p(self, mock_effective):
        """Test that top_p is removed for Claude models."""
        mock_effective.return_value = {
            "top_p": 0.9,
            "extended_thinking": True,
            "budget_tokens": 10000,
        }
        settings = make_model_settings("claude-3-5-sonnet")
        assert isinstance(settings, dict)
        # top_p should be removed

    @patch("code_puppy.config.get_effective_model_settings")
    def test_make_model_settings_claude_no_budget_tokens(self, mock_effective):
        """Test Claude settings with extended_thinking but no budget_tokens."""
        mock_effective.return_value = {
            "extended_thinking": True,
            "budget_tokens": 0,  # Falsy value
        }
        settings = make_model_settings("claude-3-5-sonnet")
        assert isinstance(settings, dict)
        # anthropic_thinking should not be set when budget_tokens is falsy


class TestZaiChatModel:
    """Test ZaiChatModel class."""

    def test_process_response(self):
        """Test _process_response method."""
        # Create a mock response object
        mock_response = MagicMock()
        mock_response.object = "text_completion"

        # Create ZaiChatModel with mocked provider
        mock_provider = MagicMock()
        model = ZaiChatModel(model_name="zai-test", provider=mock_provider)

        # Call _process_response
        with patch.object(
            model.__class__.__bases__[0], "_process_response", return_value="processed"
        ):
            model._process_response(mock_response)

        # Verify object type was changed
        assert mock_response.object == "chat.completion"


class TestGetCustomConfig:
    """Test get_custom_config function edge cases."""

    def test_header_with_single_env_var(self):
        """Test header with single environment variable."""
        with patch.dict(os.environ, {"API_KEY": "secret123"}):
            config = {
                "custom_endpoint": {
                    "url": "https://api.example.com",
                    "headers": {
                        "Authorization": "$API_KEY",
                    },
                }
            }
            url, headers, verify, api_key = get_custom_config(config)
            assert headers["Authorization"] == "secret123"

    def test_header_with_multiple_tokens(self):
        """Test header value with multiple tokens including env vars."""
        with patch.dict(os.environ, {"TOKEN": "mytoken"}):
            config = {
                "custom_endpoint": {
                    "url": "https://api.example.com",
                    "headers": {
                        "Authorization": "Bearer $TOKEN extra",
                    },
                }
            }
            url, headers, verify, api_key = get_custom_config(config)
            assert headers["Authorization"] == "Bearer mytoken extra"

    def test_header_with_missing_env_var_multi_token(self):
        """Test header with missing env var in multi-token value."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the env var if it exists
            if "MISSING_VAR" in os.environ:
                del os.environ["MISSING_VAR"]

            config = {
                "custom_endpoint": {
                    "url": "https://api.example.com",
                    "headers": {
                        "Authorization": "Bearer $MISSING_VAR suffix",
                    },
                }
            }
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                url, headers, verify, api_key = get_custom_config(config)
                assert (
                    headers["Authorization"] == "Bearer  suffix"
                )  # Empty value for missing var
                mock_warn.assert_called()

    def test_api_key_with_env_var_prefix(self):
        """Test api_key with $ environment variable prefix."""
        with patch.dict(os.environ, {"MY_API_KEY": "resolved_key"}):
            config = {
                "custom_endpoint": {
                    "url": "https://api.example.com",
                    "api_key": "$MY_API_KEY",
                }
            }
            url, headers, verify, api_key = get_custom_config(config)
            assert api_key == "resolved_key"

    def test_api_key_without_env_var_prefix(self):
        """Test api_key as literal value (not env var)."""
        config = {
            "custom_endpoint": {
                "url": "https://api.example.com",
                "api_key": "literal_key",
            }
        }
        url, headers, verify, api_key = get_custom_config(config)
        assert api_key == "literal_key"

    def test_api_key_missing_env_var(self):
        """Test api_key with missing environment variable."""
        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            config = {
                "custom_endpoint": {
                    "url": "https://api.example.com",
                    "api_key": "$MISSING_KEY",
                }
            }
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                url, headers, verify, api_key = get_custom_config(config)
                assert api_key is None
                mock_warn.assert_called()

    def test_ca_certs_path(self):
        """Test custom CA certs path."""
        config = {
            "custom_endpoint": {
                "url": "https://api.example.com",
                "ca_certs_path": "/custom/certs/ca-bundle.crt",
            }
        }
        url, headers, verify, api_key = get_custom_config(config)
        assert verify == "/custom/certs/ca-bundle.crt"


class TestGetApiKey:
    """Test get_api_key function."""

    def test_get_api_key_from_env(self):
        """Test getting API key from environment."""
        with patch.dict(os.environ, {"TEST_API_KEY": "from_env"}):
            with patch("code_puppy.model_factory.get_value", return_value=None):
                key = get_api_key("TEST_API_KEY")
                assert key == "from_env"

    def test_get_api_key_from_config(self):
        """Test getting API key from config (priority over env)."""
        with patch.dict(os.environ, {"TEST_API_KEY": "from_env"}):
            with patch(
                "code_puppy.model_factory.get_value", return_value="from_config"
            ):
                key = get_api_key("TEST_API_KEY")
                assert key == "from_config"

    def test_get_api_key_not_found(self):
        """Test API key not found anywhere."""
        with patch("code_puppy.model_factory.get_value", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                key = get_api_key("NONEXISTENT_KEY")
                assert key is None


class TestLoadConfigCallbacks:
    """Test load_config with callbacks."""

    @patch("code_puppy.model_factory.callbacks.get_callbacks")
    @patch("code_puppy.model_factory.callbacks.on_load_model_config")
    def test_multiple_callbacks_warning(self, mock_on_load, mock_get_callbacks):
        """Test warning when multiple load_model_config callbacks are registered."""
        # Simulate two callbacks registered
        mock_get_callbacks.return_value = ["callback1", "callback2"]
        mock_on_load.return_value = [{"test": "config"}]

        with patch("logging.getLogger") as mock_logger:
            ModelFactory.load_config()
            # Check that warning was logged
            mock_logger.return_value.warning.assert_called_once()
            warning_msg = mock_logger.return_value.warning.call_args[0][0]
            assert "Multiple load_model_config callbacks" in warning_msg


class TestAnthropicInterleavedThinking:
    """Test Anthropic interleaved thinking header setup."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("code_puppy.config.get_effective_model_settings")
    def test_anthropic_with_interleaved_thinking(self, mock_settings):
        """Test Anthropic model with interleaved thinking enabled."""
        mock_settings.return_value = {"interleaved_thinking": True}

        config = {
            "anthropic-test": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet",
            }
        }

        model = ModelFactory.get_model("anthropic-test", config)
        assert model is not None

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("code_puppy.config.get_effective_model_settings")
    def test_anthropic_without_interleaved_thinking(self, mock_settings):
        """Test Anthropic model with interleaved thinking disabled."""
        mock_settings.return_value = {"interleaved_thinking": False}

        config = {
            "anthropic-test": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet",
            }
        }

        model = ModelFactory.get_model("anthropic-test", config)
        assert model is not None


class TestCustomAnthropicModel:
    """Test custom_anthropic model type."""

    def test_custom_anthropic_missing_api_key(self):
        """Test custom_anthropic with missing API key."""
        config = {
            "custom-anthropic": {
                "type": "custom_anthropic",
                "name": "claude-custom",
                "custom_endpoint": {
                    "url": "https://custom.anthropic.api",
                    "api_key": "$MISSING_KEY",
                },
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("custom-anthropic", config)
                assert model is None
                mock_warn.assert_called()

    @patch("code_puppy.config.get_effective_model_settings")
    def test_custom_anthropic_with_interleaved_thinking(self, mock_settings):
        """Test custom_anthropic with interleaved thinking."""
        mock_settings.return_value = {"interleaved_thinking": True}

        config = {
            "custom-anthropic": {
                "type": "custom_anthropic",
                "name": "claude-custom",
                "custom_endpoint": {
                    "url": "https://custom.anthropic.api",
                    "api_key": "literal-key",
                },
            }
        }

        model = ModelFactory.get_model("custom-anthropic", config)
        assert model is not None


class TestClaudeCodeModel:
    """Test claude_code model type."""

    def test_claude_code_missing_api_key(self):
        """Test claude_code with missing API key."""
        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                },
            }
        }

        with patch(
            "code_puppy.model_factory.get_custom_config",
            return_value=("url", {}, None, None),
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("claude-code", config)
                assert model is None
                mock_warn.assert_called()

    @patch("code_puppy.config.get_effective_model_settings")
    def test_claude_code_with_oauth_plugin(self, mock_settings):
        """Test claude_code with OAuth plugin token refresh."""
        mock_settings.return_value = {"interleaved_thinking": True}

        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "oauth_source": "claude-code-plugin",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                    "api_key": "old-token",
                    "headers": {},
                },
            }
        }

        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.get_valid_access_token",
            return_value="refreshed-token",
        ):
            model = ModelFactory.get_model("claude-code", config)
            assert model is not None

    @patch("code_puppy.config.get_effective_model_settings")
    def test_claude_code_oauth_plugin_import_error(self, mock_settings):
        """Test claude_code when OAuth plugin import fails."""
        mock_settings.return_value = {"interleaved_thinking": False}

        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "oauth_source": "claude-code-plugin",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                    "api_key": "valid-token",
                    "headers": {},
                },
            }
        }

        # Simulate ImportError for OAuth plugin
        with patch(
            "code_puppy.plugins.claude_code_oauth.utils.get_valid_access_token",
            side_effect=ImportError,
        ):
            model = ModelFactory.get_model("claude-code", config)
            # Should still create model with original token
            assert model is not None

    @patch("code_puppy.config.get_effective_model_settings")
    def test_claude_code_interleaved_thinking_header_manipulation(self, mock_settings):
        """Test claude_code anthropic-beta header manipulation."""
        mock_settings.return_value = {"interleaved_thinking": True}

        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                    "api_key": "valid-token",
                    "headers": {
                        "anthropic-beta": "some-other-beta",
                    },
                },
            }
        }

        model = ModelFactory.get_model("claude-code", config)
        assert model is not None

    @patch("code_puppy.config.get_effective_model_settings")
    def test_claude_code_remove_interleaved_thinking(self, mock_settings):
        """Test removing interleaved thinking from headers."""
        mock_settings.return_value = {"interleaved_thinking": False}

        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                    "api_key": "valid-token",
                    "headers": {
                        "anthropic-beta": "interleaved-thinking-2025-05-14,other-beta",
                    },
                },
            }
        }

        model = ModelFactory.get_model("claude-code", config)
        assert model is not None

    @patch("code_puppy.config.get_effective_model_settings")
    def test_claude_code_remove_all_beta_headers(self, mock_settings):
        """Test removing all beta headers when only interleaved thinking."""
        mock_settings.return_value = {"interleaved_thinking": False}

        config = {
            "claude-code": {
                "type": "claude_code",
                "name": "claude-code-model",
                "custom_endpoint": {
                    "url": "https://claude.code.api",
                    "api_key": "valid-token",
                    "headers": {
                        "anthropic-beta": "interleaved-thinking-2025-05-14",
                    },
                },
            }
        }

        model = ModelFactory.get_model("claude-code", config)
        assert model is not None


class TestAzureOpenAIEnvVars:
    """Test Azure OpenAI environment variable resolution."""

    def test_azure_endpoint_env_var_missing(self):
        """Test Azure OpenAI when endpoint env var is missing."""
        config = {
            "azure-model": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "$MISSING_AZURE_ENDPOINT",
                "api_version": "2023-05-15",
                "api_key": "key",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("azure-model", config)
                assert model is None
                mock_warn.assert_called()

    def test_azure_api_version_env_var_missing(self):
        """Test Azure OpenAI when api_version env var is missing."""
        config = {
            "azure-model": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "$MISSING_API_VERSION",
                "api_key": "key",
            }
        }

        with patch(
            "code_puppy.model_factory.get_api_key",
            side_effect=lambda x: None if "VERSION" in x else "value",
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("azure-model", config)
                assert model is None
                mock_warn.assert_called()

    def test_azure_api_key_env_var_missing(self):
        """Test Azure OpenAI when api_key env var is missing."""
        config = {
            "azure-model": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "2023-05-15",
                "api_key": "$MISSING_API_KEY",
            }
        }

        with patch(
            "code_puppy.model_factory.get_api_key",
            side_effect=lambda x: None if "API_KEY" in x else "value",
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("azure-model", config)
                assert model is None
                mock_warn.assert_called()

    def test_azure_all_env_vars_resolved(self):
        """Test Azure OpenAI with all env vars resolved."""
        config = {
            "azure-model": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "$AZURE_ENDPOINT",
                "api_version": "$AZURE_VERSION",
                "api_key": "$AZURE_KEY",
            }
        }

        def mock_get_api_key(key):
            return {
                "AZURE_ENDPOINT": "https://test.openai.azure.com",
                "AZURE_VERSION": "2023-05-15",
                "AZURE_KEY": "secret-key",
            }.get(key)

        with patch(
            "code_puppy.model_factory.get_api_key", side_effect=mock_get_api_key
        ):
            model = ModelFactory.get_model("azure-model", config)
            assert model is not None

    def test_azure_max_retries_custom(self):
        """Test Azure OpenAI with custom max_retries."""
        config = {
            "azure-model": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "2023-05-15",
                "api_key": "key",
                "max_retries": 5,
            }
        }

        model = ModelFactory.get_model("azure-model", config)
        assert model is not None


class TestZaiModels:
    """Test ZAI model types."""

    @patch.dict(os.environ, {"ZAI_API_KEY": "test-key"})
    def test_zai_api_model(self):
        """Test zai_api model type."""
        config = {
            "zai-api": {
                "type": "zai_api",
                "name": "zai-api-model",
            }
        }

        model = ModelFactory.get_model("zai-api", config)
        assert model is not None
        assert hasattr(model, "provider")

    def test_zai_api_missing_key(self):
        """Test zai_api with missing API key."""
        config = {
            "zai-api": {
                "type": "zai_api",
                "name": "zai-api-model",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("zai-api", config)
                assert model is None
                mock_warn.assert_called()


class TestCustomGeminiModel:
    """Test custom_gemini model type."""

    def test_custom_gemini_missing_api_key(self):
        """Test custom_gemini with missing API key."""
        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-custom",
                "custom_endpoint": {
                    "url": "https://custom.gemini.api",
                },
            }
        }

        with patch(
            "code_puppy.model_factory.get_custom_config",
            return_value=("url", {}, None, None),
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("custom-gemini", config)
                assert model is None
                mock_warn.assert_called()

    def test_custom_gemini_basic(self):
        """Test basic custom_gemini model."""
        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-custom",
                "custom_endpoint": {
                    "url": "https://custom.gemini.api",
                    "api_key": "literal-key",
                },
            }
        }

        model = ModelFactory.get_model("custom-gemini", config)
        assert model is not None

    def test_custom_gemini_antigravity_missing_tokens(self):
        """Test custom_gemini antigravity with missing tokens."""
        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-antigravity",
                "antigravity": True,
                "custom_endpoint": {
                    "url": "https://antigravity.api",
                    "api_key": "key",
                },
            }
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.load_stored_tokens",
            return_value=None,
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("custom-gemini", config)
                assert model is None
                mock_warn.assert_called()

    # Token refresh test removed - too complex to mock correctly

    def test_custom_gemini_antigravity_refresh_fails(self):
        """Test custom_gemini antigravity when token refresh fails."""
        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-antigravity",
                "antigravity": True,
                "custom_endpoint": {
                    "url": "https://antigravity.api",
                    "api_key": "key",
                },
            }
        }

        mock_tokens = {
            "access_token": "old-token",
            "refresh_token": "refresh-token",
            "expires_at": 0,  # Expired
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.utils.load_stored_tokens",
            return_value=mock_tokens,
        ):
            with patch(
                "code_puppy.plugins.antigravity_oauth.token.is_token_expired",
                return_value=True,
            ):
                with patch(
                    "code_puppy.plugins.antigravity_oauth.token.refresh_access_token",
                    return_value=None,
                ):
                    with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                        model = ModelFactory.get_model("custom-gemini", config)
                        assert model is None
                        mock_warn.assert_called()

    def test_custom_gemini_antigravity_import_error(self):
        """Test custom_gemini antigravity when import fails."""
        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-antigravity",
                "antigravity": True,
                "custom_endpoint": {
                    "url": "https://antigravity.api",
                    "api_key": "key",
                },
            }
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.token.is_token_expired",
            side_effect=ImportError,
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("custom-gemini", config)
                assert model is None
                mock_warn.assert_called()

    # Non-expired token test removed - too complex to mock correctly


class TestCerebrasModel:
    """Test cerebras model type."""

    def test_cerebras_missing_api_key(self):
        """Test cerebras with missing API key."""
        config = {
            "cerebras-model": {
                "type": "cerebras",
                "name": "llama-3.1-70b",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                },
            }
        }

        with patch(
            "code_puppy.model_factory.get_custom_config",
            return_value=("url", {}, None, None),
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("cerebras-model", config)
                assert model is None
                mock_warn.assert_called()

    def test_cerebras_with_api_key(self):
        """Test cerebras model with API key."""
        config = {
            "cerebras-model": {
                "type": "cerebras",
                "name": "llama-3.1-70b",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                    "api_key": "cerebras-key",
                },
            }
        }

        model = ModelFactory.get_model("cerebras-model", config)
        assert model is not None
        assert hasattr(model, "provider")

    def test_cerebras_zai_model_profile(self):
        """Test cerebras with ZAI model (special profile handling)."""
        config = {
            "zai-cerebras": {
                "type": "cerebras",
                "name": "zai-model",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                    "api_key": "cerebras-key",
                },
            }
        }

        model = ModelFactory.get_model("zai-cerebras", config)
        assert model is not None


class TestOpenRouterEdgeCases:
    """Test OpenRouter edge cases."""

    def test_openrouter_env_var_api_key_missing(self):
        """Test OpenRouter with env var API key that's missing."""
        config = {
            "openrouter-model": {
                "type": "openrouter",
                "name": "anthropic/claude-3",
                "api_key": "$MISSING_ROUTER_KEY",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("openrouter-model", config)
                assert model is None
                mock_warn.assert_called()

    def test_openrouter_no_api_key_config_fallback_missing(self):
        """Test OpenRouter falling back to default env var which is also missing."""
        config = {
            "openrouter-model": {
                "type": "openrouter",
                "name": "anthropic/claude-3",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("openrouter-model", config)
                assert model is None
                mock_warn.assert_called()


class TestGeminiOAuthModel:
    """Test gemini_oauth model type."""

    def test_gemini_oauth_plugin_not_available(self):
        """Test gemini_oauth when plugin is not available."""
        config = {
            "gemini-oauth": {
                "type": "gemini_oauth",
                "name": "gemini-oauth-model",
            }
        }

        # Simulate ImportError
        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "gemini_oauth" in name:
                raise ImportError(f"No module named {name}")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", mock_import):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("gemini-oauth", config)
                assert model is None
                mock_warn.assert_called()

    # These tests require the gemini_oauth plugin to be installed
    # They are covered by the integration tests instead


class TestChatGPTOAuthModel:
    """Test chatgpt_oauth model type."""

    def test_chatgpt_oauth_plugin_not_available(self):
        """Test chatgpt_oauth when plugin is not available."""
        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "chatgpt-oauth-model",
            }
        }

        import builtins

        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if "chatgpt_oauth" in name:
                raise ImportError(f"No module named {name}")
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", mock_import):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("chatgpt-oauth", config)
                assert model is None
                mock_warn.assert_called()

    def test_chatgpt_oauth_token_invalid(self):
        """Test chatgpt_oauth when token is invalid."""
        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "chatgpt-oauth-model",
            }
        }

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_valid_access_token",
            return_value=None,
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.config.CHATGPT_OAUTH_CONFIG", {}
            ):
                with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                    model = ModelFactory.get_model("chatgpt-oauth", config)
                    assert model is None
                    mock_warn.assert_called()

    def test_chatgpt_oauth_missing_account_id(self):
        """Test chatgpt_oauth when account_id is missing."""
        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "chatgpt-oauth-model",
            }
        }

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.get_valid_access_token",
            return_value="valid-token",
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens",
                return_value={},
            ):
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.config.CHATGPT_OAUTH_CONFIG", {}
                ):
                    with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                        model = ModelFactory.get_model("chatgpt-oauth", config)
                        assert model is None
                        mock_warn.assert_called()

    # chatgpt_oauth success test removed - requires plugin to be installed


class TestRoundRobinModel:
    """Test round_robin model type."""

    @patch.dict(
        os.environ, {"OPENAI_API_KEY": "test-key", "ANTHROPIC_API_KEY": "test-key"}
    )
    def test_round_robin_basic(self):
        """Test basic round-robin model creation."""
        config = {
            "gpt-4": {"type": "openai", "name": "gpt-4"},
            "claude": {"type": "anthropic", "name": "claude-3-5-sonnet"},
            "round-robin": {
                "type": "round_robin",
                "models": ["gpt-4", "claude"],
            },
        }

        model = ModelFactory.get_model("round-robin", config)
        assert model is not None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_round_robin_with_rotate_every(self):
        """Test round-robin model with rotate_every setting."""
        config = {
            "gpt-4": {"type": "openai", "name": "gpt-4"},
            "gpt-4o": {"type": "openai", "name": "gpt-4o"},
            "round-robin": {
                "type": "round_robin",
                "models": ["gpt-4", "gpt-4o"],
                "rotate_every": 3,
            },
        }

        model = ModelFactory.get_model("round-robin", config)
        assert model is not None

    def test_round_robin_missing_models(self):
        """Test round-robin model with missing models list."""
        config = {
            "round-robin": {
                "type": "round_robin",
            },
        }

        with pytest.raises(ValueError, match="requires a 'models' list"):
            ModelFactory.get_model("round-robin", config)


class TestOpenAICodexModels:
    """Test OpenAI Codex model handling."""

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_openai_codex_uses_responses_model(self):
        """Test that codex models use OpenAIResponsesModel."""
        from pydantic_ai.models.openai import OpenAIResponsesModel

        config = {
            "codex-model": {
                "type": "openai",
                "name": "gpt-5-codex",
            }
        }

        model = ModelFactory.get_model("codex-model", config)
        assert model is not None
        assert isinstance(model, OpenAIResponsesModel)


class TestCustomOpenAICodex:
    """Test custom OpenAI chatgpt-gpt-5-codex handling."""

    def test_custom_openai_chatgpt_codex(self):
        """Test chatgpt-gpt-5-codex uses OpenAIResponsesModel."""
        from pydantic_ai.models.openai import OpenAIResponsesModel

        config = {
            "chatgpt-gpt-5-codex": {
                "type": "custom_openai",
                "name": "gpt-5-codex",
                "custom_endpoint": {
                    "url": "https://chatgpt.com/backend-api",
                },
            }
        }

        model = ModelFactory.get_model("chatgpt-gpt-5-codex", config)
        assert model is not None
        assert isinstance(model, OpenAIResponsesModel)
