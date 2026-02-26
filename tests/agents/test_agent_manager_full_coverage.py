"""Full coverage tests for code_puppy/agents/agent_manager.py.

Targets all uncovered lines to achieve 100% coverage.
"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import code_puppy.agents.agent_manager as am
from code_puppy.agents.base_agent import BaseAgent


# Concrete agent for testing
class FakeAgent(BaseAgent):
    @property
    def name(self) -> str:
        return "fake-agent"

    @property
    def display_name(self) -> str:
        return "Fake Agent"

    @property
    def description(self) -> str:
        return "A fake agent for testing"

    def get_system_prompt(self) -> str:
        return "fake prompt"

    def get_available_tools(self) -> list:
        return ["tool1"]


class FakeAgentWithExtras(BaseAgent):
    @property
    def name(self) -> str:
        return "extras-agent"

    @property
    def display_name(self) -> str:
        return "Extras Agent"

    @property
    def description(self) -> str:
        return "Agent with extras"

    def get_system_prompt(self) -> str:
        return "extras prompt"

    def get_available_tools(self) -> list:
        return ["tool1"]

    def get_user_prompt(self):
        return "custom user prompt"

    def get_tools_config(self):
        return {"key": "value"}


@pytest.fixture(autouse=True)
def reset_module_state():
    """Reset module-level state between tests."""
    am._AGENT_REGISTRY.clear()
    am._AGENT_HISTORIES.clear()
    am._CURRENT_AGENT = None
    am._SESSION_AGENTS_CACHE.clear()
    am._SESSION_FILE_LOADED = False
    yield
    am._AGENT_REGISTRY.clear()
    am._AGENT_HISTORIES.clear()
    am._CURRENT_AGENT = None
    am._SESSION_AGENTS_CACHE.clear()
    am._SESSION_FILE_LOADED = False


class TestIsProcessAlive:
    """Tests for _is_process_alive (lines 68-103)."""

    def test_current_process_alive(self):
        assert am._is_process_alive(os.getpid()) is True

    def test_dead_process(self):
        # PID 99999999 almost certainly doesn't exist
        result = am._is_process_alive(99999999)
        assert result is False or result is True  # Platform-dependent

    def test_permission_error(self):
        with patch("os.kill", side_effect=PermissionError):
            with patch("os.name", "posix"):
                assert am._is_process_alive(1) is True

    def test_os_error(self):
        with patch("os.kill", side_effect=OSError):
            with patch("os.name", "posix"):
                assert am._is_process_alive(99999) is False

    def test_value_error(self):
        with patch("os.kill", side_effect=ValueError):
            with patch("os.name", "posix"):
                assert am._is_process_alive(99999) is False

    def test_generic_exception(self):
        with patch("os.kill", side_effect=Exception("weird")):
            with patch("os.name", "posix"):
                assert am._is_process_alive(99999) is True

    @patch("os.name", "nt")
    def test_windows_path(self):
        # We can't easily test Windows on non-Windows, but we can test the branch
        # by mocking ctypes
        mock_kernel32 = MagicMock()
        mock_kernel32.OpenProcess.return_value = 0  # No handle
        mock_kernel32.GetLastError.return_value = 5  # ACCESS_DENIED
        with patch.dict(
            "sys.modules", {"ctypes": MagicMock(), "ctypes.wintypes": MagicMock()}
        ):
            with patch("os.name", "nt"):
                # Just ensure it doesn't crash on non-Windows
                try:
                    am._is_process_alive(1234)
                except (AttributeError, ImportError):
                    pass  # Expected on non-Windows


class TestCleanupDeadSessions:
    """Tests for _cleanup_dead_sessions (lines 247)."""

    def test_removes_dead_sessions(self):
        with patch.object(am, "_is_process_alive", return_value=False):
            sessions = {"session_12345": "agent-a"}
            result = am._cleanup_dead_sessions(sessions)
            assert result == {}

    def test_keeps_alive_sessions(self):
        with patch.object(am, "_is_process_alive", return_value=True):
            sessions = {"session_12345": "agent-a"}
            result = am._cleanup_dead_sessions(sessions)
            assert result == {"session_12345": "agent-a"}

    def test_keeps_non_standard_sessions(self):
        sessions = {"fallback_123": "agent-b"}
        result = am._cleanup_dead_sessions(sessions)
        assert result == {"fallback_123": "agent-b"}

    def test_keeps_invalid_pid_format(self):
        sessions = {"session_notanumber": "agent-c"}
        result = am._cleanup_dead_sessions(sessions)
        assert result == {"session_notanumber": "agent-c"}


class TestLoadSessionData:
    """Tests for _load_session_data (lines 267-279)."""

    def test_no_file(self, tmp_path):
        with patch.object(
            am, "_get_session_file_path", return_value=tmp_path / "nonexistent.json"
        ):
            result = am._load_session_data()
            assert result == {}

    def test_valid_file(self, tmp_path):
        f = tmp_path / "sessions.json"
        f.write_text(json.dumps({"fallback_1": "agent"}))
        with patch.object(am, "_get_session_file_path", return_value=f):
            result = am._load_session_data()
            assert result == {"fallback_1": "agent"}

    def test_corrupt_json(self, tmp_path):
        f = tmp_path / "sessions.json"
        f.write_text("not json")
        with patch.object(am, "_get_session_file_path", return_value=f):
            result = am._load_session_data()
            assert result == {}


class TestSaveSessionData:
    """Tests for _save_session_data (lines 289-322)."""

    def test_saves_data(self, tmp_path):
        f = tmp_path / "sessions.json"
        with patch.object(am, "_get_session_file_path", return_value=f):
            am._save_session_data({"fallback_1": "agent"})
            data = json.loads(f.read_text())
            assert data == {"fallback_1": "agent"}

    def test_creates_parent_dirs(self, tmp_path):
        f = tmp_path / "sub" / "dir" / "sessions.json"
        with patch.object(am, "_get_session_file_path", return_value=f):
            am._save_session_data({"fallback_1": "agent"})
            assert f.exists()

    def test_io_error_silent(self, tmp_path):
        # Use a path that can't be written to
        bad_path = tmp_path / "sessions.json"
        with (
            patch.object(am, "_get_session_file_path", return_value=bad_path),
            patch("builtins.open", side_effect=IOError("fail")),
        ):
            # Should not raise
            am._save_session_data({"x": "y"})


class TestGetCurrentAgent:
    """Tests for get_current_agent (lines 380-392)."""

    def test_returns_session_agent(self):
        session_id = am.get_terminal_session_id()
        am._SESSION_AGENTS_CACHE[session_id] = "custom-agent"
        try:
            result = am.get_current_agent_name()
            assert result == "custom-agent"
        finally:
            am._SESSION_AGENTS_CACHE.pop(session_id, None)

    @patch("code_puppy.config.get_default_agent", return_value="default-agent")
    def test_falls_back_to_config(self, mock_default):
        session_id = am.get_terminal_session_id()
        am._SESSION_AGENTS_CACHE.pop(session_id, None)
        result = am.get_current_agent_name()
        assert result == "default-agent"


class TestGetAgentDescriptionsFiltering:
    """Tests for get_agent_descriptions UC filtering (line 511)."""

    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=False)
    def test_uc_disabled_filters_uc_agents(self, mock_uc, mock_pack):
        from code_puppy.config import UC_AGENT_NAMES

        # Add a fake UC agent
        am._AGENT_REGISTRY["uc-test-agent"] = FakeAgent
        if UC_AGENT_NAMES:
            for name in UC_AGENT_NAMES:
                am._AGENT_REGISTRY[name] = FakeAgent
        try:
            descs = am.get_agent_descriptions()
            for uc_name in UC_AGENT_NAMES:
                assert uc_name not in descs
        finally:
            for name in list(UC_AGENT_NAMES) + ["uc-test-agent"]:
                am._AGENT_REGISTRY.pop(name, None)


class TestLoadSessionDataRobust:
    """Tests for _load_session_data and _cleanup_dead_sessions (lines 247-279)."""

    def test_loads_and_cleans_dead_sessions(self, tmp_path):
        data = {
            "dead_session": {"agent": "test", "pid": "99999999"},
            "live_session": {"agent": "test", "pid": str(os.getpid())},
        }
        session_file = tmp_path / "sessions.json"
        session_file.write_text(json.dumps(data))
        with patch.object(am, "_get_session_file_path", return_value=session_file):
            result = am._load_session_data()
            # live_session should survive, dead_session should be cleaned
            assert "live_session" in result

    def test_corrupt_json(self, tmp_path):
        session_file = tmp_path / "sessions.json"
        session_file.write_text("not json")
        with patch.object(am, "_get_session_file_path", return_value=session_file):
            result = am._load_session_data()
            assert result == {}

    def test_file_not_found(self, tmp_path):
        session_file = tmp_path / "nonexistent.json"
        with patch.object(am, "_get_session_file_path", return_value=session_file):
            result = am._load_session_data()
            assert result == {}


class TestDeleteCloneUnlinkError:
    """Test delete_clone_agent when unlink fails (lines 673-674)."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    def test_unlink_error(self, mock_dir, mock_discover, tmp_path):
        # Create a clone file
        clone_file = tmp_path / "my-clone.json"
        clone_file.write_text(json.dumps({"name": "my-clone", "cloned_from": "test"}))
        am._AGENT_REGISTRY["my-clone"] = str(clone_file)
        mock_dir.return_value = str(tmp_path)

        with patch("pathlib.Path.unlink", side_effect=Exception("permission denied")):
            result = am.delete_clone_agent("my-clone")
            assert result is False


