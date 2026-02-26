"""Test suite for Claude Code OAuth CLI command handlers.

Covers custom command routing, authentication flow, status checks, and logout.
"""

import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MOD = "code_puppy.plugins.claude_code_oauth.register_callbacks"


# ── Helpers ──────────────────────────────────────────────────────────────────


class TestOAuthResult:
    def test_defaults(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import _OAuthResult

        r = _OAuthResult()
        assert r.code is None
        assert r.state is None
        assert r.error is None


class TestCallbackHandler:
    """Test the HTTP callback handler."""

    def _make_handler(self, path="/"):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _CallbackHandler,
            _OAuthResult,
        )

        result = _OAuthResult()
        event = threading.Event()
        _CallbackHandler.result = result
        _CallbackHandler.received_event = event

        # Create a real-ish handler object with mocked I/O
        handler = object.__new__(_CallbackHandler)
        handler.path = path
        handler.wfile = MagicMock()
        handler.result = result
        handler.received_event = event
        handler._headers_buffer = []
        handler.request_version = "HTTP/1.1"
        handler.responses = {200: ("OK", ""), 400: ("Bad Request", "")}
        # Mock the response writing methods
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        return handler, result, event

    def test_do_GET_success(self):
        handler, result, event = self._make_handler("/?code=abc&state=xyz")
        handler.do_GET()
        assert result.code == "abc"
        assert result.state == "xyz"
        assert event.is_set()
        handler.send_response.assert_called_with(200)

    def test_do_GET_missing_params(self):
        handler, result, event = self._make_handler("/?foo=bar")
        handler.do_GET()
        assert result.error == "Missing code or state"
        assert event.is_set()
        handler.send_response.assert_called_with(400)

    def test_log_message_noop(self):
        handler, _, _ = self._make_handler()
        # Should not raise
        handler.log_message("test %s", "arg")


class TestStartCallbackServer:
    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_port_range": [19876, 19876]})
    @patch(f"{MOD}.assign_redirect_uri")
    def test_success(self, mock_assign):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _start_callback_server,
        )

        ctx = MagicMock()
        result = _start_callback_server(ctx)
        assert result is not None
        server, oauth_result, event = result
        server.shutdown()
        mock_assign.assert_called_once()

    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_port_range": [19876, 19876]})
    @patch(f"{MOD}.assign_redirect_uri")
    @patch(f"{MOD}.HTTPServer", side_effect=OSError("port in use"))
    @patch(f"{MOD}.emit_error")
    def test_all_ports_fail(self, mock_err, mock_http, mock_assign):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _start_callback_server,
        )

        result = _start_callback_server(MagicMock())
        assert result is None
        mock_err.assert_called_once()


