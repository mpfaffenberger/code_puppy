"""Comprehensive test suite for the Azure AI Foundry plugin.

Tests cover token provider, configuration utilities, model creation,
and slash command handlers with comprehensive mocking.
"""

import json
import os
import time
from unittest.mock import Mock, patch

import pytest


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_azure_token():
    """Sample Azure AD token response."""
    return Mock(
        token="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJ1cG4iOiJ1c2VyQGNvbXBhbnkuY29tIn0.sig",
        expires_on=time.time() + 3600,
    )


@pytest.fixture
def sample_foundry_config():
    """Sample Foundry model configuration."""
    return {
        "foundry-claude-opus": {
            "type": "azure_foundry",
            "name": "it-entra-claude-opus-4-6[1m]",
            "foundry_resource": "my-resource",
            "context_length": 1000000,
            "supported_settings": ["temperature", "extended_thinking", "budget_tokens"],
        }
    }


@pytest.fixture
def temp_extra_models(tmp_path, sample_foundry_config):
    """Create a temporary extra_models.json file."""
    extra_models_path = tmp_path / "extra_models.json"
    with open(extra_models_path, "w") as f:
        json.dump(sample_foundry_config, f)
    return extra_models_path


# ============================================================================
# CONFIG MODULE TESTS
# ============================================================================


class TestConfig:
    """Test configuration module functions."""

    def test_azure_cognitive_scope_constant(self):
        """Test that the Azure scope constant is correct."""
        from code_puppy.plugins.azure_foundry.config import AZURE_COGNITIVE_SCOPE

        assert AZURE_COGNITIVE_SCOPE == "https://cognitiveservices.azure.com/.default"

    def test_default_deployment_names(self):
        """Test default deployment name constants."""
        from code_puppy.plugins.azure_foundry.config import DEFAULT_DEPLOYMENT_NAMES

        assert "opus" in DEFAULT_DEPLOYMENT_NAMES
        assert "sonnet" in DEFAULT_DEPLOYMENT_NAMES
        assert "haiku" in DEFAULT_DEPLOYMENT_NAMES

    def test_default_context_lengths(self):
        """Test default context length constants."""
        from code_puppy.plugins.azure_foundry.config import DEFAULT_CONTEXT_LENGTHS

        assert DEFAULT_CONTEXT_LENGTHS["opus"] == 1000000
        assert DEFAULT_CONTEXT_LENGTHS["sonnet"] == 1000000
        assert DEFAULT_CONTEXT_LENGTHS["haiku"] == 200000

    def test_get_foundry_resource_from_env(self):
        """Test getting resource name from environment."""
        from code_puppy.plugins.azure_foundry.config import get_foundry_resource

        with patch.dict(os.environ, {"ANTHROPIC_FOUNDRY_RESOURCE": "test-resource"}):
            assert get_foundry_resource() == "test-resource"

    def test_get_foundry_resource_not_set(self):
        """Test getting resource name when not set."""
        from code_puppy.plugins.azure_foundry.config import get_foundry_resource

        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop("ANTHROPIC_FOUNDRY_RESOURCE", None)
            assert get_foundry_resource() is None

    def test_get_foundry_base_url_from_resource(self):
        """Test constructing base URL from resource name."""
        from code_puppy.plugins.azure_foundry.config import get_foundry_base_url

        with patch.dict(
            os.environ,
            {"ANTHROPIC_FOUNDRY_RESOURCE": "my-resource"},
            clear=True,
        ):
            os.environ.pop("ANTHROPIC_FOUNDRY_BASE_URL", None)
            url = get_foundry_base_url()
            assert url == "https://my-resource.services.ai.azure.com/anthropic/v1"

    def test_get_foundry_base_url_override(self):
        """Test using explicit base URL override."""
        from code_puppy.plugins.azure_foundry.config import get_foundry_base_url

        with patch.dict(
            os.environ,
            {"ANTHROPIC_FOUNDRY_BASE_URL": "https://custom.endpoint.com"},
        ):
            url = get_foundry_base_url()
            assert url == "https://custom.endpoint.com"


# ============================================================================
# TOKEN PROVIDER TESTS
# ============================================================================


