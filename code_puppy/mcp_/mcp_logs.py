"""
MCP Server Log Management.

This module provides persistent log file management for MCP servers.
Logs are stored in STATE_DIR/mcp_logs/<server_name>.log
"""

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from code_puppy.config import STATE_DIR

# Maximum log file size in bytes (5MB)
MAX_LOG_SIZE = 5 * 1024 * 1024

# Number of rotated logs to keep
MAX_ROTATED_LOGS = 3


def get_mcp_logs_dir() -> Path:
    """
    Get the directory for MCP server logs.

    Creates the directory if it doesn't exist.

    Returns:
        Path to the MCP logs directory
    """
    logs_dir = Path(STATE_DIR) / "mcp_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def get_log_file_path(server_name: str) -> Path:
    """
    Get the log file path for a specific server.

    Args:
        server_name: Name of the MCP server

    Returns:
        Path to the server's log file
    """
    # Sanitize server name for filesystem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)
    return get_mcp_logs_dir() / f"{safe_name}.log"


def rotate_log_if_needed(server_name: str) -> None:
    """
    Rotate log file if it exceeds MAX_LOG_SIZE.

    Args:
        server_name: Name of the MCP server
    """
    log_path = get_log_file_path(server_name)

    if not log_path.exists():
        return

    # Check if rotation is needed
    if log_path.stat().st_size < MAX_LOG_SIZE:
        return

    logs_dir = get_mcp_logs_dir()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)

    # Remove oldest rotated log if we're at the limit
    oldest = logs_dir / f"{safe_name}.log.{MAX_ROTATED_LOGS}"
    if oldest.exists():
        oldest.unlink()

    # Shift existing rotated logs
    for i in range(MAX_ROTATED_LOGS - 1, 0, -1):
        old_path = logs_dir / f"{safe_name}.log.{i}"
        new_path = logs_dir / f"{safe_name}.log.{i + 1}"
        if old_path.exists():
            old_path.rename(new_path)

    # Rotate current log
    rotated_path = logs_dir / f"{safe_name}.log.1"
    log_path.rename(rotated_path)


def write_log(server_name: str, message: str, level: str = "INFO") -> None:
    """
    Write a log message for a server.

    Args:
        server_name: Name of the MCP server
        message: Log message to write
        level: Log level (INFO, ERROR, WARN, DEBUG)
    """
    rotate_log_if_needed(server_name)

    log_path = get_log_file_path(server_name)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")


def read_logs(
    server_name: str, lines: Optional[int] = None, include_rotated: bool = False
) -> List[str]:
    """
    Read log lines for a server.

    Args:
        server_name: Name of the MCP server
        lines: Number of lines to return (from end). None means all lines.
        include_rotated: Whether to include rotated log files

    Returns:
        List of log lines (most recent last)
    """
    all_lines = []

    # Read rotated logs first (oldest to newest)
    if include_rotated:
        logs_dir = get_mcp_logs_dir()
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)

        for i in range(MAX_ROTATED_LOGS, 0, -1):
            rotated_path = logs_dir / f"{safe_name}.log.{i}"
            if rotated_path.exists():
                with open(rotated_path, "r", encoding="utf-8", errors="replace") as f:
                    all_lines.extend(f.read().splitlines())

    # Read current log
    log_path = get_log_file_path(server_name)
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines.extend(f.read().splitlines())

    # Return requested number of lines
    if lines is not None and lines > 0:
        return all_lines[-lines:]

    return all_lines


def clear_logs(server_name: str, include_rotated: bool = True) -> None:
    """
    Clear logs for a server.

    Args:
        server_name: Name of the MCP server
        include_rotated: Whether to also clear rotated log files
    """
    log_path = get_log_file_path(server_name)

    if log_path.exists():
        log_path.unlink()

    if include_rotated:
        logs_dir = get_mcp_logs_dir()
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)

        for i in range(1, MAX_ROTATED_LOGS + 1):
            rotated_path = logs_dir / f"{safe_name}.log.{i}"
            if rotated_path.exists():
                rotated_path.unlink()


def list_servers_with_logs() -> List[str]:
    """
    List all servers that have log files.

    Returns:
        List of server names with log files
    """
    logs_dir = get_mcp_logs_dir()
    servers = set()

    for path in logs_dir.glob("*.log*"):
        # Extract server name from filename
        name = path.stem
        # Remove .log suffix and rotation numbers
        name = name.replace(".log", "").rstrip(".0123456789")
        if name:
            servers.add(name)

    return sorted(servers)


def get_log_stats(server_name: str) -> dict:
    """
    Get statistics about a server's logs.

    Args:
        server_name: Name of the MCP server

    Returns:
        Dictionary with log statistics
    """
    log_path = get_log_file_path(server_name)

    stats = {
        "exists": log_path.exists(),
        "size_bytes": 0,
        "line_count": 0,
        "rotated_count": 0,
        "total_size_bytes": 0,
    }

    if log_path.exists():
        stats["size_bytes"] = log_path.stat().st_size
        stats["total_size_bytes"] = stats["size_bytes"]
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            stats["line_count"] = sum(1 for _ in f)

    # Count rotated logs
    logs_dir = get_mcp_logs_dir()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in server_name)

    for i in range(1, MAX_ROTATED_LOGS + 1):
        rotated_path = logs_dir / f"{safe_name}.log.{i}"
        if rotated_path.exists():
            stats["rotated_count"] += 1
            stats["total_size_bytes"] += rotated_path.stat().st_size

    return stats
