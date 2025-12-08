"""Catalog MCP server installation logic.

Handles prompting users for configuration and installing
MCP servers from the catalog.
"""

import os
from typing import Dict, Optional

from code_puppy.messaging import emit_info, emit_success, emit_warning

# Helpful hints for common environment variables
ENV_VAR_HINTS = {
    "GITHUB_TOKEN": "💡 Get from https://github.com/settings/tokens",
    "GITLAB_TOKEN": "💡 Get from GitLab > Preferences > Access Tokens",
    "SLACK_TOKEN": "💡 Get from https://api.slack.com/apps",
    "DISCORD_TOKEN": "💡 Get from Discord Developer Portal",
    "OPENAI_API_KEY": "💡 Get from https://platform.openai.com/api-keys",
    "ANTHROPIC_API_KEY": "💡 Get from https://console.anthropic.com/",
    "GOOGLE_CLIENT_ID": "💡 Get from Google Cloud Console",
    "GOOGLE_CLIENT_SECRET": "💡 Get from Google Cloud Console",
    "NOTION_TOKEN": "💡 Get from https://www.notion.so/my-integrations",
    "CONFLUENCE_TOKEN": "💡 Get from Atlassian API tokens",
    "JIRA_TOKEN": "💡 Get from Atlassian API tokens",
    "GRAFANA_TOKEN": "💡 Get from Grafana > Configuration > API Keys",
    "DATABASE_URL": "💡 Format: postgresql://user:pass@host:5432/db",
}


def get_env_var_hint(env_var: str) -> str:
    """Get a helpful hint for common environment variables."""
    return ENV_VAR_HINTS.get(env_var, "")


def prompt_for_server_config(manager, server) -> Optional[Dict]:
    """Prompt user for server configuration (env vars and cmd args).

    Args:
        manager: MCP manager instance
        server: Server template from catalog

    Returns:
        Dict with 'name', 'env_vars', 'cmd_args' if successful, None if cancelled
    """
    from code_puppy.config import set_config_value

    from .utils import find_server_id_by_name

    emit_info(f"\n📦 Installing: {server.display_name}\n")
    emit_info(f"   {server.description}\n")

    # Get custom name
    default_name = server.name
    try:
        name_input = input(f"  Server name [{default_name}]: ").strip()
        server_name = name_input if name_input else default_name
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning("Installation cancelled")
        return None

    # Check if server already exists
    existing = find_server_id_by_name(manager, server_name)
    if existing:
        try:
            override = input(
                f"  Server '{server_name}' exists. Override? [y/N]: "
            ).strip()
            if not override.lower().startswith("y"):
                emit_warning("Installation cancelled")
                return None
        except (KeyboardInterrupt, EOFError):
            emit_info("")
            emit_warning("Installation cancelled")
            return None

    env_vars = {}
    cmd_args = {}

    # Collect environment variables
    required_env_vars = server.get_environment_vars()
    if required_env_vars:
        emit_info("\n  🔑 Environment Variables:")
        for var in required_env_vars:
            current_value = os.environ.get(var, "")
            if current_value:
                emit_info(f"     ✓ {var}: Already set")
                env_vars[var] = current_value
            else:
                try:
                    hint = get_env_var_hint(var)
                    if hint:
                        emit_info(f"     {hint}")
                    value = input(f"     Enter {var}: ").strip()
                    if value:
                        env_vars[var] = value
                        # Save to config for future use
                        set_config_value(var, value)
                        os.environ[var] = value
                except (KeyboardInterrupt, EOFError):
                    emit_info("")
                    emit_warning("Installation cancelled")
                    return None

    # Collect command line arguments
    required_cmd_args = server.get_command_line_args()
    if required_cmd_args:
        emit_info("\n  ⚙️ Configuration:")
        for arg_config in required_cmd_args:
            name = arg_config.get("name", "")
            prompt_text = arg_config.get("prompt", name)
            default = arg_config.get("default", "")
            required = arg_config.get("required", True)

            prompt_str = f"     {prompt_text}"
            if default:
                prompt_str += f" [{default}]"
            if not required:
                prompt_str += " (optional)"

            try:
                value = input(f"{prompt_str}: ").strip()
                if value:
                    cmd_args[name] = value
                elif default:
                    cmd_args[name] = default
                elif required:
                    emit_warning(f"Required value '{name}' not provided")
                    return None
            except (KeyboardInterrupt, EOFError):
                emit_info("")
                emit_warning("Installation cancelled")
                return None

    return {
        "name": server_name,
        "env_vars": env_vars,
        "cmd_args": cmd_args,
    }


def install_catalog_server(manager, server, config: Dict) -> bool:
    """Install a server from the catalog with the given configuration.

    Args:
        manager: MCP manager instance
        server: Server template from catalog
        config: Configuration dict with 'name', 'env_vars', 'cmd_args'

    Returns:
        True if successful, False otherwise
    """
    import uuid

    from .wizard_utils import install_server_from_catalog

    server_name = config["name"]
    env_vars = config["env_vars"]
    cmd_args = config["cmd_args"]

    # Generate a group ID for messages
    group_id = f"mcp-install-{uuid.uuid4().hex[:8]}"

    emit_info(f"\n  📦 Installing {server.display_name} as '{server_name}'...")

    success = install_server_from_catalog(
        manager, server, server_name, env_vars, cmd_args, group_id
    )

    if success:
        emit_success(f"\n  ✅ Successfully installed '{server_name}'!")
        emit_info(f"  Use '/mcp start {server_name}' to start the server.\n")
    else:
        emit_warning("\n  ❌ Installation failed.\n")

    return success