class TestAzureFoundryTokenProvider:
    """Test Azure AD token provider functionality."""

    def test_singleton_pattern(self):
        """Test that get_token_provider returns singleton."""
        from code_puppy.plugins.azure_foundry.token import (
            get_token_provider,
            reset_token_provider,
        )

        reset_token_provider()
        provider1 = get_token_provider()
        provider2 = get_token_provider()
        assert provider1 is provider2

    def test_reset_token_provider(self):
        """Test resetting the singleton instance."""
        from code_puppy.plugins.azure_foundry.token import (
            get_token_provider,
            reset_token_provider,
        )

        provider1 = get_token_provider()
        reset_token_provider()
        provider2 = get_token_provider()
        assert provider1 is not provider2

    def test_get_token_success(self, mock_azure_token):
        """Test successful token acquisition."""
        from code_puppy.plugins.azure_foundry.token import (
            AzureFoundryTokenProvider,
            reset_token_provider,
        )

        reset_token_provider()

        mock_cred = Mock()
        mock_token_func = Mock(return_value="test_token_123")

        with patch("azure.identity.AzureCliCredential", return_value=mock_cred):
            with patch("azure.identity.get_bearer_token_provider", return_value=mock_token_func):
                provider = AzureFoundryTokenProvider()
                token = provider.get_token()

                assert token == "test_token_123"
                mock_token_func.assert_called_once()

    def test_check_auth_status_valid(self, mock_azure_token):
        """Test auth status check when authenticated."""
        from code_puppy.plugins.azure_foundry.token import (
            AzureFoundryTokenProvider,
            reset_token_provider,
        )

        reset_token_provider()

        mock_cred = Mock()
        mock_cred.get_token.return_value = mock_azure_token

        with patch("azure.identity.AzureCliCredential", return_value=mock_cred):
            with patch("azure.identity.get_bearer_token_provider", return_value=Mock()):
                provider = AzureFoundryTokenProvider()
                is_auth, status, user_info = provider.check_auth_status()

                assert is_auth is True
                assert "Valid" in status

    def test_check_auth_status_not_authenticated(self):
        """Test auth status when not logged in."""
        from code_puppy.plugins.azure_foundry.token import (
            AzureFoundryTokenProvider,
            reset_token_provider,
        )

        reset_token_provider()

        mock_cred = Mock()
        # Simulate CredentialUnavailableError
        mock_cred.get_token.side_effect = Exception("CredentialUnavailableError: Not logged in")

        with patch("azure.identity.AzureCliCredential", return_value=mock_cred):
            with patch("azure.identity.get_bearer_token_provider", return_value=Mock()):
                provider = AzureFoundryTokenProvider()
                is_auth, status, user_info = provider.check_auth_status()

                assert is_auth is False

    def test_init_error_handling(self):
        """Test initialization error handling."""
        from code_puppy.plugins.azure_foundry.token import (
            AzureFoundryTokenProvider,
            reset_token_provider,
        )

        reset_token_provider()

        # Create a provider that will fail to initialize
        with patch("azure.identity.AzureCliCredential", side_effect=Exception("Init failed")):
            provider = AzureFoundryTokenProvider()
            is_auth, status, user_info = provider.check_auth_status()

            assert is_auth is False
            assert "Init failed" in status or "Failed" in status


# ============================================================================
# UTILS MODULE TESTS
# ============================================================================


class TestResolveEnvVar:
    """Test environment variable resolution."""

    def test_resolve_env_var_with_dollar(self):
        """Test resolving $VAR syntax."""
        from code_puppy.plugins.azure_foundry.utils import resolve_env_var

        with patch.dict(os.environ, {"MY_VAR": "resolved_value"}):
            assert resolve_env_var("$MY_VAR") == "resolved_value"

    def test_resolve_env_var_literal(self):
        """Test literal values pass through."""
        from code_puppy.plugins.azure_foundry.utils import resolve_env_var

        assert resolve_env_var("literal_value") == "literal_value"

    def test_resolve_env_var_not_set(self):
        """Test resolving unset environment variable."""
        from code_puppy.plugins.azure_foundry.utils import resolve_env_var

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("UNSET_VAR", None)
            assert resolve_env_var("$UNSET_VAR") == ""

    def test_resolve_env_var_empty(self):
        """Test empty string passes through."""
        from code_puppy.plugins.azure_foundry.utils import resolve_env_var

        assert resolve_env_var("") == ""