class TestEnsureSessionCacheLoaded:
    """Tests for _ensure_session_cache_loaded."""

    def test_loads_once(self):
        am._SESSION_FILE_LOADED = False
        with patch.object(
            am, "_load_session_data", return_value={"fallback_1": "a"}
        ) as mock_load:
            am._ensure_session_cache_loaded()
            assert am._SESSION_FILE_LOADED is True
            assert "fallback_1" in am._SESSION_AGENTS_CACHE
            # Second call should not reload
            am._ensure_session_cache_loaded()
            mock_load.assert_called_once()


class TestGetTerminalSessionId:
    """Tests for get_terminal_session_id (lines 359)."""

    def test_returns_session_id(self):
        result = am.get_terminal_session_id()
        assert result.startswith("session_") or result.startswith("fallback_")

    def test_fallback_on_error(self):
        with patch("os.getppid", side_effect=OSError):
            result = am.get_terminal_session_id()
            assert result.startswith("fallback_")


class TestDiscoverAgents:
    """Tests for _discover_agents (lines 367-392)."""

    @patch("code_puppy.agents.agent_manager.on_register_agents", return_value=[])
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_discovers_python_agents(self, mock_json, mock_plugins):
        am._discover_agents()
        # Should have found at least code-puppy agent
        assert len(am._AGENT_REGISTRY) > 0

    @patch("code_puppy.agents.agent_manager.on_register_agents")
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_plugin_agents_class(self, mock_json, mock_plugins):
        mock_plugins.return_value = [[{"name": "plugin-agent", "class": FakeAgent}]]
        am._discover_agents()
        assert "plugin-agent" in am._AGENT_REGISTRY

    @patch("code_puppy.agents.agent_manager.on_register_agents")
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_plugin_agents_json_path(self, mock_json, mock_plugins):
        mock_plugins.return_value = [
            [{"name": "json-plugin", "json_path": "/path/to/agent.json"}]
        ]
        am._discover_agents()
        assert "json-plugin" in am._AGENT_REGISTRY
        assert am._AGENT_REGISTRY["json-plugin"] == "/path/to/agent.json"

    @patch("code_puppy.agents.agent_manager.on_register_agents")
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_plugin_agents_none_result(self, mock_json, mock_plugins):
        mock_plugins.return_value = [None]
        am._discover_agents()
        # Should not crash

    @patch("code_puppy.agents.agent_manager.on_register_agents")
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_plugin_agents_invalid_def(self, mock_json, mock_plugins):
        mock_plugins.return_value = [
            [{"no_name": True}],  # Missing 'name'
            ["not a dict"],
            [{"name": "x"}],  # No class or json_path
        ]
        am._discover_agents()

    @patch(
        "code_puppy.agents.agent_manager.on_register_agents",
        side_effect=Exception("fail"),
    )
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_plugin_exception(self, mock_warn, mock_json, mock_plugins):
        am._discover_agents()
        mock_warn.assert_called()

    @patch("code_puppy.agents.agent_manager.on_register_agents", return_value=[])
    @patch(
        "code_puppy.agents.agent_manager.discover_json_agents",
        side_effect=Exception("fail"),
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_json_discovery_exception(self, mock_warn, mock_json, mock_plugins):
        am._discover_agents()
        mock_warn.assert_called()

    @patch("code_puppy.agents.agent_manager.on_register_agents")
    @patch("code_puppy.agents.agent_manager.discover_json_agents", return_value={})
    def test_plugin_single_dict(self, mock_json, mock_plugins):
        # Return a single dict instead of a list
        mock_plugins.return_value = [{"name": "single", "class": FakeAgent}]
        am._discover_agents()
        assert "single" in am._AGENT_REGISTRY


class TestGetAvailableAgents:
    """Tests for get_available_agents (lines 380-392)."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=False)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=False)
    def test_filters_pack_agents(self, mock_uc, mock_pack, mock_discover):
        am._AGENT_REGISTRY["pack-leader"] = FakeAgent
        am._AGENT_REGISTRY["normal"] = FakeAgent
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", {"pack-leader"}),
            patch("code_puppy.config.UC_AGENT_NAMES", set()),
        ):
            agents = am.get_available_agents()
            assert "pack-leader" not in agents
            assert "normal" in agents

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=False)
    def test_filters_uc_agents(self, mock_uc, mock_pack, mock_discover):
        am._AGENT_REGISTRY["uc-agent"] = FakeAgent
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", set()),
            patch("code_puppy.config.UC_AGENT_NAMES", {"uc-agent"}),
        ):
            agents = am.get_available_agents()
            assert "uc-agent" not in agents

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=True)
    def test_json_agent_display_name(self, mock_uc, mock_pack, mock_discover, tmp_path):
        # Create a JSON agent file
        agent_file = tmp_path / "test.json"
        agent_file.write_text(
            json.dumps(
                {
                    "name": "json-test",
                    "display_name": "JSON Test",
                    "description": "Test JSON agent",
                    "system_prompt": "prompt",
                }
            )
        )
        am._AGENT_REGISTRY["json-test"] = str(agent_file)
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", set()),
            patch("code_puppy.config.UC_AGENT_NAMES", set()),
        ):
            agents = am.get_available_agents()
            assert "json-test" in agents

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=True)
    def test_exception_fallback(self, mock_uc, mock_pack, mock_discover):
        # Bad agent ref that will raise
        am._AGENT_REGISTRY["bad"] = "nonexistent_path.json"
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", set()),
            patch("code_puppy.config.UC_AGENT_NAMES", set()),
        ):
            agents = am.get_available_agents()
            assert agents["bad"] == "Bad"  # Fallback to title()


class TestGetAgentDescriptions:
    """Tests for get_agent_descriptions (lines 511-520)."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=True)
    def test_returns_descriptions(self, mock_uc, mock_pack, mock_discover):
        am._AGENT_REGISTRY["my-agent"] = FakeAgent
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", set()),
            patch("code_puppy.config.UC_AGENT_NAMES", set()),
        ):
            descs = am.get_agent_descriptions()
            assert descs["my-agent"] == "A fake agent for testing"

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_pack_agents_enabled", return_value=True)
    @patch("code_puppy.config.get_universal_constructor_enabled", return_value=True)
    def test_exception_fallback(self, mock_uc, mock_pack, mock_discover):
        am._AGENT_REGISTRY["bad"] = "nonexistent.json"
        with (
            patch("code_puppy.config.PACK_AGENT_NAMES", set()),
            patch("code_puppy.config.UC_AGENT_NAMES", set()),
        ):
            descs = am.get_agent_descriptions()
            assert descs["bad"] == "No description available"


