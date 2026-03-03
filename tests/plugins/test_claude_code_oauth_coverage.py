"""Tests for claude_code_oauth/register_callbacks.py full coverage."""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from http.server import HTTPServer
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOAuthResult:
    def test_init(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _OAuthResult,
        )

        r = _OAuthResult()
        assert r.code is None
        assert r.state is None
        assert r.error is None


class TestCallbackHandler:
    def test_do_get_success(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _CallbackHandler,
            _OAuthResult,
        )

        result = _OAuthResult()
        event = threading.Event()
        _CallbackHandler.result = result
        _CallbackHandler.received_event = event

        handler = MagicMock(spec=_CallbackHandler)
        handler.path = "/callback?code=abc&state=xyz"
        handler.result = result
        handler.received_event = event
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        _CallbackHandler.do_GET(handler)
        assert result.code == "abc"
        assert result.state == "xyz"
        assert event.is_set()

    def test_do_get_missing_params(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _CallbackHandler,
            _OAuthResult,
        )

        result = _OAuthResult()
        event = threading.Event()
        _CallbackHandler.result = result
        _CallbackHandler.received_event = event

        handler = MagicMock(spec=_CallbackHandler)
        handler.path = "/callback?nope=1"
        handler.result = result
        handler.received_event = event
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        _CallbackHandler.do_GET(handler)
        assert result.error == "Missing code or state"

    def test_log_message_noop(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _CallbackHandler,
        )

        handler = MagicMock(spec=_CallbackHandler)
        _CallbackHandler.log_message(handler, "test %s", "arg")


class TestStartCallbackServer:
    def test_all_ports_busy(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _start_callback_server,
        )

        ctx = MagicMock()
        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_port_range": [19000, 19001]},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.HTTPServer",
                side_effect=OSError("port busy"),
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            assert _start_callback_server(ctx) is None

    def test_success(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _start_callback_server,
        )

        ctx = MagicMock()
        mock_server = MagicMock(spec=HTTPServer)
        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_port_range": [19000, 19000]},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.HTTPServer",
                return_value=mock_server,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.assign_redirect_uri"
            ),
            patch("threading.Thread"),
        ):
            result = _start_callback_server(ctx)
            assert result is not None
            assert result[0] is mock_server


class TestAwaitCallback:
    def test_server_start_fails(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
        )

        ctx = MagicMock()
        with patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
            return_value=None,
        ):
            assert _await_callback(ctx) is None

    def test_no_redirect_uri(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = None
        mock_server = MagicMock()
        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, _OAuthResult(), threading.Event()),
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(ctx) is None
            mock_server.shutdown.assert_called_once()

    def test_timeout(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:19000/cb"
        mock_server = MagicMock()
        event = threading.Event()  # Never set

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, _OAuthResult(), event),
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_timeout": 0.01},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth.url",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(ctx) is None

    def test_result_error(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:19000/cb"
        mock_server = MagicMock()
        result = _OAuthResult()
        result.error = "some error"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, result, event),
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth.url",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(ctx) is None

    def test_state_mismatch(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:19000/cb"
        ctx.state = "expected_state"
        mock_server = MagicMock()
        result = _OAuthResult()
        result.code = "code123"
        result.state = "different_state"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, result, event),
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth.url",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(ctx) is None

    def test_success_headless(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:19000/cb"
        ctx.state = "the_state"
        mock_server = MagicMock()
        result = _OAuthResult()
        result.code = "the_code"
        result.state = "the_state"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, result, event),
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth.url",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
        ):
            assert _await_callback(ctx) == "the_code"

    def test_success_browser(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:19000/cb"
        ctx.state = "st"
        mock_server = MagicMock()
        result = _OAuthResult()
        result.code = "c"
        result.state = "st"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._start_callback_server",
                return_value=(mock_server, result, event),
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.CLAUDE_CODE_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth.url",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=False,
            ),
            patch("webbrowser.open"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
        ):
            assert _await_callback(ctx) == "c"


class TestCustomHelp:
    def test_returns_entries(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _custom_help,
        )

        entries = _custom_help()
        names = [n for n, _ in entries]
        assert "claude-code-auth" in names
        assert "claude-code-status" in names
        assert "claude-code-logout" in names


