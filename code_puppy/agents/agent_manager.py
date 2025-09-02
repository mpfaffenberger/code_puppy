"""Agent manager for handling different agent configurations."""

import importlib
import pkgutil
import uuid
from typing import Dict, Optional, Type, Union

from code_puppy.config import get_value, set_config_value

from ..callbacks import on_agent_reload
from ..messaging import emit_warning
from .base_agent import BaseAgent
from .json_agent import JSONAgent, discover_json_agents

# Registry of available agents (Python classes and JSON file paths)
_AGENT_REGISTRY: Dict[str, Union[Type[BaseAgent], str]] = {}
_CURRENT_AGENT_CONFIG: Optional[BaseAgent] = None


def _discover_agents(message_group_id: Optional[str] = None):
    """Dynamically discover all agent classes and JSON agents."""
    # Always clear the registry to force refresh
    _AGENT_REGISTRY.clear()

    # 1. Discover Python agent classes in the agents package
    import code_puppy.agents as agents_package

    # Iterate through all modules in the agents package
    for _, modname, _ in pkgutil.iter_modules(agents_package.__path__):
        if modname.startswith("_") or modname in [
            "base_agent",
            "json_agent",
            "agent_manager",
        ]:
            continue

        try:
            # Import the module
            module = importlib.import_module(f"code_puppy.agents.{modname}")

            # Look for BaseAgent subclasses
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAgent)
                    and attr not in [BaseAgent, JSONAgent]
                ):
                    # Create an instance to get the name
                    agent_instance = attr()
                    _AGENT_REGISTRY[agent_instance.name] = attr

        except Exception as e:
            # Skip problematic modules
            emit_warning(
                f"Warning: Could not load agent module {modname}: {e}",
                message_group=message_group_id,
            )
            continue

    # 2. Discover JSON agents in user directory
    try:
        json_agents = discover_json_agents()

        # Add JSON agents to registry (store file path instead of class)
        for agent_name, json_path in json_agents.items():
            _AGENT_REGISTRY[agent_name] = json_path

    except Exception as e:
        emit_warning(
            f"Warning: Could not discover JSON agents: {e}",
            message_group=message_group_id,
        )


def get_available_agents() -> Dict[str, str]:
    """Get a dictionary of available agents with their display names.

    Returns:
        Dict mapping agent names to display names.
    """
    # Generate a message group ID for this operation
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    agents = {}
    for name, agent_ref in _AGENT_REGISTRY.items():
        try:
            if isinstance(agent_ref, str):  # JSON agent (file path)
                agent_instance = JSONAgent(agent_ref)
            else:  # Python agent (class)
                agent_instance = agent_ref()
            agents[name] = agent_instance.display_name
        except Exception:
            agents[name] = name.title()  # Fallback

    return agents


def get_current_agent_name() -> str:
    """Get the name of the currently active agent.

    Returns:
        The name of the current agent, defaults to 'code-puppy'.
    """
    return get_value("current_agent") or "code-puppy"


def set_current_agent(agent_name: str) -> bool:
    """Set the current agent by name.

    Args:
        agent_name: The name of the agent to set as current.

    Returns:
        True if the agent was set successfully, False if agent not found.
    """
    # Generate a message group ID for agent switching
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)
    # Clear the cached config when switching agents
    global _CURRENT_AGENT_CONFIG
    _CURRENT_AGENT_CONFIG = None
    agent_obj = load_agent_config(agent_name)
    on_agent_reload(agent_obj.id, agent_name)
    set_config_value("current_agent", agent_name)
    return True


def get_current_agent_config() -> BaseAgent:
    """Get the current agent configuration.

    Returns:
        The current agent configuration instance.
    """
    global _CURRENT_AGENT_CONFIG

    if _CURRENT_AGENT_CONFIG is None:
        _CURRENT_AGENT_CONFIG = load_agent_config(get_current_agent_name())

    return _CURRENT_AGENT_CONFIG


def load_agent_config(agent_name: str) -> BaseAgent:
    """Load an agent configuration by name.

    Args:
        agent_name: The name of the agent to load.

    Returns:
        The agent configuration instance.

    Raises:
        ValueError: If the agent is not found.
    """
    # Generate a message group ID for agent loading
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    if agent_name not in _AGENT_REGISTRY:
        # Fallback to code-puppy if agent not found
        if "code-puppy" in _AGENT_REGISTRY:
            agent_name = "code-puppy"
        else:
            raise ValueError(
                f"Agent '{agent_name}' not found and no fallback available"
            )

    agent_ref = _AGENT_REGISTRY[agent_name]
    if isinstance(agent_ref, str):  # JSON agent (file path)
        return JSONAgent(agent_ref)
    else:  # Python agent (class)
        return agent_ref()


def get_agent_descriptions() -> Dict[str, str]:
    """Get descriptions for all available agents.

    Returns:
        Dict mapping agent names to their descriptions.
    """
    # Generate a message group ID for this operation
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)

    descriptions = {}
    for name, agent_ref in _AGENT_REGISTRY.items():
        try:
            if isinstance(agent_ref, str):  # JSON agent (file path)
                agent_instance = JSONAgent(agent_ref)
            else:  # Python agent (class)
                agent_instance = agent_ref()
            descriptions[name] = agent_instance.description
        except Exception:
            descriptions[name] = "No description available"

    return descriptions


def clear_agent_cache():
    """Clear the cached agent configuration to force reload."""
    global _CURRENT_AGENT_CONFIG
    _CURRENT_AGENT_CONFIG = None


def refresh_agents():
    """Refresh the agent discovery to pick up newly created agents.

    This clears the agent registry cache and forces a rediscovery of all agents.
    """
    # Generate a message group ID for agent refreshing
    message_group_id = str(uuid.uuid4())
    _discover_agents(message_group_id=message_group_id)


# Agent-aware message history functions
def get_current_agent_message_history():
    """Get the message history for the currently active agent.

    Returns:
        List of messages from the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    return current_agent.get_message_history()


def set_current_agent_message_history(history):
    """Set the message history for the currently active agent.

    Args:
        history: List of messages to set as the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.set_message_history(history)


def clear_current_agent_message_history():
    """Clear the message history for the currently active agent."""
    current_agent = get_current_agent_config()
    current_agent.clear_message_history()


def append_to_current_agent_message_history(message):
    """Append a message to the currently active agent's history.

    Args:
        message: Message to append to the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.append_to_message_history(message)


def extend_current_agent_message_history(history):
    """Extend the currently active agent's message history with multiple messages.

    Args:
        history: List of messages to append to the current agent's conversation history.
    """
    current_agent = get_current_agent_config()
    current_agent.extend_message_history(history)


def get_current_agent_compacted_message_hashes():
    """Get the set of compacted message hashes for the currently active agent.

    Returns:
        Set of hashes for messages that have been compacted/summarized.
    """
    current_agent = get_current_agent_config()
    return current_agent.get_compacted_message_hashes()


def add_current_agent_compacted_message_hash(message_hash: str):
    """Add a message hash to the current agent's set of compacted message hashes.

    Args:
        message_hash: Hash of a message that has been compacted/summarized.
    """
    current_agent = get_current_agent_config()
    current_agent.add_compacted_message_hash(message_hash)
