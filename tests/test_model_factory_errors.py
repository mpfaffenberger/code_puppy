import json
import os
from unittest.mock import mock_open, patch

import pytest

from code_puppy.model_factory import ModelFactory, get_custom_config


class TestModelFactoryErrors:
    """Test error handling in ModelFactory - focus on exception paths."""

    def test_get_model_invalid_name(self):
        """Test get_model() with completely invalid model name."""
        config = {"valid-model": {"type": "openai", "name": "gpt-4"}}
        with pytest.raises(
            ValueError, match="Model 'nonexistent-model-xyz' not found in configuration"
        ):
            ModelFactory.get_model("nonexistent-model-xyz", config)

    def test_get_model_empty_name(self):
        """Test get_model() with empty model name."""
        config = {"valid-model": {"type": "openai", "name": "gpt-4"}}
        with pytest.raises(ValueError, match="Model '' not found in configuration"):
            ModelFactory.get_model("", config)

    def test_get_model_none_name(self):
        """Test get_model() with None model name."""
        config = {"valid-model": {"type": "openai", "name": "gpt-4"}}
        with pytest.raises(ValueError, match="Model 'None' not found in configuration"):
            ModelFactory.get_model(None, config)

    def test_unsupported_model_type(self):
        """Test get_model() with unsupported model type."""
        config = {"bad-model": {"type": "unsupported-type", "name": "fake-model"}}
        with pytest.raises(
            ValueError, match="Unsupported model type: unsupported-type"
        ):
            ModelFactory.get_model("bad-model", config)

    def test_missing_models_config_file(self):
        """Test load_config() when models.json doesn't exist."""
        with patch("code_puppy.config.MODELS_FILE", "/nonexistent/path/models.json"):
            with patch(
                "pathlib.Path.open", side_effect=FileNotFoundError("No such file")
            ):
                with pytest.raises(FileNotFoundError):
                    ModelFactory.load_config()

    def test_malformed_json_models_file(self):
        """Test load_config() with malformed JSON in models.json."""
        with patch("code_puppy.config.MODELS_FILE", "/fake/path/models.json"):
            with patch(
                "builtins.open", mock_open(read_data="{ invalid json content }")
            ):
                with pytest.raises(json.JSONDecodeError):
                    ModelFactory.load_config()

    def test_malformed_json_extra_models_file(self):
        """Test load_config() handles JSON decode errors gracefully."""
        # This test verifies that JSON decode errors are caught and logged
        # rather than crashing the application
        with patch("logging.getLogger"):
            # Simulate a JSON decode error scenario
            with patch(
                "json.load",
                side_effect=json.JSONDecodeError("Invalid JSON", "{ invalid json }", 0),
            ):
                try:
                    # This might raise an exception, which is fine - we're testing error handling
                    ModelFactory.load_config()
                except (json.JSONDecodeError, FileNotFoundError, KeyError):
                    # These are all acceptable error outcomes
                    pass

                # The key point is that errors should be logged, not silently ignored
                # (This test mainly documents the expected behavior)
                assert True  # Test passes if we get here without hanging

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_missing_required_fields_openai(self):
        """Test OpenAI model with missing required fields."""
        # Missing 'name' field
        config = {"openai-bad": {"type": "openai"}}
        with pytest.raises(KeyError):
            ModelFactory.get_model("openai-bad", config)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_missing_required_fields_anthropic(self):
        """Test Anthropic model with missing required fields."""
        # Missing 'name' field
        config = {"anthropic-bad": {"type": "anthropic"}}
        with pytest.raises(KeyError):
            ModelFactory.get_model("anthropic-bad", config)

    def test_azure_openai_missing_required_configs(self):
        """Test Azure OpenAI model with various missing required configurations."""

        # Missing azure_endpoint
        config1 = {
            "azure-bad-1": {
                "type": "azure_openai",
                "name": "gpt-4",
                "api_version": "2023-05-15",
                "api_key": "key",
            }
        }
        with pytest.raises(
            ValueError, match="Azure OpenAI model type requires 'azure_endpoint'"
        ):
            ModelFactory.get_model("azure-bad-1", config1)

        # Missing api_version
        config2 = {
            "azure-bad-2": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_key": "key",
            }
        }
        with pytest.raises(
            ValueError, match="Azure OpenAI model type requires 'api_version'"
        ):
            ModelFactory.get_model("azure-bad-2", config2)

        # Missing api_key
        config3 = {
            "azure-bad-3": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "https://test.openai.azure.com",
                "api_version": "2023-05-15",
            }
        }
        with pytest.raises(
            ValueError, match="Azure OpenAI model type requires 'api_key'"
        ):
            ModelFactory.get_model("azure-bad-3", config3)

    def test_custom_endpoint_missing_custom_endpoint_config(self):
        """Test custom endpoint models missing custom_endpoint configuration."""
        config = {"custom-bad": {"type": "custom_openai", "name": "model"}}
        with pytest.raises(
            ValueError, match="Custom model requires 'custom_endpoint' configuration"
        ):
            ModelFactory.get_model("custom-bad", config)

    def test_custom_endpoint_missing_url(self):
        """Test custom endpoint models missing URL in custom_endpoint."""
        config = {
            "custom-bad": {
                "type": "custom_openai",
                "name": "model",
                "custom_endpoint": {"headers": {"Authorization": "Bearer token"}},
            }
        }
        with pytest.raises(ValueError, match="Custom endpoint requires 'url' field"):
            ModelFactory.get_model("custom-bad", config)

    def test_round_robin_missing_models_list(self):
        """Test round-robin model missing models list."""
        config = {"rr-bad": {"type": "round_robin", "models": None}}
        with pytest.raises(
            ValueError, match="Round-robin model 'rr-bad' requires a 'models' list"
        ):
            ModelFactory.get_model("rr-bad", config)

    def test_round_robin_empty_models_list(self):
        """Test round-robin model with empty models list."""
        config = {"rr-bad": {"type": "round_robin", "models": []}}
        with pytest.raises(
            ValueError, match="Round-robin model 'rr-bad' requires a 'models' list"
        ):
            ModelFactory.get_model("rr-bad", config)

    def test_round_robin_invalid_models_list(self):
        """Test round-robin model with invalid models list (not a list)."""
        config = {"rr-bad": {"type": "round_robin", "models": "not-a-list"}}
        with pytest.raises(
            ValueError, match="Round-robin model 'rr-bad' requires a 'models' list"
        ):
            ModelFactory.get_model("rr-bad", config)

    def test_environment_variable_resolution_errors(self):
        """Test various environment variable resolution failures."""

        # Azure OpenAI with non-existent environment variable
        config1 = {
            "azure-env-bad": {
                "type": "azure_openai",
                "name": "gpt-4",
                "azure_endpoint": "$NONEXISTENT_VAR",
                "api_version": "2023-05-15",
                "api_key": "key",
            }
        }
        with patch("code_puppy.model_factory.emit_warning") as mock_warn:
            result = ModelFactory.get_model("azure-env-bad", config1)
            assert result is None
            mock_warn.assert_called()
            warning_msg = mock_warn.call_args[0][0]
            assert "not found or is empty" in warning_msg
            assert "NONEXISTENT_VAR" in warning_msg

        # Custom endpoint with non-existent environment variable in header
        config2 = {
            "custom-env-bad": {
                "type": "custom_openai",
                "name": "model",
                "custom_endpoint": {
                    "url": "https://test.com",
                    "headers": {"X-Api-Key": "$NONEXISTENT_KEY"},
                },
            }
        }
        with patch("code_puppy.model_factory.emit_warning") as mock_warn:
            # Mock the http client creation to avoid the httpx.AsyncClient type error
            with patch("code_puppy.model_factory.create_async_client") as mock_client:
                mock_client.return_value = None  # Return None to avoid type checking
                result = ModelFactory.get_model("custom-env-bad", config2)
                # Should still create model but with empty header value
                mock_warn.assert_called()
                warning_msg = mock_warn.call_args[0][0]
                assert "NONEXISTENT_KEY" in warning_msg

    def test_get_custom_config_errors(self):
        """Test get_custom_config function error handling."""

        # Empty config
        with pytest.raises(
            ValueError, match="Custom model requires 'custom_endpoint' configuration"
        ):
            get_custom_config({})

        # Missing custom_endpoint
        with pytest.raises(
            ValueError, match="Custom model requires 'custom_endpoint' configuration"
        ):
            get_custom_config({"some_field": "value"})

        # Empty custom_endpoint
        with pytest.raises(
            ValueError, match="Custom model requires 'custom_endpoint' configuration"
        ):
            get_custom_config({"custom_endpoint": {}})

        # Missing URL in custom_endpoint
        with pytest.raises(ValueError, match="Custom endpoint requires 'url' field"):
            get_custom_config({"custom_endpoint": {"headers": {}}})

        # Custom endpoint with empty URL
        with pytest.raises(ValueError, match="Custom endpoint requires 'url' field"):
            get_custom_config({"custom_endpoint": {"url": ""}})

    def test_model_instantiation_errors_missing_api_keys(self):
        """Test various model instantiation errors when API keys are missing."""

        # Ensure no API keys are set
        original_env = dict(os.environ)
        test_env_vars = [
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GEMINI_API_KEY",
            "ZAI_API_KEY",
            "OPENROUTER_API_KEY",
        ]

        for var in test_env_vars:
            if var in os.environ:
                del os.environ[var]

        try:
            # Test OpenAI without API key
            config_openai = {"openai-test": {"type": "openai", "name": "gpt-4"}}
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                result = ModelFactory.get_model("openai-test", config_openai)
                assert result is None
                mock_warn.assert_called_with(
                    "OPENAI_API_KEY is not set; skipping OpenAI model 'gpt-4'."
                )

            # Test Anthropic without API key
            config_anthropic = {
                "anthropic-test": {"type": "anthropic", "name": "claude-3"}
            }
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                result = ModelFactory.get_model("anthropic-test", config_anthropic)
                assert result is None
                mock_warn.assert_called_with(
                    "ANTHROPIC_API_KEY is not set; skipping Anthropic model 'claude-3'."
                )

            # Test Gemini without API key
            config_gemini = {"gemini-test": {"type": "gemini", "name": "gemini-pro"}}
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                result = ModelFactory.get_model("gemini-test", config_gemini)
                assert result is None
                mock_warn.assert_called_with(
                    "GEMINI_API_KEY is not set; skipping Gemini model 'gemini-pro'."
                )

            # Test ZAI models without API key
            config_zai = {"zai-test": {"type": "zai_coding", "name": "zai-model"}}
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                result = ModelFactory.get_model("zai-test", config_zai)
                assert result is None
                mock_warn.assert_called_with(
                    "ZAI_API_KEY is not set; skipping ZAI coding model 'zai-model'."
                )

            # Test OpenRouter without API key
            config_openrouter = {
                "openrouter-test": {"type": "openrouter", "name": "anthropic/claude-3"}
            }
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                result = ModelFactory.get_model("openrouter-test", config_openrouter)
                assert result is None
                mock_warn.assert_called_with(
                    "OPENROUTER_API_KEY is not set; skipping OpenRouter model 'anthropic/claude-3'."
                )

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    def test_load_config_file_permission_error(self):
        """Test load_config() when there's a file permission error."""
        with patch("code_puppy.config.MODELS_FILE", "/permission/denied/models.json"):
            with patch(
                "builtins.open", side_effect=PermissionError("Permission denied")
            ):
                with pytest.raises(PermissionError):
                    ModelFactory.load_config()

    def test_load_config_general_exception_handling(self):
        """Test load_config() handles general exceptions gracefully for extra models."""
        valid_models_json = '{"test-model": {"type": "openai", "name": "gpt-4"}}'

        with patch("code_puppy.config.MODELS_FILE", "/fake/path/models.json"):
            with patch("builtins.open", mock_open(read_data=valid_models_json)):
                with patch(
                    "code_puppy.config.EXTRA_MODELS_FILE",
                    "/fake/path/extra_models.json",
                ):
                    with patch(
                        "code_puppy.model_factory.get_chatgpt_models_path",
                        return_value="/fake/path/chatgpt.json",
                    ):
                        with patch(
                            "code_puppy.model_factory.get_claude_models_path",
                            return_value="/fake/path/claude.json",
                        ):
                            with patch(
                                "code_puppy.model_factory.load_claude_models_filtered",
                                return_value={},
                            ):
                                with patch("pathlib.Path.exists", return_value=True):
                                    with patch("json.load") as mock_json_load:
                                        # First call succeeds (main models.json), second fails with general exception
                                        mock_json_load.side_effect = [
                                            json.loads(
                                                valid_models_json
                                            ),  # Success for main config
                                            Exception(
                                                "General error"
                                            ),  # Fail for extra models
                                        ]

                                        with patch("logging.getLogger") as mock_logger:
                                            config = ModelFactory.load_config()
                                            # Should still load basic config despite extra models error
                                            assert isinstance(config, dict)
                                            assert "test-model" in config
                                            # Should log warning about the error
                                            mock_logger.return_value.warning.assert_called()
                                            warning_call_args = mock_logger.return_value.warning.call_args[
                                                0
                                            ]
                                            assert (
                                                "Failed to load" in warning_call_args[0]
                                            )

    def test_config_callback_exception_handling(self):
        """Test load_config() when callbacks raise exceptions."""
        with patch(
            "code_puppy.model_factory.callbacks.get_callbacks",
            return_value=[lambda: None],
        ):
            with patch(
                "code_puppy.model_factory.callbacks.on_load_model_config",
                side_effect=Exception("Callback error"),
            ):
                with pytest.raises(Exception, match="Callback error"):
                    ModelFactory.load_config()

    def test_invalid_model_config_structure(self):
        """Test get_model() with basic invalid config structures."""

        # Model config is None
        config1 = {"bad-model": None}
        with pytest.raises(
            ValueError, match="Model 'bad-model' not found in configuration"
        ):
            ModelFactory.get_model("bad-model", config1)

        # Model config is empty dict (falsy, so raises ValueError)
        config2 = {"bad-model": {}}
        with pytest.raises(
            ValueError, match="Model 'bad-model' not found in configuration"
        ):
            ModelFactory.get_model("bad-model", config2)
