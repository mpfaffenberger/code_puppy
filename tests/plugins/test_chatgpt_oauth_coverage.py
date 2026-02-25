"""Tests for chatgpt_oauth/register_callbacks.py full coverage."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestChatgptCustomHelp:
    def test_returns_entries(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import _custom_help

        entries = _custom_help()
        names = [n for n, _ in entries]
        assert "chatgpt-auth" in names
        assert "chatgpt-status" in names
        assert "chatgpt-logout" in names


class TestHandleChatgptStatus:
    def test_authenticated_with_key(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_chatgpt_status,
        )

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at", "api_key": "key123"},
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_chatgpt_models",
                return_value={"chatgpt-gpt5": {"oauth_source": "chatgpt-oauth-plugin"}},
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_info"),
        ):
            _handle_chatgpt_status()

    def test_authenticated_no_key(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_chatgpt_status,
        )

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_chatgpt_models",
                return_value={},
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"),
        ):
            _handle_chatgpt_status()

    def test_not_authenticated(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_chatgpt_status,
        )

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_info"),
        ):
            _handle_chatgpt_status()


class TestHandleChatgptLogout:
    def test_full_logout(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_chatgpt_logout,
        )

        mock_path = MagicMock()
        mock_path.exists.return_value = True

        # Set the env var so deletion branch runs
        env_var = "CHATGPT_OAUTH_API_KEY"  # from config

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.CHATGPT_OAUTH_CONFIG",
                {"api_key_env_var": env_var},
            ),
            patch.dict(os.environ, {env_var: "value"}),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.remove_chatgpt_models",
                return_value=2,
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"),
        ):
            _handle_chatgpt_logout()
            assert env_var not in os.environ

    def test_logout_nothing(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_chatgpt_logout,
        )

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.CHATGPT_OAUTH_CONFIG",
                {"api_key_env_var": "NOT_SET_VAR"},
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.remove_chatgpt_models",
                return_value=0,
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_success"),
        ):
            _handle_chatgpt_logout()


class TestHandleCustomCommand:
    def test_empty_name(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "") is None

    def test_unknown(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "unknown") is None

    def test_auth(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.run_oauth_flow"),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.set_model_and_reload_agent"
            ),
        ):
            assert _handle_custom_command("/chatgpt-auth", "chatgpt-auth") is True

    def test_status(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks._handle_chatgpt_status"
        ):
            assert _handle_custom_command("/chatgpt-status", "chatgpt-status") is True

    def test_logout(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.chatgpt_oauth.register_callbacks._handle_chatgpt_logout"
        ):
            assert _handle_custom_command("/chatgpt-logout", "chatgpt-logout") is True


class TestCreateChatgptOauthModel:
    def test_no_access_token(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _create_chatgpt_oauth_model,
        )

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_valid_access_token",
                return_value=None,
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"),
        ):
            assert _create_chatgpt_oauth_model("m", {"name": "m"}, {}) is None

    def test_no_account_id(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _create_chatgpt_oauth_model,
        )

        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_valid_access_token",
                return_value="token",
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                return_value={},
            ),
            patch("code_puppy.plugins.chatgpt_oauth.register_callbacks.emit_warning"),
        ):
            assert _create_chatgpt_oauth_model("m", {"name": "m"}, {}) is None

    def test_success(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _create_chatgpt_oauth_model,
        )

        mock_model = MagicMock()
        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.get_valid_access_token",
                return_value="token",
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.load_stored_tokens",
                return_value={"account_id": "acc123"},
            ),
            patch(
                "code_puppy.plugins.chatgpt_oauth.register_callbacks.CHATGPT_OAUTH_CONFIG",
                {
                    "originator": "codex_cli_rs",
                    "client_version": "0.72.0",
                    "api_base_url": "https://api.example.com",
                },
            ),
            patch(
                "code_puppy.http_utils.get_cert_bundle_path",
                return_value=None,
            ),
            patch("code_puppy.chatgpt_codex_client.create_codex_async_client"),
            patch("pydantic_ai.providers.openai.OpenAIProvider"),
            patch(
                "pydantic_ai.models.openai.OpenAIResponsesModel",
                return_value=mock_model,
            ),
        ):
            result = _create_chatgpt_oauth_model(
                "m",
                {"name": "m", "custom_endpoint": {"headers": {"X-Custom": "val"}}},
                {},
            )
            assert result is mock_model


class TestRegisterModelTypes:
    def test_returns_handler(self):
        from code_puppy.plugins.chatgpt_oauth.register_callbacks import (
            _register_model_types,
        )

        types = _register_model_types()
        assert len(types) == 1
        assert types[0]["type"] == "chatgpt_oauth"
