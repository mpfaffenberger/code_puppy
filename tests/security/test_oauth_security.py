"""Security regression tests for OAuth token storage, log redaction, and callback validation."""

from __future__ import annotations

import json
import logging
import stat
from pathlib import Path
import threading
from unittest.mock import Mock, patch
from urllib.parse import urlparse

import pytest

from code_puppy.plugins.chatgpt_oauth.oauth_flow import (
    AuthBundle,
    TokenData,
    _CallbackHandler,
    _OAuthServer,
)
from code_puppy.plugins.chatgpt_oauth.utils import (
    exchange_code_for_tokens as chatgpt_exchange,
    load_stored_tokens as chatgpt_load_tokens,
    prepare_oauth_context as chatgpt_prepare_context,
    refresh_access_token as chatgpt_refresh,
    save_tokens as chatgpt_save_tokens,
)
from code_puppy.plugins.claude_code_oauth.register_callbacks import (
    _CallbackHandler as ClaudeCallbackHandler,
    _OAuthResult as ClaudeOAuthResult,
)
from code_puppy.plugins.claude_code_oauth.utils import (
    exchange_code_for_tokens as claude_exchange,
    prepare_oauth_context as claude_prepare_context,
    refresh_access_token as claude_refresh,
    save_claude_models,
)


class TestChatGPTTokenStorage:
    """ChatGPT token file must be private from creation and fixed on load."""

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_save_tokens_uses_private_atomic_write(self, mock_get_path, tmp_path: Path):
        token_file = tmp_path / "tokens.json"
        mock_get_path.return_value = token_file
        tokens = {"access_token": "secret", "refresh_token": "secret2"}
        assert chatgpt_save_tokens(tokens) is True
        assert token_file.exists()
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert not list(tmp_path.glob("*.tmp"))

    @patch("code_puppy.plugins.chatgpt_oauth.utils.get_token_storage_path")
    def test_load_tokens_warns_and_fixes_broad_mode(
        self, mock_get_path, tmp_path: Path, caplog
    ):
        token_file = tmp_path / "tokens.json"
        token_file.write_text(json.dumps({"access_token": "x"}))
        token_file.chmod(0o644)
        mock_get_path.return_value = token_file
        with caplog.at_level(logging.WARNING, logger="code_puppy.secret_storage"):
            result = chatgpt_load_tokens()
        assert result is not None
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert "mode 0644" in caplog.text


class TestChatGPTLogRedaction:
    """ChatGPT refresh/exchange must never log raw token-bearing bodies."""

    @patch("requests.post")
    def test_refresh_failure_does_not_log_token_body(self, mock_post, caplog):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"error":"invalid","access_token":"leaked"}'
        mock_response.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_response

        with patch(
            "code_puppy.plugins.chatgpt_oauth.utils.load_stored_tokens"
        ) as mock_load:
            mock_load.return_value = {"refresh_token": "rt"}
            with caplog.at_level(
                logging.ERROR, logger="code_puppy.plugins.chatgpt_oauth.utils"
            ):
                chatgpt_refresh()
        assert "leaked" not in caplog.text
        assert "status=401" in caplog.text

    @patch("requests.post")
    def test_exchange_failure_does_not_log_token_body(self, mock_post, caplog):
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = '{"error":"bad","access_token":"leaked"}'
        mock_response.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_response

        context = chatgpt_prepare_context()
        context.redirect_uri = "http://localhost:1455/callback"
        with caplog.at_level(
            logging.ERROR, logger="code_puppy.plugins.chatgpt_oauth.utils"
        ):
            chatgpt_exchange("code", context)
        assert "leaked" not in caplog.text
        assert "status=400" in caplog.text


class TestClaudeSecretStorage:
    """Claude files that may contain OAuth bearer tokens must be private."""

    @patch("code_puppy.plugins.claude_code_oauth.utils.get_claude_models_path")
    def test_save_claude_models_uses_private_atomic_write(
        self, mock_get_path, tmp_path: Path
    ):
        models_file = tmp_path / "claude_models.json"
        mock_get_path.return_value = models_file
        assert save_claude_models(
            {"claude-code-test": {"custom_endpoint": {"api_key": "secret"}}}
        )
        assert models_file.exists()
        assert stat.S_IMODE(models_file.stat().st_mode) == 0o600
        assert not list(tmp_path.glob("*.tmp"))


