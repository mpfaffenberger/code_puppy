"""Agent management system for code-puppy.

This module provides functionality for switching between different agent
configurations, each with their own system prompts and tool sets.
"""

from .agent_manager import (
    get_agent_descriptions,
    get_available_agents,
    get_current_agent,
    load_agent,
    refresh_agents,
    set_current_agent,
)

__all__ = [
    "get_available_agents",
    "get_current_agent",
    "set_current_agent",
    "load_agent",
    "get_agent_descriptions",
    "refresh_agents",
]
