import json
from unittest.mock import patch
from pathlib import Path

from code_puppy.plugins.claude_plugin_adapter.adapters.mcp import sync_mcp_adapter

def test_sync_mcp_adapter(monkeypatch, tmp_path):
    mock_plugin_dir = tmp_path / "claude_plugins"
    plugin_name = "test-plugin"
    plugin_path = mock_plugin_dir / plugin_name
    plugin_path.mkdir(parents=True)
    
    # Create plugin .mcp.json
    mcp_data = {
        "mcpServers": {
            "test_server": {
                "command": "node",
                "args": ["test.js"]
            }
        }
    }
    with open(plugin_path / ".mcp.json", "w") as f:
        json.dump(mcp_data, f)
        
    mock_mcp_servers_file = tmp_path / "mcp_servers.json"
    
    # Initial state: User has their own server
    initial_user_servers = {
        "mcp_servers": {
            "user_server": {
                "command": "python",
                "args": ["-m", "test"]
            }
        }
    }
    with open(mock_mcp_servers_file, "w") as f:
        json.dump(initial_user_servers, f)
        
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.mcp.get_claude_plugins_dir",
        lambda: mock_plugin_dir
    )
    monkeypatch.setattr(
        "code_puppy.plugins.claude_plugin_adapter.adapters.mcp.MCP_SERVERS_FILE",
        str(mock_mcp_servers_file)
    )

    # 1. Install sync
    sync_mcp_adapter(plugin_name)
    
    with open(mock_mcp_servers_file, "r") as f:
        merged = json.load(f)
        
    servers = merged["mcp_servers"]
    assert "user_server" in servers
    assert "test_server" in servers
    assert servers["test_server"]["_managed_by"] == "claude_plugin_adapter:test-plugin"
    
    # 2. Update plugin .mcp.json and sync again (idempotent update)
    mcp_data["mcpServers"]["test_server_2"] = {"command": "test"}
    with open(plugin_path / ".mcp.json", "w") as f:
        json.dump(mcp_data, f)
        
    sync_mcp_adapter(plugin_name)
    
    with open(mock_mcp_servers_file, "r") as f:
        merged2 = json.load(f)
        
    servers2 = merged2["mcp_servers"]
    assert "user_server" in servers2
    assert "test_server" in servers2
    assert "test_server_2" in servers2
    assert servers2["test_server"]["_managed_by"] == "claude_plugin_adapter:test-plugin"
    assert servers2["test_server_2"]["_managed_by"] == "claude_plugin_adapter:test-plugin"

    # 3. Uninstall sync
    sync_mcp_adapter(plugin_name, uninstall=True)
    
    with open(mock_mcp_servers_file, "r") as f:
        final = json.load(f)
        
    servers3 = final["mcp_servers"]
    assert "user_server" in servers3
    assert "test_server" not in servers3
    assert "test_server_2" not in servers3
