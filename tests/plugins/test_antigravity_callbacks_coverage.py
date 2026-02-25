"""Tests for antigravity_oauth/register_callbacks.py and oauth.py full coverage."""

from __future__ import annotations

import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest

# ── register_callbacks.py ──────────────────────────────────────────


class TestAntigravityCallbackHandler:
    def test_do_get_success(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _CallbackHandler,
            _OAuthResult,
        )

        result = _OAuthResult()
        event = threading.Event()
        _CallbackHandler.result = result
        _CallbackHandler.received_event = event

        handler = MagicMock(spec=_CallbackHandler)
        handler.path = "/cb?code=abc&state=xyz"
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
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _CallbackHandler,
            _OAuthResult,
        )

        result = _OAuthResult()
        event = threading.Event()
        _CallbackHandler.result = result
        _CallbackHandler.received_event = event

        handler = MagicMock(spec=_CallbackHandler)
        handler.path = "/cb"
        handler.result = result
        handler.received_event = event
        handler.wfile = MagicMock()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()

        _CallbackHandler.do_GET(handler)
        assert result.error == "Missing code or state"

    def test_log_message_noop(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _CallbackHandler,
        )

        handler = MagicMock(spec=_CallbackHandler)
        _CallbackHandler.log_message(handler, "test")


class TestAntigravityStartCallbackServer:
    def test_all_ports_busy(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _start_callback_server,
        )

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_port_range": [19000, 19001]},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.HTTPServer",
                side_effect=OSError,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error"),
        ):
            assert _start_callback_server(MagicMock()) is None

    def test_success(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _start_callback_server,
        )

        mock_server = MagicMock(spec=HTTPServer)
        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_port_range": [19000, 19000]},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.HTTPServer",
                return_value=mock_server,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.assign_redirect_uri",
                return_value="http://localhost:19000/cb",
            ),
            patch("threading.Thread"),
        ):
            result = _start_callback_server(MagicMock())
            assert result is not None
            assert result[0] is mock_server


class TestAntigravityAwaitCallback:
    def test_server_fails(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
        )

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
            return_value=None,
        ):
            assert _await_callback(MagicMock()) is None

    def test_timeout(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        event = threading.Event()
        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
                return_value=(
                    MagicMock(),
                    _OAuthResult(),
                    event,
                    "http://localhost/cb",
                ),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_timeout": 0.01},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(MagicMock()) is None

    def test_result_error(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        result = _OAuthResult()
        result.error = "bad"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
                return_value=(MagicMock(), result, event, "http://localhost/cb"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error"),
        ):
            assert _await_callback(MagicMock()) is None

    def test_success_headless(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        result = _OAuthResult()
        result.code = "c"
        result.state = "s"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
                return_value=(MagicMock(), result, event, "http://localhost/cb"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=True,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
        ):
            r = _await_callback(MagicMock())
            assert r == ("c", "s", "http://localhost/cb")

    def test_success_browser(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        result = _OAuthResult()
        result.code = "c"
        result.state = "s"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
                return_value=(MagicMock(), result, event, "http://localhost/cb"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                return_value=False,
            ),
            patch("webbrowser.open"),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
        ):
            r = _await_callback(MagicMock())
            assert r is not None

    def test_browser_exception(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _await_callback,
            _OAuthResult,
        )

        result = _OAuthResult()
        result.code = "c"
        result.state = "s"
        event = threading.Event()
        event.set()

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server",
                return_value=(MagicMock(), result, event, "http://localhost/cb"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.ANTIGRAVITY_OAUTH_CONFIG",
                {"callback_timeout": 5},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.build_authorization_url",
                return_value="http://auth",
            ),
            patch(
                "code_puppy.tools.common.should_suppress_browser",
                side_effect=RuntimeError("nope"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
        ):
            r = _await_callback(MagicMock())
            assert r is not None


class TestAntigravityPerformAuth:
    def test_callback_fails(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback",
                return_value=None,
            ),
        ):
            assert _perform_authentication() is False

    def test_token_exchange_fails(self):
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeFailure
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback",
                return_value=("code", "state", "redirect"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens",
                return_value=TokenExchangeFailure(error="fail"),
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error"),
        ):
            assert _perform_authentication() is False

    def test_save_fails(self):
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _perform_authentication,
        )

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback",
                return_value=("code", "state", "redirect"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens",
                return_value=TokenExchangeSuccess(
                    refresh_token="rt",
                    access_token="at",
                    expires_at=time.time() + 3600,
                    email="e@e.com",
                    project_id="pid",
                ),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens",
                return_value=False,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error"),
        ):
            assert _perform_authentication() is False

    def test_full_success_with_add_account(self):
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _perform_authentication,
        )

        mock_manager = MagicMock()
        mock_manager.account_count = 0

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback",
                return_value=("code", "state", "redirect"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens",
                return_value=TokenExchangeSuccess(
                    refresh_token="rt",
                    access_token="at",
                    expires_at=time.time() + 3600,
                    email="e@e.com",
                    project_id="pid",
                ),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
                return_value=mock_manager,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.add_models_to_config",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.reload_current_agent"
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
        ):
            assert _perform_authentication(add_account=True) is True

    def test_success_no_email(self):
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _perform_authentication,
        )

        mock_manager = MagicMock()
        mock_manager.account_count = 1

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback",
                return_value=("code", "state", "redirect"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens",
                return_value=TokenExchangeSuccess(
                    refresh_token="rt",
                    access_token="at",
                    expires_at=time.time() + 3600,
                    email=None,
                    project_id="pid",
                ),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
                return_value=mock_manager,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.add_models_to_config",
                return_value=False,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
        ):
            assert _perform_authentication(reload_agent=False) is True


