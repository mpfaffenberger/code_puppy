"""Coverage tests for OAuth & auth modules.

Covers:
- claude_code_oauth/config.py (get_claude_models_path)
- chatgpt_oauth/test_plugin.py (in-source tests)
- claude_code_oauth/test_plugin.py (in-source tests)
"""

from __future__ import annotations

from unittest.mock import patch

from code_puppy.plugins.claude_code_oauth.config import (
    get_claude_models_path,
    get_config_dir,
)
from code_puppy.plugins.claude_code_oauth.config import (
    get_token_storage_path as get_claude_token_storage_path,
)


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
