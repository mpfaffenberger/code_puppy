"""
MCP Configuration Wizard - Interactive setup for MCP servers.

Note: This module imports ServerConfig and get_mcp_manager directly from
.code_puppy.mcp.manager to avoid circular imports with the package __init__.py
"""

import re
from typing import Dict, Optional
from urllib.parse import urlparse

from rich.console import Console

from code_puppy.mcp.manager import ServerConfig, get_mcp_manager
from code_puppy.messaging import (
    emit_error,
    emit_info,
    emit_prompt,
    emit_success,
    emit_warning,
)

console = Console()


def prompt_ask(
    prompt_text: str, default: Optional[str] = None, choices: Optional[list] = None
) -> Optional[str]:
    """Helper function to replace rich.prompt.Prompt.ask with emit_prompt."""
    try:
        if default:
            full_prompt = f"{prompt_text} [{default}]"
        else:
            full_prompt = prompt_text

        if choices:
            full_prompt += f" ({'/'.join(choices)})"

        response = emit_prompt(full_prompt + ": ")

        # Handle default value
        if not response.strip() and default:
            return default

        # Handle choices validation
        if choices and response.strip() and response.strip() not in choices:
            emit_error(f"Invalid choice. Must be one of: {', '.join(choices)}")
            return None

        return response.strip() if response.strip() else None
    except Exception as e:
        emit_error(f"Input error: {e}")
        return None


def confirm_ask(prompt_text: str, default: bool = True) -> bool:
    """Helper function to replace rich.prompt.Confirm.ask with emit_prompt."""
    try:
        default_text = "[Y/n]" if default else "[y/N]"
        response = emit_prompt(f"{prompt_text} {default_text}: ")

        if not response.strip():
            return default

        response_lower = response.strip().lower()
        if response_lower in ["y", "yes", "true", "1"]:
            return True
        elif response_lower in ["n", "no", "false", "0"]:
            return False
        else:
            return default
    except Exception as e:
        emit_error(f"Input error: {e}")
        return default