class TestAntigravityHandleStatus:
    def test_not_authenticated(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_status,
        )

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
        ):
            _handle_status()

    def test_authenticated_with_status(self):
        from code_puppy.plugins.antigravity_oauth.oauth import AntigravityStatus
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_status,
        )

        mock_manager = MagicMock()
        mock_manager.account_count = 2
        acc = MagicMock()
        acc.email = "test@test.com"
        acc.rate_limit_reset_times = {"key": time.time() * 1000 + 60000}
        mock_manager.get_accounts_snapshot.return_value = [acc]

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "email": "e@e.com",
                    "expires_at": time.time() + 3600,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.fetch_antigravity_status",
                return_value=AntigravityStatus(
                    project_id="pid",
                    current_tier="free-tier",
                    allowed_tiers=["free-tier", "standard-tier"],
                    is_onboarded=True,
                ),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
                return_value=mock_manager,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_antigravity_models",
                return_value={
                    "antigravity-gemini": {"oauth_source": "antigravity-plugin"},
                    "antigravity-claude": {"oauth_source": "antigravity-plugin"},
                    "other": {"oauth_source": "antigravity-plugin"},
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
        ):
            _handle_status()

    def test_status_error(self):
        from code_puppy.plugins.antigravity_oauth.oauth import AntigravityStatus
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_status,
        )

        mock_manager = MagicMock()
        mock_manager.account_count = 1

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.fetch_antigravity_status",
                return_value=AntigravityStatus(error="failed"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
                return_value=mock_manager,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_antigravity_models",
                return_value={},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
        ):
            _handle_status()


class TestAntigravityHandleLogout:
    def test_logout_all(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_logout,
        )

        mock_token_path = MagicMock()
        mock_token_path.exists.return_value = True
        mock_accounts_path = MagicMock()
        mock_accounts_path.exists.return_value = True

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_token_path,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.get_accounts_storage_path",
                return_value=mock_accounts_path,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.clear_accounts"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.remove_antigravity_models",
                return_value=5,
            ),
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
        ):
            _handle_logout()

    def test_logout_nothing(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_logout,
        )

        mock_path = MagicMock()
        mock_path.exists.return_value = False

        with (
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.get_token_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.get_accounts_storage_path",
                return_value=mock_path,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.remove_antigravity_models",
                return_value=0,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ),
        ):
            _handle_logout()


class TestAntigravityHandleCustomCommand:
    def test_empty_name(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "") is None

    def test_unknown(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        assert _handle_custom_command("/x", "unknown") is None

    def test_auth_success(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={"access_token": "at"},
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._perform_authentication",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.set_model_and_reload_agent"
            ),
        ):
            assert (
                _handle_custom_command("/antigravity-auth", "antigravity-auth") is True
            )

    def test_auth_failure(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with (
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._perform_authentication",
                return_value=False,
            ),
        ):
            assert (
                _handle_custom_command("/antigravity-auth", "antigravity-auth") is True
            )

    def test_add(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_manager = MagicMock()
        mock_manager.account_count = 1
        with (
            patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager.load_from_disk",
                return_value=mock_manager,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks._perform_authentication"
            ),
        ):
            assert _handle_custom_command("/antigravity-add", "antigravity-add") is True

    def test_status(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks._handle_status"
        ):
            assert (
                _handle_custom_command("/antigravity-status", "antigravity-status")
                is True
            )

    def test_logout(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _handle_custom_command,
        )

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks._handle_logout"
        ):
            assert (
                _handle_custom_command("/antigravity-logout", "antigravity-logout")
                is True
            )


