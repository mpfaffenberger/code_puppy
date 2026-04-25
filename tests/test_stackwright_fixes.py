"""
Tests for Stackwright-specific fixes to code-puppy.
These cover the two changes in CHANGES_FROM_UPSTREAM.md.
"""
import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ── Fix 1: Auto-enable on startup ──────────────────────────────────────────

class TestAutoEnableOnStartup:
    """MCP servers with enabled=True should be active immediately after MCPManager init."""

    def test_server_enabled_after_init(self):
        from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig

        config = ServerConfig(
            id="test-id",
            name="test-server",
            type="stdio",
            enabled=True,
            config={"command": "echo", "args": ["hello"]},
        )
        server = ManagedMCPServer(config)

        # Before fix: _enabled was always False
        # After fix: _initialize_servers() calls server.enable() when config.enabled=True
        # We test enable() directly since _initialize_servers() is tested via MCPManager
        server.enable()
        assert server.is_enabled() is True

    def test_server_disabled_when_config_disabled(self):
        from code_puppy.mcp_.managed_server import ManagedMCPServer, ServerConfig

        config = ServerConfig(
            id="test-id",
            name="disabled-server",
            type="stdio",
            enabled=False,
            config={"command": "echo", "args": []},
        )
        server = ManagedMCPServer(config)
        # Should NOT be enabled since config.enabled=False
        assert server.is_enabled() is False

    def test_manager_enables_servers_from_config(self, tmp_path):
        """MCPManager should auto-enable servers that have enabled=True in mcp_servers.json."""
        mcp_json = tmp_path / "mcp_servers.json"
        mcp_json.write_text(json.dumps({
            "mcp_servers": {
                "my-server": {
                    "type": "stdio",
                    "command": "echo",
                    "args": ["hi"],
                    "enabled": True,
                }
            }
        }))

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_json)), \
             patch("code_puppy.mcp_.manager.MCPManager.sync_from_local_config"):
            from code_puppy.mcp_.manager import MCPManager
            manager = MCPManager()

        server = manager.get_server_by_name("my-server")
        assert server is not None

        # Find the managed server and confirm it's enabled
        managed = next(
            (s for s in manager._managed_servers.values()
             if s.config.name == "my-server"),
            None,
        )
        assert managed is not None
        assert managed.is_enabled() is True


# ── Fix 2: Local .code-puppy.json loading ──────────────────────────────────

class TestLocalCodePuppyJson:
    """Local .code-puppy.json should be loaded and registered as MCP servers."""

    def test_load_local_config_array_format(self, tmp_path):
        """mcpServers array format is parsed correctly."""
        config = {
            "mcpServers": [
                {
                    "name": "my-mcp",
                    "command": "node",
                    "args": ["server.js"],
                    "autoStart": True,
                    "workingDirectory": "${PROJECT_ROOT}/dist",
                }
            ]
        }
        config_file = tmp_path / ".code-puppy.json"
        config_file.write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config
            result = load_local_mcp_config()

        assert "my-mcp" in result
        server = result["my-mcp"]
        assert server["command"] == "node"
        assert server["enabled"] is True  # autoStart mapped to enabled
        assert "autoStart" not in server
        assert str(tmp_path) in server["cwd"]  # workingDirectory mapped to cwd, PROJECT_ROOT expanded
        assert "workingDirectory" not in server

    def test_load_local_config_object_format(self, tmp_path):
        """mcp_servers object format is parsed correctly."""
        config = {
            "mcp_servers": {
                "obj-server": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "my_mcp"],
                }
            }
        }
        config_file = tmp_path / ".code-puppy.json"
        config_file.write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config
            result = load_local_mcp_config()

        assert "obj-server" in result
        assert result["obj-server"]["command"] == "python"

    def test_load_local_config_walks_up_dirs(self, tmp_path):
        """Should find .code-puppy.json in a parent directory."""
        config = {"mcpServers": [{"name": "parent-server", "command": "echo", "args": []}]}
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(subdir)):
            from code_puppy.config import load_local_mcp_config
            result = load_local_mcp_config()

        assert "parent-server" in result

    def test_load_local_config_returns_empty_when_not_found(self, tmp_path):
        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config
            result = load_local_mcp_config()
        assert result == {}

    def test_project_root_expansion(self, tmp_path):
        """${PROJECT_ROOT} should expand to the directory containing .code-puppy.json."""
        config = {
            "mcpServers": [{
                "name": "srv",
                "command": "node",
                "args": ["${PROJECT_ROOT}/node_modules/.bin/mcp-server"],
            }]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config
            result = load_local_mcp_config()

        assert str(tmp_path) in result["srv"]["args"][0]
        assert "${PROJECT_ROOT}" not in result["srv"]["args"][0]

    def test_manager_syncs_local_config(self, tmp_path):
        """MCPManager should register servers from local .code-puppy.json."""
        local_config = {
            "mcpServers": [{
                "name": "local-server",
                "command": "node",
                "args": ["server.js"],
                "autoStart": True,
            }]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(local_config))

        empty_global = tmp_path / "mcp_servers.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)), \
             patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.mcp_.manager import MCPManager
            manager = MCPManager()

        server = manager.get_server_by_name("local-server")
        assert server is not None

        managed = next(
            (s for s in manager._managed_servers.values()
             if s.config.name == "local-server"),
            None,
        )
        assert managed is not None
        assert managed.is_enabled() is True
