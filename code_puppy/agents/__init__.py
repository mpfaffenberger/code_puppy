"""Agent management system for code-puppy.

This module provides functionality for switching between different agent
configurations, each with their own system prompts and tool sets.
"""

from .agent_manager import (
    clone_agent,
    delete_clone_agent,
    get_agent_descriptions,
    get_available_agents,
    get_current_agent,
    is_clone_agent_name,
    load_agent,
    refresh_agents,
    set_current_agent,
)

from .deferred_reload import (
    DeferredReloadQueue,
    apply_agent_reloads,
    clear_pending_agent_reloads,
    request_agent_reload,
)
from . import run_stats  # noqa: F401
from .subagent_stream_handler import subagent_stream_handler

__all__ = [
    "clone_agent",
    "delete_clone_agent",
    "get_available_agents",
    "get_current_agent",
    "is_clone_agent_name",
    "set_current_agent",
    "load_agent",
    "get_agent_descriptions",
    "refresh_agents",
    "DeferredReloadQueue",
    "request_agent_reload",
    "apply_agent_reloads",
    "clear_pending_agent_reloads",
    "subagent_stream_handler",
]
