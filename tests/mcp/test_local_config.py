"""
Tests for project-local .code-puppy.json MCP server config loading.

Covers load_local_mcp_config() (config.py) and MCPManager.sync_from_local_config()
(mcp_/manager.py) including both file formats, directory walk-up, ${PROJECT_ROOT}
expansion, git-root boundary, and manager integration.
"""

import json
from unittest.mock import patch


# ── load_local_mcp_config() ────────────────────────────────────────────────


class TestLoadLocalMcpConfig:
    """Unit tests for config.load_local_mcp_config()."""

    def test_array_format_parsed_correctly(self, tmp_path):
        """mcpServers array format (VS Code-style) is normalised to object format."""
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
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "my-mcp" in result
        server = result["my-mcp"]
        assert server["command"] == "node"
        assert server["enabled"] is True  # autoStart → enabled
        assert "autoStart" not in server
        assert (
            str(tmp_path) in server["cwd"]
        )  # workingDirectory → cwd, ${PROJECT_ROOT} expanded
        assert "workingDirectory" not in server

    def test_object_format_parsed_correctly(self, tmp_path):
        """mcp_servers object format (native style) passes through unchanged."""
        config = {
            "mcp_servers": {
                "obj-server": {
                    "type": "stdio",
                    "command": "python",
                    "args": ["-m", "my_mcp"],
                }
            }
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "obj-server" in result
        assert result["obj-server"]["command"] == "python"

    def test_walks_up_to_parent_directory(self, tmp_path):
        """Config file in a parent dir is discovered from a nested CWD."""
        config = {
            "mcpServers": [{"name": "parent-server", "command": "echo", "args": []}]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        subdir = tmp_path / "src" / "components"
        subdir.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(subdir)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "parent-server" in result

    def test_returns_empty_when_no_config_found(self, tmp_path):
        """Returns {} when no .code-puppy.json exists anywhere in the search path."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert result == {}

    def test_project_root_expansion_in_args(self, tmp_path):
        """${PROJECT_ROOT} in args expands to the directory containing the config file."""
        config = {
            "mcpServers": [
                {
                    "name": "srv",
                    "command": "node",
                    "args": ["${PROJECT_ROOT}/node_modules/.bin/mcp-server"],
                }
            ]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert str(tmp_path) in result["srv"]["args"][0]
        assert "${PROJECT_ROOT}" not in result["srv"]["args"][0]

    def test_stops_at_git_root(self, tmp_path):
        """Walk-up stops at git root — config above .git is not discovered."""
        # Layout:
        #   tmp_path/.code-puppy.json  ← above the git root, should NOT be found
        #   tmp_path/repo/.git/
        #   tmp_path/repo/src/         ← CWD
        above_config = {
            "mcpServers": [{"name": "above-root", "command": "echo", "args": []}]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(above_config))

        repo_root = tmp_path / "repo"
        (repo_root / ".git").mkdir(parents=True)
        src_dir = repo_root / "src"
        src_dir.mkdir()

        with patch("os.getcwd", return_value=str(src_dir)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        # The config above the git root must NOT bleed in
        assert "above-root" not in result

    def test_config_at_git_root_is_found(self, tmp_path):
        """Config file placed AT the git root is still discovered."""
        repo_root = tmp_path / "repo"
        (repo_root / ".git").mkdir(parents=True)
        src_dir = repo_root / "src"
        src_dir.mkdir()

        config = {
            "mcpServers": [{"name": "root-server", "command": "echo", "args": []}]
        }
        (repo_root / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(src_dir)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "root-server" in result


# ── MCPManager.sync_from_local_config() ────────────────────────────────────


class TestManagerSyncsLocalConfig:
    """Integration tests for MCPManager loading from .code-puppy.json."""

    def test_local_servers_appear_in_managed_servers(self, tmp_path):
        """Servers from .code-puppy.json land in _managed_servers, not the registry."""
        local_config = {
            "mcpServers": [
                {
                    "name": "local-server",
                    "command": "node",
                    "args": ["server.js"],
                    "autoStart": True,
                }
            ]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(local_config))

        empty_global = tmp_path / "mcp_servers.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)),
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        # Local servers bypass the registry — check _managed_servers directly
        managed = next(
            (
                s
                for s in manager._managed_servers.values()
                if s.config.name == "local-server"
            ),
            None,
        )
        assert managed is not None
        assert managed.is_enabled() is True

    def test_local_server_id_tracked_in_local_set(self, tmp_path):
        """IDs of local servers appear in _local_server_ids for the Source column."""
        local_config = {
            "mcpServers": [{"name": "tracked-server", "command": "echo", "args": []}]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(local_config))

        empty_global = tmp_path / "mcp_servers.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)),
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        tracked_id = next(
            (
                sid
                for sid, ms in manager._managed_servers.items()
                if ms.config.name == "tracked-server"
            ),
            None,
        )
        assert tracked_id is not None
        assert tracked_id in manager._local_server_ids

    def test_list_servers_marks_local_servers(self, tmp_path):
        """list_servers() returns is_local=True for .code-puppy.json servers."""
        local_config = {
            "mcpServers": [{"name": "my-local", "command": "echo", "args": []}]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(local_config))

        empty_global = tmp_path / "mcp_servers.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)),
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        infos = manager.list_servers()
        local_info = next((s for s in infos if s.name == "my-local"), None)
        assert local_info is not None
        assert local_info.is_local is True

    def test_load_local_server_configs_is_pure(self, tmp_path):
        """_load_local_server_configs() returns the parsed dict without side effects."""
        local_config = {
            "mcpServers": [{"name": "pure-server", "command": "echo", "args": []}]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(local_config))

        empty_global = tmp_path / "mcp_servers.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)),
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        # Call the pure loader directly — should return the config dict
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = manager._load_local_server_configs()

        assert "pure-server" in result
        assert result["pure-server"]["command"] == "echo"
