"""
Claude Code OAuth Plugin for Code Puppy

This plugin provides OAuth authentication for Claude Code and automatically
adds available models to the extra_models.json configuration.

The plugin also includes a token refresh heartbeat for maintaining fresh
tokens during long-running agentic operations.
"""

from .token_refresh_heartbeat import (
    TokenRefreshHeartbeat,
    force_token_refresh,
    get_current_heartbeat,
    is_heartbeat_running,
    token_refresh_heartbeat_context,
)

__all__ = [
    "TokenRefreshHeartbeat",
    "token_refresh_heartbeat_context",
    "is_heartbeat_running",
    "get_current_heartbeat",
    "force_token_refresh",
]