class MCPConfigWizard:
    """Interactive wizard for configuring MCP servers."""

    def __init__(self):
        self.manager = get_mcp_manager()

    def run_wizard(self, group_id: str = None) -> Optional[ServerConfig]:
        """
        Run the interactive configuration wizard.

        Args:
            group_id: Optional message group ID for grouping related messages

        Returns:
            ServerConfig if successful, None if cancelled
        """
        if group_id is None:
            import uuid

            group_id = str(uuid.uuid4())

        emit_info("🧙 MCP Server Configuration Wizard", message_group=group_id)

        # Step 1: Server name
        name = self.prompt_server_name(group_id)
        if not name:
            return None

        # Step 2: Server type
        server_type = self.prompt_server_type(group_id)
        if not server_type:
            return None

        # Step 3: Type-specific configuration
        config = {}
        if server_type == "sse":
            config = self.prompt_sse_config(group_id)
        elif server_type == "http":
            config = self.prompt_http_config(group_id)
        elif server_type == "stdio":
            config = self.prompt_stdio_config(group_id)

        if not config:
            return None

        # Step 4: Create ServerConfig
        server_config = ServerConfig(
            id=f"{name}_{hash(name)}",
            name=name,
            type=server_type,
            enabled=True,
            config=config,
        )

        # Step 5: Show summary and confirm
        if self.prompt_confirmation(server_config, group_id):
            return server_config

        return None

    def prompt_server_name(self, group_id: str = None) -> Optional[str]:
        """Prompt for server name with validation."""
        while True:
            name = prompt_ask("Enter server name", default=None)

            if not name:
                if not confirm_ask("Cancel configuration?", default=False):
                    continue
                return None

            # Validate name
            if not self.validate_name(name):
                emit_error(
                    "Name must be alphanumeric with hyphens/underscores only",
                    message_group=group_id,
                )
                continue

            # Check uniqueness
            existing = self.manager.registry.get_by_name(name)
            if existing:
                emit_error(f"Server '{name}' already exists", message_group=group_id)
                continue

            return name

    def prompt_server_type(self, group_id: str = None) -> Optional[str]:
        """Prompt for server type."""
        emit_info("\nServer types:", message_group=group_id)
        emit_info(
            "  sse   - Server-Sent Events (HTTP streaming)", message_group=group_id
        )
        emit_info("  http  - HTTP/REST API", message_group=group_id)
        emit_info("  stdio - Local command (subprocess)", message_group=group_id)

        while True:
            server_type = prompt_ask(
                "Select server type", choices=["sse", "http", "stdio"], default="stdio"
            )

            if server_type in ["sse", "http", "stdio"]:
                return server_type

            emit_error(
                "Invalid type. Choose: sse, http, or stdio", message_group=group_id
            )

    def prompt_sse_config(self, group_id: str = None) -> Optional[Dict]:
        """Prompt for SSE server configuration."""
        emit_info("Configuring SSE server", message_group=group_id)

        # URL
        url = self.prompt_url("SSE", group_id)
        if not url:
            return None

        config = {"type": "sse", "url": url, "timeout": 30}

        # Headers (optional)
        if confirm_ask("Add custom headers?", default=False):
            headers = self.prompt_headers(group_id)
            if headers:
                config["headers"] = headers

        # Timeout
        timeout_str = prompt_ask("Connection timeout (seconds)", default="30")
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30

        return config

    def prompt_http_config(self, group_id: str = None) -> Optional[Dict]:
        """Prompt for HTTP server configuration."""
        emit_info("Configuring HTTP server", message_group=group_id)

        # URL
        url = self.prompt_url("HTTP", group_id)
        if not url:
            return None

        config = {"type": "http", "url": url, "timeout": 30}

        # Headers (optional)
        if confirm_ask("Add custom headers?", default=False):
            headers = self.prompt_headers(group_id)
            if headers:
                config["headers"] = headers

        # Timeout
        timeout_str = prompt_ask("Request timeout (seconds)", default="30")
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30

        return config

    def prompt_stdio_config(self, group_id: str = None) -> Optional[Dict]:
        """Prompt for Stdio server configuration."""
        emit_info("Configuring Stdio server", message_group=group_id)
        emit_info("Examples:", message_group=group_id)
        emit_info(
            "  • npx -y @modelcontextprotocol/server-filesystem /path",
            message_group=group_id,
        )
        emit_info("  • python mcp_server.py", message_group=group_id)
        emit_info("  • node server.js", message_group=group_id)

        # Command
        command = prompt_ask("Enter command", default=None)

        if not command:
            return None

        config = {"type": "stdio", "command": command, "args": [], "timeout": 30}

        # Arguments
        args_str = prompt_ask("Enter arguments (space-separated)", default="")
        if args_str:
            # Simple argument parsing (handles quoted strings)
            import shlex

            try:
                config["args"] = shlex.split(args_str)
            except ValueError:
                config["args"] = args_str.split()

        # Working directory (optional)
        cwd = prompt_ask("Working directory (optional)", default="")
        if cwd:
            import os

            if os.path.isdir(os.path.expanduser(cwd)):
                config["cwd"] = os.path.expanduser(cwd)
            else:
                emit_warning(
                    f"Directory '{cwd}' not found, ignoring", message_group=group_id
                )

        # Environment variables (optional)
        if confirm_ask("Add environment variables?", default=False):
            env = self.prompt_env_vars(group_id)
            if env:
                config["env"] = env

        # Timeout
        timeout_str = prompt_ask("Startup timeout (seconds)", default="30")
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30

        return config

    def prompt_url(self, server_type: str, group_id: str = None) -> Optional[str]:
        """Prompt for and validate URL."""
        while True:
            url = prompt_ask(f"Enter {server_type} server URL", default=None)

            if not url:
                if confirm_ask("Cancel configuration?", default=False):
                    return None
                continue

            if self.validate_url(url):
                return url

            emit_error(
                "Invalid URL. Must be http:// or https://", message_group=group_id
            )

    def prompt_headers(self, group_id: str = None) -> Dict[str, str]:
        """Prompt for HTTP headers."""
        headers = {}
        emit_info("Enter headers (format: Name: Value)", message_group=group_id)
        emit_info("Press Enter with empty name to finish", message_group=group_id)

        while True:
            name = prompt_ask("Header name", default="")
            if not name:
                break

            value = prompt_ask(f"Value for '{name}'", default="")
            headers[name] = value

            if not confirm_ask("Add another header?", default=True):
                break

        return headers

    def prompt_env_vars(self, group_id: str = None) -> Dict[str, str]:
        """Prompt for environment variables."""
        env = {}
        emit_info("Enter environment variables", message_group=group_id)
        emit_info("Press Enter with empty name to finish", message_group=group_id)

        while True:
            name = prompt_ask("Variable name", default="")
            if not name:
                break

            value = prompt_ask(f"Value for '{name}'", default="")
            env[name] = value

            if not confirm_ask("Add another variable?", default=True):
                break

        return env

    def validate_name(self, name: str) -> bool:
        """Validate server name."""
        # Allow alphanumeric, hyphens, and underscores
        return bool(re.match(r"^[a-zA-Z0-9_-]+$", name))

    def validate_url(self, url: str) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(url)
            return result.scheme in ("http", "https") and bool(result.netloc)
        except Exception:
            return False

    def validate_command(self, command: str) -> bool:
        """Check if command exists (basic check)."""
        import os
        import shutil

        # If it's a path, check if file exists
        if "/" in command or "\\" in command:
            return os.path.isfile(command)

        # Otherwise check if it's in PATH
        return shutil.which(command) is not None

    def test_connection(self, config: ServerConfig, group_id: str = None) -> bool:
        """
        Test connection to the configured server.

        Args:
            config: Server configuration to test

        Returns:
            True if connection successful, False otherwise
        """
        emit_info("Testing connection...", message_group=group_id)

        try:
            # Try to create the server instance
            managed = self.manager.get_server(config.id)
            if not managed:
                # Temporarily register to test
                self.manager.register_server(config)
                managed = self.manager.get_server(config.id)

            if managed:
                # Try to get the pydantic server (this validates config)
                server = managed.get_pydantic_server()
                if server:
                    emit_success("✓ Configuration valid", message_group=group_id)
                    return True

            emit_error("✗ Failed to create server instance", message_group=group_id)
            return False

        except Exception as e:
            emit_error(f"✗ Configuration error: {e}", message_group=group_id)
            return False

    def prompt_confirmation(self, config: ServerConfig, group_id: str = None) -> bool:
        """Show summary and ask for confirmation."""
        emit_info("Configuration Summary:", message_group=group_id)
        emit_info(f"  Name: {config.name}", message_group=group_id)
        emit_info(f"  Type: {config.type}", message_group=group_id)

        if config.type in ["sse", "http"]:
            emit_info(f"  URL: {config.config.get('url')}", message_group=group_id)
        elif config.type == "stdio":
            emit_info(
                f"  Command: {config.config.get('command')}", message_group=group_id
            )
            args = config.config.get("args", [])
            if args:
                emit_info(f"  Arguments: {' '.join(args)}", message_group=group_id)

        emit_info(
            f"  Timeout: {config.config.get('timeout', 30)}s", message_group=group_id
        )

        # Test connection if requested
        if confirm_ask("Test connection?", default=True):
            if not self.test_connection(config, group_id):
                if not confirm_ask("Continue anyway?", default=False):
                    return False

        return confirm_ask("Save this configuration?", default=True)