class TestAwaitCallback:
    @patch(f"{MOD}._start_callback_server", return_value=None)
    def test_server_start_fails(self, _):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
        )

        assert _await_callback(MagicMock()) is None

    @patch(f"{MOD}._start_callback_server")
    @patch(f"{MOD}.emit_error")
    def test_no_redirect_uri(self, mock_err, mock_start):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
        )

        server = MagicMock()
        from code_puppy.plugins.claude_code_oauth.register_callbacks import _OAuthResult

        mock_start.return_value = (server, _OAuthResult(), threading.Event())
        ctx = MagicMock()
        ctx.redirect_uri = None
        assert _await_callback(ctx) is None
        server.shutdown.assert_called_once()

    @patch("code_puppy.tools.common.should_suppress_browser", return_value=True)
    @patch(f"{MOD}.emit_error")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_timeout": 0.1})
    @patch(f"{MOD}.build_authorization_url", return_value="https://auth.example.com")
    @patch(f"{MOD}._start_callback_server")
    def test_timeout(self, mock_start, mock_build, mock_info, mock_err, mock_suppress):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        event = threading.Event()  # never set
        server = MagicMock()
        mock_start.return_value = (server, _OAuthResult(), event)
        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:1234"
        ctx.state = "s"
        assert _await_callback(ctx) is None

    @patch("webbrowser.open")
    @patch("code_puppy.tools.common.should_suppress_browser", return_value=False)
    @patch(f"{MOD}.emit_error")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_timeout": 5})
    @patch(f"{MOD}.build_authorization_url", return_value="https://auth.example.com")
    @patch(f"{MOD}._start_callback_server")
    def test_success_with_browser(
        self, mock_start, mock_build, mock_info, mock_err, mock_suppress, mock_wb
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        event = threading.Event()
        result = _OAuthResult()
        result.code = "the_code"
        result.state = "the_state"
        event.set()
        server = MagicMock()
        mock_start.return_value = (server, result, event)
        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:1234"
        ctx.state = "the_state"
        assert _await_callback(ctx) == "the_code"

    @patch("code_puppy.tools.common.should_suppress_browser", return_value=True)
    @patch(f"{MOD}.emit_error")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_timeout": 5})
    @patch(f"{MOD}.build_authorization_url", return_value="https://auth.example.com")
    @patch(f"{MOD}._start_callback_server")
    def test_callback_error(
        self, mock_start, mock_build, mock_info, mock_err, mock_suppress
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        event = threading.Event()
        result = _OAuthResult()
        result.error = "something broke"
        event.set()
        server = MagicMock()
        mock_start.return_value = (server, result, event)
        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:1234"
        ctx.state = "s"
        assert _await_callback(ctx) is None

    @patch("code_puppy.tools.common.should_suppress_browser", return_value=True)
    @patch(f"{MOD}.emit_error")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.CLAUDE_CODE_OAUTH_CONFIG", {"callback_timeout": 5})
    @patch(f"{MOD}.build_authorization_url", return_value="https://auth.example.com")
    @patch(f"{MOD}._start_callback_server")
    def test_state_mismatch(
        self, mock_start, mock_build, mock_info, mock_err, mock_suppress
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        event = threading.Event()
        result = _OAuthResult()
        result.code = "code"
        result.state = "wrong_state"
        event.set()
        server = MagicMock()
        mock_start.return_value = (server, result, event)
        ctx = MagicMock()
        ctx.redirect_uri = "http://localhost:1234"
        ctx.state = "expected_state"
        assert _await_callback(ctx) is None


class TestPerformAuthentication:
    @patch(f"{MOD}._await_callback", return_value=None)
    @patch(f"{MOD}.prepare_oauth_context")
    def test_no_code(self, mock_ctx, mock_await):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        # Should return early, no further calls

    @patch(f"{MOD}._await_callback", return_value="code123")
    @patch(f"{MOD}.prepare_oauth_context")
    @patch(f"{MOD}.exchange_code_for_tokens", return_value=None)
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_error")
    def test_token_exchange_fails(
        self, mock_err, mock_info, mock_exchange, mock_ctx, mock_await
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        mock_err.assert_called()

    @patch(f"{MOD}._await_callback", return_value="code123")
    @patch(f"{MOD}.prepare_oauth_context")
    @patch(f"{MOD}.exchange_code_for_tokens", return_value={"access_token": "tk"})
    @patch(f"{MOD}.save_tokens", return_value=False)
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_error")
    def test_save_fails(
        self, mock_err, mock_info, mock_save, mock_exchange, mock_ctx, mock_await
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        mock_err.assert_called()

    @patch(f"{MOD}._await_callback", return_value="code123")
    @patch(f"{MOD}.prepare_oauth_context")
    @patch(f"{MOD}.exchange_code_for_tokens", return_value={"not_access": "x"})
    @patch(f"{MOD}.save_tokens", return_value=True)
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_success")
    @patch(f"{MOD}.emit_warning")
    def test_no_access_token(
        self,
        mock_warn,
        mock_succ,
        mock_info,
        mock_save,
        mock_exchange,
        mock_ctx,
        mock_await,
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        mock_warn.assert_called()

    @patch(f"{MOD}._await_callback", return_value="code123")
    @patch(f"{MOD}.prepare_oauth_context")
    @patch(f"{MOD}.exchange_code_for_tokens", return_value={"access_token": "tk"})
    @patch(f"{MOD}.save_tokens", return_value=True)
    @patch(f"{MOD}.fetch_claude_code_models", return_value=[])
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_success")
    @patch(f"{MOD}.emit_warning")
    def test_no_models(
        self,
        mock_warn,
        mock_succ,
        mock_info,
        mock_fetch,
        mock_save,
        mock_exchange,
        mock_ctx,
        mock_await,
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        mock_warn.assert_called()

    @patch(f"{MOD}._await_callback", return_value="code123")
    @patch(f"{MOD}.prepare_oauth_context")
    @patch(f"{MOD}.exchange_code_for_tokens", return_value={"access_token": "tk"})
    @patch(f"{MOD}.save_tokens", return_value=True)
    @patch(f"{MOD}.fetch_claude_code_models", return_value=["m1", "m2"])
    @patch(f"{MOD}.add_models_to_extra_config", return_value=True)
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_success")
    def test_full_success(
        self,
        mock_succ,
        mock_info,
        mock_add,
        mock_fetch,
        mock_save,
        mock_exchange,
        mock_ctx,
        mock_await,
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _perform_authentication,
        )

        _perform_authentication()
        mock_add.assert_called_once_with(["m1", "m2"])


class TestCustomHelpCommands:
    def test_custom_help_returns_commands(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import _custom_help

        commands = _custom_help()
        assert len(commands) == 3
        names = [n for n, _ in commands]
        assert "claude-code-auth" in names
        assert "claude-code-status" in names
        assert "claude-code-logout" in names


class TestHandleCustomCommand:
    def test_unknown_command(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "x") is None

    def test_empty_name(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "") is None

    @patch(f"{MOD}.load_stored_tokens", return_value={"access_token": "old"})
    @patch(f"{MOD}._perform_authentication")
    @patch(f"{MOD}.set_model_and_reload_agent")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_warning")
    def test_auth_with_existing_tokens(
        self, mock_warn, mock_info, mock_set, mock_auth, mock_tokens
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/claude-code-auth", "claude-code-auth") is True
        mock_warn.assert_called()  # warns about overwriting

    @patch(
        f"{MOD}.load_stored_tokens",
        return_value={"access_token": "tk", "expires_at": time.time() + 3600},
    )
    @patch(f"{MOD}.load_claude_models_filtered", return_value={})
    @patch(f"{MOD}.emit_success")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_warning")
    def test_status_authenticated_no_models(
        self, mock_warn, mock_info, mock_succ, mock_models, mock_tokens
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert (
            _handle_custom_command("/claude-code-status", "claude-code-status") is True
        )
        mock_warn.assert_called()  # no models warning

    @patch(
        f"{MOD}.load_stored_tokens",
        return_value={"access_token": "tk", "expires_at": time.time() + 3600},
    )
    @patch(
        f"{MOD}.load_claude_models_filtered",
        return_value={"m": {"oauth_source": "claude-code-plugin"}},
    )
    @patch(f"{MOD}.emit_success")
    @patch(f"{MOD}.emit_info")
    def test_status_with_claude_models(
        self, mock_info, mock_succ, mock_models, mock_tokens
    ):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert (
            _handle_custom_command("/claude-code-status", "claude-code-status") is True
        )
        # Should have called emit_info with configured models
        info_calls = [str(c) for c in mock_info.call_args_list]
        assert any("Configured Claude Code models" in c for c in info_calls)

    @patch(f"{MOD}.load_stored_tokens", return_value={"access_token": "tk"})
    @patch(
        f"{MOD}.load_claude_models_filtered",
        return_value={"m": {"oauth_source": "other"}},
    )
    @patch(f"{MOD}.emit_success")
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_warning")
    def test_status_no_expires_at(
        self, mock_warn, mock_info, mock_succ, mock_models, mock_tokens
    ):
        """Status with no expires_at field."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert (
            _handle_custom_command("/claude-code-status", "claude-code-status") is True
        )

    @patch(f"{MOD}.load_stored_tokens", return_value=None)
    @patch(f"{MOD}.emit_warning")
    @patch(f"{MOD}.emit_info")
    def test_status_not_authenticated(self, mock_info, mock_warn, mock_tokens):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert (
            _handle_custom_command("/claude-code-status", "claude-code-status") is True
        )

    @patch(f"{MOD}.get_token_storage_path")
    @patch(f"{MOD}.remove_claude_code_models", return_value=2)
    @patch(f"{MOD}.emit_info")
    @patch(f"{MOD}.emit_success")
    def test_logout_with_tokens(self, mock_succ, mock_info, mock_remove, mock_path):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_path.return_value = mock_file
        assert (
            _handle_custom_command("/claude-code-logout", "claude-code-logout") is True
        )
        mock_file.unlink.assert_called_once()

    @patch(f"{MOD}.get_token_storage_path")
    @patch(f"{MOD}.remove_claude_code_models", return_value=0)
    @patch(f"{MOD}.emit_success")
    def test_logout_no_tokens(self, mock_succ, mock_remove, mock_path):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_file = MagicMock()
        mock_file.exists.return_value = False
        mock_path.return_value = mock_file
        assert (
            _handle_custom_command("/claude-code-logout", "claude-code-logout") is True
        )


def _patch_model_deps():
    """Context manager to patch all _create_claude_code_model internal imports."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        with (
            patch("code_puppy.claude_cache_client.ClaudeCacheAsyncClient"),
            patch("code_puppy.claude_cache_client.patch_anthropic_client_messages"),
            patch(f"{MOD}.AsyncAnthropic", create=True),
            patch(f"{MOD}.AnthropicModel", create=True),
            patch(f"{MOD}.AnthropicProvider", create=True),
        ):
            pass
        yield

    return _ctx()


class TestCreateClaudeCodeModel:
    """Tests for _create_claude_code_model."""

    def _call(self, model_name, model_config, config=None):
        """Helper to call _create_claude_code_model with all deps mocked."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _create_claude_code_model,
        )

        with (
            patch("anthropic.AsyncAnthropic") as mock_async_cls,
            patch("pydantic_ai.models.anthropic.AnthropicModel"),
            patch("pydantic_ai.providers.anthropic.AnthropicProvider"),
            patch("code_puppy.claude_cache_client.ClaudeCacheAsyncClient"),
            patch("code_puppy.claude_cache_client.patch_anthropic_client_messages"),
        ):
            mock_anthropic = MagicMock()
            mock_anthropic.api_key = None
            mock_anthropic.auth_token = None
            mock_async_cls.return_value = mock_anthropic
            result = _create_claude_code_model(model_name, model_config, config or {})
        return result

    @patch(f"{MOD}.get_valid_access_token", return_value="refreshed_token")
    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=("https://api.example.com", {}, None, "old_key"),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": True},
    )
    @patch("code_puppy.http_utils.get_cert_bundle_path", return_value="/ca.pem")
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_oauth_model_refreshes_token(
        self, mock_h2, mock_cert, mock_settings, mock_custom, mock_token
    ):
        model_config = {
            "name": "claude-4",
            "oauth_source": "claude-code-plugin",
            "custom_endpoint": {"url": "https://api.example.com"},
            "context_length": 200000,
        }
        result = self._call("claude-code-opus", model_config)
        assert result is not None

    @patch(f"{MOD}.get_valid_access_token", return_value=None)
    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=("https://api.example.com", {}, None, None),
    )
    @patch("code_puppy.config.get_effective_model_settings", return_value={})
    @patch(f"{MOD}.emit_warning")
    def test_no_api_key(self, mock_warn, mock_settings, mock_custom, mock_token):
        model_config = {"name": "claude-4", "oauth_source": "claude-code-plugin"}
        result = self._call("claude-code-opus", model_config)
        assert result is None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=(
            "https://api.example.com",
            {"anthropic-beta": "existing-beta"},
            "/cert",
            "key123",
        ),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": False},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=True)
    def test_interleaved_thinking_false_strips_beta(
        self, mock_h2, mock_settings, mock_custom
    ):
        model_config = {"name": "claude-4", "context_length": 200000}
        result = self._call("test-model", model_config)
        assert result is not None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=(
            "https://api.example.com",
            {"anthropic-beta": "interleaved-thinking-2025-05-14"},
            "/cert",
            "key123",
        ),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": False},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_strip_interleaved_thinking_leaves_empty(
        self, mock_h2, mock_settings, mock_custom
    ):
        model_config = {"name": "claude-4", "context_length": 100000}
        result = self._call("test-model", model_config)
        assert result is not None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=("https://api.example.com", {}, "/cert", "key123"),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": False},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_no_beta_no_interleaved(self, mock_h2, mock_settings, mock_custom):
        model_config = {"name": "claude-4", "context_length": 100000}
        result = self._call("test-model", model_config)
        assert result is not None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=(
            "https://api.example.com",
            {"anthropic-beta": "some-other-beta"},
            "/cert",
            "key123",
        ),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": True},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_existing_beta_adds_interleaved(self, mock_h2, mock_settings, mock_custom):
        model_config = {"name": "claude-4", "context_length": 1_000_000}
        result = self._call("test-model", model_config)
        assert result is not None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=("https://api.example.com", {}, "/cert", "key123"),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": True},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_1m_context_no_existing_beta(self, mock_h2, mock_settings, mock_custom):
        model_config = {"name": "claude-4", "context_length": 1_000_000}
        result = self._call("test-model", model_config)
        assert result is not None

    @patch(
        "code_puppy.model_factory.get_custom_config",
        return_value=("https://api.example.com", {}, "/cert", "key123"),
    )
    @patch(
        "code_puppy.config.get_effective_model_settings",
        return_value={"interleaved_thinking": False},
    )
    @patch("code_puppy.http_utils.get_http2", return_value=False)
    def test_1m_context_no_beta_no_interleaved(
        self, mock_h2, mock_settings, mock_custom
    ):
        """1M context, no existing beta, interleaved=False -> only 1M beta added."""
        model_config = {"name": "claude-4", "context_length": 1_000_000}
        result = self._call("test-model", model_config)
        assert result is not None


class TestRegisterModelTypes:
    def test_returns_claude_code_type(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _register_model_types,
        )

        types = _register_model_types()
        assert len(types) == 1
        assert types[0]["type"] == "claude_code"


class TestAgentRunStart:
    @pytest.mark.asyncio
    async def test_non_claude_code_model_skipped(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        await _on_agent_run_start("agent", "gpt-4", "sess1")
        assert "sess1" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_starts_heartbeat(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        mock_hb = AsyncMock()
        mock_hb.start = AsyncMock()
        with patch(
            f"{MOD.rsplit('.', 1)[0]}.token_refresh_heartbeat.TokenRefreshHeartbeat",
            return_value=mock_hb,
        ):
            # Patch at the import location inside the function
            with patch.dict("sys.modules", {}):
                # Simpler: just patch the import
                with patch(
                    "code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat.TokenRefreshHeartbeat",
                    return_value=mock_hb,
                ):
                    await _on_agent_run_start("agent", "claude-code-opus", "sess2")
        assert "sess2" in _active_heartbeats
        _active_heartbeats.pop("sess2", None)  # cleanup

    @pytest.mark.asyncio
    async def test_import_error_handled(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_start,
        )

        with patch.dict(
            "sys.modules",
            {"code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat": None},
        ):
            # ImportError should be caught
            await _on_agent_run_start("agent", "claude-code-opus", "sess3")

    @pytest.mark.asyncio
    async def test_generic_exception_handled(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_start,
        )

        with patch(
            "code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat.TokenRefreshHeartbeat",
            side_effect=RuntimeError("boom"),
        ):
            await _on_agent_run_start("agent", "claude-code-opus", "sess4")

    @pytest.mark.asyncio
    async def test_default_session_key(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_start,
        )

        mock_hb = AsyncMock()
        mock_hb.start = AsyncMock()
        with patch(
            "code_puppy.plugins.claude_code_oauth.token_refresh_heartbeat.TokenRefreshHeartbeat",
            return_value=mock_hb,
        ):
            await _on_agent_run_start("agent", "claude-code-opus", None)
        assert "default" in _active_heartbeats
        _active_heartbeats.pop("default", None)


class TestAgentRunEnd:
    @pytest.mark.asyncio
    async def test_no_heartbeat(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _on_agent_run_end,
        )

        # Should not raise
        await _on_agent_run_end("agent", "claude-code-opus", "nonexistent")

    @pytest.mark.asyncio
    async def test_stops_heartbeat(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.stop = AsyncMock()
        mock_hb.refresh_count = 5
        _active_heartbeats["sess5"] = mock_hb
        await _on_agent_run_end("agent", "claude-code-opus", "sess5")
        mock_hb.stop.assert_called_once()
        assert "sess5" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_stop_error_handled(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.stop = AsyncMock(side_effect=RuntimeError("stop failed"))
        mock_hb.refresh_count = 0
        _active_heartbeats["sess6"] = mock_hb
        await _on_agent_run_end("agent", "claude-code-opus", "sess6")
        assert "sess6" not in _active_heartbeats

    @pytest.mark.asyncio
    async def test_default_session_key(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _active_heartbeats,
            _on_agent_run_end,
        )

        mock_hb = AsyncMock()
        mock_hb.stop = AsyncMock()
        mock_hb.refresh_count = 0
        _active_heartbeats["default"] = mock_hb
        await _on_agent_run_end("agent", "model", None)
        assert "default" not in _active_heartbeats


class TestCallbackRegistration:
    def test_callbacks_registered(self):
        from code_puppy.callbacks import get_callbacks

        assert len(get_callbacks("custom_command_help")) > 0
        assert len(get_callbacks("custom_command")) > 0
        assert len(get_callbacks("register_model_type")) > 0
        assert len(get_callbacks("agent_run_start")) > 0
        assert len(get_callbacks("agent_run_end")) > 0
