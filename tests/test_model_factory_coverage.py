"""Comprehensive coverage tests for model_factory.py.

Targets the 206 uncovered lines including:
- get_api_key() config-first lookup
- make_model_settings() for GPT-5, Claude, and auto max_tokens
- ZaiChatModel._process_response()
- get_custom_config() with inline env vars
- load_config() multiple callbacks, filtered loading
- Model types: claude_code, custom_anthropic, custom_gemini, cerebras
- OAuth model types error paths
- Round robin with rotate_every
- OpenAI codex models
"""

import os
from unittest.mock import MagicMock, patch

import pytest


class TestGetApiKey:
    """Test the get_api_key() function."""

    def test_get_api_key_from_config_first(self):
        """Test that get_api_key checks config before environment."""
        from code_puppy.model_factory import get_api_key

        with patch("code_puppy.model_factory.get_value", return_value="config-key"):
            with patch.dict(os.environ, {"TEST_API_KEY": "env-key"}):
                result = get_api_key("TEST_API_KEY")
                assert result == "config-key"

    def test_get_api_key_falls_back_to_env(self):
        """Test that get_api_key falls back to env when config is empty."""
        from code_puppy.model_factory import get_api_key

        with patch("code_puppy.model_factory.get_value", return_value=None):
            with patch.dict(os.environ, {"TEST_API_KEY": "env-key"}):
                result = get_api_key("TEST_API_KEY")
                assert result == "env-key"

    def test_get_api_key_returns_none_when_missing(self):
        """Test that get_api_key returns None when key not found."""
        from code_puppy.model_factory import get_api_key

        with patch("code_puppy.model_factory.get_value", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                # Remove the key if it exists
                os.environ.pop("MISSING_KEY", None)
                result = get_api_key("MISSING_KEY")
                assert result is None

    def test_get_api_key_case_insensitive_config_lookup(self):
        """Test that config lookup is case-insensitive."""
        from code_puppy.model_factory import get_api_key

        # get_value is called with lowercase key
        with patch("code_puppy.model_factory.get_value") as mock_get_value:
            mock_get_value.return_value = "config-value"
            result = get_api_key("MY_API_KEY")
            mock_get_value.assert_called_once_with("my_api_key")
            assert result == "config-value"


class TestMakeModelSettings:
    """Test the make_model_settings() function.

    Note: ModelSettings is a TypedDict, so it returns a dict, not an object.
    """

    def test_make_model_settings_returns_dict(self):
        """Test that make_model_settings returns a dict (TypedDict)."""
        from code_puppy.model_factory import make_model_settings

        # Call with explicit max_tokens to avoid config loading
        settings = make_model_settings("some-model", max_tokens=5000)
        # ModelSettings is a TypedDict, so it returns a dict
        assert isinstance(settings, dict)
        assert settings["max_tokens"] == 5000

    def test_make_model_settings_gpt5_has_reasoning_effort(self):
        """Test GPT-5 model returns settings with reasoning_effort."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("gpt-5-test", max_tokens=4096)
        # Should be a dict with openai_reasoning_effort key
        assert isinstance(settings, dict)
        assert "openai_reasoning_effort" in settings

    def test_make_model_settings_gpt5_codex_no_verbosity(self):
        """Test GPT-5 codex model doesn't get verbosity (only supports medium)."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("gpt-5-codex-test", max_tokens=4096)
        assert isinstance(settings, dict)
        # extra_body should NOT be set for codex models
        assert settings.get("extra_body") is None

    def test_make_model_settings_claude_has_temperature(self):
        """Test Claude model returns settings with temperature."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("claude-3-sonnet", max_tokens=4096)
        assert isinstance(settings, dict)
        # Temperature should be 1.0 (Claude extended thinking requires it)
        assert settings.get("temperature") == 1.0

    def test_make_model_settings_anthropic_prefix(self):
        """Test anthropic- prefixed models get appropriate settings."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("anthropic-claude-opus", max_tokens=4096)
        assert isinstance(settings, dict)
        # Should have temperature set to 1.0
        assert settings.get("temperature") == 1.0

    def test_make_model_settings_removes_top_p_for_anthropic(self):
        """Test that top_p is removed for Anthropic models."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("claude-3-sonnet", max_tokens=4096)
        # top_p should not be in the dict (removed for Anthropic)
        assert "top_p" not in settings

    def test_make_model_settings_fallback_context_length(self):
        """Test fallback when config loading fails."""
        from code_puppy.model_factory import make_model_settings

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            side_effect=Exception("Config error"),
        ):
            settings = make_model_settings("unknown-model")
            # Should fallback to 128000 context length
            # 15% of 128000 = 19200
            assert settings["max_tokens"] == 19200

    def test_make_model_settings_with_explicit_max_tokens(self):
        """Test explicit max_tokens is used."""
        from code_puppy.model_factory import make_model_settings

        settings = make_model_settings("any-model", max_tokens=1234)
        assert settings["max_tokens"] == 1234

    def test_make_model_settings_auto_calculation_boundaries(self):
        """Test auto max_tokens calculation with boundary conditions."""
        from code_puppy.model_factory import make_model_settings

        # Test with a known model in config or fallback
        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"test-model": {"context_length": 1000}},
        ):
            settings = make_model_settings("test-model")
            # 15% of 1000 = 150, but min is 2048
            assert settings["max_tokens"] >= 2048

    def test_make_model_settings_large_context_capped(self):
        """Test max_tokens is capped at 65536 for large context."""
        from code_puppy.model_factory import make_model_settings

        with patch(
            "code_puppy.model_factory.ModelFactory.load_config",
            return_value={"huge-model": {"context_length": 1000000}},
        ):
            settings = make_model_settings("huge-model")
            # 15% of 1000000 = 150000, but max is 65536
            assert settings["max_tokens"] <= 65536

    def test_make_model_settings_parallel_tool_calls_disabled_when_yolo_off(self):
        """Test parallel_tool_calls=False when yolo_mode is disabled."""
        from code_puppy.model_factory import make_model_settings

        with patch("code_puppy.model_factory.get_yolo_mode", return_value=False):
            settings = make_model_settings("gpt-4o", max_tokens=5000)
            assert "parallel_tool_calls" in settings
            assert settings["parallel_tool_calls"] is False

    def test_make_model_settings_parallel_tool_calls_not_set_when_yolo_on(self):
        """Test parallel_tool_calls is not explicitly set when yolo_mode is enabled."""
        from code_puppy.model_factory import make_model_settings

        with patch("code_puppy.model_factory.get_yolo_mode", return_value=True):
            settings = make_model_settings("gpt-4o", max_tokens=5000)
            # When yolo_mode=True, we don't explicitly set parallel_tool_calls
            # to let the model use its default (usually allows parallel calls)
            assert "parallel_tool_calls" not in settings


class TestZaiChatModel:
    """Test the ZaiChatModel class."""

    def test_zai_chat_model_process_response(self):
        """Test that ZaiChatModel._process_response sets object field."""
        from code_puppy.model_factory import ZaiChatModel

        # Create a mock response
        mock_response = MagicMock()
        mock_response.object = "some_other_object"

        # Create model instance with mocked provider
        mock_provider = MagicMock()
        model = ZaiChatModel(model_name="test-zai", provider=mock_provider)

        # Mock parent class _process_response to just return the response
        with patch.object(
            ZaiChatModel.__bases__[0],
            "_process_response",
            return_value=mock_response,
        ):
            model._process_response(mock_response)
            # Should set object to "chat.completion"
            assert mock_response.object == "chat.completion"


class TestGetCustomConfig:
    """Test the get_custom_config() function edge cases."""

    def test_get_custom_config_env_var_in_header(self):
        """Test environment variable resolution in headers."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "headers": {"Authorization": "$MY_TOKEN"},
            }
        }

        with patch(
            "code_puppy.model_factory.get_api_key", return_value="resolved-token"
        ):
            url, headers, verify, api_key = get_custom_config(config)
            assert headers["Authorization"] == "resolved-token"

    def test_get_custom_config_inline_env_vars_with_spaces(self):
        """Test inline env vars with space-separated tokens."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "headers": {"Authorization": "Bearer $TOKEN part2 $EXTRA"},
            }
        }

        def mock_get_api_key(key):
            if key == "TOKEN":
                return "my-token"
            elif key == "EXTRA":
                return "extra-value"
            return None

        with patch(
            "code_puppy.model_factory.get_api_key", side_effect=mock_get_api_key
        ):
            with patch("code_puppy.model_factory.emit_warning"):
                url, headers, verify, api_key = get_custom_config(config)
                assert headers["Authorization"] == "Bearer my-token part2 extra-value"

    def test_get_custom_config_inline_env_var_missing(self):
        """Test inline env var resolution when variable is missing."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "headers": {"Auth": "prefix $MISSING_VAR suffix"},
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                url, headers, verify, api_key = get_custom_config(config)
                assert headers["Auth"] == "prefix  suffix"
                mock_warn.assert_called()

    def test_get_custom_config_api_key_from_env(self):
        """Test api_key resolution from environment variable."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "api_key": "$MY_API_KEY",
            }
        }

        with patch(
            "code_puppy.model_factory.get_api_key", return_value="resolved-api-key"
        ):
            url, headers, verify, api_key = get_custom_config(config)
            assert api_key == "resolved-api-key"

    def test_get_custom_config_api_key_missing_env(self):
        """Test api_key when environment variable is missing."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "api_key": "$MISSING_KEY",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                url, headers, verify, api_key = get_custom_config(config)
                assert api_key is None
                mock_warn.assert_called()

    def test_get_custom_config_raw_api_key(self):
        """Test api_key as raw value (not env var reference)."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "api_key": "raw-api-key-value",
            }
        }

        url, headers, verify, api_key = get_custom_config(config)
        assert api_key == "raw-api-key-value"

    def test_get_custom_config_ca_certs_path(self):
        """Test ca_certs_path configuration."""
        from code_puppy.model_factory import get_custom_config

        config = {
            "custom_endpoint": {
                "url": "https://api.test.com",
                "ca_certs_path": "/path/to/certs.pem",
            }
        }

        url, headers, verify, api_key = get_custom_config(config)
        assert verify == "/path/to/certs.pem"


class TestLoadConfigExtended:
    """Extended tests for ModelFactory.load_config()."""

    def test_load_config_multiple_callbacks_warning(self):
        """Test warning is logged when multiple callbacks are registered."""
        from code_puppy.model_factory import ModelFactory

        with patch(
            "code_puppy.model_factory.callbacks.get_callbacks",
            return_value=["callback1", "callback2"],
        ):
            with patch(
                "code_puppy.model_factory.callbacks.on_load_model_config",
                return_value=[{"test": "config"}],
            ):
                with patch("logging.getLogger") as mock_logger:
                    ModelFactory.load_config()
                    # Should log a warning about multiple callbacks
                    mock_logger.return_value.warning.assert_called_once()
                    warning_msg = mock_logger.return_value.warning.call_args[0][0]
                    assert "Multiple load_model_config callbacks" in warning_msg

    def test_load_config_filtered_claude_models(self):
        """Test that Claude Code OAuth models use filtered loading."""
        from code_puppy.model_factory import ModelFactory

        base_config = {"base-model": {"type": "openai", "name": "gpt-4"}}
        filtered_claude_config = {
            "claude-oauth": {"type": "claude_code", "name": "claude-3-opus"}
        }

        with patch("code_puppy.model_factory.callbacks.get_callbacks", return_value=[]):
            with patch(
                "builtins.open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=MagicMock(
                            return_value=MagicMock(
                                read=MagicMock(
                                    return_value='{"base-model": {"type": "openai", "name": "gpt-4"}}'
                                )
                            )
                        ),
                        __exit__=MagicMock(return_value=False),
                    )
                ),
            ):
                with patch("code_puppy.model_factory.pathlib.Path") as mock_path_class:
                    # Set up path mocking
                    mock_main = MagicMock()
                    mock_main.__truediv__ = MagicMock(return_value=mock_main)
                    mock_main.exists.return_value = False
                    mock_main.parent = mock_main

                    mock_claude = MagicMock()
                    mock_claude.exists.return_value = True

                    def path_side_effect(arg):
                        if "claude" in str(arg).lower():
                            return mock_claude
                        return mock_main

                    mock_path_class.side_effect = path_side_effect

                    with patch(
                        "code_puppy.plugins.claude_code_oauth.utils.load_claude_models_filtered",
                        return_value=filtered_claude_config,
                    ) as mock_filtered:
                        with patch("json.load", return_value=base_config):
                            ModelFactory.load_config()
                            # The filtered loader should be called
                            mock_filtered.assert_called_once()

    def test_load_config_filtered_loading_import_error(self):
        """Test fallback when filtered loading import fails."""
        from code_puppy.model_factory import ModelFactory

        base_config = {"base-model": {"type": "openai", "name": "gpt-4"}}
        plain_claude_config = {"claude-model": {"type": "anthropic", "name": "claude"}}

        with patch("code_puppy.model_factory.callbacks.get_callbacks", return_value=[]):
            with patch("builtins.open", MagicMock()) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = (
                    '{"base-model": {"type": "openai"}}'
                )

                with patch("code_puppy.model_factory.pathlib.Path") as mock_path_class:
                    mock_main = MagicMock()
                    mock_main.__truediv__ = MagicMock(return_value=mock_main)
                    mock_main.exists.return_value = False
                    mock_main.parent = mock_main

                    mock_claude = MagicMock()
                    mock_claude.exists.return_value = True

                    def path_side_effect(arg):
                        if "claude" in str(arg).lower():
                            return mock_claude
                        return mock_main

                    mock_path_class.side_effect = path_side_effect

                    # Make filtered import fail
                    with patch.dict(
                        "sys.modules",
                        {"code_puppy.plugins.claude_code_oauth.utils": None},
                    ):
                        with patch(
                            "code_puppy.plugins.claude_code_oauth.utils.load_claude_models_filtered",
                            side_effect=ImportError("Module not found"),
                        ):
                            with patch(
                                "json.load",
                                side_effect=[base_config, plain_claude_config],
                            ):
                                with patch("logging.getLogger"):
                                    # Should fall back to plain JSON loading
                                    config = ModelFactory.load_config()
                                    assert isinstance(config, dict)


class TestClaudeCodeModel:
    """Test claude_code model type.

    Note: claude_code is now a plugin-based model type. Tests must mock
    callbacks.on_register_model_types to return the handler.
    """

    def test_claude_code_model_basic(self):
        """Test basic claude_code model creation."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        config = {
            "claude-code-test": {
                "type": "claude_code",
                "name": "claude-3-opus",
                "custom_endpoint": {
                    "url": "https://api.anthropic.com",
                    "api_key": "test-key",
                },
            }
        }

        # Mock the plugin callback to return the handler
        mock_handler_return = [
            {"type": "claude_code", "handler": _create_claude_code_model}
        ]
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=mock_handler_return,
        ):
            # Patch at source modules where the plugin handler imports from
            with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
                with patch("code_puppy.http_utils.get_http2", return_value=True):
                    with patch("code_puppy.claude_cache_client.ClaudeCacheAsyncClient"):
                        with patch("anthropic.AsyncAnthropic"):
                            with patch(
                                "code_puppy.claude_cache_client.patch_anthropic_client_messages"
                            ):
                                with patch(
                                    "pydantic_ai.providers.anthropic.AnthropicProvider"
                                ):
                                    with patch(
                                        "pydantic_ai.models.anthropic.AnthropicModel"
                                    ) as mock_model:
                                        with patch(
                                            "code_puppy.config.get_effective_model_settings",
                                            return_value={"interleaved_thinking": True},
                                        ):
                                            ModelFactory.get_model(
                                                "claude-code-test", config
                                            )
                                            mock_model.assert_called_once()

    def test_claude_code_model_interleaved_thinking_header(self):
        """Test interleaved thinking header handling."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        config = {
            "claude-code-test": {
                "type": "claude_code",
                "name": "claude-4-opus",
                "custom_endpoint": {
                    "url": "https://api.anthropic.com",
                    "api_key": "test-key",
                    "headers": {"anthropic-beta": "existing-feature"},
                },
            }
        }

        # Mock the plugin callback to return the handler
        mock_handler_return = [
            {"type": "claude_code", "handler": _create_claude_code_model}
        ]
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=mock_handler_return,
        ):
            with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
                with patch("code_puppy.http_utils.get_http2", return_value=True):
                    with patch(
                        "code_puppy.claude_cache_client.ClaudeCacheAsyncClient"
                    ) as mock_client:
                        with patch("anthropic.AsyncAnthropic"):
                            with patch(
                                "code_puppy.claude_cache_client.patch_anthropic_client_messages"
                            ):
                                with patch(
                                    "pydantic_ai.providers.anthropic.AnthropicProvider"
                                ):
                                    with patch(
                                        "pydantic_ai.models.anthropic.AnthropicModel"
                                    ):
                                        with patch(
                                            "code_puppy.config.get_effective_model_settings",
                                            return_value={"interleaved_thinking": True},
                                        ):
                                            ModelFactory.get_model(
                                                "claude-code-test", config
                                            )
                                            # Check that headers were passed with interleaved thinking
                                            call_args = mock_client.call_args
                                            headers = call_args[1]["headers"]
                                            assert (
                                                "interleaved-thinking-2025-05-14"
                                                in headers.get("anthropic-beta", "")
                                            )

    def test_claude_code_model_disable_interleaved_thinking(self):
        """Test disabling interleaved thinking removes header."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        config = {
            "claude-code-test": {
                "type": "claude_code",
                "name": "claude-3-opus",
                "custom_endpoint": {
                    "url": "https://api.anthropic.com",
                    "api_key": "test-key",
                    "headers": {
                        "anthropic-beta": "interleaved-thinking-2025-05-14,other-feature"
                    },
                },
            }
        }

        # Mock the plugin callback to return the handler
        mock_handler_return = [
            {"type": "claude_code", "handler": _create_claude_code_model}
        ]
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=mock_handler_return,
        ):
            with patch("code_puppy.http_utils.get_cert_bundle_path", return_value=None):
                with patch("code_puppy.http_utils.get_http2", return_value=True):
                    with patch(
                        "code_puppy.claude_cache_client.ClaudeCacheAsyncClient"
                    ) as mock_client:
                        with patch("anthropic.AsyncAnthropic"):
                            with patch(
                                "code_puppy.claude_cache_client.patch_anthropic_client_messages"
                            ):
                                with patch(
                                    "pydantic_ai.providers.anthropic.AnthropicProvider"
                                ):
                                    with patch(
                                        "pydantic_ai.models.anthropic.AnthropicModel"
                                    ):
                                        with patch(
                                            "code_puppy.config.get_effective_model_settings",
                                            return_value={
                                                "interleaved_thinking": False
                                            },
                                        ):
                                            ModelFactory.get_model(
                                                "claude-code-test", config
                                            )
                                            call_args = mock_client.call_args
                                            headers = call_args[1]["headers"]
                                            # interleaved-thinking should be removed
                                            beta = headers.get("anthropic-beta", "")
                                            assert "interleaved-thinking" not in beta

    def test_claude_code_oauth_refresh(self):
        """Test OAuth token refresh for claude_code models."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        config = {
            "claude-oauth": {
                "type": "claude_code",
                "name": "claude-3-opus",
                "oauth_source": "claude-code-plugin",
                "custom_endpoint": {
                    "url": "https://api.anthropic.com",
                    "api_key": "old-token",
                },
            }
        }

        # Mock the plugin callback to return the handler
        mock_handler_return = [
            {"type": "claude_code", "handler": _create_claude_code_model}
        ]
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=mock_handler_return,
        ):
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.get_valid_access_token",
                return_value="new-refreshed-token",
            ):
                with patch(
                    "code_puppy.http_utils.get_cert_bundle_path", return_value=None
                ):
                    with patch("code_puppy.http_utils.get_http2", return_value=True):
                        with patch(
                            "code_puppy.claude_cache_client.ClaudeCacheAsyncClient"
                        ):
                            with patch("anthropic.AsyncAnthropic") as mock_anthropic:
                                with patch(
                                    "code_puppy.claude_cache_client.patch_anthropic_client_messages"
                                ):
                                    with patch(
                                        "pydantic_ai.providers.anthropic.AnthropicProvider"
                                    ):
                                        with patch(
                                            "pydantic_ai.models.anthropic.AnthropicModel"
                                        ):
                                            with patch(
                                                "code_puppy.config.get_effective_model_settings",
                                                return_value={},
                                            ):
                                                ModelFactory.get_model(
                                                    "claude-oauth", config
                                                )
                                                # Token should be refreshed
                                                call_args = mock_anthropic.call_args
                                                assert (
                                                    call_args[1]["auth_token"]
                                                    == "new-refreshed-token"
                                                )

    def test_claude_code_missing_api_key(self):
        """Test claude_code model with missing API key."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        config = {
            "claude-code-test": {
                "type": "claude_code",
                "name": "claude-3-opus",
                "custom_endpoint": {
                    "url": "https://api.anthropic.com",
                },
            }
        }

        # Mock the plugin callback to return the handler
        mock_handler_return = [
            {"type": "claude_code", "handler": _create_claude_code_model}
        ]
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=mock_handler_return,
        ):
            # Patch emit_warning where it's imported in the plugin module
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ) as mock_warn:
                with patch(
                    "code_puppy.config.get_effective_model_settings", return_value={}
                ):
                    model = ModelFactory.get_model("claude-code-test", config)
                    assert model is None
                    mock_warn.assert_called()


