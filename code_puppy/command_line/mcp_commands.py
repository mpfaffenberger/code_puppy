"""
MCP Command Handler - Command line interface for managing MCP servers.

This module provides the MCPCommandHandler class that implements the /mcp command
interface for managing MCP servers at runtime. It provides commands for listing,
starting, stopping, configuring, and monitoring MCP servers.
"""

import logging
import shlex
from typing import List, Optional, Dict, Any
from datetime import datetime

from rich.table import Table
from rich.console import Console
from rich.text import Text
from rich.panel import Panel

from code_puppy.state_management import is_tui_mode
from code_puppy.messaging import emit_prompt
from code_puppy.mcp.manager import get_mcp_manager, ServerInfo
from code_puppy.mcp.managed_server import ServerConfig, ServerState
from code_puppy.messaging import emit_info, emit_system_message

# Configure logging
logger = logging.getLogger(__name__)


class MCPCommandHandler:
    """
    Command handler for MCP server management operations.
    
    Provides the /mcp command interface that allows users to manage MCP servers
    at runtime through commands like list, start, stop, restart, status, etc.
    Uses Rich library for formatted output with tables, colors, and status indicators.
    
    Example usage:
        handler = MCPCommandHandler()
        handler.handle_mcp_command("/mcp list")
        handler.handle_mcp_command("/mcp start filesystem")
        handler.handle_mcp_command("/mcp status filesystem")
    """
    
    def __init__(self):
        """Initialize the MCP command handler."""
        self.console = Console()
        self.manager = get_mcp_manager()
        logger.info("MCPCommandHandler initialized")
    
    def handle_mcp_command(self, command: str) -> bool:
        """
        Handle MCP commands and route to appropriate handler.
        
        Args:
            command: The full command string (e.g., "/mcp list", "/mcp start server")
            
        Returns:
            True if command was handled successfully, False otherwise
        """
        import uuid
        # Generate a group ID for this entire MCP command session
        group_id = str(uuid.uuid4())
        
        try:
            # Remove /mcp prefix and parse arguments
            command = command.strip()
            if not command.startswith("/mcp"):
                return False
            
            # Remove the /mcp prefix
            args_str = command[4:].strip()
            
            # If no subcommand, show status dashboard
            if not args_str:
                self.cmd_list([], group_id=group_id)
                return True
            
            # Parse arguments using shlex for proper handling of quoted strings
            try:
                args = shlex.split(args_str)
            except ValueError as e:
                emit_info(f"[red]Invalid command syntax: {e}[/red]", message_group=group_id)
                return True
            
            if not args:
                self.cmd_list([], group_id=group_id)
                return True
            
            subcommand = args[0].lower()
            sub_args = args[1:] if len(args) > 1 else []
            
            # Route to appropriate command handler
            command_map = {
                'list': self.cmd_list,
                'start': self.cmd_start,
                'start-all': self.cmd_start_all,
                'stop': self.cmd_stop,
                'stop-all': self.cmd_stop_all,
                'restart': self.cmd_restart,
                'status': self.cmd_status,
                'test': self.cmd_test,
                'add': self.cmd_add,
                'remove': self.cmd_remove,
                'logs': self.cmd_logs,
                'search': self.cmd_search,
                'install': self.cmd_install,
                'help': self.cmd_help,
            }
            
            handler = command_map.get(subcommand)
            if handler:
                handler(sub_args)
                return True
            else:
                emit_info(f"[yellow]Unknown MCP subcommand: {subcommand}[/yellow]", message_group=group_id)
                emit_info("Type '/mcp help' for available commands", message_group=group_id)
                return True
        
        except Exception as e:
            logger.error(f"Error handling MCP command '{command}': {e}")
            emit_info(f"Error executing MCP command: {e}", message_group=group_id)
            return True
    
    def cmd_list(self, args: List[str], group_id: str = None) -> None:
        """
        List all registered MCP servers in a formatted table.
        
        Args:
            args: Command arguments (unused for list command)
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            import uuid
            group_id = str(uuid.uuid4())
        
        try:
            servers = self.manager.list_servers()
            
            if not servers:
                emit_info("No MCP servers registered", message_group=group_id)
                return
            
            # Create table for server list
            table = Table(title="🔌 MCP Server Status Dashboard")
            table.add_column("Name", style="cyan", no_wrap=True)
            table.add_column("Type", style="dim", no_wrap=True)
            table.add_column("State", justify="center")
            table.add_column("Enabled", justify="center")
            table.add_column("Uptime", style="dim")
            table.add_column("Status", style="dim")
            
            for server in servers:
                # Format state with appropriate color and icon
                state_display = self._format_state_indicator(server.state)
                
                # Format enabled status
                enabled_display = "✓" if server.enabled else "✗"
                enabled_style = "green" if server.enabled else "red"
                
                # Format uptime
                uptime_display = self._format_uptime(server.uptime_seconds)
                
                # Format status message
                status_display = server.error_message or "OK"
                if server.quarantined:
                    status_display = "Quarantined"
                
                table.add_row(
                    server.name,
                    server.type.upper(),
                    state_display,
                    Text(enabled_display, style=enabled_style),
                    uptime_display,
                    status_display
                )
            
            emit_info(table, message_group=group_id)
            
            # Show summary
            total = len(servers)
            running = sum(1 for s in servers if s.state == ServerState.RUNNING and s.enabled)
            emit_info(f"\n📊 Summary: {running}/{total} servers running", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error listing MCP servers: {e}")
            emit_info(f"Failed to list servers: {e}", message_group=group_id)
    
    def cmd_start(self, args: List[str]) -> None:
        """
        Start a specific MCP server.
        
        Args:
            args: Command arguments, expects [server_name]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("[yellow]Usage: /mcp start <server_name>[/yellow]", message_group=group_id)
            return
        
        server_name = args[0]
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"[red]Server '{server_name}' not found[/red]", message_group=group_id)
                self._suggest_similar_servers(server_name, group_id=group_id)
                return
            
            # Start the server (enable and start process)
            success = self.manager.start_server_sync(server_id)
            
            if success:
                # This and subsequent messages will auto-group with the first message
                emit_info(f"[green]✓ Started server: {server_name}[/green]", message_group=group_id)
                
                # Give async tasks a moment to complete
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in async context, wait a bit for server to start
                    import time
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, server will start when agent uses it
                
                # Reload the agent to pick up the newly enabled server
                try:
                    from code_puppy.agents.runtime_manager import get_runtime_agent_manager
                    manager = get_runtime_agent_manager()
                    manager.reload_agent()
                    emit_info("[dim]Agent reloaded with updated servers[/dim]", message_group=group_id)
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
            else:
                emit_info(f"[red]✗ Failed to start server: {server_name}[/red]", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error starting server '{server_name}': {e}")
            emit_info(f"[red]Failed to start server: {e}[/red]", message_group=group_id)
    
    def cmd_start_all(self, args: List[str]) -> None:
        """
        Start all registered MCP servers.
        
        Args:
            args: Command arguments (unused)
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        try:
            servers = self.manager.list_servers()
            
            if not servers:
                emit_info("[yellow]No servers registered[/yellow]", message_group=group_id)
                return
            
            started_count = 0
            failed_count = 0
            already_running = 0
            
            emit_info(f"Starting {len(servers)} servers...", message_group=group_id)
            
            for server_info in servers:
                server_id = server_info.id
                server_name = server_info.name
                
                # Skip if already running
                if server_info.state == ServerState.RUNNING:
                    already_running += 1
                    emit_info(f"  • {server_name}: already running", message_group=group_id)
                    continue
                
                # Try to start the server
                success = self.manager.start_server_sync(server_id)
                
                if success:
                    started_count += 1
                    emit_info(f"  [green]✓ Started: {server_name}[/green]", message_group=group_id)
                else:
                    failed_count += 1
                    emit_info(f"  [red]✗ Failed: {server_name}[/red]", message_group=group_id)
            
            # Summary
            emit_info("", message_group=group_id)
            if started_count > 0:
                emit_info(f"[green]Started {started_count} server(s)[/green]", message_group=group_id)
            if already_running > 0:
                emit_info(f"{already_running} server(s) already running", message_group=group_id)
            if failed_count > 0:
                emit_info(f"[yellow]Failed to start {failed_count} server(s)[/yellow]", message_group=group_id)
            
            # Reload agent if any servers were started
            if started_count > 0:
                # Give async tasks a moment to complete before reloading agent
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in async context, wait a bit for servers to start
                    import time
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, servers will start when agent uses them
                
                try:
                    from code_puppy.agents.runtime_manager import get_runtime_agent_manager
                    manager = get_runtime_agent_manager()
                    manager.reload_agent()
                    emit_info("[dim]Agent reloaded with updated servers[/dim]", message_group=group_id)
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
        
        except Exception as e:
            logger.error(f"Error starting all servers: {e}")
            emit_info(f"[red]Failed to start servers: {e}[/red]", message_group=group_id)
    
    def cmd_stop(self, args: List[str]) -> None:
        """
        Stop a specific MCP server.
        
        Args:
            args: Command arguments, expects [server_name]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("[yellow]Usage: /mcp stop <server_name>[/yellow]", message_group=group_id)
            return
        
        server_name = args[0]
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                self._suggest_similar_servers(server_name, group_id=group_id)
                return
            
            # Stop the server (disable and stop process)
            success = self.manager.stop_server_sync(server_id)
            
            if success:
                emit_info(f"✓ Stopped server: {server_name}", message_group=group_id)
                
                # Reload the agent to remove the disabled server
                try:
                    from code_puppy.agents.runtime_manager import get_runtime_agent_manager
                    manager = get_runtime_agent_manager()
                    manager.reload_agent()
                    emit_info("[dim]Agent reloaded with updated servers[/dim]", message_group=group_id)
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
            else:
                emit_info(f"✗ Failed to stop server: {server_name}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error stopping server '{server_name}': {e}")
            emit_info(f"Failed to stop server: {e}", message_group=group_id)
    
    def cmd_stop_all(self, args: List[str]) -> None:
        """
        Stop all running MCP servers.
        
        Args:
            args: [group_id] - optional group ID for message grouping
        """
        group_id = args[0] if args else None
        if group_id is None:
            import uuid
            group_id = str(uuid.uuid4())
        try:
            servers = self.manager.list_servers()
            
            if not servers:
                emit_info("No servers registered", message_group=group_id)
                return
            
            stopped_count = 0
            failed_count = 0
            already_stopped = 0
            
            # Count running servers
            running_servers = [s for s in servers if s.state == ServerState.RUNNING]
            
            if not running_servers:
                emit_info("No servers are currently running", message_group=group_id)
                return
            
            emit_info(f"Stopping {len(running_servers)} running server(s)...", message_group=group_id)
            
            for server_info in running_servers:
                server_id = server_info.id
                server_name = server_info.name
                
                # Try to stop the server
                success = self.manager.stop_server_sync(server_id)
                
                if success:
                    stopped_count += 1
                    emit_info(f"  ✓ Stopped: {server_name}", message_group=group_id)
                else:
                    failed_count += 1
                    emit_info(f"  ✗ Failed: {server_name}", message_group=group_id)
            
            # Summary
            emit_info("", message_group=group_id)
            if stopped_count > 0:
                emit_info(f"Stopped {stopped_count} server(s)", message_group=group_id)
            if failed_count > 0:
                emit_info(f"Failed to stop {failed_count} server(s)", message_group=group_id)
            
            # Reload agent if any servers were stopped
            if stopped_count > 0:
                # Give async tasks a moment to complete before reloading agent
                import asyncio
                try:
                    loop = asyncio.get_running_loop()
                    # If we're in async context, wait a bit for servers to stop
                    import time
                    time.sleep(0.5)  # Small delay to let async tasks progress
                except RuntimeError:
                    pass  # No async loop, servers will stop when needed
                
                try:
                    from code_puppy.agents.runtime_manager import get_runtime_agent_manager
                    manager = get_runtime_agent_manager()
                    manager.reload_agent()
                    emit_info("[dim]Agent reloaded with updated servers[/dim]", message_group=group_id)
                except Exception as e:
                    logger.warning(f"Could not reload agent: {e}")
        
        except Exception as e:
            logger.error(f"Error stopping all servers: {e}")
            emit_info(f"Failed to stop servers: {e}", message_group=group_id)
    
    def cmd_restart(self, args: List[str]) -> None:
        """
        Restart a specific MCP server.
        
        Args:
            args: Command arguments, expects [server_name]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("Usage: /mcp restart <server_name>", message_group=group_id)
            return
        
        server_name = args[0]
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                self._suggest_similar_servers(server_name)
                return
            
            # Stop the server first
            emit_info(f"Stopping server: {server_name}", message_group=group_id)
            self.manager.stop_server_sync(server_id)
            
            # Then reload and start it
            emit_info(f"Reloading configuration...", message_group=group_id)
            reload_success = self.manager.reload_server(server_id)
            
            if reload_success:
                emit_info(f"Starting server: {server_name}", message_group=group_id)
                start_success = self.manager.start_server_sync(server_id)
                
                if start_success:
                    emit_info(f"✓ Restarted server: {server_name}", message_group=group_id)
                    
                    # Reload the agent to pick up the server changes
                    try:
                        from code_puppy.agent import get_code_generation_agent
                        get_code_generation_agent(force_reload=True)
                        emit_info("[dim]Agent reloaded with updated servers[/dim]", message_group=group_id)
                    except Exception as e:
                        logger.warning(f"Could not reload agent: {e}")
                else:
                    emit_info(f"✗ Failed to start server after reload: {server_name}", message_group=group_id)
            else:
                emit_info(f"✗ Failed to reload server configuration: {server_name}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error restarting server '{server_name}': {e}")
            emit_info(f"Failed to restart server: {e}", message_group=group_id)
    
    def cmd_status(self, args: List[str]) -> None:
        """
        Show detailed status for a specific server or all servers.
        
        Args:
            args: Command arguments, expects [server_name] (optional)
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        try:
            if args:
                # Show detailed status for specific server
                server_name = args[0]
                server_id = self._find_server_id_by_name(server_name)
                
                if not server_id:
                    emit_info(f"Server '{server_name}' not found", message_group=group_id)
                    self._suggest_similar_servers(server_name)
                    return
                
                self._show_detailed_server_status(server_id, server_name, group_id)
            else:
                # Show brief status for all servers
                self.cmd_list([])
        
        except Exception as e:
            logger.error(f"Error showing server status: {e}")
            emit_info(f"Failed to get server status: {e}", message_group=group_id)
    
    def cmd_test(self, args: List[str]) -> None:
        """
        Test connectivity to a specific MCP server.
        
        Args:
            args: Command arguments, expects [server_name]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("Usage: /mcp test <server_name>", message_group=group_id)
            return
        
        server_name = args[0]
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                self._suggest_similar_servers(server_name)
                return
            
            # Get managed server
            managed_server = self.manager.get_server(server_id)
            if not managed_server:
                emit_info(f"Server '{server_name}' not accessible", message_group=group_id)
                return
            
            emit_info(f"🔍 Testing connectivity to server: {server_name}", message_group=group_id)
            
            # Basic connectivity test - try to get the pydantic server
            try:
                pydantic_server = managed_server.get_pydantic_server()
                emit_info(f"✓ Server instance created successfully", message_group=group_id)
                
                # Try to get server info if available
                emit_info(f"  • Server type: {managed_server.config.type}", message_group=group_id)
                emit_info(f"  • Server enabled: {managed_server.is_enabled()}", message_group=group_id)
                emit_info(f"  • Server quarantined: {managed_server.is_quarantined()}", message_group=group_id)
                
                if not managed_server.is_enabled():
                    emit_info("  • Server is disabled - enable it with '/mcp start'", message_group=group_id)
                
                if managed_server.is_quarantined():
                    emit_info("  • Server is quarantined - may have recent errors", message_group=group_id)
                
                emit_info(f"✓ Connectivity test passed for: {server_name}", message_group=group_id)
                
            except Exception as test_error:
                emit_info(f"✗ Connectivity test failed: {test_error}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error testing server '{server_name}': {e}")
            emit_info(f"Failed to test server: {e}", message_group=group_id)
    
    def cmd_add(self, args: List[str]) -> None:
        """
        Add a new MCP server from JSON configuration or launch wizard.
        
        Usage:
            /mcp add                    - Launch interactive wizard
            /mcp add <json>             - Add server from JSON config
            
        Example JSON:
            /mcp add {"name": "test", "type": "stdio", "command": "echo", "args": ["hello"]}
        
        Args:
            args: Command arguments - JSON config or empty for wizard
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        try:
            if args:
                # Parse JSON from arguments
                import json
                json_str = ' '.join(args)
                
                try:
                    config_dict = json.loads(json_str)
                except json.JSONDecodeError as e:
                    emit_info(f"Invalid JSON: {e}", message_group=group_id)
                    emit_info("Usage: /mcp add <json> or /mcp add (for wizard)", message_group=group_id)
                    emit_info('Example: /mcp add {"name": "test", "type": "stdio", "command": "echo"}', message_group=group_id)
                    return
                
                # Validate required fields
                if 'name' not in config_dict:
                    emit_info("Missing required field: 'name'", message_group=group_id)
                    return
                if 'type' not in config_dict:
                    emit_info("Missing required field: 'type'", message_group=group_id)
                    return
                
                # Create ServerConfig
                from code_puppy.mcp import ServerConfig
                
                name = config_dict.pop('name')
                server_type = config_dict.pop('type')
                enabled = config_dict.pop('enabled', True)
                
                # Everything else goes into config
                server_config = ServerConfig(
                    id=f"{name}_{hash(name)}",
                    name=name,
                    type=server_type,
                    enabled=enabled,
                    config=config_dict  # Remaining fields are server-specific config
                )
                
                # Register the server
                server_id = self.manager.register_server(server_config)
                
                if server_id:
                    emit_info(f"✅ Added server '{name}' (ID: {server_id})", message_group=group_id)
                    
                    # Save to mcp_servers.json for persistence
                    from code_puppy.config import MCP_SERVERS_FILE
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
                    servers[name] = config_dict
                    servers[name]['type'] = server_type
                    
                    # Save back
                    os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
                    with open(MCP_SERVERS_FILE, 'w') as f:
                        json.dump(data, f, indent=2)
                    
                    # Reload MCP servers
                    from code_puppy.agent import reload_mcp_servers
                    reload_mcp_servers()
                    
                    emit_info("Use '/mcp list' to see all servers", message_group=group_id)
                else:
                    emit_info(f"Failed to add server '{name}'", message_group=group_id)
                    
            else:
                # No arguments - launch interactive wizard with server templates
                success = self._run_interactive_install_wizard(group_id)
                
                if success:
                    # Reload the agent to pick up new server
                    from code_puppy.agent import reload_mcp_servers
                    reload_mcp_servers()
                
        except ImportError as e:
            logger.error(f"Failed to import: {e}")
            emit_info("Required module not available", message_group=group_id)
        except Exception as e:
            logger.error(f"Error adding server: {e}")
            emit_info(f"Failed to add server: {e}", message_group=group_id)
    
    def _run_interactive_install_wizard(self, group_id: str) -> bool:
        """Run the interactive MCP server installation wizard using server templates."""
        try:
            from code_puppy.mcp.server_registry_catalog import catalog
            from code_puppy.mcp.system_tools import detector
            from code_puppy.messaging import emit_prompt
            import os
            import json
            
            emit_info("🧙 Interactive MCP Server Installation Wizard", message_group=group_id)
            emit_info("", message_group=group_id)
            
            # Step 1: Browse and select server
            selected_server = self._interactive_server_selection(group_id)
            if not selected_server:
                return False
            
            # Step 2: Get custom server name
            server_name = self._interactive_get_server_name(selected_server, group_id)
            if not server_name:
                return False
            
            # Step 3: Handle requirements and configuration
            success = self._interactive_configure_server(selected_server, server_name, group_id)
            return success
            
        except ImportError:
            emit_info("Server catalog not available, falling back to basic wizard", message_group=group_id)
            # Fall back to the old wizard
            from code_puppy.mcp.config_wizard import run_add_wizard
            return run_add_wizard(group_id)
        except Exception as e:
            emit_info(f"Installation wizard failed: {e}", message_group=group_id)
            return False
    
    def _interactive_server_selection(self, group_id: str):
        """Interactive server selection from catalog."""
        from code_puppy.mcp.server_registry_catalog import catalog
        from code_puppy.messaging import emit_prompt
        
        while True:
            emit_info("📦 Available MCP Servers:", message_group=group_id)
            emit_info("", message_group=group_id)
            
            # Show popular servers first
            popular = catalog.get_popular(5)
            if popular:
                emit_info("[bold]Popular Servers:[/bold]", message_group=group_id)
                for i, server in enumerate(popular):
                    indicators = []
                    if server.verified:
                        indicators.append("✓")
                    if server.popular:
                        indicators.append("⭐")
                    
                    emit_info(f"  {i+1}. {server.display_name} {''.join(indicators)}", message_group=group_id)
                    emit_info(f"     {server.description[:80]}...", message_group=group_id)
                emit_info("", message_group=group_id)
            
            # Prompt for selection
            choice = emit_prompt("Enter server number (1-5), 'search <term>' to search, or 'list' to see all categories: ")
            
            if not choice.strip():
                if emit_prompt("Cancel installation? [y/N]: ").lower().startswith('y'):
                    return None
                continue
            
            choice = choice.strip()
            
            # Handle numeric selection
            if choice.isdigit():
                try:
                    index = int(choice) - 1
                    if 0 <= index < len(popular):
                        return popular[index]
                    else:
                        emit_info("Invalid selection. Please try again.", message_group=group_id)
                        continue
                except ValueError:
                    pass
            
            # Handle search
            if choice.lower().startswith('search '):
                search_term = choice[7:].strip()
                results = catalog.search(search_term)
                if results:
                    emit_info(f"\n🔍 Search results for '{search_term}':", message_group=group_id)
                    for i, server in enumerate(results[:10]):
                        indicators = []
                        if server.verified:
                            indicators.append("✓")
                        if server.popular:
                            indicators.append("⭐")
                        emit_info(f"  {i+1}. {server.display_name} {''.join(indicators)}", message_group=group_id)
                        emit_info(f"     {server.description[:80]}...", message_group=group_id)
                    
                    selection = emit_prompt(f"\nSelect server (1-{min(len(results), 10)}): ")
                    if selection.isdigit():
                        try:
                            index = int(selection) - 1
                            if 0 <= index < len(results):
                                return results[index]
                        except ValueError:
                            pass
                else:
                    emit_info(f"No servers found for '{search_term}'", message_group=group_id)
                continue
            
            # Handle list categories
            if choice.lower() == 'list':
                categories = catalog.list_categories()
                emit_info("\n📂 Categories:", message_group=group_id)
                for i, category in enumerate(categories):
                    servers_count = len(catalog.get_by_category(category))
                    emit_info(f"  {i+1}. {category} ({servers_count} servers)", message_group=group_id)
                
                cat_choice = emit_prompt(f"\nSelect category (1-{len(categories)}): ")
                if cat_choice.isdigit():
                    try:
                        index = int(cat_choice) - 1
                        if 0 <= index < len(categories):
                            category_servers = catalog.get_by_category(categories[index])
                            emit_info(f"\n📦 {categories[index]} Servers:", message_group=group_id)
                            for i, server in enumerate(category_servers):
                                indicators = []
                                if server.verified:
                                    indicators.append("✓")
                                if server.popular:
                                    indicators.append("⭐")
                                emit_info(f"  {i+1}. {server.display_name} {''.join(indicators)}", message_group=group_id)
                                emit_info(f"     {server.description[:80]}...", message_group=group_id)
                            
                            server_choice = emit_prompt(f"\nSelect server (1-{len(category_servers)}): ")
                            if server_choice.isdigit():
                                try:
                                    index = int(server_choice) - 1
                                    if 0 <= index < len(category_servers):
                                        return category_servers[index]
                                except ValueError:
                                    pass
                    except ValueError:
                        pass
                continue
            
            emit_info("Invalid choice. Please try again.", message_group=group_id)
    
    def _interactive_get_server_name(self, selected_server, group_id: str) -> str:
        """Get custom server name from user."""
        from code_puppy.messaging import emit_prompt
        
        emit_info(f"\n🏷️  Server: {selected_server.display_name}", message_group=group_id)
        emit_info(f"Description: {selected_server.description}", message_group=group_id)
        emit_info("", message_group=group_id)
        
        while True:
            name = emit_prompt(f"Enter custom name for this server [{selected_server.name}]: ").strip()
            
            if not name:
                name = selected_server.name
            
            # Validate name
            if not name.replace('-', '').replace('_', '').replace('.', '').isalnum():
                emit_info("Name must contain only letters, numbers, hyphens, underscores, and dots", message_group=group_id)
                continue
            
            # Check if name already exists
            existing_server = self._find_server_id_by_name(name)
            if existing_server:
                override = emit_prompt(f"Server '{name}' already exists. Override it? [y/N]: ")
                if not override.lower().startswith('y'):
                    continue
            
            return name
    
    def _interactive_configure_server(self, selected_server, server_name: str, group_id: str) -> bool:
        """Configure the server with requirements validation."""
        from code_puppy.mcp.system_tools import detector
        from code_puppy.messaging import emit_prompt
        import os
        import json
        
        requirements = selected_server.get_requirements()
        
        emit_info(f"\n⚙️  Configuring server: {server_name}", message_group=group_id)
        emit_info("", message_group=group_id)
        
        # Step 1: Check system requirements
        if not self._interactive_check_system_requirements(requirements, group_id):
            return False
        
        # Step 2: Collect environment variables
        env_vars = self._interactive_collect_env_vars(requirements, group_id)
        
        # Step 3: Collect command line arguments
        cmd_args = self._interactive_collect_cmd_args(requirements, group_id)
        
        # Step 4: Show summary and confirm
        if not self._interactive_confirm_installation(selected_server, server_name, env_vars, cmd_args, group_id):
            return False
        
        # Step 5: Install the server
        return self._interactive_install_server(selected_server, server_name, env_vars, cmd_args, group_id)
    
    def _interactive_check_system_requirements(self, requirements, group_id: str) -> bool:
        """Check and validate system requirements."""
        from code_puppy.mcp.system_tools import detector
        
        required_tools = requirements.required_tools
        if not required_tools:
            return True
        
        emit_info("🔧 Checking system requirements...", message_group=group_id)
        
        tool_status = detector.detect_tools(required_tools)
        all_good = True
        
        for tool_name, tool_info in tool_status.items():
            if tool_info.available:
                status_text = f"✅ {tool_name}"
                if tool_info.version:
                    status_text += f" ({tool_info.version})"
                emit_info(status_text, message_group=group_id)
            else:
                status_text = f"❌ {tool_name} - {tool_info.error or 'Not found'}"
                emit_info(status_text, message_group=group_id)
                
                # Show installation suggestions
                suggestions = detector.get_installation_suggestions(tool_name)
                if suggestions:
                    emit_info(f"   Install: {suggestions[0]}", message_group=group_id)
                all_good = False
        
        if not all_good:
            emit_info("", message_group=group_id)
            cont = emit_prompt("Some tools are missing. Continue anyway? [y/N]: ")
            if not cont.lower().startswith('y'):
                emit_info("Installation cancelled", message_group=group_id)
                return False
        
        emit_info("", message_group=group_id)
        return True
    
    def _interactive_collect_env_vars(self, requirements, group_id: str) -> dict:
        """Collect environment variables from user."""
        from code_puppy.messaging import emit_prompt
        import os
        
        env_vars = {}
        required_env_vars = requirements.environment_vars
        
        if not required_env_vars:
            return env_vars
        
        emit_info("🔐 Environment Variables:", message_group=group_id)
        
        for var in required_env_vars:
            # Check if already set
            current_value = os.environ.get(var, "")
            
            if current_value:
                emit_info(f"✅ {var} (already set)", message_group=group_id)
                env_vars[var] = current_value
            else:
                value = emit_prompt(f"📝 Enter value for {var}: ").strip()
                if value:
                    env_vars[var] = value
                    # Set in current environment too
                    os.environ[var] = value
                else:
                    emit_info(f"⚠️  {var} left empty", message_group=group_id)
        
        emit_info("", message_group=group_id)
        return env_vars
    
    def _interactive_collect_cmd_args(self, requirements, group_id: str) -> dict:
        """Collect command line arguments from user."""
        from code_puppy.messaging import emit_prompt
        
        cmd_args = {}
        required_args = requirements.command_line_args
        
        if not required_args:
            return cmd_args
        
        emit_info("⚡ Command Line Arguments:", message_group=group_id)
        
        for arg_config in required_args:
            name = arg_config.get("name", "")
            prompt_text = arg_config.get("prompt", name)
            default = arg_config.get("default", "")
            required = arg_config.get("required", True)
            
            indicator = "⚡" if required else "🔧"
            label = f"{indicator} {prompt_text}"
            if not required:
                label += " (optional)"
            if default:
                label += f" [{default}]"
            
            value = emit_prompt(f"{label}: ").strip()
            
            if not value and default:
                value = default
            
            if value:
                cmd_args[name] = value
            elif required:
                emit_info(f"⚠️  Required argument '{name}' left empty", message_group=group_id)
        
        emit_info("", message_group=group_id)
        return cmd_args
    
    def _interactive_confirm_installation(self, selected_server, server_name: str, env_vars: dict, cmd_args: dict, group_id: str) -> bool:
        """Show summary and confirm installation."""
        from code_puppy.messaging import emit_prompt
        
        emit_info("📋 Installation Summary:", message_group=group_id)
        emit_info(f"  Server: {selected_server.display_name}", message_group=group_id)
        emit_info(f"  Name: {server_name}", message_group=group_id)
        emit_info(f"  Type: {selected_server.type}", message_group=group_id)
        
        if env_vars:
            emit_info(f"  Environment variables: {len(env_vars)} set", message_group=group_id)
        
        if cmd_args:
            emit_info(f"  Command arguments: {len(cmd_args)} configured", message_group=group_id)
        
        emit_info("", message_group=group_id)
        
        confirm = emit_prompt("Install this server configuration? [Y/n]: ")
        return not confirm.lower().startswith('n')
    
    def _interactive_install_server(self, selected_server, server_name: str, env_vars: dict, cmd_args: dict, group_id: str) -> bool:
        """Actually install and register the server."""
        try:
            # Get server config with command line argument overrides
            config_dict = selected_server.to_server_config(server_name, **cmd_args)
            
            # Update the config with actual environment variable values
            if 'env' in config_dict:
                for env_key, env_value in config_dict['env'].items():
                    # If it's a placeholder like $GITHUB_TOKEN, replace with actual value
                    if env_value.startswith('$'):
                        var_name = env_value[1:]  # Remove the $
                        if var_name in env_vars:
                            config_dict['env'][env_key] = env_vars[var_name]
            
            # Create and register the server
            from code_puppy.mcp import ServerConfig
            
            server_config = ServerConfig(
                id=server_name,
                name=server_name,
                type=config_dict.pop('type'),
                enabled=True,
                config=config_dict
            )
            
            server_id = self.manager.register_server(server_config)
            
            if server_id:
                # Save to mcp_servers.json for persistence
                from code_puppy.config import MCP_SERVERS_FILE
                import json
                import os
                
                if os.path.exists(MCP_SERVERS_FILE):
                    with open(MCP_SERVERS_FILE, 'r') as f:
                        data = json.load(f)
                        servers = data.get("mcp_servers", {})
                else:
                    servers = {}
                    data = {"mcp_servers": servers}
                
                servers[server_name] = config_dict
                servers[server_name]['type'] = server_config.type
                
                os.makedirs(os.path.dirname(MCP_SERVERS_FILE), exist_ok=True)
                with open(MCP_SERVERS_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                
                emit_info(f"✅ Successfully installed '{server_name}' from {selected_server.display_name}!", message_group=group_id)
                emit_info(f"Use '/mcp start {server_name}' to start the server", message_group=group_id)
                return True
            else:
                emit_info(f"❌ Failed to register server", message_group=group_id)
                return False
                
        except Exception as e:
            emit_info(f"❌ Installation failed: {str(e)}", message_group=group_id)
            return False
    
    def cmd_remove(self, args: List[str]) -> None:
        """
        Remove an MCP server.
        
        Args:
            args: Command arguments, expects [server_name]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("Usage: /mcp remove <server_name>", message_group=group_id)
            return
        
        server_name = args[0]
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                self._suggest_similar_servers(server_name)
                return
            
            # Actually remove the server
            success = self.manager.remove_server(server_id)
            
            if success:
                emit_info(f"✓ Removed server: {server_name}", message_group=group_id)
                
                # Also remove from mcp_servers.json
                from code_puppy.config import MCP_SERVERS_FILE
                import json
                import os
                
                if os.path.exists(MCP_SERVERS_FILE):
                    try:
                        with open(MCP_SERVERS_FILE, 'r') as f:
                            data = json.load(f)
                            servers = data.get("mcp_servers", {})
                        
                        # Remove the server if it exists
                        if server_name in servers:
                            del servers[server_name]
                            
                            # Save back
                            with open(MCP_SERVERS_FILE, 'w') as f:
                                json.dump(data, f, indent=2)
                    except Exception as e:
                        logger.warning(f"Could not update mcp_servers.json: {e}")
            else:
                emit_info(f"✗ Failed to remove server: {server_name}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error removing server '{server_name}': {e}")
            emit_info(f"Failed to remove server: {e}", message_group=group_id)
    
    def cmd_logs(self, args: List[str]) -> None:
        """
        Show recent events/logs for a server.
        
        Args:
            args: Command arguments, expects [server_name] and optional [limit]
        """
        import uuid
        group_id = str(uuid.uuid4())
        
        if not args:
            emit_info("Usage: /mcp logs <server_name> [limit]", message_group=group_id)
            return
        
        server_name = args[0]
        limit = 10  # Default limit
        
        if len(args) > 1:
            try:
                limit = int(args[1])
                if limit <= 0 or limit > 100:
                    emit_info("Limit must be between 1 and 100, using default: 10", message_group=group_id)
                    limit = 10
            except ValueError:
                emit_info(f"Invalid limit '{args[1]}', using default: 10", message_group=group_id)
        
        try:
            # Find server by name
            server_id = self._find_server_id_by_name(server_name)
            if not server_id:
                emit_info(f"Server '{server_name}' not found", message_group=group_id)
                self._suggest_similar_servers(server_name)
                return
            
            # Get server status which includes recent events
            status = self.manager.get_server_status(server_id)
            
            if not status.get("exists", True):
                emit_info(f"Server '{server_name}' status not available", message_group=group_id)
                return
            
            recent_events = status.get("recent_events", [])
            
            if not recent_events:
                emit_info(f"No recent events for server: {server_name}", message_group=group_id)
                return
            
            # Show events in a table
            table = Table(title=f"📋 Recent Events for {server_name} (last {limit})")
            table.add_column("Time", style="dim", no_wrap=True)
            table.add_column("Event", style="cyan")
            table.add_column("Details", style="dim")
            
            # Take only the requested number of events
            events_to_show = recent_events[-limit:] if len(recent_events) > limit else recent_events
            
            for event in reversed(events_to_show):  # Show newest first
                timestamp = datetime.fromisoformat(event["timestamp"])
                time_str = timestamp.strftime("%H:%M:%S")
                event_type = event["event_type"]
                
                # Format details
                details = event.get("details", {})
                details_str = details.get("message", "")
                if not details_str and "error" in details:
                    details_str = str(details["error"])
                
                # Color code event types
                event_style = "cyan"
                if "error" in event_type.lower():
                    event_style = "red"
                elif event_type in ["started", "enabled", "registered"]:
                    event_style = "green"
                elif event_type in ["stopped", "disabled"]:
                    event_style = "yellow"
                
                table.add_row(
                    time_str,
                    Text(event_type, style=event_style),
                    details_str or "-"
                )
            emit_info(table, message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error getting logs for server '{server_name}': {e}")
            emit_info(f"Failed to get server logs: {e}", message_group=group_id)
    
    def cmd_help(self, args: List[str]) -> None:
        """
        Show help for MCP commands.
        
        Args:
            args: Command arguments (unused)
        """
        from rich.text import Text
        from rich.console import Console
        
        # Create a console for rendering
        console = Console()
        
        # Build help text programmatically to avoid markup conflicts
        help_lines = []
        
        # Title
        help_lines.append(Text("MCP Server Management Commands", style="bold magenta"))
        help_lines.append(Text(""))
        
        # Registry Commands
        help_lines.append(Text("Registry Commands:", style="bold cyan"))
        help_lines.append(Text("/mcp search", style="cyan") + Text(" [query]     Search 30+ pre-configured servers"))
        help_lines.append(Text("/mcp install", style="cyan") + Text(" <id>       Install server from registry"))
        help_lines.append(Text(""))
        
        # Core Commands  
        help_lines.append(Text("Core Commands:", style="bold cyan"))
        help_lines.append(Text("/mcp", style="cyan") + Text("                    Show server status dashboard"))
        help_lines.append(Text("/mcp list", style="cyan") + Text("               List all registered servers"))
        help_lines.append(Text("/mcp start", style="cyan") + Text(" <name>       Start a specific server"))
        help_lines.append(Text("/mcp start-all", style="cyan") + Text("          Start all servers"))
        help_lines.append(Text("/mcp stop", style="cyan") + Text(" <name>        Stop a specific server"))
        help_lines.append(Text("/mcp stop-all", style="cyan") + Text(" [group_id]  Stop all running servers"))
        help_lines.append(Text("/mcp restart", style="cyan") + Text(" <name>     Restart a specific server"))
        help_lines.append(Text(""))
        
        # Management Commands
        help_lines.append(Text("Management Commands:", style="bold cyan"))
        help_lines.append(Text("/mcp status", style="cyan") + Text(" [name]      Show detailed status (all servers or specific)"))
        help_lines.append(Text("/mcp test", style="cyan") + Text(" <name>        Test connectivity to a server"))
        help_lines.append(Text("/mcp logs", style="cyan") + Text(" <name> [limit] Show recent events (default limit: 10)"))
        help_lines.append(Text("/mcp add", style="cyan") + Text(" [json]         Add new server (JSON or wizard)"))
        help_lines.append(Text("/mcp remove", style="cyan") + Text(" <name>      Remove/disable a server"))
        help_lines.append(Text("/mcp help", style="cyan") + Text("               Show this help message"))
        help_lines.append(Text(""))
        
        # Status Indicators
        help_lines.append(Text("Status Indicators:", style="bold"))
        help_lines.append(Text("✓ Running    ✗ Stopped    ⚠ Error    ⏸ Quarantined    ⭐ Popular"))
        help_lines.append(Text(""))
        
        # Examples
        help_lines.append(Text("Examples:", style="bold"))
        examples_text = """/mcp search database     # Find database servers
/mcp install postgres    # Install PostgreSQL server
/mcp start filesystem    # Start a specific server
/mcp start-all           # Start all servers at once
/mcp stop-all            # Stop all running servers
/mcp add {"name": "test", "type": "stdio", "command": "echo"}"""
        help_lines.append(Text(examples_text, style="dim"))
        
        # Combine all lines
        final_text = Text()
        for i, line in enumerate(help_lines):
            if i > 0:
                final_text.append("\n")
            final_text.append_text(line)
        
        import uuid
        group_id = str(uuid.uuid4())
        emit_info(final_text, message_group=group_id)
    
    def cmd_search(self, args: List[str], group_id: str = None) -> None:
        """
        Search for pre-configured MCP servers in the registry.
        
        Args:
            args: Search query terms
            group_id: Optional message group ID for grouping related messages
        """
        if group_id is None:
            import uuid
            group_id = str(uuid.uuid4())
            
        try:
            from code_puppy.mcp.server_registry_catalog import catalog
            from rich.table import Table
            
            if not args:
                # Show popular servers if no query
                emit_info("[bold cyan]Popular MCP Servers:[/bold cyan]\n", message_group=group_id)
                servers = catalog.get_popular(15)
            else:
                query = ' '.join(args)
                emit_info(f"[bold cyan]Searching for: {query}[/bold cyan]\n", message_group=group_id)
                servers = catalog.search(query)
            
            if not servers:
                emit_info("[yellow]No servers found matching your search[/yellow]", message_group=group_id)
                emit_info("Try: /mcp search database, /mcp search file, /mcp search git", message_group=group_id)
                return
            
            # Create results table
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("ID", style="cyan", width=20)
            table.add_column("Name", style="green")
            table.add_column("Category", style="yellow")
            table.add_column("Description", style="white")
            table.add_column("Tags", style="dim")
            
            for server in servers[:20]:  # Limit to 20 results
                tags = ', '.join(server.tags[:3])  # Show first 3 tags
                if len(server.tags) > 3:
                    tags += '...'
                
                # Add verified/popular indicators
                indicators = []
                if server.verified:
                    indicators.append("✓")
                if server.popular:
                    indicators.append("⭐")
                name_display = server.display_name
                if indicators:
                    name_display += f" {''.join(indicators)}"
                
                table.add_row(
                    server.id,
                    name_display,
                    server.category,
                    server.description[:50] + "..." if len(server.description) > 50 else server.description,
                    tags
                )
            
            # The first message established the group, subsequent messages will auto-group
            emit_system_message(table, message_group=group_id)
            emit_info("\n[dim]✓ = Verified  ⭐ = Popular[/dim]", message_group=group_id)
            emit_info("[yellow]To install:[/yellow] /mcp install <id>", message_group=group_id)
            emit_info("[yellow]For details:[/yellow] /mcp search <specific-term>", message_group=group_id)
            
        except ImportError:
            emit_info("[red]Server registry not available[/red]", message_group=group_id)
        except Exception as e:
            logger.error(f"Error searching servers: {e}")
            emit_info(f"[red]Search failed: {e}[/red]", message_group=group_id)
    
    def cmd_install(self, args: List[str], group_id: str = None) -> None:
        """
        Install a pre-configured MCP server from the registry.
        
        Args:
            args: Server ID and optional custom name
        """
        if group_id is None:
            import uuid
            group_id = str(uuid.uuid4())
        
        try:
            # If in TUI mode, show message to use Ctrl+T
            if is_tui_mode():
                emit_info("In TUI mode, use Ctrl+T to open the MCP Install Wizard", message_group=group_id)
                return
            
            # In interactive mode, use the new comprehensive installer
            if not args:
                # No args - launch interactive wizard
                success = self._run_interactive_install_wizard(group_id)
                if success:
                    from code_puppy.agent import reload_mcp_servers
                    reload_mcp_servers()
                return
            
            # Has args - install directly from catalog
            server_id = args[0]
            success = self._install_from_catalog(server_id, group_id)
            if success:
                from code_puppy.agent import reload_mcp_servers
                reload_mcp_servers()
            return
            
        except ImportError:
            emit_info("Server registry not available", message_group=group_id)
        except Exception as e:
            logger.error(f"Error installing server: {e}")
            emit_info(f"Installation failed: {e}", message_group=group_id)
    
    def _install_from_catalog(self, server_name_or_id: str, group_id: str) -> bool:
        """Install a server directly from the catalog by name or ID."""
        try:
            from code_puppy.mcp.server_registry_catalog import catalog
            
            # Try to find server by ID first, then by name/search
            selected_server = catalog.get_by_id(server_name_or_id)
            
            if not selected_server:
                # Try searching by name
                results = catalog.search(server_name_or_id)
                if not results:
                    emit_info(f"❌ No server found matching '{server_name_or_id}'", message_group=group_id)
                    emit_info("Try '/mcp add' to browse available servers", message_group=group_id)
                    return False
                elif len(results) == 1:
                    selected_server = results[0]
                else:
                    # Multiple matches, show them
                    emit_info(f"🔍 Multiple servers found matching '{server_name_or_id}':", message_group=group_id)
                    for i, server in enumerate(results[:5]):
                        indicators = []
                        if server.verified:
                            indicators.append("✓")
                        if server.popular:
                            indicators.append("⭐")
                        
                        indicator_str = ''
                        if indicators:
                            indicator_str = ' ' + ''.join(indicators)
                        
                        emit_info(f"  {i+1}. {server.display_name}{indicator_str}", message_group=group_id)
                        emit_info(f"     ID: {server.id}", message_group=group_id)
                    
                    emit_info(f"Please use the exact server ID: '/mcp add <server_id>'", message_group=group_id)
                    return False
            
            # Show what we're installing
            emit_info(f"📦 Installing: {selected_server.display_name}", message_group=group_id)
            description = selected_server.description if selected_server.description else "No description available"
            emit_info(f"Description: {description}", message_group=group_id)
            emit_info("", message_group=group_id)
            
            # Get custom name (default to server name)
            from code_puppy.messaging import emit_prompt
            server_name = emit_prompt(f"Enter custom name for this server [{selected_server.name}]: ").strip()
            if not server_name:
                server_name = selected_server.name
            
            # Check if name already exists
            existing_server = self._find_server_id_by_name(server_name)
            if existing_server:
                override = emit_prompt(f"Server '{server_name}' already exists. Override it? [y/N]: ")
                if not override.lower().startswith('y'):
                    emit_info("Installation cancelled", message_group=group_id)
                    return False
            
            # Configure the server with requirements
            requirements = selected_server.get_requirements()
            
            # Check system requirements
            if not self._interactive_check_system_requirements(requirements, group_id):
                return False
            
            # Collect environment variables
            env_vars = self._interactive_collect_env_vars(requirements, group_id)
            
            # Collect command line arguments  
            cmd_args = self._interactive_collect_cmd_args(requirements, group_id)
            
            # Show summary and confirm
            if not self._interactive_confirm_installation(selected_server, server_name, env_vars, cmd_args, group_id):
                return False
            
            # Install the server
            return self._interactive_install_server(selected_server, server_name, env_vars, cmd_args, group_id)
            
        except ImportError:
            emit_info("Server catalog not available", message_group=group_id)
            return False
        except Exception as e:
            import traceback
            emit_info(f"❌ Installation failed: {str(e)}", message_group=group_id)
            emit_info(f"[dim]Error details: {traceback.format_exc()}[/dim]", message_group=group_id)
            return False
    
    def _find_server_id_by_name(self, server_name: str) -> Optional[str]:
        """
        Find a server ID by its name.
        
        Args:
            server_name: Name of the server to find
            
        Returns:
            Server ID if found, None otherwise
        """
        try:
            servers = self.manager.list_servers()
            for server in servers:
                if server.name.lower() == server_name.lower():
                    return server.id
            return None
        except Exception as e:
            logger.error(f"Error finding server by name '{server_name}': {e}")
            return None
    
    def _suggest_similar_servers(self, server_name: str, group_id: str = None) -> None:
        """
        Suggest similar server names when a server is not found.
        
        Args:
            server_name: The server name that was not found
            group_id: Optional message group ID for grouping related messages
        """
        try:
            servers = self.manager.list_servers()
            if not servers:
                emit_info("No servers are registered", message_group=group_id)
                return
            
            # Simple suggestion based on partial matching
            suggestions = []
            server_name_lower = server_name.lower()
            
            for server in servers:
                if server_name_lower in server.name.lower():
                    suggestions.append(server.name)
            
            if suggestions:
                emit_info(f"Did you mean: {', '.join(suggestions)}", message_group=group_id)
            else:
                server_names = [s.name for s in servers]
                emit_info(f"Available servers: {', '.join(server_names)}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error suggesting similar servers: {e}")
    
    def _format_state_indicator(self, state: ServerState) -> Text:
        """
        Format a server state with appropriate color and icon.
        
        Args:
            state: Server state to format
            
        Returns:
            Rich Text object with colored state indicator
        """
        state_map = {
            ServerState.RUNNING: ("✓ Run", "green"),
            ServerState.STOPPED: ("✗ Stop", "red"),
            ServerState.STARTING: ("↗ Start", "yellow"),
            ServerState.STOPPING: ("↙ Stop", "yellow"),
            ServerState.ERROR: ("⚠ Err", "red"),
            ServerState.QUARANTINED: ("⏸ Quar", "yellow"),
        }
        
        display, color = state_map.get(state, ("? Unk", "dim"))
        return Text(display, style=color)

    def _format_uptime(self, uptime_seconds: Optional[float]) -> str:
        """
        Format uptime in a human-readable format.

        Args:
            uptime_seconds: Uptime in seconds, or None

        Returns:
            Formatted uptime string
        """
        if uptime_seconds is None or uptime_seconds <= 0:
            return "-"

        # Convert to readable format
        if uptime_seconds < 60:
            return f"{int(uptime_seconds)}s"
        elif uptime_seconds < 3600:
            minutes = int(uptime_seconds // 60)
            seconds = int(uptime_seconds % 60)
            return f"{minutes}m {seconds}s"
        else:
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def _show_detailed_server_status(self, server_id: str, server_name: str, group_id: str = None) -> None:
        """
        Show comprehensive status information for a specific server.
        
        Args:
            server_id: ID of the server
            server_name: Name of the server
            group_id: Optional message group ID
        """
        if group_id is None:
            import uuid
            group_id = str(uuid.uuid4())
        
        try:
            status = self.manager.get_server_status(server_id)
            
            if not status.get("exists", True):
                emit_info(f"Server '{server_name}' not found or not accessible", message_group=group_id)
                return
            
            # Create detailed status panel
            status_lines = []
            
            # Basic information
            status_lines.append(f"[bold]Server:[/bold] {server_name}")
            status_lines.append(f"[bold]ID:[/bold] {server_id}")
            status_lines.append(f"[bold]Type:[/bold] {status.get('type', 'unknown').upper()}")
            
            # State and status
            state = status.get('state', 'unknown')
            state_display = self._format_state_indicator(ServerState(state) if state in [s.value for s in ServerState] else ServerState.STOPPED)
            status_lines.append(f"[bold]State:[/bold] {state_display}")
            
            enabled = status.get('enabled', False)
            status_lines.append(f"[bold]Enabled:[/bold] {'✓ Yes' if enabled else '✗ No'}")
            
            # Check async lifecycle manager status if available
            try:
                from code_puppy.mcp.async_lifecycle import get_lifecycle_manager
                lifecycle_mgr = get_lifecycle_manager()
                if lifecycle_mgr.is_running(server_id):
                    status_lines.append(f"[bold]Process:[/bold] [green]✓ Active (subprocess/connection running)[/green]")
                else:
                    status_lines.append(f"[bold]Process:[/bold] [dim]Not active[/dim]")
            except Exception:
                pass  # Lifecycle manager not available
            
            quarantined = status.get('quarantined', False)
            if quarantined:
                status_lines.append(f"[bold]Quarantined:[/bold] [yellow]⚠ Yes[/yellow]")
            
            # Timing information
            uptime = status.get('tracker_uptime')
            if uptime:
                uptime_str = self._format_uptime(uptime.total_seconds() if hasattr(uptime, 'total_seconds') else uptime)
                status_lines.append(f"[bold]Uptime:[/bold] {uptime_str}")
            
            # Error information
            error_msg = status.get('error_message')
            if error_msg:
                status_lines.append(f"[bold]Error:[/bold] [red]{error_msg}[/red]")
            
            # Event information
            event_count = status.get('recent_events_count', 0)
            status_lines.append(f"[bold]Recent Events:[/bold] {event_count}")
            
            # Metadata
            metadata = status.get('tracker_metadata', {})
            if metadata:
                status_lines.append(f"[bold]Metadata:[/bold] {len(metadata)} keys")
            
            # Create and show the panel
            panel_content = "\n".join(status_lines)
            panel = Panel(
                panel_content,
                title=f"🔌 {server_name} Status",
                border_style="cyan"
            )
            
            emit_info(panel, message_group=group_id)
            
            # Show recent events if available
            recent_events = status.get('recent_events', [])
            if recent_events:
                emit_info("\n📋 Recent Events:", message_group=group_id)
                for event in recent_events[-5:]:  # Show last 5 events
                    timestamp = datetime.fromisoformat(event["timestamp"])
                    time_str = timestamp.strftime("%H:%M:%S")
                    event_type = event["event_type"]
                    details = event.get("details", {})
                    message = details.get("message", "")
                    
                    emit_info(f"  [dim]{time_str}[/dim] [cyan]{event_type}[/cyan] {message}", message_group=group_id)
        
        except Exception as e:
            logger.error(f"Error showing detailed status for server '{server_name}': {e}")
            emit_info(f"Failed to get detailed status: {e}", message_group=group_id)
    
    def _handle_interactive_requirements(self, template, custom_name: str, group_id: str) -> Dict:
        """Handle comprehensive requirements in interactive mode."""
        from code_puppy.messaging import emit_prompt
        
        requirements = template.get_requirements()
        config_overrides = {}
        
        # 1. Check system requirements
        if requirements.required_tools:
            emit_info("[bold cyan]Checking system requirements...[/bold cyan]", message_group=group_id)
            from code_puppy.mcp.system_tools import detector
            
            tool_status = detector.detect_tools(requirements.required_tools)
            missing_tools = []
            
            for tool_name, tool_info in tool_status.items():
                if tool_info.available:
                    emit_info(f"✅ {tool_name} ({tool_info.version or 'found'})", message_group=group_id)
                else:
                    emit_info(f"❌ {tool_name} - {tool_info.error}", message_group=group_id)
                    missing_tools.append(tool_name)
            
            if missing_tools:
                emit_info(f"[red]Missing required tools: {', '.join(missing_tools)}[/red]", message_group=group_id)
                
                # Show installation suggestions
                for tool in missing_tools:
                    suggestions = detector.get_installation_suggestions(tool)
                    emit_info(f"Install {tool}: {suggestions[0]}", message_group=group_id)
                
                proceed = emit_prompt("Continue installation anyway? (y/N): ")
                if proceed.lower() not in ['y', 'yes']:
                    raise Exception("Installation cancelled due to missing requirements")
        
        # 2. Environment variables
        env_vars = template.get_environment_vars()
        if env_vars:
            emit_info("[bold yellow]Environment Variables:[/bold yellow]", message_group=group_id)
            
            for var in env_vars:
                import os
                if var in os.environ:
                    emit_info(f"✅ {var} (already set)", message_group=group_id)
                else:
                    try:
                        value = emit_prompt(f"Enter {var}: ")
                        if value.strip():
                            os.environ[var] = value.strip()
                            emit_info(f"[green]Set {var}[/green]", message_group=group_id)
                        else:
                            emit_info(f"[yellow]Skipped {var} (empty value)[/yellow]", message_group=group_id)
                    except Exception as e:
                        emit_info(f"[yellow]Failed to get {var}: {e}[/yellow]", message_group=group_id)
        
        # 3. Command line arguments
        cmd_args = requirements.command_line_args
        if cmd_args:
            emit_info("[bold green]Command Line Arguments:[/bold green]", message_group=group_id)
            
            for arg_config in cmd_args:
                name = arg_config.get("name", "")
                prompt_text = arg_config.get("prompt", name)
                default = arg_config.get("default", "")
                required = arg_config.get("required", True)
                
                try:
                    if default:
                        value = emit_prompt(f"{prompt_text} (default: {default}): ")
                        value = value.strip() or default
                    else:
                        value = emit_prompt(f"{prompt_text}: ")
                        value = value.strip()
                    
                    if value:
                        config_overrides[name] = value
                        emit_info(f"[green]Set {name}={value}[/green]", message_group=group_id)
                    elif required:
                        emit_info(f"[yellow]Required argument {name} not provided[/yellow]", message_group=group_id)
                    
                except Exception as e:
                    emit_info(f"[yellow]Failed to get {name}: {e}[/yellow]", message_group=group_id)
        
        # 4. Package dependencies (informational)
        packages = requirements.package_dependencies
        if packages:
            emit_info("[bold magenta]Package Dependencies:[/bold magenta]", message_group=group_id)
            emit_info(f"This server requires: {', '.join(packages)}", message_group=group_id)
            emit_info("These will be installed automatically when the server starts.", message_group=group_id)
        
        return config_overrides