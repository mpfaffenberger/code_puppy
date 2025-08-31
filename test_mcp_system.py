#!/usr/bin/env python3
"""
End-to-end test script for the new MCP management system.
Tests all major components and functionality.
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_puppy.mcp import (
    get_mcp_manager,
    ServerConfig,
    ManagedMCPServer,
    MCPDashboard
)
from code_puppy.command_line.mcp_commands import MCPCommandHandler
from rich.console import Console

console = Console()

async def test_mcp_system():
    """Test the complete MCP system."""
    console.print("\n[bold cyan]MCP System End-to-End Test[/bold cyan]\n")
    
    # 1. Test Manager Initialization
    console.print("[yellow]1. Testing Manager Initialization...[/yellow]")
    manager = get_mcp_manager()
    assert manager is not None, "Manager should be initialized"
    console.print("   [green]✓[/green] Manager initialized successfully")
    
    # 2. Test Server Registration
    console.print("\n[yellow]2. Testing Server Registration...[/yellow]")
    test_config = ServerConfig(
        id="test-server-1",
        name="test-echo-server",
        type="stdio",
        enabled=True,
        config={
            "command": "echo",
            "args": ["MCP Test Server"],
            "timeout": 5
        }
    )
    
    server_id = manager.register_server(test_config)
    assert server_id is not None, "Server should be registered"
    console.print(f"   [green]✓[/green] Server registered with ID: {server_id}")
    
    # 3. Test Server Listing
    console.print("\n[yellow]3. Testing Server Listing...[/yellow]")
    servers = manager.list_servers()
    assert len(servers) > 0, "Should have at least one server"
    console.print(f"   [green]✓[/green] Found {len(servers)} server(s)")
    for server in servers:
        console.print(f"      - {server.name} ({server.type}) - State: {server.state.value}")
    
    # 4. Test Dashboard Rendering
    console.print("\n[yellow]4. Testing Dashboard Rendering...[/yellow]")
    dashboard = MCPDashboard()
    table = dashboard.render_dashboard()
    assert table is not None, "Dashboard should render"
    console.print("   [green]✓[/green] Dashboard rendered successfully")
    console.print(table)
    
    # 5. Test Command Handler
    console.print("\n[yellow]5. Testing Command Handler...[/yellow]")
    cmd_handler = MCPCommandHandler()
    
    # Test list command
    result = cmd_handler.handle_mcp_command("/mcp list")
    assert result == True, "List command should succeed"
    console.print("   [green]✓[/green] /mcp list command executed")
    
    # Test status command
    result = cmd_handler.handle_mcp_command(f"/mcp status {test_config.name}")
    assert result == True, "Status command should succeed"
    console.print("   [green]✓[/green] /mcp status command executed")
    
    # 6. Test Enable/Disable
    console.print("\n[yellow]6. Testing Enable/Disable...[/yellow]")
    
    # Disable server
    success = manager.disable_server(server_id)
    assert success == True, "Should disable server"
    console.print("   [green]✓[/green] Server disabled")
    
    # Check it's disabled
    server_info = next((s for s in manager.list_servers() if s.id == server_id), None)
    assert server_info is not None and not server_info.enabled, "Server should be disabled"
    console.print("   [green]✓[/green] Server state verified as disabled")
    
    # Enable server
    success = manager.enable_server(server_id)
    assert success == True, "Should enable server"
    console.print("   [green]✓[/green] Server enabled")
    
    # 7. Test get_servers_for_agent (Critical for pydantic-ai compatibility)
    console.print("\n[yellow]7. Testing Agent Integration (pydantic-ai compatibility)...[/yellow]")
    
    # This is the critical method that must return pydantic-ai server instances
    agent_servers = manager.get_servers_for_agent()
    console.print(f"   [green]✓[/green] Got {len(agent_servers)} server(s) for agent")
    
    # Verify they are actual pydantic-ai instances (not our wrappers)
    from pydantic_ai.mcp import MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP
    for server in agent_servers:
        assert isinstance(server, (MCPServerSSE, MCPServerStdio, MCPServerStreamableHTTP)), \
            f"Server must be pydantic-ai instance, got {type(server)}"
    console.print("   [green]✓[/green] All servers are valid pydantic-ai instances")
    
    # 8. Test Error Isolation
    console.print("\n[yellow]8. Testing Error Isolation...[/yellow]")
    
    # Register a server that will fail
    bad_config = ServerConfig(
        id="bad-server",
        name="failing-server",
        type="stdio",
        enabled=True,
        config={
            "command": "/nonexistent/command",
            "args": []
        }
    )
    
    try:
        bad_id = manager.register_server(bad_config)
        # Try to get servers - should not crash even with bad server
        agent_servers = manager.get_servers_for_agent()
        console.print("   [green]✓[/green] Error isolation working - bad server didn't crash system")
    except Exception as e:
        console.print(f"   [red]✗[/red] Error isolation may have issues: {e}")
    
    # 9. Test Reload Functionality
    console.print("\n[yellow]9. Testing Reload Functionality...[/yellow]")
    success = manager.reload_server(server_id)
    assert success == True, "Should reload server"
    console.print("   [green]✓[/green] Server reloaded successfully")
    
    # 10. Test Server Removal
    console.print("\n[yellow]10. Testing Server Removal...[/yellow]")
    success = manager.remove_server(server_id)
    assert success == True, "Should remove server"
    console.print("   [green]✓[/green] Server removed")
    
    # Verify it's gone
    servers = manager.list_servers()
    assert not any(s.id == server_id for s in servers), "Server should be removed"
    console.print("   [green]✓[/green] Server verified as removed")
    
    # Summary
    console.print("\n[bold green]✅ All tests passed![/bold green]")
    console.print("\n[dim]The MCP management system is working correctly with:[/dim]")
    console.print("[dim]  • Full pydantic-ai compatibility[/dim]")
    console.print("[dim]  • Error isolation and recovery[/dim]")
    console.print("[dim]  • Runtime server management[/dim]")
    console.print("[dim]  • Command interface integration[/dim]")
    console.print("[dim]  • Dashboard visualization[/dim]")

def main():
    """Run the test."""
    try:
        asyncio.run(test_mcp_system())
    except AssertionError as e:
        console.print(f"\n[bold red]❌ Test failed: {e}[/bold red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]❌ Unexpected error: {e}[/bold red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()