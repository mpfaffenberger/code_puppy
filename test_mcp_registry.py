#!/usr/bin/env python3
"""
Test script for MCP server registry functionality.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.command_line.mcp_commands import MCPCommandHandler
from code_puppy.mcp.server_registry_catalog import catalog
from rich.console import Console

console = Console()

def test_mcp_registry():
    """Test the MCP server registry."""
    console.print("\n[bold cyan]Testing MCP Server Registry[/bold cyan]\n")
    
    # Initialize
    handler = MCPCommandHandler()
    
    # Test 1: Show popular servers
    console.print("[yellow]1. Testing /mcp search (popular servers):[/yellow]")
    handler.handle_mcp_command("/mcp search")
    
    # Test 2: Search for specific category
    console.print("\n[yellow]2. Searching for database servers:[/yellow]")
    handler.handle_mcp_command("/mcp search database")
    
    # Test 3: Search for specific technology
    console.print("\n[yellow]3. Searching for git servers:[/yellow]")
    handler.handle_mcp_command("/mcp search git")
    
    # Test 4: Test catalog directly
    console.print("\n[yellow]4. Testing catalog directly:[/yellow]")
    
    # Get categories
    categories = catalog.list_categories()
    console.print(f"Available categories: {', '.join(categories)}")
    
    # Get popular servers
    popular = catalog.get_popular(5)
    console.print(f"\nTop 5 popular servers:")
    for server in popular:
        console.print(f"  • {server.id} - {server.display_name}")
    
    # Search test
    results = catalog.search("file")
    console.print(f"\nServers matching 'file': {len(results)} found")
    for server in results[:3]:
        console.print(f"  • {server.id} - {server.display_name}")
    
    # Test 5: Test install command (dry run)
    console.print("\n[yellow]5. Testing /mcp install command flow:[/yellow]")
    console.print("[dim]Note: This is a dry run showing what would happen[/dim]")
    
    # Show filesystem server details
    fs_server = catalog.get_by_id("filesystem")
    if fs_server:
        console.print(f"\n[cyan]Server: {fs_server.display_name}[/cyan]")
        console.print(f"Description: {fs_server.description}")
        console.print(f"Category: {fs_server.category}")
        console.print(f"Type: {fs_server.type}")
        console.print(f"Tags: {', '.join(fs_server.tags)}")
        console.print(f"Requirements: {', '.join(fs_server.requires)}")
        console.print(f"Config: {fs_server.config}")
    
    console.print("\n[bold green]✅ Registry test complete![/bold green]")
    console.print("\n[dim]The registry contains 30+ pre-configured MCP servers[/dim]")
    console.print("[dim]Users can search and install servers with:[/dim]")
    console.print("[cyan]/mcp search <query>[/cyan]  - Find servers")
    console.print("[cyan]/mcp install <id>[/cyan]    - Install a server")

if __name__ == "__main__":
    test_mcp_registry()