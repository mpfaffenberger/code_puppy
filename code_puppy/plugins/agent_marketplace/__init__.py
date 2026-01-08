"""Agent Marketplace CLI Plugin.

This plugin provides CLI commands for interacting with the Walmart Agent Marketplace,
allowing users to:
- Upload custom JSON agents to share with the community
- Search for agents published by other developers
- Download agents from the marketplace
- Manage their own published agents

Commands:
    /upload-agent    - Upload a JSON agent definition to the marketplace
    /search-agents   - Search for community agents by query or category
    /download-agent  - Download an agent by ID from the marketplace
    /my-agents       - List your own published agents
"""

from .api_client import (
    download_agent,
    get_agent_by_name,
    get_my_agents,
    run_async,
    search_agents,
    upload_agent,
    check_update,
)
from .register_callbacks import register_marketplace_commands

# Auto-register commands when plugin is imported
register_marketplace_commands()

__all__ = [
    "register_marketplace_commands",
    # API client functions
    "download_agent",
    "get_agent_by_name",
    "get_my_agents",
    "run_async",
    "search_agents",
    "upload_agent",
    "check_update",
]
