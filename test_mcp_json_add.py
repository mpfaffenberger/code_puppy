#!/usr/bin/env python3
"""
Test script for JSON-based /mcp add command.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.command_line.mcp_commands import MCPCommandHandler
from code_puppy.mcp import get_mcp_manager
from rich.console import Console

console = Console()

def test_mcp_json_add():
    """Test the /mcp add command with JSON."""
    console.print("\n[bold cyan]Testing /mcp add with JSON[/bold cyan]\n")
    
    # Initialize
    handler = MCPCommandHandler()
    manager = get_mcp_manager()
    
    # Test 1: Add stdio server via JSON
    console.print("[yellow]1. Adding stdio server via JSON:[/yellow]")
    json_cmd = '/mcp add {"name": "test-stdio", "type": "stdio", "command": "echo", "args": ["Hello MCP"], "timeout": 10}'
    console.print(f"[dim]Command: {json_cmd}[/dim]")
    handler.handle_mcp_command(json_cmd)
    
    # Test 2: Add HTTP server via JSON
    console.print("\n[yellow]2. Adding HTTP server via JSON:[/yellow]")
    json_cmd = '/mcp add {"name": "test-http", "type": "http", "url": "http://localhost:8080/mcp", "timeout": 30}'
    console.print(f"[dim]Command: {json_cmd}[/dim]")
    handler.handle_mcp_command(json_cmd)
    
    # Test 3: Add SSE server via JSON
    console.print("\n[yellow]3. Adding SSE server via JSON:[/yellow]")
    json_cmd = '/mcp add {"name": "test-sse", "type": "sse", "url": "http://localhost:3000/sse", "headers": {"Authorization": "Bearer token"}}'
    console.print(f"[dim]Command: {json_cmd}[/dim]")
    handler.handle_mcp_command(json_cmd)
    
    # Test 4: List all servers
    console.print("\n[yellow]4. Listing all servers:[/yellow]")
    handler.handle_mcp_command("/mcp list")
    
    # Test 5: Invalid JSON
    console.print("\n[yellow]5. Testing invalid JSON:[/yellow]")
    json_cmd = '/mcp add {invalid json}'
    console.print(f"[dim]Command: {json_cmd}[/dim]")
    handler.handle_mcp_command(json_cmd)
    
    # Test 6: Missing required fields
    console.print("\n[yellow]6. Testing missing required fields:[/yellow]")
    json_cmd = '/mcp add {"type": "stdio"}'
    console.print(f"[dim]Command: {json_cmd}[/dim]")
    handler.handle_mcp_command(json_cmd)
    
    # Clean up
    console.print("\n[yellow]7. Cleaning up test servers:[/yellow]")
    for name in ["test-stdio", "test-http", "test-sse"]:
        servers = manager.list_servers()
        for server in servers:
            if server.name == name:
                manager.remove_server(server.id)
                console.print(f"[green]✓[/green] Removed {name}")
    
    console.print("\n[bold green]✅ JSON-based /mcp add test complete![/bold green]")

if __name__ == "__main__":
    test_mcp_json_add()