class TestLoadSaveExtraModels:
    """Test extra_models.json loading and saving."""

    def test_load_extra_models_not_exists(self, tmp_path):
        """Test loading when file doesn't exist."""
        from code_puppy.plugins.azure_foundry.utils import load_extra_models

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=tmp_path / "nonexistent.json",
        ):
            result = load_extra_models()
            assert result == {}

    def test_load_extra_models_success(self, temp_extra_models, sample_foundry_config):
        """Test successful loading of extra_models.json."""
        from code_puppy.plugins.azure_foundry.utils import load_extra_models

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=temp_extra_models,
        ):
            result = load_extra_models()
            assert result == sample_foundry_config

    def test_load_extra_models_invalid_json(self, tmp_path):
        """Test loading invalid JSON."""
        from code_puppy.plugins.azure_foundry.utils import load_extra_models

        invalid_path = tmp_path / "invalid.json"
        invalid_path.write_text("not valid json {{{")

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=invalid_path,
        ):
            result = load_extra_models()
            assert result == {}

    def test_save_extra_models_success(self, tmp_path):
        """Test successful saving of models."""
        from code_puppy.plugins.azure_foundry.utils import save_extra_models

        models_path = tmp_path / "models.json"

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=models_path,
        ):
            result = save_extra_models({"test": {"type": "azure_foundry"}})
            assert result is True
            assert models_path.exists()

            with open(models_path) as f:
                saved = json.load(f)
            assert saved == {"test": {"type": "azure_foundry"}}


class TestBuildFoundryModelConfig:
    """Test model configuration building."""

    def test_build_config_with_defaults(self):
        """Test building config with default values."""
        from code_puppy.plugins.azure_foundry.utils import build_foundry_model_config

        config = build_foundry_model_config(
            deployment_name="claude-opus-4-6",
            model_tier="opus",
        )

        assert config["type"] == "azure_foundry"
        assert config["provider"] == "azure_foundry"
        assert config["name"] == "claude-opus-4-6"
        assert config["context_length"] == 1000000
        assert "foundry_resource" in config

    def test_build_config_with_custom_resource(self):
        """Test building config with explicit resource."""
        from code_puppy.plugins.azure_foundry.utils import build_foundry_model_config

        config = build_foundry_model_config(
            deployment_name="my-opus",
            model_tier="opus",
            foundry_resource="custom-resource",
        )

        assert config["foundry_resource"] == "custom-resource"

    def test_build_config_with_custom_context_length(self):
        """Test building config with custom context length."""
        from code_puppy.plugins.azure_foundry.utils import build_foundry_model_config

        config = build_foundry_model_config(
            deployment_name="my-haiku",
            model_tier="haiku",
            context_length=500000,
        )

        assert config["context_length"] == 500000


class TestAddRemoveFoundryModels:
    """Test adding and removing Foundry models from config."""

    def test_add_foundry_models(self, tmp_path):
        """Test adding models to configuration."""
        from code_puppy.plugins.azure_foundry.utils import (
            add_foundry_models_to_config,
            load_extra_models,
        )

        models_path = tmp_path / "models.json"

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=models_path,
        ):
            added = add_foundry_models_to_config(
                resource_name="my-resource",
                opus_deployment="it-entra-claude-opus-4-6[1m]",
                sonnet_deployment="it-entra-claude-sonnet-4-6[1m]",
            )

            assert "foundry-claude-opus" in added
            assert "foundry-claude-sonnet" in added
            assert "foundry-claude-haiku" not in added

            models = load_extra_models()
            assert "foundry-claude-opus" in models
            assert models["foundry-claude-opus"]["name"] == "it-entra-claude-opus-4-6[1m]"

    def test_remove_foundry_models(self, tmp_path, sample_foundry_config):
        """Test removing Foundry models from configuration."""
        from code_puppy.plugins.azure_foundry.utils import remove_foundry_models_from_config

        models_path = tmp_path / "models.json"
        with open(models_path, "w") as f:
            json.dump(sample_foundry_config, f)

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=models_path,
        ):
            removed = remove_foundry_models_from_config()
            assert "foundry-claude-opus" in removed

            with open(models_path) as f:
                remaining = json.load(f)
            assert "foundry-claude-opus" not in remaining