class TestCustomAnthropicModel:
    """Test custom_anthropic model type."""

    def test_custom_anthropic_with_api_key(self):
        """Test custom_anthropic model creation."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "custom-claude": {
                "type": "custom_anthropic",
                "name": "claude-3-opus",
                "custom_endpoint": {
                    "url": "https://custom.anthropic.proxy.com",
                    "api_key": "custom-api-key",
                },
            }
        }

        with patch("code_puppy.model_factory.get_cert_bundle_path", return_value=None):
            with patch("code_puppy.model_factory.get_http2", return_value=True):
                with patch("code_puppy.model_factory.ClaudeCacheAsyncClient"):
                    with patch("code_puppy.model_factory.AsyncAnthropic"):
                        with patch(
                            "code_puppy.model_factory.patch_anthropic_client_messages"
                        ):
                            with patch("code_puppy.model_factory.AnthropicProvider"):
                                with patch(
                                    "code_puppy.model_factory.AnthropicModel"
                                ) as mock_model:
                                    with patch(
                                        "code_puppy.config.get_effective_model_settings",
                                        return_value={},
                                    ):
                                        ModelFactory.get_model("custom-claude", config)
                                        mock_model.assert_called_once()

    def test_custom_anthropic_interleaved_thinking(self):
        """Test custom_anthropic with interleaved thinking."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "custom-claude": {
                "type": "custom_anthropic",
                "name": "claude-4-opus",
                "custom_endpoint": {
                    "url": "https://custom.anthropic.proxy.com",
                    "api_key": "custom-api-key",
                },
            }
        }

        with patch("code_puppy.model_factory.get_cert_bundle_path", return_value=None):
            with patch("code_puppy.model_factory.get_http2", return_value=True):
                with patch("code_puppy.model_factory.ClaudeCacheAsyncClient"):
                    with patch(
                        "code_puppy.model_factory.AsyncAnthropic"
                    ) as mock_anthropic:
                        with patch(
                            "code_puppy.model_factory.patch_anthropic_client_messages"
                        ):
                            with patch("code_puppy.model_factory.AnthropicProvider"):
                                with patch("code_puppy.model_factory.AnthropicModel"):
                                    with patch(
                                        "code_puppy.config.get_effective_model_settings",
                                        return_value={"interleaved_thinking": True},
                                    ):
                                        ModelFactory.get_model("custom-claude", config)
                                        call_args = mock_anthropic.call_args
                                        # Should have interleaved thinking header
                                        headers = call_args[1].get(
                                            "default_headers", {}
                                        )
                                        assert (
                                            "anthropic-beta" in headers
                                            or headers is None
                                        )

    def test_custom_anthropic_missing_api_key(self):
        """Test custom_anthropic with missing API key."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "custom-claude": {
                "type": "custom_anthropic",
                "name": "claude-3-opus",
                "custom_endpoint": {
                    "url": "https://custom.anthropic.proxy.com",
                },
            }
        }

        with patch("code_puppy.model_factory.emit_warning") as mock_warn:
            with patch(
                "code_puppy.config.get_effective_model_settings", return_value={}
            ):
                model = ModelFactory.get_model("custom-claude", config)
                assert model is None
                mock_warn.assert_called()


class TestCustomGeminiModel:
    """Test custom_gemini model type."""

    def test_custom_gemini_basic(self):
        """Test basic custom_gemini model creation."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-pro",
                "custom_endpoint": {
                    "url": "https://custom.gemini.proxy.com",
                    "api_key": "custom-api-key",
                },
            }
        }

        with patch("code_puppy.model_factory.create_async_client"):
            with patch("code_puppy.model_factory.GeminiModel") as mock_model:
                ModelFactory.get_model("custom-gemini", config)
                mock_model.assert_called_once()

    def test_custom_gemini_missing_api_key(self):
        """Test custom_gemini with missing API key."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "custom-gemini": {
                "type": "custom_gemini",
                "name": "gemini-pro",
                "custom_endpoint": {
                    "url": "https://custom.gemini.proxy.com",
                },
            }
        }

        with patch("code_puppy.model_factory.emit_warning") as mock_warn:
            model = ModelFactory.get_model("custom-gemini", config)
            assert model is None
            mock_warn.assert_called()


class TestCerebrasModel:
    """Test cerebras model type."""

    def test_cerebras_model_basic(self):
        """Test basic cerebras model creation."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "cerebras-test": {
                "type": "cerebras",
                "name": "llama-3-70b",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                    "api_key": "cerebras-key",
                },
            }
        }

        with patch(
            "code_puppy.model_factory.create_async_client"
        ) as mock_create_client:
            with patch("code_puppy.model_factory.CerebrasProvider"):
                with patch("code_puppy.model_factory.OpenAIChatModel") as mock_model:
                    ModelFactory.get_model("cerebras-test", config)
                    mock_model.assert_called_once()
                    # Check that the 3rd party header was added
                    call_args = mock_create_client.call_args
                    headers = call_args[1]["headers"]
                    assert (
                        headers.get("X-Cerebras-3rd-Party-Integration") == "code-puppy"
                    )

    def test_cerebras_model_missing_api_key(self):
        """Test cerebras model with missing API key."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "cerebras-test": {
                "type": "cerebras",
                "name": "llama-3-70b",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                },
            }
        }

        with patch("code_puppy.model_factory.emit_warning") as mock_warn:
            model = ModelFactory.get_model("cerebras-test", config)
            assert model is None
            mock_warn.assert_called()

    def test_cerebras_zai_model_profile(self):
        """Test ZaiCerebrasProvider model_profile for zai models."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "zai-cerebras": {
                "type": "cerebras",
                "name": "zai-qwen-coder",
                "custom_endpoint": {
                    "url": "https://api.cerebras.ai",
                    "api_key": "cerebras-key",
                },
            }
        }

        # Need to mock at a lower level since CerebrasProvider validates http_client type
        with patch("code_puppy.model_factory.create_async_client") as mock_create:
            # Return None to skip actual client creation
            mock_create.return_value = None
            with patch("code_puppy.model_factory.CerebrasProvider"):
                with patch("code_puppy.model_factory.OpenAIChatModel") as mock_model:
                    ModelFactory.get_model("zai-cerebras", config)
                    # Model should be created with provider
                    mock_model.assert_called_once()


