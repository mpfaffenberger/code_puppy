"""Custom MCP server installation logic.

Handles prompting users for custom server configuration and installing
custom MCP servers with JSON configuration.
"""

import json
import os

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
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json"
  },
  "timeout": 30
}""",
    "sse": """{
  "type": "sse",
  "url": "http://localhost:8080/sse",
  "headers": {
    "Authorization": "Bearer YOUR_API_KEY"
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
    from code_puppy.config import MCP_SERVERS_FILE
    from code_puppy.mcp_.managed_server import ServerConfig

    from .utils import find_server_id_by_name

    emit_info("\n➕ Add Custom MCP Server\n")
    emit_info("  Configure your own MCP server using JSON.\n")

    # Get server name
    try:
        server_name = input("  Server name: ").strip()
        if not server_name:
            emit_warning("Server name is required")
            return False
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning("Cancelled")
        return False

    # Check if server already exists
    existing = find_server_id_by_name(manager, server_name)
    if existing:
        try:
            override = input(
                f"  Server '{server_name}' exists. Override? [y/N]: "
            ).strip()
            if not override.lower().startswith("y"):
                emit_warning("Cancelled")
                return False
        except (KeyboardInterrupt, EOFError):
            emit_info("")
            emit_warning("Cancelled")
            return False

    # Select server type
    emit_info("\n  Select server type:\n")
    emit_info("    1. 📟 stdio  - Local command (npx, python, uvx, etc.)")
    emit_info("    2. 🌐 http   - HTTP endpoint")
    emit_info("    3. 📡 sse    - Server-Sent Events\n")

    try:
        type_choice = input("  Enter choice [1-3]: ").strip()
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning("Cancelled")
        return False

    type_map = {"1": "stdio", "2": "http", "3": "sse"}
    server_type = type_map.get(type_choice)
    if not server_type:
        emit_warning("Invalid choice")
        return False

    # Show example for selected type
    example = CUSTOM_SERVER_EXAMPLES.get(server_type, "{}")
    emit_info(f"\n  Example {server_type} configuration:\n")
    for line in example.split("\n"):
        emit_info(f"    {line}")
    emit_info("")

    # Get JSON configuration
    emit_info("  Enter your JSON configuration (paste and press Enter twice):\n")

    json_lines = []
    empty_count = 0
    try:
        while True:
            line = input()
            if line.strip() == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                json_lines.append(line)
            else:
                empty_count = 0
                json_lines.append(line)
    except (KeyboardInterrupt, EOFError):
        emit_info("")
        emit_warning("Cancelled")
        return False

    json_str = "\n".join(json_lines).strip()
    if not json_str:
        emit_warning("No configuration provided")
        return False

    # Parse JSON
    try:
        config_dict = json.loads(json_str)
    except json.JSONDecodeError as e:
        emit_error(f"Invalid JSON: {e}")
        return False

    # Validate required fields based on type
    if server_type == "stdio":
        if "command" not in config_dict:
            emit_error("stdio servers require a 'command' field")
            return False
    elif server_type in ("http", "sse"):
        if "url" not in config_dict:
            emit_error(f"{server_type} servers require a 'url' field")
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
            emit_error("Failed to register server")
            return False

        # Save to mcp_servers.json for persistence
        if os.path.exists(MCP_SERVERS_FILE):
            with open(MCP_SERVERS_FILE, "r") as f:
                data = json.load(f)
                servers = data.get("mcp_servers", {})
        else:
            servers = {}
            data = {"mcp_servers": servers}

        # Add new server with type
        save_config = config_dict.copy()
        save_config["type"] = server_type
        servers[server_name] = save_config

        # Save back
        os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
        with open(MCP_SERVERS_FILE, "w") as f:
            json.dump(data, f, indent=2)

        emit_success(f"\n  ✅ Successfully added custom server '{server_name}'!")
        emit_info(f"  Use '/mcp start {server_name}' to start the server.\n")
        return True

    except Exception as e:
        emit_error(f"Failed to add server: {e}")
        return False