def run_add_wizard(group_id: str = None) -> bool:
    """
    Run the MCP add wizard and register the server.

    Args:
        group_id: Optional message group ID for grouping related messages

    Returns:
        True if server was added, False otherwise
    """
    if group_id is None:
        import uuid

        group_id = str(uuid.uuid4())

    wizard = MCPConfigWizard()
    config = wizard.run_wizard(group_id)

    if config:
        try:
            manager = get_mcp_manager()
            server_id = manager.register_server(config)

            emit_success(
                f"\n✅ Server '{config.name}' added successfully!",
                message_group=group_id,
            )
            emit_info(f"Server ID: {server_id}", message_group=group_id)
            emit_info("Use '/mcp list' to see all servers", message_group=group_id)
            emit_info(
                f"Use '/mcp start {config.name}' to start the server",
                message_group=group_id,
            )

            # Also save to mcp_servers.json for persistence
            import json
            import os

            from code_puppy.config import MCP_SERVERS_FILE

            # Load existing configs
            if os.path.exists(MCP_SERVERS_FILE):
                with open(MCP_SERVERS_FILE, "r") as f:
                    data = json.load(f)
                    servers = data.get("mcp_servers", {})
            else:
                servers = {}
                data = {"mcp_servers": servers}

            # Add new server
            servers[config.name] = config.config

            # Save back
            os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
            with open(MCP_SERVERS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            emit_info(
                f"[dim]Configuration saved to {MCP_SERVERS_FILE}[/dim]",
                message_group=group_id,
            )
            return True

        except Exception as e:
            emit_error(f"Failed to add server: {e}", message_group=group_id)
            return False
    else:
        emit_warning("Configuration cancelled", message_group=group_id)
        return False
