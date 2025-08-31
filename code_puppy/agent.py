from pathlib import Path
from typing import Dict, Optional

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from code_puppy.agents import get_current_agent_config
from code_puppy.http_utils import (
    create_reopenable_async_client,
    resolve_env_var_in_header,
)
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
    puppy_rules_path = Path("AGENT.md")
    if puppy_rules_path.exists():
        with open(puppy_rules_path, "r") as f:
            puppy_rules = f.read()
            return puppy_rules


# Load at import
PUPPY_RULES = load_puppy_rules()
_LAST_MODEL_NAME = None
_code_generation_agent = None


def _load_mcp_servers(extra_headers: Optional[Dict[str, str]] = None):
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
        timeout = conf.get("timeout", 30)
        server_headers = {}
        if extra_headers:
            server_headers.update(extra_headers)
        user_headers = conf.get("headers") or {}
        if isinstance(user_headers, dict) and user_headers:
            try:
                user_headers = resolve_env_var_in_header(user_headers)
            except Exception:
                pass
            server_headers.update(user_headers)
        http_client = None

        try:
            if server_type == "http" and url:
                emit_system_message(
                    f"Registering MCP Server (HTTP) - {url} (timeout: {timeout}s, headers: {bool(server_headers)})"
                )
                http_client = create_reopenable_async_client(
                    timeout=timeout, headers=server_headers or None, verify=False
                )
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
                emit_system_message(
                    f"Registering MCP Server (SSE) - {url} (timeout: {timeout}s, headers: {bool(server_headers)})"
                )
                # For SSE, allow long reads; only bound connect timeout
                http_client = create_reopenable_async_client(
                    timeout=30, headers=server_headers or None, verify=False
                )
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
    from code_puppy.agents import clear_agent_cache

    # Clear both ModelFactory cache and config cache when force reloading
    clear_model_cache()
    clear_agent_cache()

    model_name = get_model_name()
    emit_info(f"[bold cyan]Loading Model: {model_name}[/bold cyan]")
    models_config = ModelFactory.load_config()
    model = ModelFactory.get_model(model_name, models_config)

    # Get agent-specific system prompt
    agent_config = get_current_agent_config()
    emit_info(
        f"[bold magenta]Loading Agent: {agent_config.display_name}[/bold magenta]"
    )

    instructions = agent_config.get_system_prompt()

    if PUPPY_RULES:
        instructions += f"\n{PUPPY_RULES}"

    mcp_servers = _load_mcp_servers()

    # Configure model settings with max_tokens if set
    model_settings_dict = {"seed": 42}
    output_tokens = min(int(0.05 * get_model_context_length()) - 1024, 16384)
    console.print(f"Max output tokens per message: {output_tokens}")
    model_settings_dict["max_tokens"] = output_tokens

    model_settings = ModelSettings(**model_settings_dict)
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
    Build UsageLimits based on the active model's configuration.

    Supports the following optional per-model fields in models.json:
    - max_requests_per_minute -> maps to UsageLimits.request_limit
    - max_token_limit_per_minute -> maps to UsageLimits.request_tokens_limit and total_tokens_limit

    Fallbacks:
    - request_limit defaults to 100 (doubling pydantic-ai's default of 50)
    - token limits remain unlimited if not specified
    """
    # Defaults
    request_limit = 100
    request_tokens_limit = None
    total_tokens_limit = None

    try:
        # Determine the active model and read its config
        from code_puppy.config import get_model_name
        model_name = get_model_name()
        models_config = ModelFactory.load_config()
        model_cfg = models_config.get(model_name) or {}

        # Apply per-model overrides if specified
        if isinstance(model_cfg, dict):
            rpm = model_cfg.get("max_requests_per_minute")
            if isinstance(rpm, int) and rpm > 0:
                request_limit = rpm

            tpm = model_cfg.get("max_token_limit_per_minute")
            if isinstance(tpm, int) and tpm > 0:
                # Apply to request tokens and total tokens to be conservative
                request_tokens_limit = tpm
                total_tokens_limit = tpm
    except Exception:
        # On any error, fall back to defaults silently
        pass

    return UsageLimits(
        request_limit=request_limit,
        request_tokens_limit=request_tokens_limit,
        total_tokens_limit=total_tokens_limit,
    )