class TestClaudeLogRedaction:
    """Claude exchange/refresh non-JSON and failure logs must not emit raw bodies."""

    @patch("requests.post")
    def test_exchange_non_json_does_not_log_raw_body(self, mock_post, caplog):
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html>access_token=leaked</html>"
        mock_post.return_value = mock_response

        context = claude_prepare_context()
        context.redirect_uri = "http://localhost:8765/callback"
        with caplog.at_level(
            logging.ERROR, logger="code_puppy.plugins.claude_code_oauth.utils"
        ):
            claude_exchange("code", context)
        assert "leaked" not in caplog.text

    @patch("requests.post")
    def test_refresh_failure_does_not_log_token_body(self, mock_post, caplog):
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = '{"error":"invalid","access_token":"leaked"}'
        mock_response.headers = {"content-type": "application/json"}
        mock_post.return_value = mock_response

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.utils.load_stored_tokens"
            ) as mock_load,
            patch(
                "code_puppy.plugins.claude_code_oauth.utils.is_token_expired",
                return_value=True,
            ),
        ):
            mock_load.return_value = {"refresh_token": "rt"}
            with caplog.at_level(
                logging.ERROR, logger="code_puppy.plugins.claude_code_oauth.utils"
            ):
                claude_refresh()
        assert "leaked" not in caplog.text
        assert "status=401" in caplog.text


class TestClaudeCallbackSecurity:
    """Claude callback logging must not leak authorization code or state."""

    def test_callback_log_redacts_query(self, caplog):
        handler = ClaudeCallbackHandler.__new__(ClaudeCallbackHandler)
        handler.path = "/callback?code=secret_code&state=secret_state"
        handler.result = ClaudeOAuthResult()
        handler.received_event = threading.Event()

        with (
            patch.object(handler, "_write_response"),
            caplog.at_level(
                logging.INFO,
                logger="code_puppy.plugins.claude_code_oauth.register_callbacks",
            ),
        ):
            handler.do_GET()

        assert "secret_code" not in caplog.text
        assert "secret_state" not in caplog.text
        assert "code=" not in caplog.text
        assert "state=" not in caplog.text
        assert "/callback" in caplog.text


class TestChatGPTCallbackSecurity:
    """Callback must validate state and redirect without leaking secrets in the URL."""

    @pytest.fixture
    def _handler(self):
        server = Mock(spec=_OAuthServer)
        server.exit_code = 1
        server.exchange_code = Mock()
        server.context = Mock()
        server.context.state = "correct_state"
        server.verbose = False

        mock_request = Mock()
        mock_request.rfile = Mock()
        mock_request.rfile.readline = Mock(return_value=b"")
        with patch(
            "code_puppy.plugins.chatgpt_oauth.oauth_flow._CallbackHandler.handle_one_request"
        ):
            handler = _CallbackHandler(mock_request, ("127.0.0.1", 1455), server)
            handler.server = server
            handler.requestline = "GET / HTTP/1.1"
            return handler

    def test_rejects_missing_state(self, _handler):
        with (
            patch.object(_handler, "_send_failure") as mock_fail,
            patch.object(_handler, "_shutdown") as mock_shutdown,
        ):
            _handler.path = "/auth/callback?code=mycode"
            _handler.do_GET()
            mock_fail.assert_called_once_with(
                400, "Invalid state parameter — possible CSRF attack."
            )
            mock_shutdown.assert_called_once()

    def test_rejects_mismatched_state(self, _handler):
        with (
            patch.object(_handler, "_send_failure") as mock_fail,
            patch.object(_handler, "_shutdown") as mock_shutdown,
        ):
            _handler.path = "/auth/callback?code=mycode&state=wrong_state"
            _handler.do_GET()
            mock_fail.assert_called_once_with(
                400, "Invalid state parameter — possible CSRF attack."
            )
            mock_shutdown.assert_called_once()

    def test_valid_state_exchanges_code(self, _handler):
        _handler.server.exchange_code.return_value = AuthBundle(
            api_key="key",
            token_data=TokenData(
                id_token="id",
                access_token="at",
                refresh_token="rt",
                account_id="acc",
            ),
            last_refresh="2024-01-01T00:00:00Z",
        )
        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.oauth_flow.save_tokens",
                return_value=True,
            ),
            patch.object(_handler, "_send_redirect") as mock_redirect,
            patch.object(_handler, "_shutdown_after_delay") as mock_shutdown,
        ):
            _handler.path = "/auth/callback?code=mycode&state=correct_state"
            _handler.do_GET()
            _handler.server.exchange_code.assert_called_once_with("mycode")
            mock_redirect.assert_called_once_with("http://127.0.0.1:1455/success")
            assert _handler.server.exit_code == 0
            mock_shutdown.assert_called_once_with(2.0)

    def test_success_redirect_has_no_tokens(self, _handler):
        _handler.server.exchange_code.return_value = AuthBundle(
            api_key="key",
            token_data=TokenData(
                id_token="id",
                access_token="at",
                refresh_token="rt",
                account_id="acc",
            ),
            last_refresh="2024-01-01T00:00:00Z",
        )
        with (
            patch(
                "code_puppy.plugins.chatgpt_oauth.oauth_flow.save_tokens",
                return_value=True,
            ),
            patch.object(_handler, "_send_redirect") as mock_redirect,
            patch.object(_handler, "_shutdown_after_delay"),
        ):
            _handler.path = "/auth/callback?code=mycode&state=correct_state"
            _handler.do_GET()
            url = mock_redirect.call_args[0][0]
            parsed = urlparse(url)
            assert parsed.path == "/success"
            assert not parsed.query
            assert "code=" not in url
            assert "token" not in url.lower()