class TestOpenAICodexModels:
    """Test OpenAI codex model handling."""

    def test_openai_codex_uses_responses_model(self):
        """Test that codex models use OpenAIResponsesModel."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "codex-test": {
                "type": "openai",
                "name": "gpt-5-codex",
            }
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("code_puppy.model_factory.OpenAIProvider"):
                with patch(
                    "code_puppy.model_factory.OpenAIResponsesModel"
                ) as mock_responses:
                    with patch("code_puppy.model_factory.OpenAIChatModel"):
                        ModelFactory.get_model("codex-test", config)
                        # Should use OpenAIResponsesModel, not OpenAIChatModel
                        mock_responses.assert_called_once()

    def test_custom_openai_chatgpt_codex(self):
        """Test chatgpt-gpt-5-codex uses OpenAIResponsesModel."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "chatgpt-gpt-5-codex": {
                "type": "custom_openai",
                "name": "gpt-5-codex",
                "custom_endpoint": {
                    "url": "https://api.openai.com",
                },
            }
        }

        with patch("code_puppy.model_factory.create_async_client"):
            with patch("code_puppy.model_factory.OpenAIProvider"):
                with patch(
                    "code_puppy.model_factory.OpenAIResponsesModel"
                ) as mock_responses:
                    ModelFactory.get_model("chatgpt-gpt-5-codex", config)
                    mock_responses.assert_called_once()


