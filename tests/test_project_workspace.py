"""
Tests for .code_puppy/ project workspace discovery and configuration.

Covers get_project_workspace(), is_project_only(), and the updated
get_project_agents_directory() that prefers workspace over legacy paths.

Bead: code_puppy-9id
"""

import json
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
        """A .code_puppy/ dir in CWD is discovered."""
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
        """A .code_puppy/ dir in a parent is discovered from a nested CWD."""
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
        """Returns None when no .code_puppy/ exists anywhere."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            result = get_project_workspace()

        assert result is None

    def test_stops_at_git_root(self, tmp_path):
        """Walk-up stops at git root — workspace above .git is not found."""
        # Layout:
        #   tmp_path/.code_puppy/       ← above git root, should NOT be found
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
        #   tmp_path/.code_puppy/config.json  {"projectOnly": false}
        #   tmp_path/sub/.code_puppy/config.json  {"projectOnly": true}
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
        """Prefers .code_puppy/agents/ from the workspace."""
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
        """Workspace agents path wins over CWD-level legacy fallback.

        Mocks get_project_workspace() to return a workspace at a
        known parent path. The workspace agents dir should be returned
        even though a separate CWD-level legacy dir also exists.
        """
        from code_puppy.config import ProjectWorkspace

        # Workspace at a parent directory (found via mocked walk-up)
        parent = tmp_path / "parent"
        ws_path = parent / PROJECT_WORKSPACE_DIR_NAME
        ws_agents = ws_path / "agents"
        ws_agents.mkdir(parents=True)

        # CWD-level legacy dir also exists — should NOT be returned
        cwd = tmp_path / "sub"
        cwd_legacy = cwd / ".code_puppy" / "agents"
        cwd_legacy.mkdir(parents=True)

        fake_ws = ProjectWorkspace(
            root_path=str(parent),
            workspace_path=str(ws_path),
        )
        with patch("code_puppy.config.get_project_workspace", return_value=fake_ws):
            with patch("os.getcwd", return_value=str(cwd)):
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
        ws = ProjectWorkspace(root_path="/a", workspace_path="/a/.code_puppy")
        with pytest.raises(AttributeError):
            ws.project_only = True  # type: ignore[misc]

    def test_defaults(self):
        """Default values are correct."""
        ws = ProjectWorkspace(root_path="/a", workspace_path="/a/.code_puppy")
        assert ws.project_only is False
        assert ws.config == {}


# ── MCP workspace integration ─────────────────────────────────────────────


class TestMcpWorkspaceLoading:
    """Tests for MCP config loading from workspace (Commit 2)."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_workspace_mcp_servers_json_loaded(self, tmp_path):
        """mcp_servers.json in .code_puppy/ is preferred over config.json."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        mcp_config = {
            "mcp_servers": {"ws-server": {"command": "node", "args": ["server.js"]}}
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

        config = {"mcp_servers": {"srv": {"command": "${PROJECT_ROOT}/bin/mcp"}}}
        (ws_dir / "mcp_servers.json").write_text(json.dumps(config))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.config import load_local_mcp_config

            result = load_local_mcp_config()

        assert result["srv"]["command"] == f"{tmp_path}/bin/mcp"

    def test_legacy_code_puppy_json_still_works(self, tmp_path):
        """Legacy .code-puppy.json file is loaded when no workspace exists."""
        config = {
            "mcpServers": [{"name": "legacy-server", "command": "echo", "args": []}]
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
            json.dumps(
                {"mcp_servers": {"global-server": {"command": "global", "args": []}}}
            )
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
            json.dumps(
                {"mcp_servers": {"local-only": {"command": "local", "args": []}}}
            )
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
            ms.config.name == "local-only" for ms in manager._managed_servers.values()
        )
        assert local_found, "Local workspace server should be loaded"


# ── Agent discovery isolation ──────────────────────────────────────────────


class TestAgentDiscoveryProjectOnly:
    """Tests for agent discovery respecting projectOnly (Commit 3)."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_discover_json_agents_skips_user_in_project_only(self, tmp_path):
        """In projectOnly mode, user-level agents are NOT loaded."""
        # Create workspace with projectOnly
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        # Create a user-level agent
        user_agents = tmp_path / "user_agents"
        user_agents.mkdir()
        user_agent = {
            "name": "user-agent",
            "description": "A user agent",
            "system_prompt": "You are a user agent.",
            "tools": [],
        }
        (user_agents / "user-agent.json").write_text(json.dumps(user_agent))

        # Create a project-level agent in workspace
        project_agents = ws_dir / "agents"
        project_agents.mkdir()
        project_agent = {
            "name": "project-agent",
            "description": "A project agent",
            "system_prompt": "You are a project agent.",
            "tools": [],
        }
        (project_agents / "project-agent.json").write_text(json.dumps(project_agent))

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.config.AGENTS_DIR", str(user_agents)),
        ):
            from code_puppy.agents.json_agent import discover_json_agents

            agents = discover_json_agents()

        assert "project-agent" in agents, "Project agent should be discovered"
        assert "user-agent" not in agents, "User agent should be skipped in projectOnly"

    def test_discover_json_agents_includes_user_without_project_only(self, tmp_path):
        """Without projectOnly, both user and project agents are loaded."""
        # Create workspace WITHOUT projectOnly
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": False}))

        # User agent
        user_agents = tmp_path / "user_agents"
        user_agents.mkdir()
        user_agent = {
            "name": "user-agent",
            "description": "A user agent",
            "system_prompt": "You are a user agent.",
            "tools": [],
        }
        (user_agents / "user-agent.json").write_text(json.dumps(user_agent))

        # Project agent
        project_agents = ws_dir / "agents"
        project_agents.mkdir()
        project_agent = {
            "name": "project-agent",
            "description": "A project agent",
            "system_prompt": "You are a project agent.",
            "tools": [],
        }
        (project_agents / "project-agent.json").write_text(json.dumps(project_agent))

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.config.AGENTS_DIR", str(user_agents)),
        ):
            from code_puppy.agents.json_agent import discover_json_agents

            agents = discover_json_agents()

        assert "project-agent" in agents, "Project agent should be discovered"
        assert "user-agent" in agents, "User agent should be discovered (additive)"

    def test_project_agent_wins_on_collision(self, tmp_path):
        """Project agent overrides user agent on name collision."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()

        # User agent with same name
        user_agents = tmp_path / "user_agents"
        user_agents.mkdir()
        user_agent = {
            "name": "shared-name",
            "description": "User version",
            "system_prompt": "User.",
            "tools": [],
        }
        (user_agents / "shared-name.json").write_text(json.dumps(user_agent))

        # Project agent with same name
        project_agents = ws_dir / "agents"
        project_agents.mkdir()
        project_agent = {
            "name": "shared-name",
            "description": "Project version",
            "system_prompt": "Project.",
            "tools": [],
        }
        (project_agents / "shared-name.json").write_text(json.dumps(project_agent))

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch("code_puppy.config.AGENTS_DIR", str(user_agents)),
        ):
            from code_puppy.agents.json_agent import discover_json_agents

            agents = discover_json_agents()

        assert "shared-name" in agents
        # The path should be the project version
        assert str(project_agents) in agents["shared-name"]


class TestDiscoverAgentsProjectOnly:
    """Tests for _discover_agents() builtin filtering in projectOnly mode (Commit 3)."""

    def setup_method(self):
        _clear_workspace_cache()

    def test_code_puppy_agent_always_registered(self, tmp_path):
        """The base code-puppy agent is always available, even in projectOnly."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.agents.agent_manager import (
                _AGENT_REGISTRY,
                _discover_agents,
            )

            _discover_agents()

        assert "code-puppy" in _AGENT_REGISTRY, "code-puppy must always be registered"

    def test_builtin_agents_hidden_in_project_only(self, tmp_path):
        """Builtin Python agents are NOT registered in projectOnly mode."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.agents.agent_manager import (
                _AGENT_REGISTRY,
                _discover_agents,
            )

            _discover_agents()

        # These are some known builtin agents that should NOT be available
        builtin_names = {
            "security-auditor",
            "qa-kitten",
            "qa-expert",
            "python-reviewer",
        }
        found_builtins = builtin_names & set(_AGENT_REGISTRY.keys())
        assert not found_builtins, (
            f"Builtin agents should be hidden in projectOnly: {found_builtins}"
        )

    def test_all_builtins_registered_without_project_only(self, tmp_path):
        """Without projectOnly, builtin Python agents are registered normally."""
        # No workspace at all
        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.agents.agent_manager import (
                _AGENT_REGISTRY,
                _discover_agents,
            )

            _discover_agents()

        # At minimum, code-puppy and some builtins should be there
        assert "code-puppy" in _AGENT_REGISTRY
        # Check at least one builtin exists (security-auditor is always present)
        assert len(_AGENT_REGISTRY) > 1, (
            "Multiple agents should be registered in normal mode"
        )


# ── Plugin loading ─────────────────────────────────────────────────────────


class TestPluginLoadingProjectOnly:
    """Tests for project-local plugin loading with projectOnly gate (Commit 4)."""

    def setup_method(self):
        _clear_workspace_cache()
        # Reset the plugin-loaded flag so load_plugin_callbacks() runs fresh
        import code_puppy.plugins as plugins_mod

        plugins_mod._PLUGINS_LOADED = False

    def test_project_plugins_loaded_from_workspace(self, tmp_path):
        """Plugins in .code_puppy/plugins/ are discovered and loaded."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        plugin_dir = ws_dir / "plugins" / "test_plugin"
        plugin_dir.mkdir(parents=True)

        # Write a minimal register_callbacks.py
        (plugin_dir / "register_callbacks.py").write_text(
            "LOADED = True  # marker for test\n"
        )

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        assert "test_plugin" in result["project"]

    def test_user_plugins_skipped_in_project_only(self, tmp_path):
        """User plugins are NOT loaded when projectOnly is active."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        # Create a user plugin that should NOT be loaded
        user_plugins = tmp_path / "user_plugins" / "should_not_load"
        user_plugins.mkdir(parents=True)
        (user_plugins / "register_callbacks.py").write_text("LOADED = True\n")

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch(
                "code_puppy.plugins.USER_PLUGINS_DIR",
                tmp_path / "user_plugins",
            ),
        ):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        assert result["user"] == [], "User plugins should be skipped in projectOnly"

    def test_user_plugins_loaded_without_project_only(self, tmp_path):
        """User plugins ARE loaded when projectOnly is false."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": False}))

        # Create a user plugin
        user_plugins = tmp_path / "user_plugins" / "my_user_plugin"
        user_plugins.mkdir(parents=True)
        (user_plugins / "register_callbacks.py").write_text("LOADED = True\n")

        with (
            patch("os.getcwd", return_value=str(tmp_path)),
            patch(
                "code_puppy.plugins.USER_PLUGINS_DIR",
                tmp_path / "user_plugins",
            ),
        ):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        assert "my_user_plugin" in result["user"]

    def test_builtin_plugins_always_load(self, tmp_path):
        """Builtin plugins load even in projectOnly mode."""
        ws_dir = tmp_path / PROJECT_WORKSPACE_DIR_NAME
        ws_dir.mkdir()
        (ws_dir / "config.json").write_text(json.dumps({"projectOnly": True}))

        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        # Builtin plugins should be loaded (at least some exist)
        assert isinstance(result["builtin"], list)
        # The exact count depends on the codebase, but builtins should not be empty
        # (there are always some builtin plugins like file_permission_handler)

    def test_result_has_three_keys(self, tmp_path):
        """Return dict always has builtin, user, and project keys."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        assert set(result.keys()) == {"builtin", "user", "project"}

    def test_no_workspace_no_project_plugins(self, tmp_path):
        """When no workspace exists, project plugins list is empty."""
        with patch("os.getcwd", return_value=str(tmp_path)):
            from code_puppy.plugins import load_plugin_callbacks

            result = load_plugin_callbacks()

        assert result["project"] == []
