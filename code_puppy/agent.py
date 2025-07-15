import os
from pathlib import Path

import pydantic
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerSSE
from pydantic_ai.usage import UsageLimits

from code_puppy.agent_prompts import get_system_prompt
from code_puppy.model_factory import ModelFactory
from code_puppy.session_memory import SessionMemory
from code_puppy.tools import register_all_tools
from code_puppy.tools.common import console


# Puppy rules loader
PUPPY_RULES_PATH = Path(".puppy_rules")
PUPPY_RULES = None


def load_puppy_rules(path=None):
    global PUPPY_RULES
    rules_path = Path(path) if path else PUPPY_RULES_PATH
    if rules_path.exists():
        with open(rules_path, "r") as f:
            PUPPY_RULES = f.read()
    else:
        PUPPY_RULES = None


# Load at import
load_puppy_rules()


class AgentResponse(pydantic.BaseModel):
    """Represents a response from the agent."""

    output_message: str = pydantic.Field(
        ..., description="The final output message to display to the user"
    )
    awaiting_user_input: bool = pydantic.Field(
        False, description="True if user input is needed to continue the task"
    )


# --- NEW DYNAMIC AGENT LOGIC ---
_LAST_MODEL_NAME = None
_code_generation_agent = None
_session_memory = None


def session_memory():
    """
    Returns a singleton SessionMemory instance to allow agent and tools to persist and recall context/history.
    """
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemory()
    return _session_memory


def _load_mcp_servers():
    from code_puppy.config import load_mcp_server_configs

    configs = load_mcp_server_configs()
    servers = []
    for name, conf in configs.items():
        url = conf.get("url")
        if url:
            console.print(f"Registering MCP Server - {url}")
            servers.append(MCPServerSSE(url))
    return servers


def reload_code_generation_agent():
    """Force-reload the agent, usually after a model change."""
    global _code_generation_agent, _LAST_MODEL_NAME
    from code_puppy.config import get_model_name, clear_model_cache
    
    # Clear both ModelFactory cache and config cache when force reloading
    clear_model_cache()

    model_name = get_model_name()
    console.print(f"[bold cyan]Loading Model: {model_name}[/bold cyan]")
    from code_puppy.config import CONFIG_DIR

    models_config_path = os.path.join(CONFIG_DIR, "models.json")
    models_config = ModelFactory.load_config(models_config_path)
    model = ModelFactory.get_model(model_name, models_config)
    instructions = get_system_prompt()
    if PUPPY_RULES:
        instructions += f"\n{PUPPY_RULES}"

    mcp_servers = _load_mcp_servers()
    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=AgentResponse,
        retries=3,
        mcp_servers=mcp_servers,
    )
    register_all_tools(agent)
    _code_generation_agent = agent
    _LAST_MODEL_NAME = model_name
    # NEW: Log session event
    try:
        session_memory().log_task(f"Agent loaded with model: {model_name}")
    except Exception:
        pass
    return _code_generation_agent


def get_code_generation_agent(force_reload=False):
    """
    Retrieve the agent with the currently configured model.
    Forces a reload if the model has changed, or if force_reload is passed.
    """
    global _code_generation_agent, _LAST_MODEL_NAME
    from code_puppy.config import get_model_name

    model_name = get_model_name()
    if _code_generation_agent is None or _LAST_MODEL_NAME != model_name or force_reload:
        return reload_code_generation_agent()
    return _code_generation_agent


def get_custom_usage_limits():
    """
    Returns custom usage limits with increased request limit.
    This centralizes the configuration of rate limiting for the agent.
    """
    return UsageLimits(request_limit=100)