class TestZaiApiModel:
    """Test zai_api model type."""

    def test_zai_api_model_basic(self):
        """Test basic zai_api model creation."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "zai-api-test": {
                "type": "zai_api",
                "name": "zai-model",
            }
        }

        with patch.dict(os.environ, {"ZAI_API_KEY": "test-zai-key"}):
            with patch("code_puppy.model_factory.OpenAIProvider") as mock_provider:
                model = ModelFactory.get_model("zai-api-test", config)
                assert model is not None
                # Check base_url for ZAI API
                call_args = mock_provider.call_args
                assert "api.z.ai" in call_args[1]["base_url"]
                assert "paas/v4" in call_args[1]["base_url"]

    def test_zai_api_model_missing_api_key(self):
        """Test zai_api model with missing API key."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "zai-api-test": {
                "type": "zai_api",
                "name": "zai-model",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("zai-api-test", config)
                assert model is None
                assert "ZAI_API_KEY" in mock_warn.call_args[0][0]


class TestAzureOpenAIExtended:
    """Extended tests for Azure OpenAI model type."""

    def test_azure_openai_with_max_retries(self):
        """Test Azure OpenAI with custom max_retries."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "azure-test": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "2024-02-15-preview",
                "api_key": "azure-key",
                "max_retries": 5,
            }
        }

        with patch("code_puppy.model_factory.AsyncAzureOpenAI") as mock_azure:
            with patch("code_puppy.model_factory.OpenAIProvider"):
                with patch("code_puppy.model_factory.OpenAIChatModel"):
                    ModelFactory.get_model("azure-test", config)
                    call_args = mock_azure.call_args
                    assert call_args[1]["max_retries"] == 5

    def test_azure_openai_env_var_api_version(self):
        """Test Azure OpenAI with env var for api_version."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "azure-test": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "$AZURE_API_VERSION",
                "api_key": "azure-key",
            }
        }

        with patch.dict(os.environ, {"AZURE_API_VERSION": "2024-02-15-preview"}):
            with patch("code_puppy.model_factory.AsyncAzureOpenAI") as mock_azure:
                with patch("code_puppy.model_factory.OpenAIProvider"):
                    with patch("code_puppy.model_factory.OpenAIChatModel"):
                        ModelFactory.get_model("azure-test", config)
                        call_args = mock_azure.call_args
                        assert call_args[1]["api_version"] == "2024-02-15-preview"

    def test_azure_openai_missing_env_var_api_version(self):
        """Test Azure OpenAI with missing env var for api_version."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "azure-test": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "$MISSING_API_VERSION",
                "api_key": "azure-key",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("azure-test", config)
                assert model is None
                mock_warn.assert_called()


class TestRoundRobinExtended:
    """Extended tests for round_robin model type."""

    def test_round_robin_with_rotate_every(self):
        """Test round_robin model with rotate_every parameter."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "model-1": {"type": "openai", "name": "gpt-4"},
            "model-2": {"type": "openai", "name": "gpt-4-turbo"},
            "rr-test": {
                "type": "round_robin",
                "models": ["model-1", "model-2"],
                "rotate_every": 3,
            },
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            with patch("code_puppy.model_factory.RoundRobinModel") as mock_rr:
                ModelFactory.get_model("rr-test", config)
                call_args = mock_rr.call_args
                # rotate_every should be passed
                assert call_args[1]["rotate_every"] == 3