class TestGetFoundryModelsFromConfig:
    """Test getting Foundry models from configuration."""

    def test_get_foundry_models(self, temp_extra_models, sample_foundry_config):
        """Test filtering Foundry models from config."""
        from code_puppy.plugins.azure_foundry.utils import get_foundry_models_from_config

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=temp_extra_models,
        ):
            models = get_foundry_models_from_config()
            assert "foundry-claude-opus" in models

    def test_get_foundry_models_mixed_types(self, tmp_path):
        """Test filtering when other model types present."""
        from code_puppy.plugins.azure_foundry.utils import get_foundry_models_from_config

        mixed_config = {
            "foundry-model": {"type": "azure_foundry", "name": "test"},
            "openai-model": {"type": "openai", "name": "gpt-4"},
            "anthropic-model": {"type": "anthropic", "name": "claude"},
        }
        models_path = tmp_path / "models.json"
        with open(models_path, "w") as f:
            json.dump(mixed_config, f)

        with patch(
            "code_puppy.plugins.azure_foundry.utils.get_extra_models_path",
            return_value=models_path,
        ):
            foundry_models = get_foundry_models_from_config()
            assert len(foundry_models) == 1
            assert "foundry-model" in foundry_models


# ============================================================================
# REGISTER CALLBACKS TESTS
# ============================================================================


class TestSlashCommands:
    """Test slash command handlers."""

    @patch("code_puppy.plugins.azure_foundry.register_callbacks.get_token_provider")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.get_foundry_resource")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.get_foundry_models_from_config")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_info")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_success")
    def test_handle_foundry_status_authenticated(
        self, mock_emit_success, mock_emit_info, mock_get_models, mock_get_resource, mock_get_provider
    ):
        """Test /foundry-status when authenticated."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_foundry_status

        mock_provider = Mock()
        mock_provider.check_auth_status.return_value = (
            True,
            "Valid (expires in 45 minutes)",
            "user@company.com",
        )
        mock_get_provider.return_value = mock_provider
        mock_get_resource.return_value = "my-resource"
        mock_get_models.return_value = {
            "foundry-claude-opus": {"name": "claude-opus-4-6"}
        }

        _handle_foundry_status()

        mock_emit_success.assert_called()
        # Check that authentication status was displayed
        calls = [str(call) for call in mock_emit_success.call_args_list]
        assert any("Valid" in str(c) for c in calls)

    @patch("code_puppy.plugins.azure_foundry.register_callbacks.get_token_provider")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_warning")
    @patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_info")
    def test_handle_foundry_status_not_authenticated(
        self, mock_emit_info, mock_emit_warning, mock_get_provider
    ):
        """Test /foundry-status when not authenticated."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_foundry_status

        mock_provider = Mock()
        mock_provider.check_auth_status.return_value = (
            False,
            "Not authenticated - run 'az login'",
            None,
        )
        mock_get_provider.return_value = mock_provider

        _handle_foundry_status()

        mock_emit_warning.assert_called()

    def test_handle_custom_command_status(self):
        """Test custom command routing to status."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_custom_command

        with patch(
            "code_puppy.plugins.azure_foundry.register_callbacks._handle_foundry_status"
        ) as mock_status:
            result = _handle_custom_command("/foundry-status", "foundry-status")
            assert result is True
            mock_status.assert_called_once()

    def test_handle_custom_command_setup(self):
        """Test custom command routing to setup."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_custom_command

        with patch(
            "code_puppy.plugins.azure_foundry.register_callbacks._handle_foundry_setup"
        ) as mock_setup:
            result = _handle_custom_command("/foundry-setup", "foundry-setup")
            assert result is True
            mock_setup.assert_called_once()

    def test_handle_custom_command_remove(self):
        """Test custom command routing to remove."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_custom_command

        with patch(
            "code_puppy.plugins.azure_foundry.register_callbacks._handle_foundry_remove"
        ) as mock_remove:
            result = _handle_custom_command("/foundry-remove", "foundry-remove")
            assert result is True
            mock_remove.assert_called_once()

    def test_handle_custom_command_unknown(self):
        """Test custom command returns None for unknown commands."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _handle_custom_command

        result = _handle_custom_command("/other-command", "other-command")
        assert result is None

    def test_custom_help_entries(self):
        """Test that help entries are returned."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _custom_help

        help_entries = _custom_help()
        assert len(help_entries) == 3

        command_names = [entry[0] for entry in help_entries]
        assert "foundry-status" in command_names
        assert "foundry-setup" in command_names
        assert "foundry-remove" in command_names


class TestRegisterModelTypes:
    """Test model type registration."""

    def test_register_model_types(self):
        """Test that azure_foundry model type is registered."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _register_model_types

        registrations = _register_model_types()
        assert len(registrations) == 1
        assert registrations[0]["type"] == "azure_foundry"
        assert callable(registrations[0]["handler"])


