"""Tests for the GitHub Models OAuth plugin."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.github_models_oauth import config, utils
from code_puppy.plugins.github_models_oauth.device_flow import (
    DeviceFlowResponse,
    poll_for_access_token,
    start_device_flow,
)


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


class TestConfig:
    """Test configuration helpers."""

    def test_config_has_required_keys(self):
        assert "device_code_url" in config.GITHUB_MODELS_OAUTH_CONFIG
        assert "access_token_url" in config.GITHUB_MODELS_OAUTH_CONFIG
        assert "api_base_url" in config.GITHUB_MODELS_OAUTH_CONFIG
        assert "prefix" in config.GITHUB_MODELS_OAUTH_CONFIG
        assert "scope" in config.GITHUB_MODELS_OAUTH_CONFIG

    def test_config_values(self):
        cfg = config.GITHUB_MODELS_OAUTH_CONFIG
        assert cfg["device_code_url"] == "https://github.com/login/device/code"
        assert cfg["access_token_url"] == "https://github.com/login/oauth/access_token"
        assert cfg["api_base_url"] == "https://models.github.ai/inference"
        assert cfg["prefix"] == "github-"
        assert cfg["scope"] == "read:user"

    def test_token_storage_path(self):
        token_path = config.get_token_storage_path()
        assert token_path.name == "github_models_oauth.json"
        assert "code_puppy" in str(token_path)

    def test_github_models_path(self):
        models_path = config.get_github_models_path()
        assert models_path.name == "github_models.json"
        assert "code_puppy" in str(models_path)

    def test_get_client_id_default_is_empty(self):
        with patch.dict(os.environ, {}, clear=False):
            env = dict(os.environ)
            env.pop("GITHUB_MODELS_CLIENT_ID", None)
            with patch.dict(os.environ, env, clear=True):
                client_id = config.get_client_id()
                assert client_id == ""

    def test_get_client_id_from_env(self):
        with patch.dict(os.environ, {"GITHUB_MODELS_CLIENT_ID": "custom_id_123"}):
            client_id = config.get_client_id()
            assert client_id == "custom_id_123"


# ---------------------------------------------------------------------------
# utils.py tests
# ---------------------------------------------------------------------------


class TestGhCliToken:
    """Test gh CLI token detection."""

    def test_get_gh_cli_token_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "gho_abc123_from_cli\n"

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.subprocess.run",
            return_value=mock_result,
        ):
            token = utils.get_gh_cli_token()
            assert token == "gho_abc123_from_cli"

    def test_get_gh_cli_token_not_installed(self):
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            token = utils.get_gh_cli_token()
            assert token is None

    def test_get_gh_cli_token_not_logged_in(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.subprocess.run",
            return_value=mock_result,
        ):
            token = utils.get_gh_cli_token()
            assert token is None

    def test_get_gh_cli_token_empty_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.subprocess.run",
            return_value=mock_result,
        ):
            token = utils.get_gh_cli_token()
            assert token is None


class TestEnvToken:
    """Test GITHUB_TOKEN / GH_TOKEN env var detection."""

    def test_get_env_token_github_token(self):
        with patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_abc123"}, clear=False):
            token = utils.get_env_token()
            assert token == "ghp_abc123"

    def test_get_env_token_gh_token(self):
        env = dict(os.environ)
        env.pop("GITHUB_TOKEN", None)
        env["GH_TOKEN"] = "ghp_from_gh"
        with patch.dict(os.environ, env, clear=True):
            token = utils.get_env_token()
            assert token == "ghp_from_gh"

    def test_get_env_token_prefers_github_token(self):
        with patch.dict(
            os.environ,
            {"GITHUB_TOKEN": "ghp_first", "GH_TOKEN": "ghp_second"},
            clear=False,
        ):
            token = utils.get_env_token()
            assert token == "ghp_first"

    def test_get_env_token_returns_none_when_unset(self):
        env = dict(os.environ)
        env.pop("GITHUB_TOKEN", None)
        env.pop("GH_TOKEN", None)
        with patch.dict(os.environ, env, clear=True):
            token = utils.get_env_token()
            assert token is None

    def test_get_env_token_ignores_empty(self):
        with patch.dict(
            os.environ, {"GITHUB_TOKEN": "", "GH_TOKEN": ""}, clear=False
        ):
            # Remove any pre-existing values
            env = dict(os.environ)
            env["GITHUB_TOKEN"] = ""
            env["GH_TOKEN"] = ""
            with patch.dict(os.environ, env, clear=True):
                token = utils.get_env_token()
                assert token is None



class TestPromptForToken:
    """Test interactive PAT prompt."""

    def test_prompt_returns_valid_token(self):
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.getpass.getpass",
            return_value="ghp_validtoken123",
        ):
            token = utils.prompt_for_token()
            assert token == "ghp_validtoken123"

    def test_prompt_returns_none_on_empty(self):
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.getpass.getpass",
            return_value="",
        ):
            token = utils.prompt_for_token()
            assert token is None

    def test_prompt_returns_none_on_keyboard_interrupt(self):
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.getpass.getpass",
            side_effect=KeyboardInterrupt,
        ):
            token = utils.prompt_for_token()
            assert token is None


class TestTokenPersistence:
    """Test token save/load operations."""

    def test_save_and_load_tokens(self, tmp_path):
        token_file = tmp_path / "github_models_oauth.json"
        tokens = {"access_token": "gho_test123", "username": "testuser"}

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            assert utils.save_tokens(tokens) is True
            loaded = utils.load_stored_tokens()
            assert loaded is not None
            assert loaded["access_token"] == "gho_test123"
            assert loaded["username"] == "testuser"

    def test_save_tokens_rejects_none(self):
        with pytest.raises(TypeError, match="cannot be None"):
            utils.save_tokens(None)

    def test_load_tokens_returns_none_when_missing(self, tmp_path):
        token_file = tmp_path / "nonexistent.json"
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            assert utils.load_stored_tokens() is None

    def test_save_tokens_sets_permissions(self, tmp_path):
        token_file = tmp_path / "github_models_oauth.json"
        tokens = {"access_token": "gho_test"}

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_token_storage_path",
            return_value=token_file,
        ):
            utils.save_tokens(tokens)
            # Check file permissions (owner read/write only)
            mode = oct(token_file.stat().st_mode)[-3:]
            assert mode == "600"


class TestGitHubUsername:
    """Test GitHub user API calls."""

    def test_get_username_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "octocat", "name": "Octo Cat"}

        with patch("code_puppy.plugins.github_models_oauth.utils.requests.get", return_value=mock_response):
            username = utils.get_github_username("gho_test")
            assert username == "octocat"

    def test_get_username_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("code_puppy.plugins.github_models_oauth.utils.requests.get", return_value=mock_response):
            username = utils.get_github_username("bad_token")
            assert username is None


class TestModelConfig:
    """Test model configuration management."""

    def test_add_and_load_models(self, tmp_path):
        models_file = tmp_path / "github_models.json"

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_github_models_path",
            return_value=models_file,
        ):
            result = utils.add_models_to_config(["openai/gpt-4.1", "meta/llama-4-scout"])
            assert result is True

            config_data = utils.load_github_models_config()
            assert "github-openai-gpt-4.1" in config_data
            assert "github-meta-llama-4-scout" in config_data
            assert config_data["github-openai-gpt-4.1"]["type"] == "github_models"
            assert config_data["github-openai-gpt-4.1"]["name"] == "openai/gpt-4.1"
            assert config_data["github-openai-gpt-4.1"]["oauth_source"] == "github-models-plugin"

    def test_remove_models(self, tmp_path):
        models_file = tmp_path / "github_models.json"

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_github_models_path",
            return_value=models_file,
        ):
            utils.add_models_to_config(["openai/gpt-4.1"])
            removed = utils.remove_github_models()
            assert removed == 1

            config_data = utils.load_github_models_config()
            assert len(config_data) == 0

    def test_load_empty_config(self, tmp_path):
        models_file = tmp_path / "nonexistent.json"
        with patch(
            "code_puppy.plugins.github_models_oauth.utils.get_github_models_path",
            return_value=models_file,
        ):
            assert utils.load_github_models_config() == {}


class TestFetchModels:
    """Test model catalog fetching."""

    def test_fetch_models_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"id": "openai/gpt-4.1"},
            {"id": "meta/llama-4-scout"},
        ]

        with patch("code_puppy.plugins.github_models_oauth.utils.requests.get", return_value=mock_response):
            models = utils.fetch_github_models("gho_test")
            assert "openai/gpt-4.1" in models
            assert "meta/llama-4-scout" in models

    def test_fetch_models_fallback_on_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("code_puppy.plugins.github_models_oauth.utils.requests.get", return_value=mock_response):
            models = utils.fetch_github_models("gho_test")
            assert models == utils.DEFAULT_GITHUB_MODELS

    def test_fetch_models_fallback_on_timeout(self):
        import requests as req_lib

        with patch(
            "code_puppy.plugins.github_models_oauth.utils.requests.get",
            side_effect=req_lib.exceptions.Timeout("timed out"),
        ):
            models = utils.fetch_github_models("gho_test")
            assert models == utils.DEFAULT_GITHUB_MODELS


# ---------------------------------------------------------------------------
# device_flow.py tests
# ---------------------------------------------------------------------------


class TestDeviceFlow:
    """Test the GitHub OAuth device flow."""

    def test_start_device_flow_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "device_code": "dc_abc123",
            "user_code": "ABCD-1234",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }

        with patch("code_puppy.plugins.github_models_oauth.device_flow.requests.post", return_value=mock_response):
            result = start_device_flow()
            assert result is not None
            assert result.device_code == "dc_abc123"
            assert result.user_code == "ABCD-1234"
            assert result.verification_uri == "https://github.com/login/device"
            assert result.interval == 5

    def test_start_device_flow_network_error(self):
        import requests as req_lib

        with patch(
            "code_puppy.plugins.github_models_oauth.device_flow.requests.post",
            side_effect=req_lib.exceptions.ConnectionError("no network"),
        ):
            result = start_device_flow()
            assert result is None

    def test_poll_success_immediate(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "gho_success_token"}

        with patch("code_puppy.plugins.github_models_oauth.device_flow.requests.post", return_value=mock_response):
            with patch("code_puppy.plugins.github_models_oauth.device_flow.time.sleep"):
                token = poll_for_access_token("dc_test", interval=1)
                assert token == "gho_success_token"

    def test_poll_handles_authorization_pending(self):
        pending_response = MagicMock()
        pending_response.json.return_value = {"error": "authorization_pending"}

        success_response = MagicMock()
        success_response.json.return_value = {"access_token": "gho_after_wait"}

        with patch(
            "code_puppy.plugins.github_models_oauth.device_flow.requests.post",
            side_effect=[pending_response, pending_response, success_response],
        ):
            with patch("code_puppy.plugins.github_models_oauth.device_flow.time.sleep"):
                token = poll_for_access_token("dc_test", interval=1)
                assert token == "gho_after_wait"

    def test_poll_handles_slow_down(self):
        slow_response = MagicMock()
        slow_response.json.return_value = {"error": "slow_down", "interval": 10}

        success_response = MagicMock()
        success_response.json.return_value = {"access_token": "gho_slowed"}

        with patch(
            "code_puppy.plugins.github_models_oauth.device_flow.requests.post",
            side_effect=[slow_response, success_response],
        ):
            with patch("code_puppy.plugins.github_models_oauth.device_flow.time.sleep"):
                token = poll_for_access_token("dc_test", interval=1)
                assert token == "gho_slowed"

    def test_poll_handles_expired_token(self):
        expired_response = MagicMock()
        expired_response.json.return_value = {"error": "expired_token"}

        with patch(
            "code_puppy.plugins.github_models_oauth.device_flow.requests.post",
            return_value=expired_response,
        ):
            with patch("code_puppy.plugins.github_models_oauth.device_flow.time.sleep"):
                token = poll_for_access_token("dc_test", interval=1)
                assert token is None

    def test_poll_handles_unknown_error(self):
        error_response = MagicMock()
        error_response.json.return_value = {
            "error": "access_denied",
            "error_description": "User denied access",
        }

        with patch(
            "code_puppy.plugins.github_models_oauth.device_flow.requests.post",
            return_value=error_response,
        ):
            with patch("code_puppy.plugins.github_models_oauth.device_flow.time.sleep"):
                token = poll_for_access_token("dc_test", interval=1)
                assert token is None


# ---------------------------------------------------------------------------
# register_callbacks.py tests
# ---------------------------------------------------------------------------


class TestCustomCommands:
    """Test slash command routing."""

    def test_github_auth_returns_true(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.github_models_oauth.register_callbacks._handle_auth"
        ):
            with patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.set_model_and_reload_agent"
            ):
                result = _handle_custom_command("/github-auth", "github-auth")
                assert result is True

    def test_github_status_returns_true(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.github_models_oauth.register_callbacks._handle_status"
        ):
            result = _handle_custom_command("/github-status", "github-status")
            assert result is True

    def test_github_logout_returns_true(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.github_models_oauth.register_callbacks._handle_logout"
        ):
            result = _handle_custom_command("/github-logout", "github-logout")
            assert result is True

    def test_unknown_command_returns_none(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("/something-else", "something-else")
        assert result is None

    def test_empty_name_returns_none(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("", "")
        assert result is None


class TestModelTypeHandler:
    """Test the model type registration."""

    def test_register_returns_github_models_type(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _register_model_types,
        )

        result = _register_model_types()
        assert len(result) == 2
        types = {r["type"] for r in result}
        assert "github_models" in types
        assert "github_copilot" in types
        for r in result:
            assert callable(r["handler"])

    def test_model_handler_returns_none_without_token(self, tmp_path):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _create_github_models_model,
        )

        token_file = tmp_path / "no_tokens.json"
        with patch(
            "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
            return_value=None,
        ):
            model = _create_github_models_model(
                "github-openai-gpt-4.1",
                {"name": "openai/gpt-4.1", "custom_endpoint": {"url": "https://models.github.ai/inference"}},
                {},
            )
            assert model is None


class TestCustomHelp:
    """Test the help entries."""

    def test_help_entries(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _custom_help,
        )

        entries = _custom_help()
        names = [e[0] for e in entries]
        assert "github-auth" in names
        assert "github-status" in names
        assert "github-logout" in names


class TestAuthFlow:
    """Test the multi-auth _handle_auth flow."""

    def test_auth_uses_gh_cli_token_when_available(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value="gho_from_cli",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_github_username",
                return_value="octocat",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
                return_value=True,
            ) as mock_save,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_github_models",
                return_value=["openai/gpt-4.1"],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_models_to_config",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.run_device_flow"
            ) as mock_device_flow,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_copilot_models",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_copilot_models_to_config",
                return_value=True,
            ),
        ):
            _handle_auth()
            mock_device_flow.assert_not_called()
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert saved_data["access_token"] == "gho_from_cli"
            assert saved_data["username"] == "octocat"

    def test_auth_uses_env_token_when_gh_cli_unavailable(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_env_token",
                return_value="ghp_from_env",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_github_username",
                return_value="envuser",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
                return_value=True,
            ) as mock_save,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_github_models",
                return_value=["openai/gpt-4.1"],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_models_to_config",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.prompt_for_token",
            ) as mock_prompt,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_copilot_models",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_copilot_models_to_config",
                return_value=True,
            ),
        ):
            _handle_auth()
            mock_prompt.assert_not_called()
            saved_data = mock_save.call_args[0][0]
            assert saved_data["access_token"] == "ghp_from_env"

    def test_auth_prompts_for_pat_when_auto_methods_fail(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_env_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.prompt_for_token",
                return_value="ghp_pasted",
            ) as mock_prompt,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_github_username",
                return_value="pasteuser",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_github_models",
                return_value=["openai/gpt-4.1"],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_models_to_config",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_copilot_models",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_copilot_models_to_config",
                return_value=True,
            ),
        ):
            _handle_auth()
            mock_prompt.assert_called_once()

    def test_auth_falls_back_to_device_flow(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_env_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.prompt_for_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_client_id",
                return_value="Iv1.real_client_id",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.run_device_flow",
                return_value="gho_from_device_flow",
            ) as mock_device_flow,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_github_username",
                return_value="devuser",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_github_models",
                return_value=["openai/gpt-4.1"],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_models_to_config",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.fetch_copilot_models",
                return_value=[],
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.add_copilot_models_to_config",
                return_value=True,
            ),
        ):
            _handle_auth()
            mock_device_flow.assert_called_once()

    def test_auth_shows_error_when_all_methods_fail(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_env_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.prompt_for_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_client_id",
                return_value="",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.emit_error",
            ) as mock_emit_error,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
            ) as mock_save,
        ):
            _handle_auth()
            mock_emit_error.assert_called()
            error_msg = mock_emit_error.call_args[0][0]
            assert "Authentication failed" in error_msg
            mock_save.assert_not_called()

    def test_auth_rejects_invalid_token(self):
        from code_puppy.plugins.github_models_oauth.register_callbacks import (
            _handle_auth,
        )

        with (
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_gh_cli_token",
                return_value="bad_token",
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.get_github_username",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.emit_error",
            ) as mock_emit_error,
            patch(
                "code_puppy.plugins.github_models_oauth.register_callbacks.save_tokens",
            ) as mock_save,
        ):
            _handle_auth()
            mock_emit_error.assert_called()
            error_msg = mock_emit_error.call_args[0][0]
            assert "Token validation failed" in error_msg
            mock_save.assert_not_called()
