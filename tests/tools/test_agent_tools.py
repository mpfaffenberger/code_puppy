"""Tests for code_puppy/tools/agent_tools.py - 100% coverage."""

import json
import pickle
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateDbosWorkflowId:
    def test_unique_ids(self):
        from code_puppy.tools.agent_tools import _generate_dbos_workflow_id

        id1 = _generate_dbos_workflow_id("base")
        id2 = _generate_dbos_workflow_id("base")
        assert id1 != id2
        assert id1.startswith("base-wf-")


class TestGenerateSessionHashSuffix:
    def test_returns_hex_string(self):
        from code_puppy.tools.agent_tools import _generate_session_hash_suffix

        result = _generate_session_hash_suffix()
        assert len(result) == 6
        int(result, 16)  # Should be valid hex


class TestValidateSessionId:
    def test_valid_ids(self):
        from code_puppy.tools.agent_tools import _validate_session_id

        _validate_session_id("my-session")
        _validate_session_id("agent-session-1")
        _validate_session_id("a")

    def test_empty(self):
        from code_puppy.tools.agent_tools import _validate_session_id

        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_session_id("")

    def test_too_long(self):
        from code_puppy.tools.agent_tools import _validate_session_id

        with pytest.raises(ValueError, match="128 characters"):
            _validate_session_id("a" * 129)

    def test_invalid_format(self):
        from code_puppy.tools.agent_tools import _validate_session_id

        with pytest.raises(ValueError, match="kebab-case"):
            _validate_session_id("MySession")
        with pytest.raises(ValueError, match="kebab-case"):
            _validate_session_id("my_session")


class TestSubagentSessionsDir:
    @patch("code_puppy.tools.agent_tools.DATA_DIR", "/tmp/test_data")
    def test_creates_dir(self):
        from code_puppy.tools.agent_tools import _get_subagent_sessions_dir

        with patch("pathlib.Path.mkdir"):
            result = _get_subagent_sessions_dir()
            assert str(result).endswith("subagent_sessions")


class TestSaveSessionHistory:
    def test_save_new_session(self, tmp_path):
        from code_puppy.tools.agent_tools import _save_session_history

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            _save_session_history("my-session", ["msg1"], "agent", "hello")
        pkl = tmp_path / "my-session.pkl"
        txt = tmp_path / "my-session.txt"
        assert pkl.exists()
        assert txt.exists()
        with open(txt) as f:
            meta = json.load(f)
        assert meta["session_id"] == "my-session"
        assert meta["initial_prompt"] == "hello"

    def test_save_updates_existing(self, tmp_path):
        from code_puppy.tools.agent_tools import _save_session_history

        txt = tmp_path / "my-session.txt"
        txt.write_text(json.dumps({"session_id": "my-session", "message_count": 1}))
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            _save_session_history("my-session", ["msg1", "msg2"], "agent")
        with open(txt) as f:
            meta = json.load(f)
        assert meta["message_count"] == 2

    def test_save_invalid_session_id(self):
        from code_puppy.tools.agent_tools import _save_session_history

        with pytest.raises(ValueError):
            _save_session_history("INVALID", [], "agent")

    def test_save_corrupted_txt(self, tmp_path):
        from code_puppy.tools.agent_tools import _save_session_history

        txt = tmp_path / "my-session.txt"
        txt.write_text("not json")
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            _save_session_history("my-session", ["msg"], "agent")  # shouldn't raise


class TestLoadSessionHistory:
    def test_load_nonexistent(self, tmp_path):
        from code_puppy.tools.agent_tools import _load_session_history

        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            result = _load_session_history("no-session")
        assert result == []

    def test_load_existing(self, tmp_path):
        from code_puppy.tools.agent_tools import _load_session_history

        pkl = tmp_path / "my-session.pkl"
        with open(pkl, "wb") as f:
            pickle.dump(["msg1", "msg2"], f)
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            result = _load_session_history("my-session")
        assert result == ["msg1", "msg2"]

    def test_load_corrupted(self, tmp_path):
        from code_puppy.tools.agent_tools import _load_session_history

        pkl = tmp_path / "my-session.pkl"
        pkl.write_bytes(b"not pickle")
        with patch(
            "code_puppy.tools.agent_tools._get_subagent_sessions_dir",
            return_value=tmp_path,
        ):
            result = _load_session_history("my-session")
        assert result == []

    def test_load_invalid_session_id(self):
        from code_puppy.tools.agent_tools import _load_session_history

        with pytest.raises(ValueError):
            _load_session_history("INVALID")


