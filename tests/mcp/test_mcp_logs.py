"""
Tests for MCP server log management.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from code_puppy.mcp_.mcp_logs import (
    MAX_LOG_SIZE,
    clear_logs,
    get_log_stats,
    get_mcp_logs_dir,
    list_servers_with_logs,
    read_logs,
    rotate_log_if_needed,
    write_log,
)


@pytest.fixture
def temp_logs_dir(tmp_path):
    """Create a temporary logs directory."""
    logs_dir = tmp_path / "mcp_logs"
    logs_dir.mkdir()
    with patch("code_puppy.mcp_.mcp_logs.get_mcp_logs_dir", return_value=logs_dir):
        # Also patch get_log_file_path to use temp directory
        def patched_get_log_file_path(server_name: str) -> Path:
            safe_name = "".join(
                c if c.isalnum() or c in "-_" else "_" for c in server_name
            )
            return logs_dir / f"{safe_name}.log"

        with patch(
            "code_puppy.mcp_.mcp_logs.get_log_file_path", patched_get_log_file_path
        ):
            yield logs_dir


class TestMCPLogs:
    """Tests for MCP log management functions."""

    def test_get_mcp_logs_dir_creates_directory(self, tmp_path):
        """Test that get_mcp_logs_dir creates the directory if it doesn't exist."""
        with patch("code_puppy.mcp_.mcp_logs.STATE_DIR", str(tmp_path)):
            logs_dir = get_mcp_logs_dir()
            assert logs_dir.exists()
            assert logs_dir.is_dir()
            assert logs_dir.name == "mcp_logs"

    def test_get_log_file_path_sanitizes_name(self, temp_logs_dir):
        """Test that server names are sanitized for filesystem safety."""
        # We need to test the real function, not the patched one
        with patch(
            "code_puppy.mcp_.mcp_logs.get_mcp_logs_dir", return_value=temp_logs_dir
        ):
            # Re-import to get fresh function
            from code_puppy.mcp_.mcp_logs import get_log_file_path

            path = get_log_file_path("my-server")
            assert path.name == "my-server.log"

            path = get_log_file_path("server/with/slashes")
            assert "/" not in path.name
            assert path.name == "server_with_slashes.log"

    def test_write_and_read_logs(self, temp_logs_dir):
        """Test writing and reading log messages."""
        server_name = "test-server"

        # Write some logs
        write_log(server_name, "First message", "INFO")
        write_log(server_name, "Second message", "ERROR")
        write_log(server_name, "Third message", "DEBUG")

        # Read all logs
        logs = read_logs(server_name)
        assert len(logs) == 3
        assert "First message" in logs[0]
        assert "[INFO]" in logs[0]
        assert "Second message" in logs[1]
        assert "[ERROR]" in logs[1]
        assert "Third message" in logs[2]
        assert "[DEBUG]" in logs[2]

    def test_read_logs_with_limit(self, temp_logs_dir):
        """Test reading a limited number of log lines."""
        server_name = "test-server"

        # Write many logs
        for i in range(10):
            write_log(server_name, f"Message {i}", "INFO")

        # Read only last 3
        logs = read_logs(server_name, lines=3)
        assert len(logs) == 3
        assert "Message 7" in logs[0]
        assert "Message 8" in logs[1]
        assert "Message 9" in logs[2]

    def test_read_logs_nonexistent_server(self, temp_logs_dir):
        """Test reading logs for a server that doesn't exist."""
        logs = read_logs("nonexistent-server")
        assert logs == []

    def test_clear_logs(self, temp_logs_dir):
        """Test clearing logs for a server."""
        server_name = "test-server"

        # Write some logs
        write_log(server_name, "Test message", "INFO")
        assert read_logs(server_name) != []

        # Clear logs
        clear_logs(server_name)

        # Verify logs are gone
        assert read_logs(server_name) == []

    def test_get_log_stats(self, temp_logs_dir):
        """Test getting log statistics."""
        server_name = "test-server"

        # No logs yet
        stats = get_log_stats(server_name)
        assert stats["exists"] is False
        assert stats["line_count"] == 0

        # Write some logs
        write_log(server_name, "Message 1", "INFO")
        write_log(server_name, "Message 2", "INFO")

        stats = get_log_stats(server_name)
        assert stats["exists"] is True
        assert stats["line_count"] == 2
        assert stats["size_bytes"] > 0

    def test_list_servers_with_logs(self, temp_logs_dir):
        """Test listing servers that have log files."""
        # Initially no servers
        with patch(
            "code_puppy.mcp_.mcp_logs.get_mcp_logs_dir", return_value=temp_logs_dir
        ):
            servers = list_servers_with_logs()
            assert servers == []

            # Create logs for some servers
            (temp_logs_dir / "server-a.log").write_text("log")
            (temp_logs_dir / "server-b.log").write_text("log")

            servers = list_servers_with_logs()
            assert "server-a" in servers
            assert "server-b" in servers

    def test_rotate_log_if_needed_small_file(self, temp_logs_dir):
        """Test that small files are not rotated."""
        server_name = "test-server"
        log_path = temp_logs_dir / f"{server_name}.log"

        # Write a small log
        log_path.write_text("Small content")

        # Should not rotate
        rotate_log_if_needed(server_name)

        # Original file should still exist, no rotated files
        assert log_path.exists()
        assert not (temp_logs_dir / f"{server_name}.log.1").exists()

    def test_rotate_log_if_needed_large_file(self, temp_logs_dir):
        """Test that large files are rotated."""
        server_name = "test-server"
        log_path = temp_logs_dir / f"{server_name}.log"

        # Write a large log (bigger than MAX_LOG_SIZE)
        large_content = "x" * (MAX_LOG_SIZE + 1000)
        log_path.write_text(large_content)

        # Should rotate
        rotate_log_if_needed(server_name)

        # Original file should be gone, rotated file should exist
        assert not log_path.exists()
        assert (temp_logs_dir / f"{server_name}.log.1").exists()
