"""
Tests for .code-puppy/ project workspace discovery and configuration.

Covers get_project_workspace(), is_project_only(), and the updated
get_project_agents_directory() that prefers workspace over legacy paths.

Bead: code_puppy-9id
"""

import json
import os
from unittest.mock import patch

import pytest

from code_puppy.config import (
    PROJECT_WORKSPACE_DIR_NAME,
    ProjectWorkspace,
    get_project_agents_directory,
    get_project_workspace,
    is_project_only,
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _clear_workspace_cache():
    """Reset the module-level workspace cache between tests."""
    import code_puppy.config as cfg

    cfg._workspace_cache = None
    cfg._workspace_cache_cwd = None


# ── get_project_workspace() ────────────────────────────────────────────────


class TestGetProjectWorkspace:
    """Unit tests for workspace discovery."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_workspace_found_at_cwd(self, tmp_path):
        """A .code-puppy/ dir in CWD is discovered."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is not None
        assert result.root_path == str(tmp_path)
        assert result.workspace_path == str(ws_dir)
        assert result.project_only is False
        assert result.config == {}

    def test_workspace_found_in_parent(self, tmp_path):
        """A .code-puppy/ dir in a parent is discovered from a nested CWD."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        nested = tmp_path / "src" / "components"
        nested.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(nested)):
            result = get_project_workspace()

        assert result is not None
        assert result.root_path == str(tmp_path)

    def test_config_json_parsed(self, tmp_path):
        """config.json is read and projectOnly is extracted."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        config = {"projectOnly": True, "extra": "value"}
        (ws_dir / "config.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is not None
        assert result.project_only is True
        assert result.config == config

    def test_project_only_defaults_false(self, tmp_path):
        """projectOnly defaults to False when missing from config.json."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"other": "stuff"}))

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is not None
        assert result.project_only is False

    def test_no_config_json_is_valid(self, tmp_path):
        """A workspace dir without config.json is valid — uses defaults."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is not None
        assert result.project_only is False
        assert result.config == {}

    def test_malformed_config_json_treated_as_empty(self, tmp_path):
        """Malformed config.json doesn't crash — treated as empty."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text("{ this is not valid json }")

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is not None
        assert result.project_only is False
        assert result.config == {}

    def test_returns_none_when_no_workspace(self, tmp_path):
        """Returns None when no .code-puppy/ exists anywhere."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is None

    def test_stops_at_git_root(self, tmp_path):
        """Walk-up stops at git root — workspace above .git is not found."""
        # Layout:
        #   tmp_path/.code-puppy/       ← above git root, should NOT be found
        #   tmp_path/repo/.git/
        #   tmp_path/repo/src/          ← CWD
        (tmp_path / PROJECT_WORKSPACE_DIR_NAME).mkdir()

        repo_root = tmp_path / "repo"
        (repo_root / ".git").mkdir(parents=True)
        src_dir = repo_root / "src"
        src_dir.mkdir()

        with patch("os.getcwd", return_value=str(src_dir)):
            result = get_project_workspace()

        assert result is None

    def test_workspace_at_git_root_is_found(self, tmp_path):
        """Workspace placed AT the git root is still discovered."""
        repo_root = tmp_path / "repo"
        (repo_root / ".git").mkdir(parents=True)
        ws_dir = repo_root / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        src_dir = repo_root / "src"
        src_dir.mkdir()

        with patch("os.getcwd", return_value=str(src_dir)):
            result = get_project_workspace()

        assert result is not None
        assert result.root_path == str(repo_root)

    def test_caching_returns_same_result(self, tmp_path):
        """Subsequent calls with same CWD return cached result."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            first = get_project_workspace()
            second = get_project_workspace()

        assert first is second  # Same object, not just equal

    def test_cache_invalidated_on_cwd_change(self, tmp_path):
        """Cache is invalidated when CWD changes."""
        dir_a = tmp_path / "a"
        dir_a.mkdir()
        (dir_a / PROJECT_WORKSPACE_DIR_NAME).mkdir()

        dir_b = tmp_path / "b"
        dir_b.mkdir()
        # dir_b has NO workspace

        with patch("os.getcwd", return_value=str(dir_a)):
            result_a = get_project_workspace()
        assert result_a is not None

        _clear_workspace_cache()

        with patch("os.getcwd", return_value=str(dir_b)):
            result_b = get_project_workspace()
        assert result_b is None

    def test_nearest_workspace_wins(self, tmp_path):
        """When nested workspaces exist, the nearest one wins."""
        # Layout:
        #   tmp_path/.code-puppy/config.json  {"projectOnly": false}
        #   tmp_path/sub/.code-puppy/config.json  {"projectOnly": true}
        outer_ws = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        outer_ws.mkdir()
        (outer_ws / "config.json").write_text(json.dumps({"projectOnly": False}))

        sub = tmp_path / "sub"
        sub.mkdir()
        inner_ws = sub / PROJECT_WORKSPACE_DIR_NAME
        inner_ws.mkdir()
        (inner_ws / "config.json").write_text(json.dumps({"projectOnly": True}))

        with patch("os.getcwd", return_value=str(sub)):
            result = get_project_workspace()

        assert result is not None
        assert result.root_path == str(sub)
        assert result.project_only is True


# ── is_project_only() ─────────────────────────────────────────────────────


class TestIsProjectOnly:
    """Tests for the convenience wrapper."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_true_when_project_only_set(self, tmp_path):
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        with patch("os.getcwd", return_value=str(tmp_path)):
            assert is_project_only() is True

    def test_false_when_project_only_not_set(self, tmp_path):
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            assert is_project_only() is False

    def test_false_when_no_workspace(self, tmp_path):
        with patch("os.getcwd", return_value=str(tmp_path)):
            assert is_project_only() is False


# ── get_project_agents_directory() ─────────────────────────────────────────


class TestGetProjectAgentsDirectory:
    """Tests for workspace-aware agent directory discovery."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_returns_workspace_agents_dir(self, tmp_path):
        """Prefers .code-puppy/agents/ from the workspace."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        agents_dir = ws_dir / "agents"
        agents_dir.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_agents_directory()

        assert result == str(agents_dir)

    def test_falls_back_to_legacy_dir(self, tmp_path):
        """Falls back to .code_puppy/agents/ (underscore) when no workspace."""
        legacy_dir = tmp_path / ".code_puppy" / "agents"
        legacy_dir.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_agents_directory()

        assert result == str(legacy_dir)

    def test_workspace_preferred_over_legacy(self, tmp_path):
        """When both workspace and legacy exist, workspace wins."""
        # Workspace
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_agents = ws_dir / "agents"
        ws_agents.mkdir(parents=True)

        # Legacy
        legacy_dir = tmp_path / ".code_puppy" / "agents"
        legacy_dir.mkdir(parents=True)

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_agents_directory()

        assert result == str(ws_agents)

    def test_returns_none_when_no_agents_dir(self, tmp_path):
        """Returns None when workspace exists but has no agents/ subdir."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_agents_directory()

        assert result is None

    def test_returns_none_when_nothing_exists(self, tmp_path):
        """Returns None when neither workspace nor legacy dir exists."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_agents_directory()

        assert result is None


# ── ProjectWorkspace dataclass ─────────────────────────────────────────────


class TestProjectWorkspaceDataclass:
    """Tests for the frozen dataclass itself."""

    def test_frozen(self):
        """ProjectWorkspace is immutable."""
        ws = ProjectWorkspace(root_path="/a", workspace_path="/a/.code-puppy")
        with pytest.raises(AttributeError):
            ws.project_only = True  # type: ignore[misc]

    def test_defaults(self):
        """Default values are correct."""
        ws = ProjectWorkspace(root_path="/a", workspace_path="/a/.code-puppy")
        assert ws.project_only is False
        assert ws.config == {}


# ── MCP workspace integration ─────────────────────────────────────────────


class TestMcpWorkspaceLoading:
    """Tests for MCP config loading from workspace (Commit 2)."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_workspace_mcp_servers_json_loaded(self, tmp_path):
        """mcp_servers.json in .code-puppy/ is preferred over config.json."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        mcp_config = {
            "mcp_servers": {
                "ws-server": {"command": "node", "args": ["server.js"]}
            }
        }
        (ws_dir / "mcp_servers.json").write_text(json.dumps(mcp_config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "ws-server" in result
        assert result["ws-server"]["command"] == "node"

    def test_workspace_config_json_mcp_fallback(self, tmp_path):
        """mcpServers in config.json used when no mcp_servers.json exists."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        config = {
            "projectOnly": True,
            "mcpServers": [
                {"name": "cfg-server", "command": "echo", "args": ["hello"]}
            ],
        }
        (ws_dir / "config.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "cfg-server" in result
        assert result["cfg-server"]["command"] == "echo"

    def test_workspace_mcp_servers_json_preferred_over_config_json(self, tmp_path):
        """Dedicated mcp_servers.json takes priority over config.json keys."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        # mcp_servers.json has "preferred-server"
        (ws_dir / "mcp_servers.json").write_text(
            json.dumps({"mcp_servers": {"preferred-server": {"command": "a"}}})
        )
        # config.json also has MCP config
        (ws_dir / "config.json").write_text(
            json.dumps({"mcpServers": [{"name": "config-server", "command": "b"}]})
        )

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "preferred-server" in result
        assert "config-server" not in result

    def test_project_root_expanded_in_workspace_mcp(self, tmp_path):
        """${PROJECT_ROOT} expands to the workspace root_path."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        config = {
            "mcp_servers": {
                "srv": {"command": "${PROJECT_ROOT}/bin/mcp"}
            }
        }
        (ws_dir / "mcp_servers.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert result["srv"]["command"] == f"{tmp_path}/bin/mcp"

    def test_legacy_code_puppy_json_still_works(self, tmp_path):
        """Legacy .code-puppy.json file is loaded when no workspace exists."""
        config = {
            "mcpServers": [
                {"name": "legacy-server", "command": "echo", "args": []}
            ]
        }
        (tmp_path / ".code-puppy.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "legacy-server" in result

    def test_workspace_takes_priority_over_legacy_json(self, tmp_path):
        """When both workspace and .code-puppy.json exist, workspace wins."""
        # Workspace
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "mcp_servers.json").write_text(
            json.dumps({"mcp_servers": {"ws-win": {"command": "ws"}}})
        )
        # Legacy file
        (tmp_path / ".code-puppy.json").write_text(
            json.dumps({"mcpServers": [{"name": "legacy-lose", "command": "leg"}]})
        )

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert "ws-win" in result
        assert "legacy-lose" not in result


class TestMcpProjectOnlyMode:
    """Tests for projectOnly blocking global MCP config (Commit 2)."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_sync_from_config_skipped_in_project_only_mode(self, tmp_path):
        """MCPManager.sync_from_config() is a no-op when projectOnly is true."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        # Create a global config with a server that should NOT appear
        global_mcp = tmp_path / "global_mcp_servers.json"
        global_mcp.write_text(
            json.dumps({
                "mcp_servers": {
                    "global-server": {"command": "global", "args": []}
                }
            })
        )

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.config.MCP_SERVERS_FILE", str(global_mcp)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        # Global server should NOT be in managed servers
        global_found = any(
            ms.config.name == "global-server"
            for ms in manager._managed_servers.values()
        )
        assert not global_found, "Global server should be blocked by projectOnly"

    def test_local_servers_still_load_in_project_only_mode(self, tmp_path):
        """Local workspace servers are loaded even in projectOnly mode."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))
        (ws_dir / "mcp_servers.json").write_text(
            json.dumps({
                "mcp_servers": {
                    "local-only": {"command": "local", "args": []}
                }
            })
        )

        empty_global = tmp_path / "empty_global.json"
        empty_global.write_text(json.dumps({"mcp_servers": {}}))

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        local_found = any(
            ms.config.name == "local-only"
            for ms in manager._managed_servers.values()
        )
        assert local_found, "Local workspace server should be loaded"
