"""
MCP Command Utilities - Shared helper functions for MCP command handlers.

Provides common utility functions used across multiple MCP command modules.
"""

from typing import Optional

from rich.text import Text

from code_puppy.mcp.managed_server import ServerState


def format_state_indicator(state: ServerState) -> Text:
    """
    Format a server state with appropriate color and icon.

    Args:
        state: Server state to format

    Returns:
        Rich Text object with colored state indicator
    """
    state_map = {
        ServerState.RUNNING: ("✓ Run", "green"),
        ServerState.STOPPED: ("✗ Stop", "red"),
        ServerState.STARTING: ("↗ Start", "yellow"),
        ServerState.STOPPING: ("↙ Stop", "yellow"),
        ServerState.ERROR: ("⚠ Err", "red"),
        ServerState.QUARANTINED: ("⏸ Quar", "yellow"),
    }

    display, color = state_map.get(state, ("? Unk", "dim"))
    return Text(display, style=color)


def format_uptime(uptime_seconds: Optional[float]) -> str:
    """
    Format uptime in a human-readable format.

    Args:
        uptime_seconds: Uptime in seconds, or None

    Returns:
        Formatted uptime string
    """
    if uptime_seconds is None or uptime_seconds <= 0:
        return "-"

    # Convert to readable format
    if uptime_seconds < 60:
        return f"{int(uptime_seconds)}s"
    elif uptime_seconds < 3600:
        minutes = int(uptime_seconds // 60)
        seconds = int(uptime_seconds % 60)
        return f"{minutes}m {seconds}s"
    else:
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"


def find_server_id_by_name(manager, server_name: str) -> Optional[str]:
    """
    Find a server ID by its name.

    Args:
        manager: MCP manager instance
        server_name: Name of the server to find

    Returns:
        Server ID if found, None otherwise
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        servers = manager.list_servers()
        for server in servers:
            if server.name.lower() == server_name.lower():
                return server.id
        return None
    except Exception as e:
        logger.error(f"Error finding server by name '{server_name}': {e}")
        return None


def suggest_similar_servers(
    manager, server_name: str, group_id: Optional[str] = None
) -> None:
    """
    Suggest similar server names when a server is not found.

    Args:
        manager: MCP manager instance
        server_name: The server name that was not found
        group_id: Optional message group ID for grouping related messages
    """
    import logging

    from code_puppy.messaging import emit_info

    logger = logging.getLogger(__name__)

    try:
        servers = manager.list_servers()
        if not servers:
            emit_info("No servers are registered", message_group=group_id)
            return

        # Simple suggestion based on partial matching
        suggestions = []
        server_name_lower = server_name.lower()

        for server in servers:
            if server_name_lower in server.name.lower():
                suggestions.append(server.name)

        if suggestions:
            emit_info(f"Did you mean: {', '.join(suggestions)}", message_group=group_id)
        else:
            server_names = [s.name for s in servers]
            emit_info(
                f"Available servers: {', '.join(server_names)}", message_group=group_id
            )

    except Exception as e:
        logger.error(f"Error suggesting similar servers: {e}")
