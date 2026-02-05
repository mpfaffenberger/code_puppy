"""Test suite for Claude Code OAuth CLI command handlers.

Covers custom command routing, authentication flow, status checks, and logout.
"""

import time
from unittest.mock import MagicMock, patch

import pytest


class TestCustomHelpCommands:
    """Test custom command help output."""

    def test_custom_help_returns_commands(self):
        """Test that custom help returns expected commands."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import _custom_help

        commands = _custom_help()

        assert isinstance(commands, list)
        assert len(commands) == 3
        command_names = [name for name, _ in commands]
        assert "claude-code-auth" in command_names
        assert "claude-code-status" in command_names
        assert "claude-code-logout" in command_names

    def test_custom_help_has_descriptions(self):
        """Test that commands have descriptions."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import _custom_help

        commands = _custom_help()

        for name, description in commands:
            assert name
            assert description
            assert len(description) > 0


class TestHandleCustomCommand:
    """Test custom command handler routing."""

    def test_handle_custom_command_unknown_command(self):
        """Test unknown command returns None."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("/unknown", "unknown")

        assert result is None

    def test_handle_custom_command_no_name(self):
        """Test missing name returns None."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("/something", "")

        assert result is None

    def test_handle_custom_command_none_name(self):
        """Test None name returns None."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        result = _handle_custom_command("/something", None)

        assert result is None

    @patch("code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens")
    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
    )
    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks.set_model_and_reload_agent"
    )
    def test_handle_custom_command_auth(
        self, mock_set_model, mock_auth, mock_load_tokens
    ):
        """Test auth command handler."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_load_tokens.return_value = None  # No existing tokens

        with patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"):
            result = _handle_custom_command("/claude-code-auth", "claude-code-auth")

        assert result is True
        mock_auth.assert_called_once()
        mock_set_model.assert_called_once_with("claude-code-claude-opus-4-6")

    @patch("code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens")
    def test_handle_custom_command_status_not_authenticated(self, mock_load_tokens):
        """Test status command when not authenticated."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_load_tokens.return_value = None

        with patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"
        ):
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"
            ):
                result = _handle_custom_command(
                    "/claude-code-status", "claude-code-status"
                )

        assert result is True

    @patch("code_puppy.plugins.claude_code_oauth.register_callbacks.load_stored_tokens")
    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks.load_claude_models_filtered"
    )
    def test_handle_custom_command_status_authenticated(
        self, mock_load_models, mock_load_tokens
    ):
        """Test status command when authenticated."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        now = time.time()
        mock_load_tokens.return_value = {
            "access_token": "test_token",
            "expires_at": now + 3600,
        }
        mock_load_models.return_value = {
            "claude-code-opus": {"oauth_source": "claude-code-plugin"},
        }

        with patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
        ):
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"
            ):
                result = _handle_custom_command(
                    "/claude-code-status", "claude-code-status"
                )

        assert result is True

    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks.get_token_storage_path"
    )
    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks.remove_claude_code_models"
    )
    def test_handle_custom_command_logout(self, mock_remove_models, mock_token_path):
        """Test logout command."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_file = MagicMock()
        mock_file.exists.return_value = True
        mock_token_path.return_value = mock_file
        mock_remove_models.return_value = 2

        with patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_info"):
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ):
                result = _handle_custom_command(
                    "/claude-code-logout", "claude-code-logout"
                )

        assert result is True
        mock_file.unlink.assert_called_once()

    @patch(
        "code_puppy.plugins.claude_code_oauth.register_callbacks.get_token_storage_path"
    )
    def test_handle_custom_command_logout_no_tokens(self, mock_token_path):
        """Test logout when no tokens exist."""
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _handle_custom_command,
        )

        mock_file = MagicMock()
        mock_file.exists.return_value = False
        mock_token_path.return_value = mock_file

        with patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks.remove_claude_code_models"
        ) as mock_remove:
            mock_remove.return_value = 0
            with patch(
                "code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"
            ):
                result = _handle_custom_command(
                    "/claude-code-logout", "claude-code-logout"
                )

        assert result is True
        mock_file.unlink.assert_not_called()


class TestCallbackRegistration:
    """Test that callbacks are properly registered."""

    def test_callbacks_registered(self):
        """Test that plugin registers callbacks with the system."""
        from code_puppy.callbacks import get_callbacks

        # Ensure callbacks are loaded
        help_callbacks = get_callbacks("custom_command_help")
        command_callbacks = get_callbacks("custom_command")

        # Should have at least the Claude Code OAuth callbacks
        assert len(help_callbacks) > 0
        assert len(command_callbacks) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
