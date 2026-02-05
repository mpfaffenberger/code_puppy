"""ChatGPT OAuth integration tests - models and commands.

Covers:
- Model loading, saving, and management
- Model fetching from API
- Custom commands (auth, status, logout)
- Plugin configuration
"""

import json
import os
from unittest.mock import Mock, patch

import requests

from code_puppy.plugins.chatgpt_oauth.config import (
    CHATGPT_OAUTH_CONFIG,
    get_chatgpt_models_path,
    get_config_dir,
    get_token_storage_path,
)
from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
    _custom_help,
    _handle_chatgpt_logout,
    _handle_chatgpt_status,
    _handle_custom_command,
)
from code_puppy.plugins.chatgpt_oauth.utils import (
    add_models_to_extra_config,
    fetch_chatgpt_models,
    load_chatgpt_models,
    remove_chatgpt_models,
    save_chatgpt_models,
)

# ============================================================================
# Model Management Tests
# ============================================================================


class TestModelManagement:
    """Test ChatGPT model configuration and management."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_load_chatgpt_models_success(self, mock_path, tmp_path):
        """Test loading ChatGPT models from storage."""
        models_file = tmp_path / "models.json"
        models_data = {
            "chatgpt-gpt-5.2": {"type": "chatgpt_oauth", "name": "gpt-5.2"},
            "chatgpt-gpt-5.2-codex": {"type": "chatgpt_oauth", "name": "gpt-5.2-codex"},
        }
        models_file.write_text(json.dumps(models_data))
        mock_path.return_value = models_file

        loaded = load_chatgpt_models()

        assert loaded == models_data

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_load_chatgpt_models_empty(self, mock_path, tmp_path):
        """Test loading models when file doesn't exist returns empty dict."""
        models_file = tmp_path / "nonexistent.json"
        mock_path.return_value = models_file

        loaded = load_chatgpt_models()

        assert loaded == {}

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_save_chatgpt_models_success(self, mock_path, tmp_path):
        """Test saving ChatGPT models to storage."""
        models_file = tmp_path / "models.json"
        mock_path.return_value = models_file
        models_data = {"chatgpt-gpt-5.2": {"type": "chatgpt_oauth"}}

        result = save_chatgpt_models(models_data)

        assert result is True
        assert models_file.exists()
        assert json.loads(models_file.read_text()) == models_data

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_add_models_to_extra_config(self, mock_path, tmp_path):
        """Test adding models to configuration."""
        models_file = tmp_path / "models.json"
        mock_path.return_value = models_file

        result = add_models_to_extra_config(["gpt-5.2", "gpt-5.2-codex"])

        assert result is True
        models = json.loads(models_file.read_text())
        assert "chatgpt-gpt-5.2" in models
        assert "chatgpt-gpt-5.2-codex" in models

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_add_models_with_context_settings(self, mock_path, tmp_path):
        """Test models are added with proper context settings."""
        models_file = tmp_path / "models.json"
        mock_path.return_value = models_file

        add_models_to_extra_config(["gpt-5.2"])

        models = json.loads(models_file.read_text())
        model_config = models["chatgpt-gpt-5.2"]

        assert model_config["type"] == "chatgpt_oauth"
        assert (
            model_config["context_length"]
            == CHATGPT_OAUTH_CONFIG["default_context_length"]
        )
        assert "supported_settings" in model_config
        assert "oauth_source" in model_config

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_chatgpt_models_path")
    def test_remove_chatgpt_models(self, mock_path, tmp_path):
        """Test removing ChatGPT models from configuration."""
        models_file = tmp_path / "models.json"
        models_data = {
            "chatgpt-gpt-5.2": {
                "type": "chatgpt_oauth",
                "oauth_source": "chatgpt-oauth-plugin",
            },
            "other-model": {"type": "openai"},  # Should not be removed
        }
        models_file.write_text(json.dumps(models_data))
        mock_path.return_value = models_file

        removed = remove_chatgpt_models()

        assert removed == 1
        models = json.loads(models_file.read_text())
        assert "chatgpt-gpt-5.2" not in models
        assert "other-model" in models

    @patch("requests.get")
    def test_fetch_chatgpt_models_success(self, mock_get):
        """Test fetching models from API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"slug": "gpt-5.2", "id": "gpt5.2"},
                {"slug": "gpt-5.2-codex", "id": "gpt5.2.codex"},
            ]
        }
        mock_get.return_value = mock_response

        models = fetch_chatgpt_models("test_token", "test_account")

        assert models == ["gpt-5.2", "gpt-5.2-codex"]

    @patch("requests.get")
    def test_fetch_chatgpt_models_api_error(self, mock_get):
        """Test fetch falls back to defaults on API error."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        models = fetch_chatgpt_models("test_token", "test_account")

        assert models is not None
        assert len(models) > 0  # Should return default models

    @patch("requests.get")
    def test_fetch_chatgpt_models_timeout(self, mock_get):
        """Test fetch handles timeout gracefully."""
        mock_get.side_effect = requests.Timeout("Timeout")

        models = fetch_chatgpt_models("test_token", "test_account")

        assert models is not None
        assert len(models) > 0  # Should return default models

    @patch("requests.get")
    def test_fetch_chatgpt_models_network_error(self, mock_get):
        """Test fetch handles network errors."""
        mock_get.side_effect = requests.ConnectionError("Network error")

        models = fetch_chatgpt_models("test_token", "test_account")

        assert models is not None
        assert len(models) > 0  # Should return default models


