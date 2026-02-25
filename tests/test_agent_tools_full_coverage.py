"""Full coverage tests for tools/agent_tools.py."""

import json
from unittest.mock import patch

import pytest

from code_puppy.tools.agent_tools import (
    AgentInfo,
    AgentInvokeOutput,
    ListAgentsOutput,
    _generate_dbos_workflow_id,
    _generate_session_hash_suffix,
    _get_subagent_sessions_dir,
    _load_session_history,
    _save_session_history,
    _validate_session_id,
)


class TestValidateSessionId:
    def test_valid(self):
        _validate_session_id("my-session")
        _validate_session_id("a")
        _validate_session_id("agent-1-session")

    def test_empty(self):
        with pytest.raises(ValueError, match="empty"):
            _validate_session_id("")

    def test_too_long(self):
        with pytest.raises(ValueError, match="128"):
            _validate_session_id("a" * 129)

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="kebab-case"):
            _validate_session_id("MySession")
        with pytest.raises(ValueError, match="kebab-case"):
            _validate_session_id("my_session")
        with pytest.raises(ValueError, match="kebab-case"):
            _validate_session_id("my session")


class TestGenerateDbosWorkflowId:
    def test_unique(self):
        id1 = _generate_dbos_workflow_id("base")
        id2 = _generate_dbos_workflow_id("base")
        assert id1 != id2
        assert id1.startswith("base-wf-")


class TestGenerateSessionHashSuffix:
    def test_returns_6_char_hex(self):
        suffix = _generate_session_hash_suffix()
        assert len(suffix) == 6
        int(suffix, 16)  # Should be valid hex


class TestSessionHistory:
    def test_save_and_load(self, tmp_path):
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            msgs = ["msg1", "msg2"]
            _save_session_history("test-session", msgs, "agent1", "initial")
            loaded = _load_session_history("test-session")
            assert loaded == msgs

    def test_save_update_metadata(self, tmp_path):
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            _save_session_history("test-session", ["msg1"], "agent1", "initial")
            _save_session_history("test-session", ["msg1", "msg2"], "agent1")
            txt = tmp_path / "test-session.txt"
            data = json.loads(txt.read_text())
            assert data["message_count"] == 2

    def test_load_nonexistent(self, tmp_path):
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            assert _load_session_history("nope") == []

    def test_load_corrupted(self, tmp_path):
        pkl = tmp_path / "bad.pkl"
        pkl.write_bytes(b"not a pickle")
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            assert _load_session_history("bad") == []

    def test_save_invalid_session_id(self, tmp_path):
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            with pytest.raises(ValueError):
                _save_session_history("BAD SESSION", [], "agent")

    def test_load_invalid_session_id(self, tmp_path):
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            with pytest.raises(ValueError):
                _load_session_history("BAD SESSION")

    def test_save_metadata_update_error(self, tmp_path):
        """Metadata update failure is silently handled."""
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            _save_session_history("test-session", ["msg1"], "agent1", "initial")
            # Corrupt the txt file
            txt = tmp_path / "test-session.txt"
            txt.write_text("not json")
            # Should not raise
            _save_session_history("test-session", ["msg1", "msg2"], "agent1")


class TestGetSubagentSessionsDir:
    def test_creates_dir(self, tmp_path):
        with patch("code_puppy.tools.agent_tools.DATA_DIR", str(tmp_path)):
            d = _get_subagent_sessions_dir()
            assert d.exists()


class TestModels:
    def test_agent_info(self):
        ai = AgentInfo(name="test", display_name="Test", description="desc")
        assert ai.name == "test"

    def test_list_agents_output(self):
        out = ListAgentsOutput(agents=[])
        assert out.error is None

    def test_agent_invoke_output(self):
        out = AgentInvokeOutput(response="ok", agent_name="test")
        assert out.response == "ok"
