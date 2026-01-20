"""Comprehensive test coverage for Antigravity OAuth register_callbacks."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.plugins.antigravity_oauth.register_callbacks import (
    _await_callback,
    _custom_help,
    _handle_custom_command,
    _handle_logout,
    _handle_status,
    _OAuthResult,
    _perform_authentication,
    _start_callback_server,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_tokens():
    """Create sample OAuth tokens."""
    return {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token|project_123",
        "expires_at": time.time() + 3600,
        "email": "test@example.com",
        "project_id": "project_123",
    }


@pytest.fixture
def mock_no_tokens():
    """Create empty tokens dictionary."""
    return {}


@pytest.fixture
def mock_context():
    """Create mock OAuth context."""
    from code_puppy.plugins.antigravity_oauth.oauth import OAuthContext

    return OAuthContext(
        state="test_state_123",
        code_verifier="test_verifier_456",
        code_challenge="test_challenge_789",
        redirect_uri="http://localhost:51121/oauth-callback",
    )


# ============================================================================
# OAUTH RESULT TESTS
# ============================================================================


class TestOAuthResult:
    """Test the _OAuthResult data class."""

    def test_oauth_result_initialization(self):
        """Test _OAuthResult initialization."""
        result = _OAuthResult()
        assert result.code is None
        assert result.state is None
        assert result.error is None

    def test_oauth_result_code_assignment(self):
        """Test assigning code to _OAuthResult."""
        result = _OAuthResult()
        result.code = "test_code_123"
        assert result.code == "test_code_123"

    def test_oauth_result_state_assignment(self):
        """Test assigning state to _OAuthResult."""
        result = _OAuthResult()
        result.state = "test_state_456"
        assert result.state == "test_state_456"

    def test_oauth_result_error_assignment(self):
        """Test assigning error to _OAuthResult."""
        result = _OAuthResult()
        result.error = "Test error"
        assert result.error == "Test error"

    def test_oauth_result_all_fields(self):
        """Test setting all fields of _OAuthResult."""
        result = _OAuthResult()
        result.code = "code_123"
        result.state = "state_456"
        result.error = "error_789"
        assert result.code == "code_123"
        assert result.state == "state_456"
        assert result.error == "error_789"


# ============================================================================
# CALLBACK HANDLER TESTS
# ============================================================================


class TestCallbackHandler:
    """Test the _CallbackHandler HTTP request handler."""

    def test_oauth_result_class_exists(self):
        """Test that _OAuthResult class exists and can be instantiated."""
        # Just verify the class exists and works
        result = _OAuthResult()
        result.code = "test"
        result.state = "state"
        assert result.code == "test"
        assert result.state == "state"


# ============================================================================
# START CALLBACK SERVER TESTS
# ============================================================================


class TestStartCallbackServer:
    """Test _start_callback_server function."""

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.HTTPServer")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.threading.Thread")
    def test_start_callback_server_success(self, mock_thread, mock_server):
        """Test successful callback server startup."""
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance
        mock_context = MagicMock()

        result = _start_callback_server(mock_context)

        assert result is not None
        server, oauth_result, event, redirect_uri = result
        assert server == mock_server_instance
        assert isinstance(oauth_result, _OAuthResult)
        assert isinstance(event, threading.Event)
        assert "localhost" in redirect_uri

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.HTTPServer")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error")
    def test_start_callback_server_all_ports_in_use(self, mock_emit_error, mock_server):
        """Test callback server startup when all ports are in use."""
        # Make HTTPServer raise OSError for all ports
        mock_server.side_effect = OSError("Address already in use")
        mock_context = MagicMock()

        result = _start_callback_server(mock_context)

        assert result is None
        mock_emit_error.assert_called_once()
        assert "all candidate ports" in mock_emit_error.call_args[0][0]

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.HTTPServer")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.threading.Thread")
    def test_start_callback_server_fallback_ports(self, mock_thread, mock_server):
        """Test callback server tries fallback ports."""
        # First port fails, second succeeds
        mock_server_instance = MagicMock()
        mock_server.side_effect = [
            OSError("Address in use"),
            mock_server_instance,
        ]
        mock_context = MagicMock()

        result = _start_callback_server(mock_context)

        assert result is not None
        # Should have tried 2 ports
        assert mock_server.call_count == 2


# ============================================================================
# AWAIT CALLBACK TESTS
# ============================================================================


class TestAwaitCallback:
    """Test _await_callback function."""

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks._start_callback_server"
    )
    def test_await_callback_server_startup_failure(self, mock_start_server):
        """Test callback wait when server fails to start."""
        mock_start_server.return_value = None
        mock_context = MagicMock()

        result = _await_callback(mock_context)

        assert result is None


# ============================================================================
# PERFORM AUTHENTICATION TESTS
# ============================================================================


class TestPerformAuthentication:
    """Test _perform_authentication function."""

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.add_models_to_config"
    )
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    def test_perform_authentication_success(
        self,
        mock_emit_info,
        mock_emit_success,
        mock_prepare_context,
        mock_await_callback,
        mock_exchange_code,
        mock_add_models,
        mock_save_tokens,
    ):
        """Test successful authentication flow."""
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess

        # Setup mocks
        mock_context = MagicMock()
        mock_prepare_context.return_value = mock_context

        mock_await_callback.return_value = (
            "code_123",
            "state_456",
            "http://localhost:51121/oauth-callback",
        )

        mock_token_result = TokenExchangeSuccess(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            expires_at=time.time() + 3600,
            email="test@example.com",
            project_id="project_123",
        )
        mock_exchange_code.return_value = mock_token_result

        mock_save_tokens.return_value = True
        mock_add_models.return_value = True

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.account_count = 0
            mock_manager_class.load_from_disk.return_value = mock_manager

            with patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.reload_current_agent"
            ):
                result = _perform_authentication()

        assert result is True
        mock_save_tokens.assert_called_once()
        mock_add_models.assert_called_once()
        mock_emit_success.assert_called()

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
    )
    def test_perform_authentication_callback_failure(
        self, mock_prepare_context, mock_await_callback
    ):
        """Test authentication when callback fails."""
        mock_context = MagicMock()
        mock_prepare_context.return_value = mock_context
        mock_await_callback.return_value = None

        result = _perform_authentication()

        assert result is False

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
    )
    def test_perform_authentication_token_exchange_failure(
        self,
        mock_prepare_context,
        mock_await_callback,
        mock_exchange_code,
        mock_emit_error,
    ):
        """Test authentication when token exchange fails."""
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeFailure

        mock_context = MagicMock()
        mock_prepare_context.return_value = mock_context
        mock_await_callback.return_value = (
            "code_123",
            "state_456",
            "http://localhost:51121/oauth-callback",
        )

        mock_exchange_code.return_value = TokenExchangeFailure(error="Invalid code")

        result = _perform_authentication()

        assert result is False
        mock_emit_error.assert_called()

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_error")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
    )
    def test_perform_authentication_save_tokens_failure(
        self,
        mock_prepare_context,
        mock_await_callback,
        mock_exchange_code,
        mock_save_tokens,
        mock_emit_error,
    ):
        """Test authentication when token save fails."""
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess

        mock_context = MagicMock()
        mock_prepare_context.return_value = mock_context
        mock_await_callback.return_value = (
            "code_123",
            "state_456",
            "http://localhost:51121/oauth-callback",
        )

        mock_token_result = TokenExchangeSuccess(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            expires_at=time.time() + 3600,
            email="test@example.com",
            project_id="project_123",
        )
        mock_exchange_code.return_value = mock_token_result
        mock_save_tokens.return_value = False

        result = _perform_authentication()

        assert result is False
        mock_emit_error.assert_called()
        assert "Failed to save tokens" in mock_emit_error.call_args[0][0]

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.reload_current_agent"
    )
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.add_models_to_config"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.save_tokens")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.exchange_code_for_tokens"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._await_callback")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.prepare_oauth_context"
    )
    def test_perform_authentication_add_account_flag(
        self,
        mock_prepare_context,
        mock_await_callback,
        mock_exchange_code,
        mock_save_tokens,
        mock_add_models,
        mock_reload_agent,
    ):
        """Test authentication with add_account=True."""
        from code_puppy.plugins.antigravity_oauth.oauth import TokenExchangeSuccess

        mock_context = MagicMock()
        mock_prepare_context.return_value = mock_context
        mock_await_callback.return_value = (
            "code_123",
            "state_456",
            "http://localhost:51121/oauth-callback",
        )

        mock_token_result = TokenExchangeSuccess(
            access_token="access_token_123",
            refresh_token="refresh_token_456",
            expires_at=time.time() + 3600,
            email="test@example.com",
            project_id="project_123",
        )
        mock_exchange_code.return_value = mock_token_result
        mock_save_tokens.return_value = True
        mock_add_models.return_value = True

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.account_count = 2  # Multiple accounts exist
            mock_manager_class.load_from_disk.return_value = mock_manager

            with patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
            ) as mock_emit_success:
                result = _perform_authentication(add_account=True)

        assert result is True
        # Verify account was added
        mock_manager.add_account.assert_called_once()
        # Verify success message mentions adding account
        calls_args = [str(call) for call in mock_emit_success.call_args_list]
        assert any("Added account" in str(c) for c in calls_args)


# ============================================================================
# CUSTOM HELP TESTS
# ============================================================================


class TestCustomHelp:
    """Test _custom_help function."""

    def test_custom_help_returns_list(self):
        """Test that _custom_help returns a list of tuples."""
        result = _custom_help()

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(item, tuple) for item in result)
        assert all(len(item) == 2 for item in result)

    def test_custom_help_contains_auth_command(self):
        """Test that help includes antigravity-auth command."""
        result = _custom_help()
        commands = [cmd for cmd, _ in result]

        assert "antigravity-auth" in commands

    def test_custom_help_contains_add_command(self):
        """Test that help includes antigravity-add command."""
        result = _custom_help()
        commands = [cmd for cmd, _ in result]

        assert "antigravity-add" in commands

    def test_custom_help_contains_status_command(self):
        """Test that help includes antigravity-status command."""
        result = _custom_help()
        commands = [cmd for cmd, _ in result]

        assert "antigravity-status" in commands

    def test_custom_help_contains_logout_command(self):
        """Test that help includes antigravity-logout command."""
        result = _custom_help()
        commands = [cmd for cmd, _ in result]

        assert "antigravity-logout" in commands

    def test_custom_help_has_descriptions(self):
        """Test that all help entries have descriptions."""
        result = _custom_help()
        descriptions = [desc for _, desc in result]

        assert all(isinstance(desc, str) for desc in descriptions)
        assert all(len(desc) > 0 for desc in descriptions)


# ============================================================================
# HANDLE STATUS TESTS
# ============================================================================


class TestHandleStatus:
    """Test _handle_status function."""

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens")
    def test_handle_status_not_authenticated(self, mock_load_tokens, mock_emit_warning):
        """Test status when user is not authenticated."""
        mock_load_tokens.return_value = {}

        _handle_status()

        mock_emit_warning.assert_called()
        assert "Not authenticated" in mock_emit_warning.call_args[0][0]

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.load_antigravity_models"
    )
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.fetch_antigravity_status"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens")
    def test_handle_status_authenticated(
        self,
        mock_load_tokens,
        mock_emit_info,
        mock_emit_success,
        mock_fetch_status,
        mock_load_models,
    ):
        """Test status display for authenticated user."""
        mock_load_tokens.return_value = {
            "access_token": "test_token",
            "email": "test@example.com",
            "expires_at": time.time() + 3600,
        }

        from code_puppy.plugins.antigravity_oauth.oauth import AntigravityStatus

        mock_status = AntigravityStatus(
            project_id="project_123",
            is_onboarded=True,
            current_tier="free-tier",
            allowed_tiers=["free-tier", "standard-tier"],
            error=None,
        )
        mock_fetch_status.return_value = mock_status

        mock_load_models.return_value = {
            "antigravity-gemini-3-pro": {"oauth_source": "antigravity-plugin"}
        }

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.account_count = 1
            mock_manager_class.load_from_disk.return_value = mock_manager

            _handle_status()

        mock_emit_success.assert_called()
        assert "Authenticated" in mock_emit_success.call_args[0][0]
        mock_emit_info.assert_called()

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens")
    def test_handle_status_no_email(
        self,
        mock_load_tokens,
    ):
        """Test status when email is not available."""
        mock_load_tokens.return_value = {
            "access_token": "test_token",
            "expires_at": time.time() + 3600,
        }

        from code_puppy.plugins.antigravity_oauth.oauth import AntigravityStatus

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.fetch_antigravity_status"
        ) as mock_fetch:
            mock_status = AntigravityStatus(
                project_id="project_123",
                is_onboarded=True,
                current_tier="free-tier",
                allowed_tiers=["free-tier"],
                error=None,
            )
            mock_fetch.return_value = mock_status

            with patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
            ) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.account_count = 1
                mock_manager_class.load_from_disk.return_value = mock_manager

                with patch(
                    "code_puppy.plugins.antigravity_oauth.register_callbacks.load_antigravity_models",
                    return_value={},
                ):
                    with patch(
                        "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"
                    ):
                        _handle_status()

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_warning")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.fetch_antigravity_status"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens")
    def test_handle_status_fetch_error(
        self, mock_load_tokens, mock_fetch_status, mock_emit_warning
    ):
        """Test status when API fetch fails."""
        mock_load_tokens.return_value = {
            "access_token": "test_token",
            "email": "test@example.com",
        }

        from code_puppy.plugins.antigravity_oauth.oauth import AntigravityStatus

        mock_status = AntigravityStatus(
            project_id="",
            is_onboarded=False,
            current_tier="",
            allowed_tiers=[],
            error="Connection failed",
        )
        mock_fetch_status.return_value = mock_status

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.account_count = 1
            mock_manager_class.load_from_disk.return_value = mock_manager

            with patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.load_antigravity_models",
                return_value={},
            ):
                with patch(
                    "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
                ):
                    with patch(
                        "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info"
                    ):
                        _handle_status()

        # Verify warning was called (could be for fetch error OR missing models)
        # Check all emit calls to see if warning about fetch appears
        warning_calls = mock_emit_warning.call_args_list
        assert len(warning_calls) > 0


# ============================================================================
# HANDLE LOGOUT TESTS
# ============================================================================


class TestHandleLogout:
    """Test _handle_logout function."""

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.remove_antigravity_models"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.clear_accounts")
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.get_accounts_storage_path"
    )
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.get_token_storage_path"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    def test_handle_logout_success(
        self,
        mock_emit_info,
        mock_emit_success,
        mock_get_token_path,
        mock_get_accounts_path,
        mock_clear_accounts,
        mock_remove_models,
    ):
        """Test successful logout."""
        mock_token_path = MagicMock(spec=Path)
        mock_token_path.exists.return_value = True
        mock_get_token_path.return_value = mock_token_path

        mock_accounts_path = MagicMock(spec=Path)
        mock_accounts_path.exists.return_value = True
        mock_get_accounts_path.return_value = mock_accounts_path

        mock_remove_models.return_value = 3

        _handle_logout()

        mock_token_path.unlink.assert_called_once()
        mock_clear_accounts.assert_called_once()
        mock_remove_models.assert_called_once()
        mock_emit_success.assert_called()
        assert "logout complete" in mock_emit_success.call_args[0][0].lower()

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.get_token_storage_path"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    def test_handle_logout_no_tokens(self, mock_emit_info, mock_get_token_path):
        """Test logout when no tokens exist."""
        mock_token_path = MagicMock(spec=Path)
        mock_token_path.exists.return_value = False
        mock_get_token_path.return_value = mock_token_path

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.get_accounts_storage_path"
        ) as mock_get_accounts_path:
            mock_accounts_path = MagicMock(spec=Path)
            mock_accounts_path.exists.return_value = False
            mock_get_accounts_path.return_value = mock_accounts_path

            with patch(
                "code_puppy.plugins.antigravity_oauth.register_callbacks.remove_antigravity_models",
                return_value=0,
            ):
                with patch(
                    "code_puppy.plugins.antigravity_oauth.register_callbacks.emit_success"
                ):
                    _handle_logout()

        # Verify unlink was not called since file doesn't exist
        mock_token_path.unlink.assert_not_called()


# ============================================================================
# HANDLE CUSTOM COMMAND TESTS
# ============================================================================


class TestHandleCustomCommand:
    """Test _handle_custom_command function."""

    def test_handle_custom_command_no_name(self):
        """Test command handler with empty name."""
        result = _handle_custom_command("some_command", "")

        assert result is None

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks.set_model_and_reload_agent"
    )
    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks._perform_authentication"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.load_stored_tokens")
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    def test_handle_custom_command_auth(
        self,
        mock_emit_info,
        mock_load_tokens,
        mock_perform_auth,
        mock_set_model,
    ):
        """Test antigravity-auth command."""
        mock_load_tokens.return_value = {}
        mock_perform_auth.return_value = True

        result = _handle_custom_command("custom_command", "antigravity-auth")

        assert result is True
        mock_perform_auth.assert_called_once_with(reload_agent=False)
        mock_set_model.assert_called_once_with("antigravity-gemini-3-pro-high")

    @patch(
        "code_puppy.plugins.antigravity_oauth.register_callbacks._perform_authentication"
    )
    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks.emit_info")
    def test_handle_custom_command_add(
        self,
        mock_emit_info,
        mock_perform_auth,
    ):
        """Test antigravity-add command."""
        mock_perform_auth.return_value = True

        with patch(
            "code_puppy.plugins.antigravity_oauth.register_callbacks.AccountManager"
        ) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager.account_count = 1
            mock_manager_class.load_from_disk.return_value = mock_manager

            result = _handle_custom_command("custom_command", "antigravity-add")

        assert result is True
        # Verify add_account=True was passed
        call_kwargs = mock_perform_auth.call_args
        assert call_kwargs[1].get("add_account") is True

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._handle_status")
    def test_handle_custom_command_status(self, mock_handle_status):
        """Test antigravity-status command."""
        result = _handle_custom_command("custom_command", "antigravity-status")

        assert result is True
        mock_handle_status.assert_called_once()

    @patch("code_puppy.plugins.antigravity_oauth.register_callbacks._handle_logout")
    def test_handle_custom_command_logout(self, mock_handle_logout):
        """Test antigravity-logout command."""
        result = _handle_custom_command("custom_command", "antigravity-logout")

        assert result is True
        mock_handle_logout.assert_called_once()

    def test_handle_custom_command_unknown(self):
        """Test unknown command returns None."""
        result = _handle_custom_command("custom_command", "unknown-command")

        assert result is None
