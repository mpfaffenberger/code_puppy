"""Persistent agent-mode state."""

from __future__ import annotations

from enum import Enum

from code_puppy.config import get_value, set_value


class AgentMode(str, Enum):
    PLAN = "plan"
    BUILD = "build"


def get_agent_mode() -> AgentMode:
    raw = (get_value("agent_mode") or AgentMode.BUILD.value).strip().lower()
    try:
        return AgentMode(raw)
    except ValueError:
        return AgentMode.BUILD


def set_agent_mode(mode: AgentMode | str) -> AgentMode:
    resolved = mode if isinstance(mode, AgentMode) else AgentMode(mode.strip().lower())
    set_value("agent_mode", resolved.value)
    return resolved


def toggle_agent_mode() -> AgentMode:
    current = get_agent_mode()
    return set_agent_mode(
        AgentMode.PLAN if current is AgentMode.BUILD else AgentMode.BUILD
    )
