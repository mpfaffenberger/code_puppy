"""Register custom commands for the Agent Marketplace plugin.

This module hooks into code-puppy's callback system to expose marketplace
commands to the CLI.
"""

from typing import Optional

from code_puppy.callbacks import register_callback

_registered = False


def _custom_help() -> list[tuple[str, str]]:
    """Provide help text for marketplace commands.

    Returns:
        List of (command_name, description) tuples.
    """
    return [
        ("upload-agent", "Upload a JSON agent to the marketplace"),
        ("search-agents", "Search for community agents"),
        ("download-agent", "Download an agent from the marketplace"),
        ("delete-agent", "Delete your agent from the marketplace"),
        ("my-agents", "List your published agents"),
    ]


def _handle_custom_command(command: str, name: str) -> Optional[bool]:
    """Route marketplace commands to handlers.

    Args:
        command: The full command string (e.g., "/search-agents data").
        name: The command name without slash (e.g., "search-agents").

    Returns:
        True if command was handled, None otherwise.
    """
    # Import handlers lazily to avoid circular imports
    if name == "upload-agent":
        from .upload import handle_upload_agent

        return handle_upload_agent(command)
    elif name == "search-agents":
        from .search import handle_search_agents

        return handle_search_agents(command)
    elif name == "download-agent":
        from .download import handle_download_agent

        return handle_download_agent(command)
    elif name == "my-agents":
        from .my_agents import handle_my_agents

        return handle_my_agents(command)
    elif name == "delete-agent":
        from .delete import handle_delete_agent

        return handle_delete_agent(command)
    return None


def register_marketplace_commands() -> None:
    """Register all marketplace commands with the callback system.

    This function is safe to call multiple times - it will only register once.
    """
    global _registered
    if _registered:
        return

    register_callback("custom_command_help", _custom_help)
    register_callback("custom_command", _handle_custom_command)
    _registered = True
