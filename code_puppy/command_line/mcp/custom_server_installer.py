"""Custom MCP server installation logic.

Handles prompting users for custom server configuration and installing
custom MCP servers with JSON configuration.
"""

import json

from code_puppy.command_line.utils import safe_input
from code_puppy.i18n import t
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning

# Example configurations for each server type
CUSTOM_SERVER_EXAMPLES = {
    "stdio": """{
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
  "env": {
    "NODE_ENV": "production"
  },
  "timeout": 30
}""",
    "http": """{
  "type": "http",
  "url": "http://localhost:8080/mcp",
  "headers": {
    "Authorization": "Bearer $MY_API_KEY",
    "Content-Type": "application/json"
  },
  "timeout": 30
}""",
    "sse": """{
  "type": "sse",
  "url": "http://localhost:8080/sse",
  "headers": {
    "Authorization": "Bearer $MY_API_KEY"
  }
}""",
}


def prompt_and_install_custom_server(manager) -> bool:
    """Prompt for custom server configuration and install it.

    Args:
        manager: MCP manager instance

    Returns:
        True if successful, False otherwise
    """
    from code_puppy.command_line.mcp.mcp_servers_store import upsert_mcp_server
    from code_puppy.mcp_.managed_server import ServerConfig

    from .utils import find_server_id_by_name

    emit_info(t("mcp.custom_server.header"))
    emit_info(t("mcp.custom_server.subheader"))

    # Get server name
    try:
        server_name = safe_input("  Server name: ")
        if not server_name:
            emit_warning(t("mcp.custom_server.name_required"))
            return False
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning(t("mcp.custom_server.cancelled"))
        return False

    # Check if server already exists
    existing = find_server_id_by_name(manager, server_name)
    if existing:
        try:
            override = safe_input(f"  Server '{server_name}' exists. Override? [y/N]: ")
            if not override.lower().startswith("y"):
                emit_warning(t("mcp.custom_server.cancelled"))
                return False
        except (KeyboardInterrupt, EOFError):
            emit_info("")
            emit_warning(t("mcp.custom_server.cancelled"))
            return False

    # Select server type
    emit_info(t("mcp.custom_server.type_header"))
    emit_info(t("mcp.custom_server.type_stdio"))
    emit_info(t("mcp.custom_server.type_http"))
    emit_info(t("mcp.custom_server.type_sse"))

    try:
        type_choice = safe_input("  Enter choice [1-3]: ")
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning(t("mcp.custom_server.cancelled"))
        return False

    type_map = {"1": "stdio", "2": "http", "3": "sse"}
    server_type = type_map.get(type_choice)
    if not server_type:
        emit_warning(t("mcp.custom_server.invalid_choice"))
        return False

    # Show example for selected type
    example = CUSTOM_SERVER_EXAMPLES.get(server_type, "{}")
    emit_info(t("mcp.custom_server.example_header", server_type=server_type))
    for line in example.split("\n"):
        emit_info(f"    {line}")
    emit_info("")

    # Get JSON configuration
    emit_info(t("mcp.custom_server.json_prompt"))

    json_lines = []
    empty_count = 0
    try:
        while True:
            line = safe_input("")
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                json_lines.append(line)
            else:
                empty_count = 0
                json_lines.append(line)
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning(t("mcp.custom_server.cancelled"))
        return False

    json_str = "\n".join(json_lines).strip()
    if not json_str:
        emit_warning(t("mcp.custom_server.no_config"))
        return False

    # Parse JSON
    try:
        config_dict = json.loads(json_str)
    except json.JSONDecodeError as e:
        emit_error(t("mcp.custom_server.invalid_json", error=e))
        return False

    # Validate required fields based on type
    if server_type == "stdio":
        if "command" not in config_dict:
            emit_error(t("mcp.custom_server.stdio_missing_command"))
            return False
    elif server_type in ("http", "sse"):
        if "url" not in config_dict:
            emit_error(t("mcp.custom_server.url_missing", server_type=server_type))
            return False

    # Create server config
    try:
        server_config = ServerConfig(
            id=server_name,
            name=server_name,
            type=server_type,
            enabled=True,
            config=config_dict,
        )

        # Register with manager
        server_id = manager.register_server(server_config)

        if not server_id:
            emit_error(t("mcp.custom_server.register_failed"))
            return False

        # Save to mcp_servers.json for persistence
        save_config = config_dict.copy()
        save_config["type"] = server_type
        upsert_mcp_server(server_name, save_config)

        emit_success(t("mcp.custom_server.success", server_name=server_name))
        emit_info(t("mcp.custom_server.start_hint", server_name=server_name))

        # Strict opt-in: prompt the user to bind this server to agents.
        try:
            from code_puppy.command_line.mcp_binding_menu import (
                prompt_bind_after_install_sync,
            )

            prompt_bind_after_install_sync(server_name)
        except Exception as exc:
            emit_warning(t("mcp.custom_server.bind_skipped", error=exc))

        return True

    except Exception as e:
        emit_error(t("mcp.custom_server.add_failed", error=e))
        return False