class TestCreateAntigravityModel:
    def test_no_api_key(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, None),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
        ):
            assert _create_antigravity_model("m", {"name": "m"}, {}) is None

    def test_no_tokens(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
        ):
            assert _create_antigravity_model("m", {"name": "m"}, {}) is None

    def test_refresh_fails(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": 0,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.is_token_expired",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.refresh_access_token",
                return_value=None,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning"
            ),
        ):
            assert _create_antigravity_model("m", {"name": "m"}, {}) is None

    def test_success_with_refresh(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        new_tokens = MagicMock()
        new_tokens.access_token = "new_at"
        new_tokens.refresh_token = "new_rt"
        new_tokens.expires_at = time.time() + 3600

        mock_model = MagicMock()

        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": 0,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.is_token_expired",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.refresh_access_token",
                return_value=new_tokens,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.create_antigravity_client"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.antigravity_model.AntigravityModel",
                return_value=mock_model,
            ),
        ):
            result = _create_antigravity_model("m", {"name": "m"}, {})
            assert result is mock_model

    def test_success_no_refresh_needed(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        mock_model = MagicMock()
        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": time.time() + 3600,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.is_token_expired",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.create_antigravity_client"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.antigravity_model.AntigravityModel",
                return_value=mock_model,
            ),
        ):
            result = _create_antigravity_model("m", {"name": "m"}, {})
            assert result is mock_model

    def test_fallback_to_gemini_model(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        mock_model = MagicMock()
        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": time.time() + 3600,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.is_token_expired",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.create_antigravity_client"
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.antigravity_model.AntigravityModel",
                None,  # Simulates ImportError leading to None
            ),
            patch(
                "code_puppy.gemini_model.GeminiModel",
                return_value=mock_model,
            ),
        ):
            result = _create_antigravity_model("m", {"name": "m"}, {})
            assert result is mock_model

    def test_on_token_refreshed_callback(self):
        """Test the on_token_refreshed closure."""
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _create_antigravity_model,
        )

        captured_callback = None

        def capture_client(**kwargs):
            nonlocal captured_callback
            captured_callback = kwargs.get("on_token_refreshed")
            return MagicMock()

        mock_model = MagicMock()
        with (
            patch(
                "code_puppy.model_factory.get_custom_config",
                return_value=("http://url", {}, None, "key"),
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
                return_value={
                    "access_token": "at",
                    "refresh_token": "rt",
                    "expires_at": time.time() + 3600,
                },
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.is_token_expired",
                return_value=False,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.create_antigravity_client",
                side_effect=capture_client,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.antigravity_model.AntigravityModel",
                return_value=mock_model,
            ),
            patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens",
                return_value=True,
            ),
        ):
            _create_antigravity_model("m", {"name": "m"}, {})

        assert captured_callback is not None
        # Call it
        new_tokens = MagicMock()
        new_tokens.access_token = "new_at"
        new_tokens.refresh_token = "new_rt"
        new_tokens.expires_at = 99999
        captured_callback(new_tokens)

        # Test exception handling
        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens",
            side_effect=RuntimeError("fail"),
        ):
            captured_callback(new_tokens)  # Should not raise


# ── oauth.py ──────────────────────────────────────────────────────


