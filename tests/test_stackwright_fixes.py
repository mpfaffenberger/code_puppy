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

        # enable() sets the _enabled flag so get_servers_for_agent() returns
        # this server to pydantic-ai.  It does NOT start a subprocess.
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

        # Patch _persist and _load to prevent writing test servers to the real
        # mcp_registry.json and loading stale entries from it.
        with patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_json)), \
             patch("code_puppy.mcp_.manager.MCPManager.sync_from_local_config"), \
             patch("code_puppy.mcp_.registry.ServerRegistry._persist"), \
             patch("code_puppy.mcp_.registry.ServerRegistry._load"):
            from code_puppy.mcp_.manager import MCPManager
            manager = MCPManager()

        # my-server was synced through the registry (global config path)
        server = manager.get_server_by_name("my-server")
        assert server is not None

        # Find the managed server — it must be enabled (flag) so that
        # get_servers_for_agent() returns it to pydantic-ai.
        managed = next(
            (s for s in manager._managed_servers.values()
             if s.config.name == "my-server"),
            None,
        )
        assert managed is not None
        assert managed.is_enabled() is True

        # Status tracker must be STOPPED — no subprocess has been spawned.
        # The tracker advances to RUNNING only via start_server() which also
        # calls record_start_time() and actually starts the process.
        # Falsely setting RUNNING here caused "State: ✓ Run, Uptime: -" in
        # /mcp status because record_start_time() was never called.
        # get_status() returns a ServerState enum; key is the server's UUID.
        from code_puppy.mcp_.managed_server import ServerState
        tracker_state = manager.status_tracker.get_status(managed.config.id)
        assert tracker_state == ServerState.STOPPED, (
            f"Expected tracker STOPPED, got {tracker_state} — "
            "start_server() is responsible for advancing to RUNNING"
        )


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
        """MCPManager should load servers from local .code-puppy.json into managed servers."""
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

        # Patch _persist and _load to prevent writing test servers to the real
        # mcp_registry.json and loading stale entries from it.
        with patch("code_puppy.config.MCP_SERVERS_FILE", str(empty_global)), \
             patch("os.getcwd", return_value=str(tmp_path)), \
             patch("code_puppy.mcp_.registry.ServerRegistry._persist"), \
             patch("code_puppy.mcp_.registry.ServerRegistry._load"):
            from code_puppy.mcp_.manager import MCPManager
            manager = MCPManager()

        # Local servers bypass the registry (ephemeral — not written to
        # mcp_registry.json).  Check _managed_servers directly.
        managed = next(
            (s for s in manager._managed_servers.values()
             if s.config.name == "local-server"),
            None,
        )
        assert managed is not None
        assert managed.is_enabled() is True


# ── Fix 3: ask_user_question JSON-string coercion ──────────────────────────

class TestAskUserQuestionJsonCoercion:
    """BeforeValidator in registration.py should coerce JSON strings to lists."""

    def test_coerce_valid_json_string_to_list(self):
        """A JSON-stringified array should be parsed to a native list."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        questions = [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
        json_string = json.dumps(questions)
        result = _coerce_questions_json_string(json_string)
        assert result == questions
        assert isinstance(result, list)

    def test_passthrough_native_list(self):
        """A native list passes through unchanged."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        questions = [{"question": "q", "header": "h", "options": [{"label": "a"}]}]
        result = _coerce_questions_json_string(questions)
        assert result is questions  # exact same object — no copy

    def test_passthrough_invalid_json_string(self):
        """A non-JSON string passes through unchanged (pydantic produces the error)."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        bad = "not-json"
        result = _coerce_questions_json_string(bad)
        assert result == bad

    def test_passthrough_none(self):
        """None passes through unchanged."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        assert _coerce_questions_json_string(None) is None

    def test_passthrough_dict(self):
        """A dict (wrong type but not a string) passes through unchanged."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        d = {"question": "q"}
        result = _coerce_questions_json_string(d)
        assert result is d

    def test_coerce_empty_array_string(self):
        """The string '[]' coerces to an empty list."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        result = _coerce_questions_json_string("[]")
        assert result == []

    def test_coerce_single_element_array_string(self):
        """A single-element JSON array string coerces correctly (the failing case)."""
        from code_puppy.tools.ask_user_question.registration import (
            _coerce_questions_json_string,
        )
        q = [{"question": "Which theme?", "header": "Theme", "options": [{"label": "A"}, {"label": "B"}]}]
        result = _coerce_questions_json_string(json.dumps(q))
        assert result == q
        assert len(result) == 1