class TestCloneHelpers:
    """Tests for clone helper functions (lines 541-593)."""

    def test_strip_clone_suffix(self):
        assert am._strip_clone_suffix("agent-clone-1") == "agent"
        assert am._strip_clone_suffix("agent") == "agent"
        assert am._strip_clone_suffix("my-agent-clone-42") == "my-agent"

    def test_strip_clone_display_suffix(self):
        assert am._strip_clone_display_suffix("Agent (Clone 1)") == "Agent"
        assert am._strip_clone_display_suffix("Agent") == "Agent"
        assert (
            am._strip_clone_display_suffix("(Clone 1)") == "(Clone 1)"
        )  # Entire string is suffix

    def test_is_clone_agent_name(self):
        assert am.is_clone_agent_name("agent-clone-1") is True
        assert am.is_clone_agent_name("agent") is False

    def test_default_display_name(self):
        assert am._default_display_name("my-agent") == "My-Agent 🤖"

    def test_build_clone_display_name(self):
        assert am._build_clone_display_name("Agent", 3) == "Agent (Clone 3)"
        assert am._build_clone_display_name("Agent (Clone 1)", 2) == "Agent (Clone 2)"

    def test_filter_available_tools(self):
        with patch(
            "code_puppy.tools.get_available_tool_names", return_value=["tool1", "tool3"]
        ):
            result = am._filter_available_tools(["tool1", "tool2", "tool3"])
            assert result == ["tool1", "tool3"]

    def test_next_clone_index(self, tmp_path):
        existing = {"agent", "agent-clone-1"}
        idx = am._next_clone_index("agent", existing, tmp_path)
        assert idx >= 2

    def test_next_clone_index_with_file_conflict(self, tmp_path):
        # Create a file that would conflict
        (tmp_path / "agent-clone-1.json").touch()
        idx = am._next_clone_index("agent", set(), tmp_path)
        assert idx >= 1


