"""sync_from_config drops registry entries that left mcp_servers.json."""

import json
from unittest.mock import patch

from code_puppy.mcp_.manager import MCPManager


def test_sync_from_config_drops_servers_absent_from_json(tmp_path, monkeypatch):
    monkeypatch.setattr("code_puppy.config.DATA_DIR", str(tmp_path))

    present = {
        "proj-stdio": {"type": "stdio", "command": "/usr/bin/true", "enabled": True}
    }

    with patch("code_puppy.config.load_mcp_server_configs", return_value=present):
        manager = MCPManager()

    assert manager.registry.get_by_name("proj-stdio") is not None

    with patch("code_puppy.config.load_mcp_server_configs", return_value={}):
        manager.sync_from_config()

    assert manager.registry.get_by_name("proj-stdio") is None


def test_sync_from_config_keeps_registry_when_json_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr("code_puppy.config.DATA_DIR", str(tmp_path))
    servers_file = tmp_path / "mcp_servers.json"
    monkeypatch.setattr("code_puppy.config.MCP_SERVERS_FILE", str(servers_file))
    monkeypatch.setattr(
        "code_puppy.mcp_.project_config.load_project_mcp_server_configs",
        lambda *args, **kwargs: {},
    )

    present = {"keepme": {"type": "stdio", "command": "/usr/bin/true", "enabled": True}}
    servers_file.write_text(json.dumps({"mcp_servers": present}))

    manager = MCPManager()
    assert manager.registry.get_by_name("keepme") is not None

    servers_file.write_text("{not json")
    manager.sync_from_config()

    assert manager.registry.get_by_name("keepme") is not None