class TestPerformAuthentication:
    def test_no_code(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value=None,
            ),
        ):
            _perform_authentication()  # should return early

    def test_token_exchange_fails(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value="code123",
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.exchange_code_for_tokens",
                return_value=None,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            _perform_authentication()

    def test_save_fails(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value="code123",
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.exchange_code_for_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.save_tokens",
                return_value=False,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_error"),
        ):
            _perform_authentication()

    def test_no_access_token(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value="code123",
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.exchange_code_for_tokens",
                return_value={"refresh_token": "rt"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ),
        ):
            _perform_authentication()

    def test_no_models_returned(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value="code123",
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.exchange_code_for_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.fetch_claude_code_models",
                return_value=[],
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ),
        ):
            _perform_authentication()

    def test_full_success(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._await_callback",
                return_value="code123",
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.exchange_code_for_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.fetch_claude_code_models",
                return_value=["model-a", "model-b"],
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.add_models_to_extra_config",
                return_value=True,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
        ):
            _perform_authentication()


class TestHandleCustomCommand:
    def test_empty_name(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "") is None

    def test_unknown(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "unknown") is None

    def test_auth(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.set_model_and_reload_agent"
            ),
        ):
            assert (
                _handle_custom_command("/claude-code-auth", "claude-code-auth") is True
            )

    def test_auth_no_existing_tokens(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.set_model_and_reload_agent"
            ),
        ):
            assert (
                _handle_custom_command("/claude-code-auth", "claude-code-auth") is True
            )

    def test_status_authenticated(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at", "expires_at": time.time() + 3600},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_claude_models_filtered",
                return_value={
                    "claude-code-opus": {"oauth_source": "claude-code-plugin"}
                },
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
        ):
            assert (
                _handle_custom_command("/claude-code-status", "claude-code-status")
                is True
            )

    def test_status_no_models(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_claude_models_filtered",
                return_value={},
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ),
        ):
            assert (
                _handle_custom_command("/claude-code-status", "claude-code-status")
                is True
            )

    def test_status_not_authenticated(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
        ):
            assert (
                _handle_custom_command("/claude-code-status", "claude-code-status")
                is True
            )

    def test_logout(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_path = MagicMock()
        mock_path.exists.return_value = True

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.remove_claude_code_models",
                return_value=3,
            ),
            patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
        ):
            assert (
                _handle_custom_command("/claude-code-logout", "claude-code-logout")
                is True
            )

    def test_logout_no_tokens(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with (
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.remove_claude_code_models",
                return_value=0,
            ),
            patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ),
        ):
            assert (
                _handle_custom_command("/claude-code-logout", "claude-code-logout")
                is True
            )


# Patch targets for lazy imports in _create_claude_code_model
_MF = "code_puppy.model_factory"
_CFG = "code_puppy.config"
_HU = "code_puppy.http_utils"
_CC = "code_puppy.claude_cache_client"
_RC = "code_puppy.plugins.claude_code_oauth.register_callbacks"


@contextmanager
def _model_patches(
    headers=None,
    api_key="key",
    interleaved=True,
    verify=None,
    http2=False,
    mock_model=None,
):
    """Context manager for _create_claude_code_model patches."""
    if headers is None:
        headers = {}
    if mock_model is None:
        mock_model = MagicMock()
    with (
        patch(
            f"{_MF}.get_custom_config",
            return_value=("http://url", headers, verify, api_key),
        ),
        patch(
            f"{_CFG}.get_effective_model_settings",
            return_value={"interleaved_thinking": interleaved},
        ),
        patch(f"{_HU}.get_cert_bundle_path", return_value=verify),
        patch(f"{_HU}.get_http2", return_value=http2),
        patch(f"{_CC}.ClaudeCacheAsyncClient"),
        patch("anthropic.AsyncAnthropic"),
        patch(f"{_CC}.patch_anthropic_client_messages"),
        patch("pydantic_ai.providers.anthropic.AnthropicProvider"),
        patch("pydantic_ai.models.anthropic.AnthropicModel", return_value=mock_model),
    ):
        yield