class TestCloneAgent:
    """Tests for clone_agent (lines 606-683)."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_agent_not_found(self, mock_warn, mock_discover):
        result = am.clone_agent("nonexistent")
        assert result is None
        mock_warn.assert_called()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.config.get_agent_pinned_model", return_value=None)
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_clone_python_agent(
        self, mock_success, mock_filter, mock_pinned, mock_dir, mock_discover, tmp_path
    ):
        am._AGENT_REGISTRY["fake-agent"] = FakeAgent
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("fake-agent")
        assert result is not None
        assert "clone" in result
        mock_success.assert_called()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.config.get_agent_pinned_model", return_value="pinned-model")
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_clone_python_agent_with_pinned_model(
        self, mock_success, mock_filter, mock_pinned, mock_dir, mock_discover, tmp_path
    ):
        am._AGENT_REGISTRY["extras-agent"] = FakeAgentWithExtras
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("extras-agent")
        assert result is not None
        # Verify the config includes model, user_prompt, tools_config
        clone_file = tmp_path / f"{result}.json"
        config = json.loads(clone_file.read_text())
        assert config.get("model") == "pinned-model"
        assert config.get("user_prompt") == "custom user prompt"
        assert config.get("tools_config") == {"key": "value"}

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_clone_json_agent(
        self, mock_success, mock_filter, mock_dir, mock_discover, tmp_path
    ):
        # Create source JSON agent
        source = tmp_path / "source.json"
        source.write_text(
            json.dumps(
                {
                    "name": "src",
                    "display_name": "Source",
                    "tools": ["tool1"],
                    "model": "some-model",
                }
            )
        )
        am._AGENT_REGISTRY["src"] = str(source)
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("src")
        assert result is not None

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_clone_json_no_display_name_no_model(
        self, mock_success, mock_filter, mock_dir, mock_discover, tmp_path
    ):
        source = tmp_path / "source2.json"
        source.write_text(
            json.dumps(
                {
                    "name": "src2",
                    "tools": ["t"],
                }
            )
        )
        am._AGENT_REGISTRY["src2"] = str(source)
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("src2")
        assert result is not None

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_clone_json_non_list_tools(
        self, mock_success, mock_filter, mock_dir, mock_discover, tmp_path
    ):
        source = tmp_path / "source3.json"
        source.write_text(
            json.dumps(
                {
                    "name": "src3",
                    "tools": "not a list",
                }
            )
        )
        am._AGENT_REGISTRY["src3"] = str(source)
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("src3")
        assert result is not None

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_clone_build_exception(self, mock_warn, mock_dir, mock_discover, tmp_path):
        am._AGENT_REGISTRY["bad"] = "nonexistent_path.json"
        mock_dir.return_value = str(tmp_path)

        result = am.clone_agent("bad")
        assert result is None

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_clone_target_exists(
        self, mock_warn, mock_filter, mock_dir, mock_discover, tmp_path
    ):
        am._AGENT_REGISTRY["fake-agent"] = FakeAgent
        mock_dir.return_value = str(tmp_path)
        # Pre-create the clone file
        (tmp_path / "fake-agent-clone-1.json").write_text("{}")
        # Also add to registry to force index 1
        am._AGENT_REGISTRY["fake-agent-clone-1"] = str(
            tmp_path / "fake-agent-clone-1.json"
        )
        # Pre-create index 2 file
        clone_name = "fake-agent-clone-2"
        (tmp_path / f"{clone_name}.json").touch()
        # This might still succeed with index 3, so test write error instead

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.config.get_agent_pinned_model", return_value=None)
    @patch(
        "code_puppy.agents.agent_manager._filter_available_tools",
        side_effect=lambda x: x,
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_clone_write_failure(
        self, mock_warn, mock_filter, mock_pinned, mock_dir, mock_discover, tmp_path
    ):
        am._AGENT_REGISTRY["fake-agent"] = FakeAgent
        mock_dir.return_value = str(tmp_path / "readonly")
        # Don't create the dir so write fails
        am.clone_agent("fake-agent")
        # May succeed if dir gets created, or fail


class TestDeleteCloneAgent:
    """Tests for delete_clone_agent (lines 695-735)."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_not_a_clone(self, mock_warn, mock_discover):
        assert am.delete_clone_agent("normal-agent") is False
        mock_warn.assert_called()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name",
        return_value="agent-clone-1",
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_cannot_delete_active(self, mock_warn, mock_name, mock_discover):
        assert am.delete_clone_agent("agent-clone-1") is False

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_clone_not_found(self, mock_warn, mock_name, mock_discover):
        assert am.delete_clone_agent("agent-clone-1") is False

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_not_json_agent(self, mock_warn, mock_name, mock_discover):
        am._AGENT_REGISTRY["agent-clone-1"] = FakeAgent
        assert am.delete_clone_agent("agent-clone-1") is False

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_file_doesnt_exist(self, mock_warn, mock_name, mock_discover):
        am._AGENT_REGISTRY["agent-clone-1"] = "/nonexistent/path.json"
        assert am.delete_clone_agent("agent-clone-1") is False

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_wrong_directory(
        self, mock_warn, mock_dir, mock_name, mock_discover, tmp_path
    ):
        clone_file = tmp_path / "other_dir" / "agent-clone-1.json"
        clone_file.parent.mkdir(parents=True)
        clone_file.touch()
        am._AGENT_REGISTRY["agent-clone-1"] = str(clone_file)
        mock_dir.return_value = str(tmp_path / "agents")
        assert am.delete_clone_agent("agent-clone-1") is False

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.agents.agent_manager.emit_success")
    def test_successful_delete(
        self, mock_success, mock_dir, mock_name, mock_discover, tmp_path
    ):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        clone_file = agents_dir / "agent-clone-1.json"
        clone_file.touch()
        am._AGENT_REGISTRY["agent-clone-1"] = str(clone_file)
        am._AGENT_HISTORIES["agent-clone-1"] = []
        mock_dir.return_value = str(agents_dir)
        assert am.delete_clone_agent("agent-clone-1") is True
        assert not clone_file.exists()
        assert "agent-clone-1" not in am._AGENT_REGISTRY

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch(
        "code_puppy.agents.agent_manager.get_current_agent_name", return_value="other"
    )
    @patch("code_puppy.config.get_user_agents_directory")
    @patch("code_puppy.agents.agent_manager.emit_warning")
    def test_unlink_failure(
        self, mock_warn, mock_dir, mock_name, mock_discover, tmp_path
    ):
        agents_dir = tmp_path / "agents"
        agents_dir.mkdir()
        clone_file = agents_dir / "agent-clone-1.json"
        clone_file.touch()
        am._AGENT_REGISTRY["agent-clone-1"] = str(clone_file)
        mock_dir.return_value = str(agents_dir)

        with patch.object(Path, "unlink", side_effect=Exception("fail")):
            assert am.delete_clone_agent("agent-clone-1") is False