class TestCreateAzureFoundryModel:
    """Test Azure Foundry model creation."""

    def test_create_model_no_resource(self):
        """Test model creation fails without resource."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _create_azure_foundry_model

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_FOUNDRY_RESOURCE", None)

            with patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_warning") as mock_warn:
                result = _create_azure_foundry_model(
                    model_name="foundry-test",
                    model_config={"name": "test-deployment"},
                    config={},
                )

                assert result is None
                mock_warn.assert_called()

    def test_create_model_no_deployment_name(self):
        """Test model creation fails without deployment name."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _create_azure_foundry_model

        with patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_warning") as mock_warn:
            result = _create_azure_foundry_model(
                model_name="foundry-test",
                model_config={"foundry_resource": "my-resource"},  # Missing 'name'
                config={},
            )

            assert result is None
            mock_warn.assert_called()

    def test_create_model_auth_failed(self):
        """Test model creation fails when not authenticated."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _create_azure_foundry_model

        mock_provider = Mock()
        mock_provider.check_auth_status.return_value = (
            False,
            "Not authenticated",
            None,
        )

        with patch("code_puppy.plugins.azure_foundry.register_callbacks.get_token_provider", return_value=mock_provider):
            with patch("code_puppy.plugins.azure_foundry.register_callbacks.emit_warning") as mock_warn:
                result = _create_azure_foundry_model(
                    model_name="foundry-test",
                    model_config={
                        "name": "test-deployment",
                        "foundry_resource": "my-resource",
                    },
                    config={},
                )

                assert result is None
                mock_warn.assert_called()

    def test_create_model_success(self):
        """Test successful model creation."""
        from code_puppy.plugins.azure_foundry.register_callbacks import _create_azure_foundry_model

        # Setup mocks
        mock_provider = Mock()
        mock_provider.check_auth_status.return_value = (True, "Valid", "user@test.com")
        mock_provider.get_token = Mock(return_value="token123")

        mock_client = Mock()
        mock_client._custom_headers = {}
        mock_model = Mock()

        with patch("code_puppy.plugins.azure_foundry.register_callbacks.get_token_provider", return_value=mock_provider):
            # Patch at anthropic module since it's imported inside the function
            with patch("anthropic.AsyncAnthropicFoundry", return_value=mock_client) as mock_azure_class:
                with patch("code_puppy.claude_cache_client.patch_anthropic_client_messages"):
                    with patch("code_puppy.config.get_effective_model_settings", return_value={}):
                        with patch("code_puppy.provider_identity.resolve_provider_identity", return_value="identity"):
                            with patch("code_puppy.provider_identity.make_anthropic_provider", return_value=Mock()):
                                with patch("pydantic_ai.models.anthropic.AnthropicModel", return_value=mock_model):
                                    result = _create_azure_foundry_model(
                                        model_name="foundry-claude-opus",
                                        model_config={
                                            "name": "it-entra-claude-opus-4-6[1m]",
                                            "foundry_resource": "my-resource",
                                            "context_length": 1000000,
                                        },
                                        config={},
                                    )

                                    assert result is mock_model
                                    mock_azure_class.assert_called_once()
                                    # Verify resource parameter
                                    call_kwargs = mock_azure_class.call_args.kwargs
                                    assert "resource" in call_kwargs
                                    assert call_kwargs["resource"] == "my-resource"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestPluginCallbackRegistration:
    """Test that callbacks are properly registered on import."""

    def test_callbacks_registered(self):
        """Test that importing the module registers callbacks."""
        # Import triggers callback registration (side effect is intentional)
        import code_puppy.plugins.azure_foundry.register_callbacks  # noqa: F401

        from code_puppy.callbacks import get_callbacks

        # Check that there are callbacks registered for each phase
        help_callbacks = get_callbacks("custom_command_help")
        assert len(help_callbacks) > 0

        cmd_callbacks = get_callbacks("custom_command")
        assert len(cmd_callbacks) > 0

        model_callbacks = get_callbacks("register_model_type")
        assert len(model_callbacks) > 0

    def test_help_includes_foundry_commands(self):
        """Test that foundry commands are in help output."""
        # Import the module to ensure callbacks are registered
        from code_puppy.plugins.azure_foundry.register_callbacks import _custom_help

        help_entries = _custom_help()
        command_names = [name for name, _ in help_entries]

        assert "foundry-status" in command_names
        assert "foundry-setup" in command_names
        assert "foundry-remove" in command_names
