"""
MCP Configuration Wizard - Interactive setup for MCP servers.
"""

import re
from typing import Dict, Optional
from urllib.parse import urlparse

from code_puppy.mcp import ServerConfig, get_mcp_manager
from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from rich.prompt import Prompt, Confirm
from rich.console import Console

console = Console()


class MCPConfigWizard:
    """Interactive wizard for configuring MCP servers."""
    
    def __init__(self):
        self.manager = get_mcp_manager()
    
    def run_wizard(self) -> Optional[ServerConfig]:
        """
        Run the interactive configuration wizard.
        
        Returns:
            ServerConfig if successful, None if cancelled
        """
        console.print("\n[bold cyan]🧙 MCP Server Configuration Wizard[/bold cyan]\n")
        
        # Step 1: Server name
        name = self.prompt_server_name()
        if not name:
            return None
        
        # Step 2: Server type
        server_type = self.prompt_server_type()
        if not server_type:
            return None
        
        # Step 3: Type-specific configuration
        config = {}
        if server_type == "sse":
            config = self.prompt_sse_config()
        elif server_type == "http":
            config = self.prompt_http_config()
        elif server_type == "stdio":
            config = self.prompt_stdio_config()
        
        if not config:
            return None
        
        # Step 4: Create ServerConfig
        server_config = ServerConfig(
            id=f"{name}_{hash(name)}",
            name=name,
            type=server_type,
            enabled=True,
            config=config
        )
        
        # Step 5: Show summary and confirm
        if self.prompt_confirmation(server_config):
            return server_config
        
        return None
    
    def prompt_server_name(self) -> Optional[str]:
        """Prompt for server name with validation."""
        while True:
            name = Prompt.ask(
                "[yellow]Enter server name[/yellow]",
                default=None
            )
            
            if not name:
                if not Confirm.ask("Cancel configuration?", default=False):
                    continue
                return None
            
            # Validate name
            if not self.validate_name(name):
                emit_error("Name must be alphanumeric with hyphens/underscores only")
                continue
            
            # Check uniqueness
            existing = self.manager.registry.get_by_name(name)
            if existing:
                emit_error(f"Server '{name}' already exists")
                continue
            
            return name
    
    def prompt_server_type(self) -> Optional[str]:
        """Prompt for server type."""
        console.print("\n[cyan]Server types:[/cyan]")
        console.print("  [bold]sse[/bold]   - Server-Sent Events (HTTP streaming)")
        console.print("  [bold]http[/bold]  - HTTP/REST API")
        console.print("  [bold]stdio[/bold] - Local command (subprocess)")
        
        while True:
            server_type = Prompt.ask(
                "\n[yellow]Select server type[/yellow]",
                choices=["sse", "http", "stdio"],
                default="stdio"
            )
            
            if server_type in ["sse", "http", "stdio"]:
                return server_type
            
            emit_error("Invalid type. Choose: sse, http, or stdio")
    
    def prompt_sse_config(self) -> Optional[Dict]:
        """Prompt for SSE server configuration."""
        console.print("\n[cyan]Configuring SSE server[/cyan]")
        
        # URL
        url = self.prompt_url("SSE")
        if not url:
            return None
        
        config = {
            "type": "sse",
            "url": url,
            "timeout": 30
        }
        
        # Headers (optional)
        if Confirm.ask("Add custom headers?", default=False):
            headers = self.prompt_headers()
            if headers:
                config["headers"] = headers
        
        # Timeout
        timeout_str = Prompt.ask(
            "Connection timeout (seconds)",
            default="30"
        )
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30
        
        return config
    
    def prompt_http_config(self) -> Optional[Dict]:
        """Prompt for HTTP server configuration."""
        console.print("\n[cyan]Configuring HTTP server[/cyan]")
        
        # URL
        url = self.prompt_url("HTTP")
        if not url:
            return None
        
        config = {
            "type": "http",
            "url": url,
            "timeout": 30
        }
        
        # Headers (optional)
        if Confirm.ask("Add custom headers?", default=False):
            headers = self.prompt_headers()
            if headers:
                config["headers"] = headers
        
        # Timeout
        timeout_str = Prompt.ask(
            "Request timeout (seconds)",
            default="30"
        )
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30
        
        return config
    
    def prompt_stdio_config(self) -> Optional[Dict]:
        """Prompt for Stdio server configuration."""
        console.print("\n[cyan]Configuring Stdio server[/cyan]")
        console.print("[dim]Examples:[/dim]")
        console.print("[dim]  • npx -y @modelcontextprotocol/server-filesystem /path[/dim]")
        console.print("[dim]  • python mcp_server.py[/dim]")
        console.print("[dim]  • node server.js[/dim]")
        
        # Command
        command = Prompt.ask(
            "\n[yellow]Enter command[/yellow]",
            default=None
        )
        
        if not command:
            return None
        
        config = {
            "type": "stdio",
            "command": command,
            "args": [],
            "timeout": 30
        }
        
        # Arguments
        args_str = Prompt.ask(
            "Enter arguments (space-separated)",
            default=""
        )
        if args_str:
            # Simple argument parsing (handles quoted strings)
            import shlex
            try:
                config["args"] = shlex.split(args_str)
            except ValueError:
                config["args"] = args_str.split()
        
        # Working directory (optional)
        cwd = Prompt.ask(
            "Working directory (optional)",
            default=""
        )
        if cwd:
            import os
            if os.path.isdir(os.path.expanduser(cwd)):
                config["cwd"] = os.path.expanduser(cwd)
            else:
                emit_warning(f"Directory '{cwd}' not found, ignoring")
        
        # Environment variables (optional)
        if Confirm.ask("Add environment variables?", default=False):
            env = self.prompt_env_vars()
            if env:
                config["env"] = env
        
        # Timeout
        timeout_str = Prompt.ask(
            "Startup timeout (seconds)",
            default="30"
        )
        try:
            config["timeout"] = int(timeout_str)
        except ValueError:
            config["timeout"] = 30
        
        return config
    
    def prompt_url(self, server_type: str) -> Optional[str]:
        """Prompt for and validate URL."""
        while True:
            url = Prompt.ask(
                f"[yellow]Enter {server_type} server URL[/yellow]",
                default=None
            )
            
            if not url:
                if Confirm.ask("Cancel configuration?", default=False):
                    return None
                continue
            
            if self.validate_url(url):
                return url
            
            emit_error("Invalid URL. Must be http:// or https://")
    
    def prompt_headers(self) -> Dict[str, str]:
        """Prompt for HTTP headers."""
        headers = {}
        console.print("[dim]Enter headers (format: Name: Value)[/dim]")
        console.print("[dim]Press Enter with empty name to finish[/dim]")
        
        while True:
            name = Prompt.ask("Header name", default="")
            if not name:
                break
            
            value = Prompt.ask(f"Value for '{name}'", default="")
            headers[name] = value
            
            if not Confirm.ask("Add another header?", default=True):
                break
        
        return headers
    
    def prompt_env_vars(self) -> Dict[str, str]:
        """Prompt for environment variables."""
        env = {}
        console.print("[dim]Enter environment variables[/dim]")
        console.print("[dim]Press Enter with empty name to finish[/dim]")
        
        while True:
            name = Prompt.ask("Variable name", default="")
            if not name:
                break
            
            value = Prompt.ask(f"Value for '{name}'", default="")
            env[name] = value
            
            if not Confirm.ask("Add another variable?", default=True):
                break
        
        return env
    
    def validate_name(self, name: str) -> bool:
        """Validate server name."""
        # Allow alphanumeric, hyphens, and underscores
        return bool(re.match(r'^[a-zA-Z0-9_-]+$', name))
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format."""
        try:
            result = urlparse(url)
            return result.scheme in ('http', 'https') and bool(result.netloc)
        except Exception:
            return False
    
    def validate_command(self, command: str) -> bool:
        """Check if command exists (basic check)."""
        import shutil
        import os
        
        # If it's a path, check if file exists
        if '/' in command or '\\' in command:
            return os.path.isfile(command)
        
        # Otherwise check if it's in PATH
        return shutil.which(command) is not None
    
    def test_connection(self, config: ServerConfig) -> bool:
        """
        Test connection to the configured server.
        
        Args:
            config: Server configuration to test
            
        Returns:
            True if connection successful, False otherwise
        """
        emit_info("Testing connection...")
        
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
                    emit_success("✓ Configuration valid")
                    return True
            
            emit_error("✗ Failed to create server instance")
            return False
            
        except Exception as e:
            emit_error(f"✗ Configuration error: {e}")
            return False
    
    def prompt_confirmation(self, config: ServerConfig) -> bool:
        """Show summary and ask for confirmation."""
        console.print("\n[bold cyan]Configuration Summary:[/bold cyan]")
        console.print(f"  [bold]Name:[/bold] {config.name}")
        console.print(f"  [bold]Type:[/bold] {config.type}")
        
        if config.type in ["sse", "http"]:
            console.print(f"  [bold]URL:[/bold] {config.config.get('url')}")
        elif config.type == "stdio":
            console.print(f"  [bold]Command:[/bold] {config.config.get('command')}")
            args = config.config.get('args', [])
            if args:
                console.print(f"  [bold]Arguments:[/bold] {' '.join(args)}")
        
        console.print(f"  [bold]Timeout:[/bold] {config.config.get('timeout', 30)}s")
        
        # Test connection if requested
        if Confirm.ask("\n[yellow]Test connection?[/yellow]", default=True):
            if not self.test_connection(config):
                if not Confirm.ask("Continue anyway?", default=False):
                    return False
        
        return Confirm.ask("\n[bold green]Save this configuration?[/bold green]", default=True)


def run_add_wizard() -> bool:
    """
    Run the MCP add wizard and register the server.
    
    Returns:
        True if server was added, False otherwise
    """
    wizard = MCPConfigWizard()
    config = wizard.run_wizard()
    
    if config:
        try:
            manager = get_mcp_manager()
            server_id = manager.register_server(config)
            
            emit_success(f"\n✅ Server '{config.name}' added successfully!")
            emit_info(f"Server ID: {server_id}")
            emit_info("Use '/mcp list' to see all servers")
            emit_info(f"Use '/mcp start {config.name}' to start the server")
            
            # Also save to mcp_servers.json for persistence
            from code_puppy.config import MCP_SERVERS_FILE, load_mcp_server_configs
            import json
            import os
            
            # Load existing configs
            if os.path.exists(MCP_SERVERS_FILE):
                with open(MCP_SERVERS_FILE, 'r') as f:
                    data = json.load(f)
                    servers = data.get("mcp_servers", {})
            else:
                servers = {}
                data = {"mcp_servers": servers}
            
            # Add new server
            servers[config.name] = config.config
            
            # Save back
            os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
            with open(MCP_SERVERS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
            
            emit_info(f"[dim]Configuration saved to {MCP_SERVERS_FILE}[/dim]")
            return True
            
        except Exception as e:
            emit_error(f"Failed to add server: {e}")
            return False
    else:
        emit_warning("Configuration cancelled")
        return False