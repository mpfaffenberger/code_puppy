"""Agent adapter — bridges Code Puppy's agent system to ACP.

Provides discovery and metadata helpers so the ACP server can
dynamically register every available Code Puppy agent without
hardcoding names or descriptions.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Maximum retry attempts when registry is being modified concurrently
_MAX_REGISTRY_RETRIES = 3


@dataclass(frozen=True)
class AgentInfo:
    """Immutable snapshot of a Code Puppy agent's public metadata."""

    name: str
    display_name: str
    description: str


async def discover_agents() -> List[AgentInfo]:
    """Discover all available Code Puppy agents.

    Merges data from ``get_available_agents()`` (name → display_name)
    and ``get_agent_descriptions()`` (name → description) into a flat
    list of :class:`AgentInfo` records.

    Agents that fail to load are logged and skipped — one broken agent
    must never take down the whole ACP server.
    """
    try:
        from code_puppy.agents import get_available_agents, get_agent_descriptions

        # Retry if registry is being modified concurrently (e.g. plugin loading)
        for attempt in range(_MAX_REGISTRY_RETRIES):
            try:
                agents_map: Dict[str, str] = get_available_agents()
                descriptions_map: Dict[str, str] = get_agent_descriptions()
                break
            except RuntimeError:
                if attempt == _MAX_REGISTRY_RETRIES - 1:
                    raise
                await asyncio.sleep(0.1)
    except Exception:
        logger.exception("Failed to query Code Puppy agent registry")
        return []

    agents: List[AgentInfo] = []
    for name, display_name in agents_map.items():
        description = descriptions_map.get(name, "No description available.")
        agents.append(
            AgentInfo(
                name=name,
                display_name=display_name,
                description=description,
            )
        )

    logger.info("Discovered %d Code Puppy agent(s) for ACP", len(agents))
    return agents


def discover_agents_sync() -> List[AgentInfo]:
    """Synchronous variant of :func:`discover_agents`.

    Used by helpers that run outside an async context (e.g.
    ``_build_config_options``).  The underlying registry calls are
    already synchronous — the async version only adds a retry sleep.
    """
    try:
        from code_puppy.agents import get_available_agents, get_agent_descriptions

        agents_map: Dict[str, str] = get_available_agents()
        descriptions_map: Dict[str, str] = get_agent_descriptions()
    except Exception:
        logger.debug("Failed to query agent registry (sync)", exc_info=True)
        return []

    agents: List[AgentInfo] = []
    for name, display_name in agents_map.items():
        description = descriptions_map.get(name, "No description available.")
        agents.append(
            AgentInfo(name=name, display_name=display_name, description=description)
        )
    return agents


def build_agent_metadata(agent_name: str) -> Optional[dict]:
    """Return ACP-compatible metadata for a single agent.

    This is useful for enriching ACP responses or building
    agent-card–style payloads later.

    Args:
        agent_name: The internal Code Puppy agent name.

    Returns:
        A dict with ``name``, ``display_name``, ``description``,
        and ``version`` keys.
    """
    try:
        from code_puppy.agents import get_available_agents, get_agent_descriptions

        available = get_available_agents()
        if agent_name not in available:
            return None
        display_name = available.get(agent_name, agent_name)
        description = get_agent_descriptions().get(
            agent_name, "No description available."
        )
    except Exception:
        logger.exception(
            "Failed to build metadata for agent '%s'", agent_name
        )
        display_name = agent_name
        description = "No description available."

    return {
        "name": agent_name,
        "display_name": display_name,
        "description": description,
        "version": "0.1.0",
    }
