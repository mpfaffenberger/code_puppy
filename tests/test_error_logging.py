"""Tests for the error_logging module."""

import os
import tempfile
from unittest.mock import patch

from code_puppy.error_logging import (
    get_log_file_path,
    get_logs_dir,
    log_error,
    log_error_message,
)


class TestErrorLogging:
    """Tests for error logging functionality."""

    def test_get_logs_dir_returns_path(self):
        """Test that get_logs_dir returns a valid path."""
        logs_dir = get_logs_dir()
        assert logs_dir is not None
        assert isinstance(logs_dir, str)
        assert "logs" in logs_dir

    def test_get_log_file_path_returns_path(self):
        """Test that get_log_file_path returns a valid path."""
        log_path = get_log_file_path()
        assert log_path is not None
        assert isinstance(log_path, str)
        assert log_path.endswith("errors.log")

    def test_ensure_logs_dir_creates_directory(self):
        """Test that _ensure_logs_dir creates the logs directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_logs_dir = os.path.join(tmpdir, "logs")
            with patch("code_puppy.error_logging.LOGS_DIR", test_logs_dir):
                from code_puppy import error_logging

                original_logs_dir = error_logging.LOGS_DIR
                error_logging.LOGS_DIR = test_logs_dir
                try:
                    error_logging._ensure_logs_dir()
                    assert os.path.exists(test_logs_dir)
                    assert os.path.isdir(test_logs_dir)
                finally:
                    error_logging.LOGS_DIR = original_logs_dir

    def test_log_error_writes_to_file(self):
        """Test that log_error writes error details to the log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_logs_dir = os.path.join(tmpdir, "logs")
            test_log_file = os.path.join(test_logs_dir, "errors.log")

            from code_puppy import error_logging

            original_logs_dir = error_logging.LOGS_DIR
            original_log_file = error_logging.ERROR_LOG_FILE
            error_logging.LOGS_DIR = test_logs_dir
            error_logging.ERROR_LOG_FILE = test_log_file

            try:
                # Create a test exception
                try:
                    raise ValueError("Test error message")
                except Exception as e:
                    log_error(e, context="Test context")

                # Verify the log file was created and contains expected content
                assert os.path.exists(test_log_file)
                with open(test_log_file, "r") as f:
                    content = f.read()
                    assert "ValueError" in content
                    assert "Test error message" in content
                    assert "Test context" in content
                    assert "Traceback" in content
            finally:
                error_logging.LOGS_DIR = original_logs_dir
                error_logging.ERROR_LOG_FILE = original_log_file

    def test_log_error_without_traceback(self):
        """Test that log_error can skip traceback."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_logs_dir = os.path.join(tmpdir, "logs")
            test_log_file = os.path.join(test_logs_dir, "errors.log")

            from code_puppy import error_logging

            original_logs_dir = error_logging.LOGS_DIR
            original_log_file = error_logging.ERROR_LOG_FILE
            error_logging.LOGS_DIR = test_logs_dir
            error_logging.ERROR_LOG_FILE = test_log_file

            try:
                try:
                    raise RuntimeError("No traceback test")
                except Exception as e:
                    log_error(e, include_traceback=False)

                with open(test_log_file, "r") as f:
                    content = f.read()
                    assert "RuntimeError" in content
                    assert "No traceback test" in content
                    # Traceback should not be in the content
                    assert "Traceback:" not in content
            finally:
                error_logging.LOGS_DIR = original_logs_dir
                error_logging.ERROR_LOG_FILE = original_log_file

    def test_log_error_message_writes_to_file(self):
        """Test that log_error_message writes a simple message to the log file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_logs_dir = os.path.join(tmpdir, "logs")
            test_log_file = os.path.join(test_logs_dir, "errors.log")

            from code_puppy import error_logging

            original_logs_dir = error_logging.LOGS_DIR
            original_log_file = error_logging.ERROR_LOG_FILE
            error_logging.LOGS_DIR = test_logs_dir
            error_logging.ERROR_LOG_FILE = test_log_file

            try:
                log_error_message("Simple error message", context="Simple context")

                assert os.path.exists(test_log_file)
                with open(test_log_file, "r") as f:
                    content = f.read()
                    assert "Simple error message" in content
                    assert "Simple context" in content
            finally:
                error_logging.LOGS_DIR = original_logs_dir
                error_logging.ERROR_LOG_FILE = original_log_file

    def test_log_error_handles_write_failure_silently(self):
        """Test that log_error doesn't raise if it can't write."""
        from code_puppy import error_logging

        original_log_file = error_logging.ERROR_LOG_FILE
        # Point to an invalid path that can't be written
        error_logging.ERROR_LOG_FILE = "/nonexistent/path/that/cant/exist/errors.log"

        try:
            # This should not raise an exception
            try:
                raise ValueError("Test")
            except Exception as e:
                log_error(e)  # Should silently fail
        finally:
            error_logging.ERROR_LOG_FILE = original_log_file

    def test_log_error_message_handles_write_failure_silently(self):
        """Test that log_error_message doesn't raise if it can't write."""
        from code_puppy import error_logging

        original_log_file = error_logging.ERROR_LOG_FILE
        error_logging.ERROR_LOG_FILE = "/nonexistent/path/that/cant/exist/errors.log"

        try:
            # This should not raise an exception
            log_error_message("Test message")  # Should silently fail
        finally:
            error_logging.ERROR_LOG_FILE = original_log_file
