#!/usr/bin/env python3
"""
Test script for the /mcp add command functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.command_line.mcp_commands import MCPCommandHandler
from code_puppy.mcp import get_mcp_manager
from rich.console import Console

console = Console()

def test_mcp_add():
    """Test the /mcp add command."""
    console.print("\n[bold cyan]Testing /mcp add Command[/bold cyan]\n")
    
    # Initialize command handler
    handler = MCPCommandHandler()
    manager = get_mcp_manager()
    
    # Test 1: Test /mcp list before adding
    console.print("[yellow]1. Current servers:[/yellow]")
    handler.handle_mcp_command("/mcp list")
    
    # Test 2: Show help
    console.print("\n[yellow]2. Testing /mcp help:[/yellow]")
    handler.handle_mcp_command("/mcp help")
    
    # Test 3: Test the add command (non-interactive for now)
    console.print("\n[yellow]3. Testing /mcp add command structure:[/yellow]")
    console.print("[dim]Note: The wizard is interactive, so we'll test the command handler[/dim]")
    
    # Check that the command is properly handled
    result = handler.handle_mcp_command("/mcp add")
    console.print(f"Command handled: {result}")
    
    # Test 4: Test programmatic server addition
    console.print("\n[yellow]4. Testing programmatic server addition:[/yellow]")
    from code_puppy.mcp import ServerConfig
    
    test_config = ServerConfig(
        id="test-programmatic",
        name="test-prog-server",
        type="stdio",
        enabled=True,
        config={
            "command": "echo",
            "args": ["Test MCP Server"],
            "timeout": 5
        }
    )
    
    try:
        server_id = manager.register_server(test_config)
        console.print(f"[green]✓[/green] Programmatically added server: {server_id}")
        
        # List servers again
        console.print("\n[yellow]5. Servers after addition:[/yellow]")
        handler.handle_mcp_command("/mcp list")
        
        # Clean up
        manager.remove_server(server_id)
        console.print(f"\n[green]✓[/green] Cleaned up test server")
        
    except Exception as e:
        console.print(f"[red]✗[/red] Error: {e}")
    
    console.print("\n[bold green]✅ /mcp add command structure test complete![/bold green]")
    console.print("\n[dim]To test the interactive wizard, run:[/dim]")
    console.print("[cyan]python3 -c \"from code_puppy.mcp.config_wizard import run_add_wizard; run_add_wizard()\"[/cyan]")

if __name__ == "__main__":
    test_mcp_add()