import os
from pathlib import Path
from typing import Dict, Optional

import pydantic
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from code_puppy.agent_prompts import get_system_prompt
from code_puppy.messaging.message_queue import (
    emit_error,
    emit_info,
    emit_system_message,
)
from code_puppy.model_factory import ModelFactory
from code_puppy.session_memory import SessionMemory
from code_puppy.tools import register_all_tools

from .http_utils import create_reopenable_async_client
from .state_management import message_history_accumulator

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


def _load_mcp_servers(walmart_headers: Optional[Dict[str, str]] = None):
    from code_puppy.config import get_value, load_mcp_server_configs

    # Check if MCP servers are disabled
    mcp_disabled = get_value("disable_mcp_servers")
    if mcp_disabled and str(mcp_disabled).lower() in ("1", "true", "yes", "on"):
        emit_system_message("[dim]MCP servers disabled via config[/dim]")
        return []

    configs = load_mcp_server_configs()
    if not configs:
        emit_system_message("[dim]No MCP servers configured[/dim]")
        return []
    servers = []
    for name, conf in configs.items():
        server_type = conf.get("type", "sse")
        url = conf.get("url")
        walmart_internal = conf.get("walmart_internal", False)
        http_client = (
            create_reopenable_async_client(headers=walmart_headers)
            if walmart_internal
            else None
        )

        try:
            if server_type == "http" and url:
                timeout = conf.get("timeout", 30)  # Default 30 seconds for HTTP servers
                emit_system_message(
                    f"Registering {'Internal ' if walmart_internal else ''}MCP Server (HTTP) - {url} (timeout: {timeout}s)"
                )
                # Note: MCPServerStreamableHTTP may not support timeout parameter - check pydantic-ai docs
                servers.append(
                    MCPServerStreamableHTTP(url=url, http_client=http_client)
                )
            elif (
                server_type == "stdio"
            ):  # Fixed: was "stdios" (plural), should be "stdio" (singular)
                command = conf.get("command")
                args = conf.get("args", [])
                timeout = conf.get(
                    "timeout", 30
                )  # Default 30 seconds for stdio servers (npm downloads can be slow)
                if command:
                    emit_system_message(
                        f"Registering MCP Server (Stdio) - {command} {args} (timeout: {timeout}s)"
                    )
                    servers.append(MCPServerStdio(command, args=args, timeout=timeout))
                else:
                    emit_error(f"MCP Server '{name}' missing required 'command' field")
            elif server_type == "sse" and url:
                timeout = conf.get("timeout", 30)  # Default 30 seconds for SSE servers
                emit_system_message(
                    f"Registering {'Internal ' if walmart_internal else ''} MCP Server (SSE) - {url} (timeout: {timeout}s)"
                )
                # Note: MCPServerSSE may not support timeout parameter - check pydantic-ai docs
                servers.append(MCPServerSSE(url=url, http_client=http_client))
            else:
                emit_error(
                    f"Invalid type '{server_type}' or missing URL for MCP server '{name}'"
                )
        except Exception as e:
            emit_error(f"Failed to register MCP server '{name}': {str(e)}")
            emit_info(f"Skipping server '{name}' and continuing with other servers...")
            # Continue with other servers instead of crashing
            continue

    if servers:
        emit_system_message(
            f"[green]Successfully registered {len(servers)} MCP server(s)[/green]"
        )
    else:
        emit_system_message(
            "[yellow]No MCP servers were successfully registered[/yellow]"
        )

    return servers


def reload_code_generation_agent():
    """Force-reload the agent, usually after a model change."""
    global _code_generation_agent, _LAST_MODEL_NAME
    from code_puppy.config import clear_model_cache, get_model_name

    # Clear both ModelFactory cache and config cache when force reloading
    clear_model_cache()

    model_name = get_model_name()
    emit_info(f"[bold cyan]Loading Model: {model_name}[/bold cyan]")
    from code_puppy.config import CONFIG_DIR

    models_config_path = os.path.join(CONFIG_DIR, "models.json")
    models_config = ModelFactory.load_config(models_config_path)
    model = ModelFactory.get_model(model_name, models_config)
    instructions = get_system_prompt()
    if PUPPY_RULES:
        instructions += f"\n{PUPPY_RULES}"

    mcp_servers = _load_mcp_servers()

    # Configure model settings with max_tokens if set
    from code_puppy.config import get_max_tokens

    model_settings_dict = {"seed": 42}
    max_tokens = get_max_tokens()
    if max_tokens is not None:
        model_settings_dict["max_tokens"] = max_tokens
        emit_info(f"[cyan]Using max_tokens: {max_tokens}[/cyan]")

    model_settings = ModelSettings(**model_settings_dict)
    agent = Agent(
        model=model,
        instructions=instructions,
        output_type=AgentResponse,
        retries=3,
        mcp_servers=mcp_servers,
        history_processors=[message_history_accumulator],
        model_settings=model_settings,
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
    Returns custom usage limits with increased request limit of 100 requests per minute.
    This centralizes the configuration of rate limiting for the agent.
    Default pydantic-ai limit is 50, this increases it to 100.
    """
    return UsageLimits(request_limit=100)