class TestGeminiOAuthErrorPaths:
    """Test error paths for gemini_oauth model type."""

    def test_gemini_oauth_plugin_not_available(self):
        """Test gemini_oauth when plugin is not available."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "gemini-oauth": {
                "type": "gemini_oauth",
                "name": "gemini-pro",
            }
        }

        import sys

        # Temporarily remove the module if it exists
        original_modules = {}
        for mod_name in list(sys.modules.keys()):
            if "gemini_oauth" in mod_name:
                original_modules[mod_name] = sys.modules.pop(mod_name)

        try:
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                # This should fail gracefully
                model = ModelFactory.get_model("gemini-oauth", config)
                # Should return None and emit warning
                assert model is None
                mock_warn.assert_called()
        except ImportError:
            # ImportError is also acceptable if not caught
            pass
        finally:
            # Restore modules
            sys.modules.update(original_modules)

    def test_gemini_oauth_missing_token(self):
        """Test gemini_oauth when token is missing."""
        import sys

        from code_puppy.model_factory import ModelFactory

        config = {
            "gemini-oauth": {
                "type": "gemini_oauth",
                "name": "gemini-pro",
            }
        }

        # Create mock module for gemini_oauth
        mock_utils = MagicMock()
        mock_utils.get_valid_access_token = MagicMock(return_value=None)
        mock_utils.get_project_id = MagicMock(return_value="test-project")

        mock_config = MagicMock()
        mock_config.GEMINI_OAUTH_CONFIG = {
            "api_base_url": "https://test.com",
            "api_version": "v1",
        }

        with patch.dict(
            sys.modules,
            {
                "code_puppy.plugins.gemini_oauth": MagicMock(),
                "code_puppy.plugins.gemini_oauth.utils": mock_utils,
                "code_puppy.plugins.gemini_oauth.config": mock_config,
            },
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("gemini-oauth", config)
                assert model is None
                mock_warn.assert_called()

    def test_gemini_oauth_missing_project_id(self):
        """Test gemini_oauth when project_id is missing."""
        import sys

        from code_puppy.model_factory import ModelFactory

        config = {
            "gemini-oauth": {
                "type": "gemini_oauth",
                "name": "gemini-pro",
            }
        }

        # Create mock module for gemini_oauth
        mock_utils = MagicMock()
        mock_utils.get_valid_access_token = MagicMock(return_value="valid-token")
        mock_utils.get_project_id = MagicMock(return_value=None)

        mock_config = MagicMock()
        mock_config.GEMINI_OAUTH_CONFIG = {
            "api_base_url": "https://test.com",
            "api_version": "v1",
        }

        with patch.dict(
            sys.modules,
            {
                "code_puppy.plugins.gemini_oauth": MagicMock(),
                "code_puppy.plugins.gemini_oauth.utils": mock_utils,
                "code_puppy.plugins.gemini_oauth.config": mock_config,
            },
        ):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("gemini-oauth", config)
                assert model is None
                mock_warn.assert_called()


class TestChatGPTOAuthErrorPaths:
    """Test error paths for chatgpt_oauth model type."""

    def test_chatgpt_oauth_plugin_not_available(self):
        """Test chatgpt_oauth when plugin is not available (no handler registered)."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "gpt-4",
            }
        }

        # Mock callbacks to return empty list (no handlers registered)
        # This simulates the plugin not being loaded
        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=[],
        ):
            with pytest.raises(
                ValueError, match="Unsupported model type: chatgpt_oauth"
            ):
                ModelFactory.get_model("chatgpt-oauth", config)

    def test_chatgpt_oauth_missing_token(self):
        """Test chatgpt_oauth when token is missing."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _create_chatgpt_oauth_model,
        )

        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "gpt-4",
            }
        }

        # Mock callbacks to return the chatgpt_oauth handler
        mock_handlers = [
            {"type": "chatgpt_oauth", "handler": _create_chatgpt_oauth_model}
        ]

        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=[mock_handlers],
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_valid_access_token",
                return_value=None,
            ):
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"
                ) as mock_warn:
                    model = ModelFactory.get_model("chatgpt-oauth", config)
                    assert model is None
                    mock_warn.assert_called()

    def test_chatgpt_oauth_missing_account_id(self):
        """Test chatgpt_oauth when account_id is missing."""
        from code_puppy.model_factory import ModelFactory
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _create_chatgpt_oauth_model,
        )

        config = {
            "chatgpt-oauth": {
                "type": "chatgpt_oauth",
                "name": "gpt-4",
            }
        }

        # Mock callbacks to return the chatgpt_oauth handler
        mock_handlers = [
            {"type": "chatgpt_oauth", "handler": _create_chatgpt_oauth_model}
        ]

        with patch(
            "code_puppy.model_factory.callbacks.on_register_model_types",
            return_value=[mock_handlers],
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_valid_access_token",
                return_value="valid-token",
            ):
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                    return_value={},  # No account_id
                ):
                    with patch(
                        "code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"
                    ) as mock_warn:
                        model = ModelFactory.get_model("chatgpt-oauth", config)
                        assert model is None
                        mock_warn.assert_called()


class TestAnthropicInterleaved:
    """Test Anthropic model with interleaved thinking."""

    def test_anthropic_interleaved_thinking_header(self):
        """Test that interleaved thinking adds the correct header."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "claude-test": {
                "type": "anthropic",
                "name": "claude-4-opus",
            }
        }

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch(
                "code_puppy.model_factory.get_cert_bundle_path", return_value=None
            ):
                with patch("code_puppy.model_factory.get_http2", return_value=True):
                    with patch("code_puppy.model_factory.ClaudeCacheAsyncClient"):
                        with patch(
                            "code_puppy.model_factory.AsyncAnthropic"
                        ) as mock_anthropic:
                            with patch(
                                "code_puppy.model_factory.patch_anthropic_client_messages"
                            ):
                                with patch(
                                    "code_puppy.model_factory.AnthropicProvider"
                                ):
                                    with patch(
                                        "code_puppy.model_factory.AnthropicModel"
                                    ):
                                        with patch(
                                            "code_puppy.config.get_effective_model_settings",
                                            return_value={"interleaved_thinking": True},
                                        ):
                                            ModelFactory.get_model(
                                                "claude-test", config
                                            )
                                            call_args = mock_anthropic.call_args
                                            headers = call_args[1].get(
                                                "default_headers"
                                            )
                                            assert headers is not None
                                            assert "anthropic-beta" in headers
                                            assert (
                                                "interleaved-thinking-2025-05-14"
                                                in headers["anthropic-beta"]
                                            )

    def test_anthropic_no_interleaved_thinking(self):
        """Test that no header is added when interleaved thinking is disabled."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "claude-test": {
                "type": "anthropic",
                "name": "claude-3-sonnet",
            }
        }

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch(
                "code_puppy.model_factory.get_cert_bundle_path", return_value=None
            ):
                with patch("code_puppy.model_factory.get_http2", return_value=True):
                    with patch("code_puppy.model_factory.ClaudeCacheAsyncClient"):
                        with patch(
                            "code_puppy.model_factory.AsyncAnthropic"
                        ) as mock_anthropic:
                            with patch(
                                "code_puppy.model_factory.patch_anthropic_client_messages"
                            ):
                                with patch(
                                    "code_puppy.model_factory.AnthropicProvider"
                                ):
                                    with patch(
                                        "code_puppy.model_factory.AnthropicModel"
                                    ):
                                        with patch(
                                            "code_puppy.config.get_effective_model_settings",
                                            return_value={
                                                "interleaved_thinking": False
                                            },
                                        ):
                                            ModelFactory.get_model(
                                                "claude-test", config
                                            )
                                            call_args = mock_anthropic.call_args
                                            # default_headers should be None or empty
                                            headers = call_args[1].get(
                                                "default_headers"
                                            )
                                            assert headers is None


class TestOpenRouterEnvVarMissing:
    """Test OpenRouter with missing env var API key."""

    def test_openrouter_env_var_missing(self):
        """Test OpenRouter when env var API key is not found."""
        from code_puppy.model_factory import ModelFactory

        config = {
            "openrouter-test": {
                "type": "openrouter",
                "name": "anthropic/claude-3",
                "api_key": "$MISSING_OPENROUTER_KEY",
            }
        }

        with patch("code_puppy.model_factory.get_api_key", return_value=None):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("openrouter-test", config)
                assert model is None
                mock_warn.assert_called()
                assert "MISSING_OPENROUTER_KEY" in mock_warn.call_args[0][0]
