"""Tests for /session_logging command."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.command_line.config_commands import handle_session_logging_command
from code_puppy.session_logging import (
    SessionLogger,
    get_global_session_logger,
    set_global_session_logger,
)
from code_puppy.session_logging.config_schema import SessionLoggingConfig


class TestSessionLoggingCommand:
    """Tests for /session_logging command handler."""

    def setup_method(self):
        """Reset global logger before each test."""
        set_global_session_logger(None)

    def teardown_method(self):
        """Clean up global logger after each test."""
        set_global_session_logger(None)

    def test_command_no_logger_configured(self):
        """Test command when logger is not configured."""
        with patch("code_puppy.messaging.emit_warning") as mock_warn:
            result = handle_session_logging_command("/session_logging")
            assert result is True
            mock_warn.assert_called_once()
            assert "not configured" in mock_warn.call_args[0][0]

    def test_command_status_enabled(self):
        """Test status command when logging is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            with patch("code_puppy.messaging.emit_info") as mock_info:
                result = handle_session_logging_command("/session_logging status")
                assert result is True
                mock_info.assert_called_once()
                call_args = mock_info.call_args[0][0]
                assert "enabled" in call_args
                assert str(logger.log_path) in call_args

    def test_command_status_disabled(self):
        """Test status command when logging is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            with patch("code_puppy.messaging.emit_info") as mock_info:
                result = handle_session_logging_command("/session_logging")
                assert result is True
                mock_info.assert_called_once()
                assert "disabled" in mock_info.call_args[0][0]

    def test_command_enable(self):
        """Test enabling logging via command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            assert logger.is_enabled() is False

            with patch(
                "code_puppy.messaging.emit_success"
            ) as mock_success:
                result = handle_session_logging_command("/session_logging on")
                assert result is True
                mock_success.assert_called_once()
                assert "enabled" in mock_success.call_args[0][0]

            assert logger.is_enabled() is True

    def test_command_enable_already_enabled(self):
        """Test enabling when already enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            with patch("code_puppy.messaging.emit_info") as mock_info:
                result = handle_session_logging_command("/session_logging on")
                assert result is True
                mock_info.assert_called_once()
                assert "already enabled" in mock_info.call_args[0][0]

    def test_command_disable(self):
        """Test disabling logging via command."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            assert logger.is_enabled() is True

            with patch(
                "code_puppy.messaging.emit_success"
            ) as mock_success:
                result = handle_session_logging_command("/session_logging off")
                assert result is True
                mock_success.assert_called_once()
                assert "disabled" in mock_success.call_args[0][0]

            assert logger.is_enabled() is False

    def test_command_disable_already_disabled(self):
        """Test disabling when already disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            with patch("code_puppy.messaging.emit_info") as mock_info:
                result = handle_session_logging_command("/session_logging off")
                assert result is True
                mock_info.assert_called_once()
                assert "already disabled" in mock_info.call_args[0][0]

    def test_command_toggle_on(self):
        """Test toggling from off to on."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            assert logger.is_enabled() is False

            with patch(
                "code_puppy.messaging.emit_success"
            ) as mock_success:
                result = handle_session_logging_command("/session_logging toggle")
                assert result is True
                mock_success.assert_called_once()
                assert "enabled" in mock_success.call_args[0][0]

            assert logger.is_enabled() is True

    def test_command_toggle_off(self):
        """Test toggling from on to off."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            assert logger.is_enabled() is True

            with patch(
                "code_puppy.messaging.emit_success"
            ) as mock_success:
                result = handle_session_logging_command("/session_logging toggle")
                assert result is True
                mock_success.assert_called_once()
                assert "disabled" in mock_success.call_args[0][0]

            assert logger.is_enabled() is False

    def test_command_invalid_subcommand(self):
        """Test invalid subcommand."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            with patch("code_puppy.messaging.emit_error") as mock_error:
                result = handle_session_logging_command("/session_logging invalid")
                assert result is True
                mock_error.assert_called_once()
                assert "Unknown subcommand" in mock_error.call_args[0][0]

    def test_get_session_logging_status_not_configured(self):
        """Test status helper when not configured."""
        from code_puppy.command_line.config_commands import _get_session_logging_status

        set_global_session_logger(None)
        status = _get_session_logging_status()
        assert "not configured" in status

    def test_get_session_logging_status_enabled(self):
        """Test status helper when enabled."""
        from code_puppy.command_line.config_commands import _get_session_logging_status

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=True, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            status = _get_session_logging_status()
            assert "enabled" in status
            assert "/session_logging" in status

    def test_get_session_logging_status_disabled(self):
        """Test status helper when disabled."""
        from code_puppy.command_line.config_commands import _get_session_logging_status

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = str(Path(tmpdir) / "test.md")
            config = SessionLoggingConfig(enabled=False, log_file=log_file)
            logger = SessionLogger(config, "test-session")
            set_global_session_logger(logger)

            status = _get_session_logging_status()
            assert "disabled" in status
            assert "/session_logging" in status
