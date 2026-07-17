"""Agent management system for mist.

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

# Import for its side effect: auto-registers the TTFT/TG run-stats hooks.
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
    "subagent_stream_handler",
]