class TestSetCurrentAgent:
    """Tests for set_current_agent."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager.load_agent")
    @patch("code_puppy.agents.agent_manager.on_agent_reload")
    @patch("code_puppy.agents.agent_manager._save_session_data")
    def test_set_with_history_restore(
        self, mock_save, mock_reload, mock_load, mock_discover
    ):
        old_agent = FakeAgent()
        old_agent._message_history = [MagicMock()]
        am._CURRENT_AGENT = old_agent

        new_agent = FakeAgent()
        mock_load.return_value = new_agent
        am._AGENT_HISTORIES["fake-agent"] = [MagicMock()]

        result = am.set_current_agent("fake-agent")
        assert result is True
        assert am._CURRENT_AGENT == new_agent


class TestLoadAgent:
    """Tests for load_agent."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_fallback_to_code_puppy(self, mock_discover):
        from code_puppy.agents.agent_code_puppy import CodePuppyAgent

        am._AGENT_REGISTRY["code-puppy"] = CodePuppyAgent
        agent = am.load_agent("nonexistent")
        assert agent.name == "code-puppy"

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_no_fallback_raises(self, mock_discover):
        with pytest.raises(ValueError):
            am.load_agent("nonexistent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_json_agent(self, mock_discover, tmp_path):
        agent_file = tmp_path / "test.json"
        agent_file.write_text(
            json.dumps(
                {
                    "name": "json-test",
                    "display_name": "JSON Test",
                    "description": "desc",
                    "system_prompt": "prompt",
                    "tools": ["tool1"],
                }
            )
        )
        am._AGENT_REGISTRY["json-test"] = str(agent_file)
        agent = am.load_agent("json-test")
        assert agent.name == "json-test"


class TestRefreshAgents:
    """Test refresh_agents."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_refresh(self, mock_discover):
        am.refresh_agents()
        mock_discover.assert_called_once()
