"""Coverage tests for OAuth & auth modules (code_puppy-0yx).

Covers:
- antigravity_oauth/token.py (TokenRefreshError, refresh_access_token)
- antigravity_oauth/config.py (path helpers)
- claude_code_oauth/config.py (get_claude_models_path)
- antigravity_oauth/test_plugin.py (in-source tests)
- chatgpt_oauth/test_plugin.py (in-source tests)
- claude_code_oauth/test_plugin.py (in-source tests)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.antigravity_oauth.config import (
    get_accounts_storage_path,
    get_antigravity_models_path,
    get_token_storage_path,
)
from code_puppy.plugins.antigravity_oauth.token import (
    OAuthTokens,
    TokenRefreshError,
    refresh_access_token,
)
from code_puppy.plugins.claude_code_oauth.config import (
    get_claude_models_path,
    get_config_dir,
)
from code_puppy.plugins.claude_code_oauth.config import (
    get_token_storage_path as get_claude_token_storage_path,
)


class TestTokenRefreshError:
    """Cover TokenRefreshError.__init__ (lines 48-50)."""

    def test_basic(self):
        err = TokenRefreshError("boom")
        assert str(err) == "boom"
        assert err.code is None
        assert err.status is None

    def test_with_code_and_status(self):
        err = TokenRefreshError("revoked", code="invalid_grant", status=400)
        assert err.code == "invalid_grant"
        assert err.status == 400


class TestRefreshAccessToken:
    """Cover refresh_access_token (lines 99-167)."""

    def test_empty_refresh_token_returns_none(self):
        assert refresh_access_token("") is None

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_success(self, mock_post):
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {
            "access_token": "new_access",
            "expires_in": 3600,
            "refresh_token": "new_refresh",
        }
        mock_post.return_value = resp

        result = refresh_access_token("old_refresh|proj|managed")
        assert isinstance(result, OAuthTokens)
        assert result.access_token == "new_access"
        assert "new_refresh" in result.refresh_token
        assert "proj" in result.refresh_token
        assert "managed" in result.refresh_token

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_success_no_new_refresh(self, mock_post):
        """When response has no refresh_token, reuse the old one."""
        resp = MagicMock()
        resp.ok = True
        resp.json.return_value = {"access_token": "a", "expires_in": 100}
        mock_post.return_value = resp

        result = refresh_access_token("keep_me")
        assert result is not None
        assert "keep_me" in result.refresh_token

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_invalid_grant_raises(self, mock_post):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 400
        resp.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token revoked",
        }
        mock_post.return_value = resp

        with pytest.raises(TokenRefreshError) as exc_info:
            refresh_access_token("bad_token")
        assert exc_info.value.code == "invalid_grant"
        assert exc_info.value.status == 400

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_non_grant_error_returns_none(self, mock_post):
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 500
        resp.text = "server error"
        resp.json.return_value = {"error": "server_error", "error_description": "oops"}
        mock_post.return_value = resp

        assert refresh_access_token("tok") is None

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_error_json_parse_failure(self, mock_post):
        """Cover the except branch when error response isn't valid JSON."""
        resp = MagicMock()
        resp.ok = False
        resp.status_code = 502
        resp.text = "bad gateway"
        resp.json.side_effect = ValueError("no json")
        mock_post.return_value = resp

        assert refresh_access_token("tok") is None

    @patch("code_puppy.plugins.antigravity_oauth.token.requests.post")
    def test_network_exception_returns_none(self, mock_post):
        mock_post.side_effect = ConnectionError("offline")
        assert refresh_access_token("tok") is None


# ---------------------------------------------------------------------------
# 2. antigravity_oauth/config.py — path helpers (lines 26-42)
# ---------------------------------------------------------------------------


class TestAntigravityConfigPaths:
    @patch("code_puppy.plugins.antigravity_oauth.config.config")
    def test_get_token_storage_path(self, mock_cfg, tmp_path):
        mock_cfg.DATA_DIR = str(tmp_path)
        p = get_token_storage_path()
        assert p.name == "antigravity_oauth.json"
        assert p.parent == tmp_path

    @patch("code_puppy.plugins.antigravity_oauth.config.config")
    def test_get_accounts_storage_path(self, mock_cfg, tmp_path):
        mock_cfg.DATA_DIR = str(tmp_path)
        p = get_accounts_storage_path()
        assert p.name == "antigravity_accounts.json"

    @patch("code_puppy.plugins.antigravity_oauth.config.config")
    def test_get_antigravity_models_path(self, mock_cfg, tmp_path):
        mock_cfg.DATA_DIR = str(tmp_path)
        p = get_antigravity_models_path()
        assert p.name == "antigravity_models.json"


# ---------------------------------------------------------------------------
# 3. claude_code_oauth/config.py — get_claude_models_path (lines 43-45)
# ---------------------------------------------------------------------------


class TestClaudeCodeConfigPaths:
    @patch("code_puppy.plugins.claude_code_oauth.config.config")
    def test_get_claude_models_path(self, mock_cfg, tmp_path):
        mock_cfg.DATA_DIR = str(tmp_path)
        p = get_claude_models_path()
        assert p.name == "claude_models.json"
        assert p.parent == tmp_path

    @patch("code_puppy.plugins.claude_code_oauth.config.config")
    def test_get_config_dir(self, mock_cfg, tmp_path):
        mock_cfg.CONFIG_DIR = str(tmp_path)
        p = get_config_dir()
        assert p == tmp_path

    @patch("code_puppy.plugins.claude_code_oauth.config.config")
    def test_get_token_storage_path(self, mock_cfg, tmp_path):
        mock_cfg.DATA_DIR = str(tmp_path)
        p = get_claude_token_storage_path()
        assert p.name == "claude_code_oauth.json"
        assert p.parent == tmp_path


