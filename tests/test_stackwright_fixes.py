"""
Tests for Stackwright-specific fixes to code-puppy.

Covers: MCP auto-enable on startup, ask_user_question JSON-string coercion.
Local .code-puppy.json loading tests live in tests/mcp/test_local_config.py.
"""

import json
from unittest.mock import patch


# ── Auto-enable on startup ────────────────────────────────────────────────


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
        mcp_json.write_text(
            json.dumps(
                {
                    "mcp_servers": {
                        "my-server": {
                            "type": "stdio",
                            "command": "echo",
                            "args": ["hi"],
                            "enabled": True,
                        }
                    }
                }
            )
        )

        # Patch _persist and _load to prevent writing test servers to the real
        # mcp_registry.json and loading stale entries from it.
        with (
            patch("code_puppy.config.MCP_SERVERS_FILE", str(mcp_json)),
            patch("code_puppy.mcp_.manager.MCPManager.sync_from_local_config"),
            patch("code_puppy.mcp_.registry.ServerRegistry._persist"),
            patch("code_puppy.mcp_.registry.ServerRegistry._load"),
        ):
            from code_puppy.mcp_.manager import MCPManager

            manager = MCPManager()

        # my-server was synced through the registry (global config path)
        server = manager.get_server_by_name("my-server")
        assert server is not None

        # Find the managed server — it must be enabled (flag) so that
        # get_servers_for_agent() returns it to pydantic-ai.
        managed = next(
            (
                s
                for s in manager._managed_servers.values()
                if s.config.name == "my-server"
            ),
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

        q = [
            {
                "question": "Which theme?",
                "header": "Theme",
                "options": [{"label": "A"}, {"label": "B"}],
            }
        ]
        result = _coerce_questions_json_string(json.dumps(q))
        assert result == q
        assert len(result) == 1
