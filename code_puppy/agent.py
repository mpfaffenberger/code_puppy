import uuid
from pathlib import Path
from pydantic_ai.models.openai import OpenAIModelSettings, OpenAIResponsesModelSettings
from typing import Dict, Optional

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from code_puppy.message_history_processor import (
    get_model_context_length,
    message_history_accumulator,
)
from code_puppy.messaging.message_queue import (
    emit_error,
    emit_info,
    emit_system_message,
)
from code_puppy.model_factory import ModelFactory

# Tool registration is imported on demand
from code_puppy.tools.common import console


def load_puppy_rules():
    global PUPPY_RULES

    # Check for all 4 combinations of the rules file
    possible_paths = ["AGENTS.md", "AGENT.md", "agents.md", "agent.md"]

    for path_str in possible_paths:
        puppy_rules_path = Path(path_str)
        if puppy_rules_path.exists():
            with open(puppy_rules_path, "r") as f:
                puppy_rules = f.read()
                return puppy_rules

    # If none of the files exist, return None
    return None


# Load at import
PUPPY_RULES = load_puppy_rules()
_LAST_MODEL_NAME = None
_code_generation_agent = None


def _load_mcp_servers(extra_headers: Optional[Dict[str, str]] = None):
    """Load MCP servers using the new manager while maintaining backward compatibility."""
    from code_puppy.config import get_value, load_mcp_server_configs
    from code_puppy.mcp import ServerConfig, get_mcp_manager

    # Check if MCP servers are disabled
    mcp_disabled = get_value("disable_mcp_servers")
    if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
        emit_system_message("[dim]MCP servers disabled via config[/dim]")
        return []

    # Get the MCP manager singleton
    manager = get_mcp_manager()

    # Load configurations from legacy file for backward compatibility
    configs = load_mcp_server_configs()
    if not configs:
        # Check if manager already has servers (could be from new system)
        existing_servers = manager.list_servers()
        if not existing_servers:
            emit_system_message("[dim]No MCP servers configured[/dim]")
            return []
    else:
        # Register servers from legacy config with manager
        for name, conf in configs.items():
            try:
                # Convert legacy format to new ServerConfig
                server_config = ServerConfig(
                    id=conf.get("id", f"{name}_{hash(name)}"),
                    name=name,
                    type=conf.get("type", "sse"),
                    enabled=conf.get("enabled", True),
                    config=conf,
                )

                # Check if server already registered
                existing = manager.get_server_by_name(name)
                if not existing:
                    # Register new server
                    manager.register_server(server_config)
                    emit_system_message(f"[dim]Registered MCP server: {name}[/dim]")
                else:
                    # Update existing server config if needed
                    if existing.config != server_config.config:
                        manager.update_server(existing.id, server_config)
                        emit_system_message(f"[dim]Updated MCP server: {name}[/dim]")

            except Exception as e:
                emit_error(f"Failed to register MCP server '{name}': {str(e)}")
                continue

    # Get pydantic-ai compatible servers from manager
    servers = manager.get_servers_for_agent()

    if servers:
        emit_system_message(
            f"[green]Successfully loaded {len(servers)} MCP server(s)[/green]"
        )
    else:
        emit_system_message(
            "[yellow]No MCP servers available (check if servers are enabled)[/yellow]"
        )

    return servers


def reload_mcp_servers():
    """Reload MCP servers without restarting the agent."""
    from code_puppy.mcp import get_mcp_manager

    manager = get_mcp_manager()
    # Reload configurations
    _load_mcp_servers()
    # Return updated servers
    return manager.get_servers_for_agent()


def reload_code_generation_agent(message_group: str | None):
    """Force-reload the agent, usually after a model change."""
    if message_group is None:
        message_group = str(uuid.uuid4())
    global _code_generation_agent, _LAST_MODEL_NAME
    from code_puppy.agents import clear_agent_cache
    from code_puppy.config import clear_model_cache, get_model_name

    # Clear both ModelFactory cache and config cache when force reloading
    clear_model_cache()
    clear_agent_cache()

    # Check if current agent has a pinned model
    from code_puppy.agents import get_current_agent_config

    agent_config = get_current_agent_config()
    agent_model_name = None
    if hasattr(agent_config, "get_model_name"):
        agent_model_name = agent_config.get_model_name()

    # Use agent-specific model if pinned, otherwise use global model
    model_name = agent_model_name if agent_model_name else get_model_name()
    emit_info(
        f"[bold cyan]Loading Model: {model_name}[/bold cyan]",
        message_group=message_group,
    )
    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    # Get agent-specific system prompt
    agent_config = get_current_agent_config()
    emit_info(
        f"[bold magenta]Loading Agent: {agent_config.display_name}[/bold magenta]",
        message_group=message_group,
    )

    instructions = agent_config.get_system_prompt()

    if PUPPY_RULES:
        instructions += f"\n{PUPPY_RULES}"

    mcp_servers = _load_mcp_servers()

    # Configure model settings with max_tokens if set
    model_settings_dict = {"seed": 42}
    output_tokens = max(2048, min(int(0.05 * get_model_context_length()) - 1024, 16384))
    console.print(f"Max output tokens per message: {output_tokens}")
    model_settings_dict["max_tokens"] = output_tokens


    model_settings = ModelSettings(**model_settings_dict)
    if "gpt-5" in model_name:
        model_settings_dict["openai_reasoning_effort"] = "high"
        model_settings_dict["extra_body"] = {
            "verbosity": "low"
        }
        model_settings = OpenAIModelSettings(**model_settings_dict)
    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=str,
        retries=3,
        mcp_servers=mcp_servers,
        history_processors=[message_history_accumulator],
        model_settings=model_settings,
    )

    # Register tools specified by the agent
    from code_puppy.tools import register_tools_for_agent

    agent_tools = agent_config.get_available_tools()
    register_tools_for_agent(agent, agent_tools)
    _code_generation_agent = agent
    _LAST_MODEL_NAME = model_name
    return _code_generation_agent


def get_code_generation_agent(force_reload=False, message_group: str | None = None):
    """
    Retrieve the agent with the currently configured model.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _code_generation_agent, _LAST_MODEL_NAME
    if message_group is None:
        message_group = str(uuid.uuid4())
    from code_puppy.config import get_model_name

    # Get the global model name
    global_model_name = get_model_name()

    # Check if current agent has a pinned model
    from code_puppy.agents import get_current_agent_config

    agent_config = get_current_agent_config()
    agent_model_name = None
    if hasattr(agent_config, "get_model_name"):
        agent_model_name = agent_config.get_model_name()

    # Use agent-specific model if pinned, otherwise use global model
    model_name = agent_model_name if agent_model_name else global_model_name

    if _code_generation_agent is None or _LAST_MODEL_NAME != model_name or force_reload:
        return reload_code_generation_agent(message_group)
    return _code_generation_agent


def get_custom_usage_limits():
    """
    Returns custom usage limits with configurable request limit.
    This centralizes the configuration of rate limiting for the agent.
    Default pydantic-ai limit is 50, this increases it to the configured value (default 100).
    """
    from code_puppy.config import get_message_limit

    return UsageLimits(request_limit=get_message_limit())