# ---------------------------------------------------------------------------
# 4-6. In-source test_plugin.py modules — import to get coverage
# ---------------------------------------------------------------------------


class TestAntigravityTestPlugin:
    """Exercise antigravity_oauth/test_plugin.py by importing its test classes."""

    def test_pkce(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestPKCE

        t = TestPKCE()
        t.test_code_verifier_length()
        t.test_code_challenge_is_sha256()
        t.test_different_verifiers_produce_different_challenges()
        t.test_prepare_oauth_context()

    def test_state_encoding(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestStateEncoding

        t = TestStateEncoding()
        t.test_encode_decode_roundtrip()
        t.test_encode_without_project_id()
        t.test_decode_invalid_state_raises()

    def test_refresh_parts(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestRefreshParts

        t = TestRefreshParts()
        t.test_parse_simple_token()
        t.test_parse_with_project_id()
        t.test_parse_with_managed_project()
        t.test_parse_empty_string()
        t.test_format_roundtrip()

    def test_token_expiry(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestTokenExpiry

        t = TestTokenExpiry()
        t.test_none_expires_is_expired()
        t.test_past_time_is_expired()
        t.test_future_time_not_expired()
        t.test_expiry_buffer()

    def test_storage_migration(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import (
            TestStorageMigration,
        )

        t = TestStorageMigration()
        t.test_migrate_v1_to_v2()
        t.test_migrate_v2_to_v3()

    def test_account_manager(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestAccountManager

        t = TestAccountManager()
        t.test_empty_manager()
        t.test_add_account()
        t.test_get_current_for_family()
        t.test_rate_limit_switches_account()
        t.test_min_wait_time_calculation()
        t.test_gemini_dual_quota()

    def test_constants(self):
        from code_puppy.plugins.antigravity_oauth.test_plugin import TestConstants

        t = TestConstants()
        t.test_models_have_required_fields()
        t.test_thinking_models_have_budget()
        t.test_scopes_are_valid()
        t.test_config_has_required_fields()


class TestChatgptTestPlugin:
    """Exercise chatgpt_oauth/test_plugin.py."""

    def test_config_paths(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import test_config_paths

        test_config_paths()

    def test_oauth_config(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import test_oauth_config

        test_oauth_config()

    def test_jwt_parsing_with_nested_org(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_jwt_parsing_with_nested_org,
        )

        test_jwt_parsing_with_nested_org()

    def test_code_verifier_generation(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_code_verifier_generation,
        )

        test_code_verifier_generation()

    def test_code_challenge_computation(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_code_challenge_computation,
        )

        test_code_challenge_computation()

    def test_prepare_oauth_context(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_prepare_oauth_context,
        )

        test_prepare_oauth_context()

    def test_assign_redirect_uri(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_assign_redirect_uri,
        )

        test_assign_redirect_uri()

    def test_build_authorization_url(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_build_authorization_url,
        )

        test_build_authorization_url()

    def test_parse_jwt_claims(self):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import test_parse_jwt_claims

        test_parse_jwt_claims()

    def test_save_and_load_tokens(self, tmp_path):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_save_and_load_tokens,
        )

        test_save_and_load_tokens(tmp_path)

    def test_save_and_load_chatgpt_models(self, tmp_path):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_save_and_load_chatgpt_models,
        )

        test_save_and_load_chatgpt_models(tmp_path)

    def test_remove_chatgpt_models(self, tmp_path):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_remove_chatgpt_models,
        )

        test_remove_chatgpt_models(tmp_path)

    def test_exchange_code_for_tokens(self):
        """Delegate to the in-source test (it uses its own @patch decorator)."""
        from code_puppy.plugins.chatgpt_oauth import test_plugin

        # Call the underlying decorated function directly
        test_plugin.test_exchange_code_for_tokens()

    def test_fetch_chatgpt_models(self):
        from code_puppy.plugins.chatgpt_oauth import test_plugin

        test_plugin.test_fetch_chatgpt_models()

    def test_fetch_chatgpt_models_fallback(self):
        from code_puppy.plugins.chatgpt_oauth import test_plugin

        test_plugin.test_fetch_chatgpt_models_fallback()

    def test_add_models_to_chatgpt_config(self, tmp_path):
        from code_puppy.plugins.chatgpt_oauth.test_plugin import (
            test_add_models_to_chatgpt_config,
        )

        test_add_models_to_chatgpt_config(tmp_path)


class TestClaudeCodeTestPlugin:
    """Exercise claude_code_oauth/test_plugin.py."""

    def test_plugin_imports(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import (
            test_plugin_imports,
        )

        assert test_plugin_imports() is True

    def test_oauth_helpers(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import (
            test_oauth_helpers,
        )

        assert test_oauth_helpers() is True

    def test_file_operations(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import (
            test_file_operations,
        )

        assert test_file_operations() is True

    def test_command_handlers(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import (
            test_command_handlers,
        )

        assert test_command_handlers() is True

    def test_configuration(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import (
            test_configuration,
        )

        assert test_configuration() is True

    def test_main_all_pass(self):
        from code_puppy.plugins.claude_code_oauth.test_plugin import main

        assert main() is True
