"""Agent management system for code-puppy.

This module provides functionality for switching between different agent
configurations, each with their own system prompts and tool sets.
"""

from .agent_manager import (
    get_available_agents,
    get_current_agent_config,
    set_current_agent,
    load_agent_config,
    get_agent_descriptions,
    clear_agent_cache,
    refresh_agents,
)

__all__ = [
    "get_available_agents",
    "get_current_agent_config",
    "set_current_agent",
    "load_agent_config",
    "get_agent_descriptions",
    "clear_agent_cache",
    "refresh_agents",
]