class TestCreateClaudeCodeModel:
    def test_no_api_key(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        with (
            patch(
                f"{_MF}.get_custom_config", return_value=("http://url", {}, None, None)
            ),
            patch(f"{_RC}.emit_warning"),
        ):
            assert _create_claude_code_model("m", {"name": "m"}, {}) is None

    def test_oauth_source_refresh(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        mock_model = MagicMock()
        with (
            _model_patches(api_key="old_key", mock_model=mock_model),
            patch(f"{_RC}.get_valid_access_token", return_value="new_token"),
        ):
            result = _create_claude_code_model(
                "m",
                {
                    "name": "m",
                    "oauth_source": "claude-code-plugin",
                    "custom_endpoint": {"api_key": "old"},
                    "context_length": 200000,
                },
                {},
            )
            assert result is mock_model

    def test_interleaved_thinking_false_removes_beta(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        mock_model = MagicMock()
        with _model_patches(
            headers={"anthropic-beta": "interleaved-thinking-2025-05-14,other-beta"},
            interleaved=False,
            mock_model=mock_model,
        ):
            result = _create_claude_code_model(
                "m", {"name": "m", "context_length": 200000}, {}
            )
            assert result is mock_model

    def test_interleaved_thinking_false_removes_all_beta(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        mock_model = MagicMock()
        with _model_patches(
            headers={"anthropic-beta": "interleaved-thinking-2025-05-14"},
            interleaved=False,
            mock_model=mock_model,
        ):
            result = _create_claude_code_model(
                "m", {"name": "m", "context_length": 200000}, {}
            )
            assert result is mock_model

    def test_1m_context_beta(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        mock_model = MagicMock()
        with _model_patches(
            headers={"anthropic-beta": "existing"},
            verify="/path/cert",
            http2=True,
            mock_model=mock_model,
        ):
            result = _create_claude_code_model(
                "m", {"name": "m", "context_length": 1_000_000}, {}
            )
            assert result is mock_model

    def test_1m_context_no_existing_beta(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        mock_model = MagicMock()
        with _model_patches(interleaved=False, mock_model=mock_model):
            result = _create_claude_code_model(
                "m", {"name": "m", "context_length": 1_000_000}, {}
            )
            assert result is mock_model


class TestRegisterModelTypes:
    def test_returns_handler(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _register_model_types,
        )

        types = _register_model_types()
        assert len(types) == 1
        assert types[0]["type"] == "claude_code"


class TestAgentRunCallbacks:
    @pytest.mark.asyncio
    async def test_start_non_claude_model(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_start,
        )

        await _on_agent_run_start("agent", "gpt-4", "sess")  # should return early

    @pytest.mark.asyncio
    async def test_start_claude_model(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        mock_heartbeat = AsyncMock()
        with patch(
            "code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat.TokenRefreshHeartbeat",
            return_value=mock_heartbeat,
        ):
            await _on_agent_run_start("agent", "claude-code-opus", "sess1")
            assert "sess1" in _active_heartbeats
            mock_heartbeat.start.assert_awaited_once()
            _active_heartbeats.pop("sess1", None)

    @pytest.mark.asyncio
    async def test_start_import_error(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_start,
        )

        with patch.dict(
            "sys.modules",
            {"code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat": None},
        ):
            # ImportError should be handled gracefully
            await _on_agent_run_start("agent", "claude-code-x", "sess")

    @pytest.mark.asyncio
    async def test_start_exception(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_start,
        )

        with patch(
            "code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat.TokenRefreshHeartbeat",
            side_effect=RuntimeError("boom"),
        ):
            await _on_agent_run_start("agent", "claude-code-x", "sess")

    @pytest.mark.asyncio
    async def test_end_with_heartbeat(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.refresh_count = 5
        _active_heartbeats["s1"] = mock_hb
        await _on_agent_run_end("agent", "claude-code-x", session_id="s1")
        mock_hb.stop.assert_awaited_once()
        assert "s1" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_end_no_heartbeat(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_end,
        )

        await _on_agent_run_end("agent", "model", session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_end_default_session(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.refresh_count = 0
        _active_heartbeats["default"] = mock_hb
        await _on_agent_run_end("agent", "model")
        mock_hb.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_end_stop_exception(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.stop.side_effect = RuntimeError("fail")
        mock_hb.refresh_count = 0
        _active_heartbeats["s2"] = mock_hb
        await _on_agent_run_end("agent", "model", session_id="s2")