class TestAntigravityOAuthOnboardUser:
    def test_onboard_success(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _onboard_user

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "done": True,
            "response": {"cloudaicompanionProject": {"id": "proj-123"}},
        }

        with patch("requests.post", return_value=mock_resp):
            result = _onboard_user("token")
            assert result == "proj-123"

    def test_onboard_not_done_retries(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _onboard_user

        # First call not done, second done
        resp_not_done = MagicMock()
        resp_not_done.ok = True
        resp_not_done.json.return_value = {"done": False}

        resp_done = MagicMock()
        resp_done.ok = True
        resp_done.json.return_value = {
            "done": True,
            "response": {"cloudaicompanionProject": {"id": "p"}},
        }

        with (
            patch("requests.post", side_effect=[resp_not_done, resp_done]),
            patch("time.sleep"),
        ):
            result = _onboard_user("token")
            assert result == "p"

    def test_onboard_http_error(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _onboard_user

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "error"

        with patch("requests.post", return_value=mock_resp):
            result = _onboard_user("token")
            assert result == ""

    def test_onboard_exception(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _onboard_user

        with patch("requests.post", side_effect=RuntimeError("boom")):
            result = _onboard_user("token")
            assert result == ""

    def test_onboard_standard_tier(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _onboard_user

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "done": True,
            "response": {"cloudaicompanionProject": {"id": "proj"}},
        }

        with patch("requests.post", return_value=mock_resp):
            result = _onboard_user("token", "standard-tier", "my-gcp-project")
            assert result == "proj"


class TestFetchAntigravityStatus:
    def test_success_string_project(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            fetch_antigravity_status,
        )

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "cloudaicompanionProject": "proj-str",
            "allowedTiers": [{"id": "free-tier", "isDefault": True}],
        }

        with patch("requests.post", return_value=mock_resp):
            status = fetch_antigravity_status("token")
            assert status.project_id == "proj-str"
            assert status.current_tier == "free-tier"

    def test_success_dict_project(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            fetch_antigravity_status,
        )

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "cloudaicompanionProject": {"id": "proj-dict"},
            "allowedTiers": [{"id": "standard-tier"}],
        }

        with patch("requests.post", return_value=mock_resp):
            status = fetch_antigravity_status("token")
            assert status.project_id == "proj-dict"

    def test_all_endpoints_fail(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            fetch_antigravity_status,
        )

        with patch("requests.post", side_effect=RuntimeError("fail")):
            status = fetch_antigravity_status("token")
            assert status.error is not None

    def test_http_error(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            fetch_antigravity_status,
        )

        mock_resp = MagicMock()
        mock_resp.ok = False

        with patch("requests.post", return_value=mock_resp):
            status = fetch_antigravity_status("token")
            assert status.error is not None


class TestFetchProjectId:
    def test_string_project(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"cloudaicompanionProject": "proj"}

        with patch("requests.post", return_value=mock_resp):
            assert _fetch_project_id("token") == "proj"

    def test_dict_project(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"cloudaicompanionProject": {"id": "proj-d"}}

        with patch("requests.post", return_value=mock_resp):
            assert _fetch_project_id("token") == "proj-d"

    def test_no_project_free_tier_default(self):
        """Test when no project, free-tier is default and needs onboard."""
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "allowedTiers": [{"id": "free-tier", "isDefault": False}]
        }

        with (
            patch("requests.post", return_value=mock_resp),
            patch(
                "code_puppy.plugins.antigravity_oauth.oauth._onboard_user",
                return_value="onboarded",
            ),
        ):
            assert _fetch_project_id("token") == "onboarded"

    def test_no_project_onboard_success(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {
            "allowedTiers": [{"id": "free-tier", "isDefault": True}]
        }

        with (
            patch("requests.post", return_value=mock_resp),
            patch(
                "code_puppy.plugins.antigravity_oauth.oauth._onboard_user",
                return_value="onboarded-proj",
            ),
        ):
            assert _fetch_project_id("token") == "onboarded-proj"

    def test_all_fail(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "err"

        with patch("requests.post", return_value=mock_resp):
            assert _fetch_project_id("token") == ""

    def test_exception(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _fetch_project_id

        with patch("requests.post", side_effect=RuntimeError("boom")):
            assert _fetch_project_id("token") == ""


class TestExchangeCodeForTokens:
    def test_success(self):
        from code_puppy.plugins.antigravity_oauth.oauth import exchange_code_for_tokens

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }

        mock_user_resp = MagicMock()
        mock_user_resp.ok = True
        mock_user_resp.json.return_value = {"email": "e@e.com"}

        # Build a valid state
        from code_puppy.plugins.antigravity_oauth.oauth import _encode_state

        state = _encode_state("verifier", "proj")

        with (
            patch("requests.post", return_value=mock_token_resp),
            patch("requests.get", return_value=mock_user_resp),
        ):
            result = exchange_code_for_tokens("code", state, "http://redirect")
            assert result.access_token == "at"
            assert result.email == "e@e.com"

    def test_http_error(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            TokenExchangeFailure,
            _encode_state,
            exchange_code_for_tokens,
        )

        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.text = "bad request"

        state = _encode_state("v", "p")
        with patch("requests.post", return_value=mock_resp):
            result = exchange_code_for_tokens("code", state, "http://redirect")
            assert isinstance(result, TokenExchangeFailure)

    def test_no_refresh_token(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            TokenExchangeFailure,
            _encode_state,
            exchange_code_for_tokens,
        )

        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"access_token": "at"}

        state = _encode_state("v", "p")
        with patch("requests.post", return_value=mock_resp):
            result = exchange_code_for_tokens("code", state, "http://redirect")
            assert isinstance(result, TokenExchangeFailure)

    def test_exception(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            TokenExchangeFailure,
            exchange_code_for_tokens,
        )

        with patch("requests.post", side_effect=RuntimeError("boom")):
            # Invalid state will cause ValueError
            result = exchange_code_for_tokens("code", "bad-state", "http://redirect")
            assert isinstance(result, TokenExchangeFailure)

    def test_email_fetch_exception(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            _encode_state,
            exchange_code_for_tokens,
        )

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }

        state = _encode_state("v", "proj")

        with (
            patch("requests.post", return_value=mock_token_resp),
            patch("requests.get", side_effect=RuntimeError("email fail")),
        ):
            result = exchange_code_for_tokens("code", state, "http://redirect")
            assert result.access_token == "at"
            assert result.email is None

    def test_no_project_id_fetches(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            _encode_state,
            exchange_code_for_tokens,
        )

        mock_token_resp = MagicMock()
        mock_token_resp.ok = True
        mock_token_resp.json.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_in": 3600,
        }

        mock_user_resp = MagicMock()
        mock_user_resp.ok = False

        state = _encode_state("v")  # no project_id

        with (
            patch("requests.post", return_value=mock_token_resp),
            patch("requests.get", return_value=mock_user_resp),
            patch(
                "code_puppy.plugins.antigravity_oauth.oauth._fetch_project_id",
                return_value="fetched-proj",
            ),
        ):
            result = exchange_code_for_tokens("code", state, "http://redirect")
            assert result.project_id == "fetched-proj"