class TestModels:
    def test_agent_info(self):
        from code_puppy.tools.agent_tools import AgentInfo

        a = AgentInfo(name="n", display_name="d", description="desc")
        assert a.name == "n"

    def test_list_agents_output(self):
        from code_puppy.tools.agent_tools import ListAgentsOutput

        o = ListAgentsOutput(agents=[])
        assert o.error is None

    def test_agent_invoke_output(self):
        from code_puppy.tools.agent_tools import AgentInvokeOutput

        o = AgentInvokeOutput(response="r", agent_name="a")
        assert o.response == "r"


class TestRegisterListAgents:
    def test_register_and_call(self):
        from code_puppy.tools.agent_tools import register_list_agents

        agent = MagicMock()
        captured = {}

        def tool_dec(fn):
            captured["fn"] = fn
            return fn

        agent.tool = tool_dec
        register_list_agents(agent)

        ctx = MagicMock()
        with (
            patch("code_puppy.tools.agent_tools.generate_group_id", return_value="grp"),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch(
                "code_puppy.agents.get_available_agents", return_value={"a": "Agent A"}
            ),
            patch(
                "code_puppy.agents.get_agent_descriptions", return_value={"a": "desc"}
            ),
            patch("code_puppy.config.get_banner_color", return_value="blue"),
        ):
            result = captured["fn"](ctx)
        assert len(result.agents) == 1

    def test_register_error(self):
        from code_puppy.tools.agent_tools import register_list_agents

        agent = MagicMock()
        captured = {}
        agent.tool = lambda fn: (captured.update({"fn": fn}), fn)[-1]
        register_list_agents(agent)

        ctx = MagicMock()
        with (
            patch("code_puppy.tools.agent_tools.generate_group_id", return_value="grp"),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch("code_puppy.config.get_banner_color", return_value="blue"),
            patch(
                "code_puppy.agents.get_available_agents", side_effect=Exception("boom")
            ),
        ):
            result = captured["fn"](ctx)
        assert result.error is not None


class TestRegisterInvokeAgent:
    @pytest.mark.asyncio
    async def test_invalid_session_id(self):
        from code_puppy.tools.agent_tools import register_invoke_agent

        agent = MagicMock()
        captured = {}
        agent.tool = lambda fn: (captured.update({"fn": fn}), fn)[-1]
        register_invoke_agent(agent)

        ctx = MagicMock()
        with (
            patch("code_puppy.tools.agent_tools.generate_group_id", return_value="grp"),
            patch("code_puppy.tools.agent_tools.emit_error"),
        ):
            result = await captured["fn"](
                ctx, agent_name="test", prompt="hi", session_id="INVALID_ID"
            )
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_agent_not_found(self):
        import contextvars

        from code_puppy.tools.agent_tools import register_invoke_agent

        agent = MagicMock()
        captured = {}
        agent.tool = lambda fn: (captured.update({"fn": fn}), fn)[-1]
        register_invoke_agent(agent)

        # Create real context vars for the token reset
        fake_term_var = contextvars.ContextVar("fake_term")
        fake_browser_var = contextvars.ContextVar("fake_browser")
        term_token = fake_term_var.set("x")
        browser_token = fake_browser_var.set("y")

        ctx = MagicMock()
        with (
            patch("code_puppy.tools.agent_tools.generate_group_id", return_value="grp"),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch("code_puppy.tools.agent_tools.get_message_bus"),
            patch(
                "code_puppy.tools.agent_tools.get_session_context", return_value=None
            ),
            patch("code_puppy.tools.agent_tools.set_session_context"),
            patch(
                "code_puppy.tools.browser.terminal_tools.set_terminal_session",
                return_value=term_token,
            ),
            patch(
                "code_puppy.tools.browser.browser_manager.set_browser_session",
                return_value=browser_token,
            ),
            patch(
                "code_puppy.tools.browser.terminal_tools._terminal_session_var",
                fake_term_var,
            ),
            patch(
                "code_puppy.tools.browser.browser_manager._browser_session_var",
                fake_browser_var,
            ),
            patch(
                "code_puppy.agents.load_agent", side_effect=Exception("Agent not found")
            ),
        ):
            result = await captured["fn"](ctx, agent_name="nonexistent", prompt="hi")
        assert result.error is not None