# ============================================================================
# Custom Commands Tests
# ============================================================================


class TestCustomCommands:
    """Test ChatGPT OAuth custom commands."""

    def test_custom_help(self):
        """Test custom command help is returned."""
        help_items = _custom_help()

        assert isinstance(help_items, list)
        assert len(help_items) >= 3

        # Check expected commands
        commands = {item[0] for item in help_items}
        assert "chatgpt-auth" in commands
        assert "chatgpt-status" in commands
        assert "chatgpt-logout" in commands

    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_info")
    def test_handle_chatgpt_status_authenticated(
        self, mock_info, mock_success, mock_load
    ):
        """Test status shows authenticated when tokens exist."""
        mock_load.return_value = {
            "access_token": "test_token",
            "api_key": "test_api_key",
        }

        with patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_chatgpt_models"
        ) as mock_models:
            mock_models.return_value = {}
            _handle_chatgpt_status()

        mock_success.assert_called()
        success_call = mock_success.call_args[0][0]
        assert "Authenticated" in success_call

    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning")
    def test_handle_chatgpt_status_not_authenticated(self, mock_warning, mock_load):
        """Test status shows not authenticated when no tokens."""
        mock_load.return_value = None

        _handle_chatgpt_status()

        mock_warning.assert_called()
        warning_call = mock_warning.call_args[0][0]
        assert "Not authenticated" in warning_call

    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.remove_chatgpt_models")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.get_token_storage_path")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success")
    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_info")
    def test_handle_chatgpt_logout(
        self, mock_info, mock_success, mock_path, mock_remove
    ):
        """Test logout removes tokens and models."""
        token_file = Mock()
        token_file.exists.return_value = True
        mock_path.return_value = token_file
        mock_remove.return_value = 2  # Removed 2 models

        with patch.dict(os.environ, {"CHATGPT_OAUTH_API_KEY": "test_key"}):
            _handle_chatgpt_logout()

        token_file.unlink.assert_called_once()
        mock_info.assert_called()
        mock_success.assert_called()

    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.run_oauth_flow")
    @patch(
        "code_puppy.plugins.chatgpt_oauth.register_callbacks.set_model_and_reload_agent"
    )
    def test_handle_custom_command_auth(self, mock_set_model, mock_oauth):
        """Test chatgpt-auth command triggers OAuth flow."""
        result = _handle_custom_command("custom_command", "chatgpt-auth")

        assert result is True
        mock_oauth.assert_called_once()
        mock_set_model.assert_called_once_with("chatgpt-gpt-5.3-codex")

    @patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens")
    def test_handle_custom_command_status(self, mock_load):
        """Test chatgpt-status command returns True."""
        mock_load.return_value = {"access_token": "token"}

        with patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_chatgpt_models"
        ):
            with patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"
            ):
                result = _handle_custom_command("custom_command", "chatgpt-status")

        assert result is True

    def test_handle_custom_command_logout(self):
        """Test chatgpt-logout command returns True."""
        with patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_token_storage_path"
        ) as mock_path:
            mock_path.return_value = Mock(exists=Mock(return_value=False))
            with patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.remove_chatgpt_models"
            ):
                with patch(
                    "code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"
                ):
                    result = _handle_custom_command("custom_command", "chatgpt-logout")

        assert result is True

    def test_handle_custom_command_unknown(self):
        """Test unknown command returns None."""
        result = _handle_custom_command("custom_command", "unknown-command")
        assert result is None

    def test_handle_custom_command_empty_name(self):
        """Test empty command name returns None."""
        result = _handle_custom_command("custom_command", "")
        assert result is None


# ============================================================================
# Configuration Tests
# ============================================================================


class TestConfiguration:
    """Test plugin configuration paths and constants."""

    def test_chatgpt_oauth_config_structure(self):
        """Test OAuth config has all required fields."""
        required_fields = [
            "issuer",
            "auth_url",
            "token_url",
            "client_id",
            "scope",
            "redirect_host",
            "redirect_path",
            "required_port",
        ]

        for field in required_fields:
            assert field in CHATGPT_OAUTH_CONFIG
            assert CHATGPT_OAUTH_CONFIG[field]  # Should not be empty

    def test_required_port_constant(self):
        """Test required port matches config."""
        assert CHATGPT_OAUTH_CONFIG["required_port"] == 1455

    @patch("code_puppy.plugins.chatgpt_oauth.config.Path.mkdir")
    @patch("code_puppy.plugins.chatgpt_oauth.config.Path.exists", return_value=False)
    def test_get_token_storage_path(self, mock_exists, mock_mkdir):
        """Test token storage path is created correctly."""
        path = get_token_storage_path()

        assert path is not None
        assert "chatgpt_oauth.json" in str(path)

    @patch("code_puppy.plugins.chatgpt_oauth.config.Path.mkdir")
    def test_get_config_dir(self, mock_mkdir):
        """Test config directory is handled correctly."""
        from pathlib import Path

        config_dir = get_config_dir()

        assert config_dir is not None
        assert isinstance(config_dir, Path)

    @patch("code_puppy.plugins.chatgpt_oauth.config.Path.mkdir")
    def test_get_chatgpt_models_path(self, mock_mkdir):
        """Test models file path is created correctly."""
        path = get_chatgpt_models_path()

        assert path is not None
        assert "chatgpt_models.json" in str(path)