class TestOAuthHelpers:
    def test_decode_state_invalid(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _decode_state

        with pytest.raises(ValueError):
            _decode_state("!!!invalid!!!")

    def test_build_auth_url_no_redirect(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            OAuthContext,
            build_authorization_url,
        )

        ctx = OAuthContext(state="s", code_verifier="v", code_challenge="c")
        with pytest.raises(RuntimeError):
            build_authorization_url(ctx)


class TestAntigravityOAuthHelpers:
    def test_urlsafe_b64encode(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _urlsafe_b64encode

        result = _urlsafe_b64encode(b"hello")
        assert isinstance(result, str)
        assert "=" not in result

    def test_generate_code_verifier(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _generate_code_verifier

        v = _generate_code_verifier()
        assert len(v) > 10

    def test_compute_code_challenge(self):
        from code_puppy.plugins.antigravity_oauth.oauth import _compute_code_challenge

        c = _compute_code_challenge("verifier")
        assert isinstance(c, str)

    def test_prepare_oauth_context(self):
        from code_puppy.plugins.antigravity_oauth.oauth import prepare_oauth_context

        ctx = prepare_oauth_context()
        assert ctx.state
        assert ctx.code_verifier
        assert ctx.code_challenge

    def test_assign_redirect_uri(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            OAuthContext,
            assign_redirect_uri,
        )

        ctx = OAuthContext(state="s", code_verifier="v", code_challenge="c")
        uri = assign_redirect_uri(ctx, 12345)
        assert "12345" in uri
        assert ctx.redirect_uri == uri

    def test_build_authorization_url(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            OAuthContext,
            build_authorization_url,
        )

        ctx = OAuthContext(state="s", code_verifier="v", code_challenge="c")
        ctx.redirect_uri = "http://localhost:8080/cb"
        url = build_authorization_url(ctx, "proj-123")
        assert "accounts.google.com" in url
        assert "code_challenge" in url

    def test_encode_decode_state_roundtrip(self):
        from code_puppy.plugins.antigravity_oauth.oauth import (
            _decode_state,
            _encode_state,
        )

        state = _encode_state("my_verifier", "my_project")
        v, p = _decode_state(state)
        assert v == "my_verifier"
        assert p == "my_project"

    def test_decode_state_non_string_project(self):
        """Test _decode_state when projectId is not a string."""
        import base64
        import json

        payload = json.dumps({"verifier": "v", "projectId": 123}).encode()
        state = base64.urlsafe_b64encode(payload).decode().rstrip("=")
        from code_puppy.plugins.antigravity_oauth.oauth import _decode_state

        v, p = _decode_state(state)
        assert v == "v"
        assert p == ""


class TestAntigravityCustomHelp:
    def test_returns_entries(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _custom_help,
        )

        entries = _custom_help()
        names = [n for n, _ in entries]
        assert "antigravity-auth" in names


class TestRegisterModelTypes:
    def test_returns_handler(self):
        from code_puppy.plugins.antigravity_oauth.register_callbacks import (
            _register_model_types,
        )

        types = _register_model_types()
        assert len(types) == 1
        assert types[0]["type"] == "antigravity"
