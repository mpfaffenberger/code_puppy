import json
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from code_puppy.model_factory import ModelFactory


class TestModelFactoryBasics:
    """Test core functionality of ModelFactory."""

    @patch("code_puppy.model_factory.pathlib.Path.exists", return_value=False)
    @patch("code_puppy.model_factory.callbacks.get_callbacks", return_value=[])
    def test_load_config_basic(self, mock_callbacks, mock_exists):
        """Test basic config loading from models.json."""
        test_config = {
            "claude-3-5-sonnet": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet-20241022",
            },
            "gpt-4": {"type": "openai", "name": "gpt-4"},
        }

        # Mock the file operations with actual JSON data
        with patch("builtins.open", mock_open(read_data=json.dumps(test_config))):
            config = ModelFactory.load_config()

            assert isinstance(config, dict)
            assert "claude-3-5-sonnet" in config
            assert "gpt-4" in config
            assert config["claude-3-5-sonnet"]["type"] == "anthropic"

    @patch("code_puppy.model_factory.load_claude_models_filtered", return_value={})
    @patch("code_puppy.model_factory.get_claude_models_path")
    @patch("code_puppy.model_factory.get_chatgpt_models_path")
    @patch("code_puppy.model_factory.pathlib.Path")
    @patch("code_puppy.model_factory.callbacks.get_callbacks", return_value=[])
    def test_load_config_with_extra_models(
        self,
        mock_callbacks,
        mock_path_class,
        mock_chatgpt_path_func,
        mock_claude_path_func,
        mock_load_claude,
    ):
        """Test config loading with extra models file."""
        base_config = {
            "claude-3-5-sonnet": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet-20241022",
            }
        }
        extra_config = {
            "custom-model": {"type": "custom_openai", "name": "custom-gpt-4"}
        }

        # Create mock path instances
        mock_main_path = MagicMock()
        mock_extra_path = MagicMock()
        mock_chatgpt_path = MagicMock()
        mock_claude_path = MagicMock()

        # Configure exists() for each path
        mock_main_path.exists.return_value = True  # models.json exists
        mock_extra_path.exists.return_value = True  # extra models exists
        mock_chatgpt_path.exists.return_value = False  # ChatGPT models doesn't exist
        mock_claude_path.exists.return_value = False  # Claude models doesn't exist

        # Mock the plugin path functions
        mock_chatgpt_path_func.return_value = mock_chatgpt_path
        mock_claude_path_func.return_value = mock_claude_path

        # Configure Path() constructor to return appropriate mocks
        def path_side_effect(path_arg):
            if "extra" in str(path_arg):
                return mock_extra_path
            else:
                return mock_main_path

        mock_path_class.side_effect = path_side_effect

        # Mock file reads - handle multiple file opens properly
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.read.side_effect = [
                json.dumps(base_config),  # Source models.json
                json.dumps(base_config),  # Target models.json after copy
            ]
            # Mock json.load for the extra models file
            with patch(
                "json.load",
                side_effect=[
                    base_config,  # Main models.json
                    extra_config,  # Extra models file
                ],
            ):
                config = ModelFactory.load_config()

        assert "claude-3-5-sonnet" in config
        assert "custom-model" in config

    @patch("code_puppy.model_factory.load_claude_models_filtered", return_value={})
    @patch("code_puppy.model_factory.get_claude_models_path")
    @patch("code_puppy.model_factory.get_chatgpt_models_path")
    @patch("code_puppy.model_factory.pathlib.Path")
    @patch("code_puppy.model_factory.callbacks.get_callbacks", return_value=[])
    def test_load_config_invalid_json(
        self,
        mock_callbacks,
        mock_path_class,
        mock_chatgpt_path_func,
        mock_claude_path_func,
        mock_load_claude,
    ):
        """Test handling of invalid JSON in extra models files."""
        base_config = {
            "claude-3-5-sonnet": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet-20241022",
            }
        }

        # Create mock path instances
        mock_main_path = MagicMock()
        mock_extra_path = MagicMock()
        mock_chatgpt_path = MagicMock()
        mock_claude_path = MagicMock()

        # Configure exists() for each path
        mock_main_path.exists.return_value = True  # models.json exists
        mock_extra_path.exists.return_value = (
            True  # extra models exists (but has invalid JSON)
        )
        mock_chatgpt_path.exists.return_value = False  # ChatGPT models doesn't exist
        mock_claude_path.exists.return_value = False  # Claude models doesn't exist

        # Mock the plugin path functions
        mock_chatgpt_path_func.return_value = mock_chatgpt_path
        mock_claude_path_func.return_value = mock_claude_path

        # Configure Path() constructor to return appropriate mocks
        def path_side_effect(path_arg):
            if "extra" in str(path_arg):
                return mock_extra_path
            else:
                return mock_main_path

        mock_path_class.side_effect = path_side_effect

        # Mock file operations
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.return_value.read.side_effect = [
                json.dumps(base_config),  # Source models.json (valid)
                json.dumps(base_config),  # Target models.json after copy (valid)
            ]
            # Mock json.load to raise JSONDecodeError for extra models
            with patch(
                "json.load",
                side_effect=[
                    base_config,  # Main models.json (valid)
                    json.JSONDecodeError(
                        "Invalid JSON", "doc", 0
                    ),  # Extra models file (invalid)
                ],
            ):
                # Should still load base config despite invalid extra config
                config = ModelFactory.load_config()
                assert "claude-3-5-sonnet" in config

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_get_model_openai(self):
        """Test getting an OpenAI model."""
        config = {"gpt-4": {"type": "openai", "name": "gpt-4"}}

        model = ModelFactory.get_model("gpt-4", config)

        assert model is not None
        assert hasattr(model, "provider")
        assert model.model_name == "gpt-4"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    def test_get_model_anthropic(self):
        """Test getting an Anthropic model."""
        config = {
            "claude-3-5-sonnet": {
                "type": "anthropic",
                "name": "claude-3-5-sonnet-20241022",
            }
        }

        model = ModelFactory.get_model("claude-3-5-sonnet", config)

        assert model is not None
        assert model.model_name == "claude-3-5-sonnet-20241022"

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    def test_get_model_gemini(self):
        """Test getting a Gemini model."""
        config = {"gemini-pro": {"type": "gemini", "name": "gemini-pro"}}

        model = ModelFactory.get_model("gemini-pro", config)

        assert model is not None
        assert hasattr(model, "provider")
        assert model.model_name == "gemini-pro"

    def test_get_model_missing_api_key(self):
        """Test getting a model when API key is missing."""
        config = {"gpt-4": {"type": "openai", "name": "gpt-4"}}

        # Remove OPENAI_API_KEY from environment
        with patch.dict(os.environ, {}, clear=True):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("gpt-4", config)
                assert model is None
                mock_warn.assert_called_once()

    def test_get_model_not_found(self):
        """Test getting a model that doesn't exist in config."""
        config = {"gpt-4": {"type": "openai", "name": "gpt-4"}}

        with pytest.raises(
            ValueError, match="Model 'nonexistent-model' not found in configuration"
        ):
            ModelFactory.get_model("nonexistent-model", config)

    def test_get_model_unsupported_type(self):
        """Test getting a model with unsupported type."""
        config = {
            "unsupported-model": {
                "type": "unsupported_type",
                "name": "unsupported-model",
            }
        }

        with pytest.raises(
            ValueError, match="Unsupported model type: unsupported_type"
        ):
            ModelFactory.get_model("unsupported-model", config)

    def test_get_model_custom_openai(self):
        """Test getting a custom OpenAI model."""
        config = {
            "custom-model": {
                "type": "custom_openai",
                "name": "custom-gpt-4",
                "custom_endpoint": {
                    "url": "https://api.custom.com/v1",
                    "headers": {"Authorization": "Bearer test-key"},
                },
            }
        }

        model = ModelFactory.get_model("custom-model", config)

        assert model is not None
        assert hasattr(model, "provider")
        assert model.model_name == "custom-gpt-4"

    def test_get_model_custom_openai_env_vars(self):
        """Test custom OpenAI model with environment variable resolution."""
        config = {
            "custom-model": {
                "type": "custom_openai",
                "name": "custom-gpt-4",
                "custom_endpoint": {
                    "url": "https://api.custom.com/v1",
                    "headers": {"Authorization": "Bearer $CUSTOM_API_KEY"},
                    "api_key": "$CUSTOM_API_KEY",
                },
            }
        }

        with patch.dict(os.environ, {"CUSTOM_API_KEY": "resolved-key"}):
            model = ModelFactory.get_model("custom-model", config)

            assert model is not None
            assert model.model_name == "custom-gpt-4"

    def test_get_model_custom_openai_missing_env_var(self):
        """Test custom OpenAI model with missing environment variable."""
        config = {
            "custom-model": {
                "type": "custom_openai",
                "name": "custom-gpt-4",
                "custom_endpoint": {
                    "url": "https://api.custom.com/v1",
                    "headers": {"Authorization": "Bearer $MISSING_API_KEY"},
                },
            }
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch("code_puppy.model_factory.emit_warning") as mock_warn:
                model = ModelFactory.get_model("custom-model", config)

                # Model should still be created but with empty header value
                assert model is not None
                mock_warn.assert_called()

    def test_get_model_custom_openai_missing_url(self):
        """Test custom OpenAI model missing required URL."""
        config = {
            "custom-model": {
                "type": "custom_openai",
                "name": "custom-gpt-4",
                "custom_endpoint": {"headers": {"Authorization": "Bearer test-key"}},
            }
        }

        with pytest.raises(ValueError, match="Custom endpoint requires 'url' field"):
            ModelFactory.get_model("custom-model", config)

    def test_get_model_custom_openai_missing_config(self):
        """Test custom OpenAI model missing custom_endpoint config."""
        config = {"custom-model": {"type": "custom_openai", "name": "custom-gpt-4"}}

        with pytest.raises(
            ValueError, match="Custom model requires 'custom_endpoint' configuration"
        ):
            ModelFactory.get_model("custom-model", config)

    def test_model_caching_behavior(self):
        """Test that models are created fresh each time (no caching in factory)."""
        config = {"gpt-4": {"type": "openai", "name": "gpt-4"}}

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            model1 = ModelFactory.get_model("gpt-4", config)
            model2 = ModelFactory.get_model("gpt-4", config)

            # Models should be different instances (no caching)
            assert model1 is not model2
            assert model1.model_name == model2.model_name

    @patch(
        "code_puppy.model_factory.callbacks.get_callbacks",
        return_value=["test_callback"],
    )
    @patch(
        "code_puppy.model_factory.callbacks.on_load_model_config",
        return_value=[{"test": "config"}],
    )
    @patch("builtins.open", new_callable=mock_open, read_data="{}")
    @patch("code_puppy.model_factory.pathlib.Path.exists", return_value=False)
    def test_load_config_with_callbacks(
        self, mock_exists, mock_file, mock_on_load, mock_get_callbacks
    ):
        """Test config loading using callbacks."""
        config = ModelFactory.load_config()

        # When callbacks are present, the callback result should be used
        assert config == {"test": "config"}
        mock_get_callbacks.assert_called_once_with("load_model_config")
        mock_on_load.assert_called_once()

    @patch.dict(os.environ, {"ZAI_API_KEY": "test-key"})
    def test_get_model_zai_coding(self):
        """Test getting a ZAI coding model."""
        config = {"zai-coding": {"type": "zai_coding", "name": "zai-coding-model"}}

        model = ModelFactory.get_model("zai-coding", config)

        assert model is not None
        assert hasattr(model, "provider")
        assert model.model_name == "zai-coding-model"

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    def test_get_model_openrouter(self):
        """Test getting an OpenRouter model."""
        config = {
            "openrouter-model": {
                "type": "openrouter",
                "name": "anthropic/claude-3.5-sonnet",
            }
        }

        model = ModelFactory.get_model("openrouter-model", config)

        assert model is not None
        assert hasattr(model, "provider")
        assert model.model_name == "anthropic/claude-3.5-sonnet"

    def test_get_model_openrouter_config_api_key(self):
        """Test OpenRouter model with API key in config."""
        config = {
            "openrouter-model": {
                "type": "openrouter",
                "name": "anthropic/claude-3.5-sonnet",
                "api_key": "config-api-key",
            }
        }

        model = ModelFactory.get_model("openrouter-model", config)

        assert model is not None
        assert model.model_name == "anthropic/claude-3.5-sonnet"

    def test_get_model_openrouter_env_var_api_key(self):
        """Test OpenRouter model with environment variable API key."""
        config = {
            "openrouter-model": {
                "type": "openrouter",
                "name": "anthropic/claude-3.5-sonnet",
                "api_key": "$ROUTER_API_KEY",
            }
        }

        with patch.dict(os.environ, {"ROUTER_API_KEY": "env-api-key"}):
            model = ModelFactory.get_model("openrouter-model", config)

            assert model is not None
            assert model.model_name == "anthropic/claude-3.5-sonnet"
