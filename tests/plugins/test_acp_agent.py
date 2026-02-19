"""Tests for the CodePuppyAgent — ACP SDK-based agent implementation.

Covers:
- Agent lifecycle (on_connect, initialize, new_session)
- Prompt dispatch and text extraction
- Session management and multi-turn history
- Cancellation
- Extension methods (x/list-agents, x/set-agent, x/agent-info)
- Error handling
- Tool event extraction and streaming

All Code Puppy internals are mocked — no LLM calls are made.
"""

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_puppy.plugins.acp_gateway.agent import (
    CodePuppyAgent,
    _SessionState,
    _extract_text,
    _extract_plan_steps,
    _safe_serialize_args,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


def _make_mock_client() -> MagicMock:
    """Create a mock ACP Client with async methods."""
    client = MagicMock()
    client.session_update = AsyncMock()
    client.request_permission = AsyncMock()
    client.read_text_file = AsyncMock()
    client.write_text_file = AsyncMock()
    client.create_terminal = AsyncMock()
    return client


def _make_text_block(text: str) -> dict:
    """Create a minimal ACP TextContentBlock dict."""
    return {"type": "text", "text": text}


def _make_image_block(url: str = "data:image/png;base64,abc") -> dict:
    """Create a minimal ACP ImageContentBlock dict."""
    return {"type": "image", "image": url}


def _make_mock_result(output: str = "Hello from Code Puppy!", messages=None):
    """Create a mock pydantic-ai RunResult."""
    result = MagicMock()
    result.output = output
    result.data = output  # fallback for older pydantic-ai
    result.all_messages = MagicMock(return_value=messages or [])
    return result


@pytest.fixture
def agent():
    """Fresh CodePuppyAgent instance."""
    return CodePuppyAgent(default_agent="code-puppy")


@pytest.fixture
def connected_agent():
    """CodePuppyAgent with a mock client connected."""
    a = CodePuppyAgent(default_agent="code-puppy")
    client = _make_mock_client()
    a.on_connect(client)
    return a, client


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------


class TestExtractText:
    """Test the _extract_text helper."""

    def test_single_text_block(self):
        blocks = [_make_text_block("hello world")]
        assert _extract_text(blocks) == "hello world"

    def test_multiple_text_blocks(self):
        blocks = [_make_text_block("hello"), _make_text_block("world")]
        assert _extract_text(blocks) == "hello\nworld"

    def test_empty_blocks(self):
        assert _extract_text([]) == ""

    def test_non_text_blocks_ignored(self):
        blocks = [_make_image_block(), _make_text_block("actual text")]
        assert _extract_text(blocks) == "actual text"

    def test_dict_blocks(self):
        blocks = [{"text": "from dict"}]
        assert _extract_text(blocks) == "from dict"

    def test_mixed_empty_and_text(self):
        blocks = [{"text": ""}, _make_text_block("real")]
        assert _extract_text(blocks) == "real"

    def test_strips_whitespace(self):
        blocks = [_make_text_block("  hello  ")]
        assert _extract_text(blocks) == "hello"


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


class TestSafeSerializeArgs:
    """Test _safe_serialize_args."""

    def test_none_returns_empty(self):
        assert _safe_serialize_args(None) == {}

    def test_dict_passthrough(self):
        args = {"key": "value", "num": 42}
        result = _safe_serialize_args(args)
        assert result == {"key": "value", "num": 42}

    def test_long_string_truncated(self):
        args = {"big": "x" * 500}
        result = _safe_serialize_args(args)
        assert len(result["big"]) == 200

    def test_non_dict_wrapped(self):
        result = _safe_serialize_args("raw string")
        assert "raw" in result


class TestExtractPlanSteps:
    """Test _extract_plan_steps."""

    def test_numbered_list(self):
        content = "1. First step\n2. Second step\n3. Third step"
        steps = _extract_plan_steps(content)
        assert len(steps) == 3
        assert steps[0]["step"] == 1
        assert steps[0]["description"] == "First step"

    def test_bullet_list(self):
        content = "- Do this\n- Do that\n- Finish up"
        steps = _extract_plan_steps(content)
        assert len(steps) == 3

    def test_single_item_not_a_plan(self):
        content = "1. Only one step"
        steps = _extract_plan_steps(content)
        assert len(steps) == 0

    def test_empty_content(self):
        assert _extract_plan_steps("") == []

    def test_no_pattern_match(self):
        assert _extract_plan_steps("just some random text") == []


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


class TestAgentLifecycle:
    """Test on_connect and initialize."""

    def test_on_connect_stores_client(self, agent):
        client = _make_mock_client()
        agent.on_connect(client)
        assert agent._conn is client

    @pytest.mark.asyncio
    async def test_initialize_returns_protocol_version(self, agent):
        resp = await agent.initialize(protocol_version=1)
        assert resp.protocol_version == 1

    @pytest.mark.asyncio
    async def test_initialize_with_client_info(self, agent):
        resp = await agent.initialize(
            protocol_version=2,
            client_info=MagicMock(name="TestClient"),
        )
        assert resp.protocol_version == 2


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


class TestSessionManagement:
    """Test new_session and session state."""

    @pytest.mark.asyncio
    async def test_new_session_returns_id(self, agent):
        resp = await agent.new_session(cwd="/tmp")
        assert resp.session_id is not None
        assert len(resp.session_id) > 0

    @pytest.mark.asyncio
    async def test_new_session_creates_state(self, agent):
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id
        assert sid in agent._sessions
        assert agent._sessions[sid].agent_name == "code-puppy"

    @pytest.mark.asyncio
    async def test_multiple_sessions_unique(self, agent):
        r1 = await agent.new_session(cwd="/a")
        r2 = await agent.new_session(cwd="/b")
        assert r1.session_id != r2.session_id

    def test_session_state_initial(self):
        state = _SessionState("sid-123", agent_name="test-agent")
        assert state.session_id == "sid-123"
        assert state.agent_name == "test-agent"
        assert state.message_history == []


# ---------------------------------------------------------------------------
# Prompt handling
# ---------------------------------------------------------------------------


class TestPrompt:
    """Test prompt dispatch."""

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_end_turn(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        result = await agent.prompt(prompt=[], session_id=sid)
        assert result.stop_reason == "end_turn"
        # Should have sent "No prompt text found"
        client.session_update.assert_called()

    @pytest.mark.asyncio
    async def test_prompt_auto_creates_session(self):
        agent, client = _make_agent_with_client()
        # Don't call new_session — prompt should auto-create
        mock_result = _make_mock_result("Agent response")

        with _mock_code_puppy_agent(mock_result):
            result = await agent.prompt(
                prompt=[_make_text_block("hello")],
                session_id="auto-session",
            )

        assert result.stop_reason == "end_turn"
        assert "auto-session" in agent._sessions

    @pytest.mark.asyncio
    async def test_prompt_runs_agent_and_sends_result(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_result = _make_mock_result("The answer is 42")

        with _mock_code_puppy_agent(mock_result):
            result = await agent.prompt(
                prompt=[_make_text_block("What is the answer?")],
                session_id=sid,
            )

        assert result.stop_reason == "end_turn"
        # Should have called session_update at least once
        assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_prompt_error_returns_error_stop_reason(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with _mock_code_puppy_agent_error(RuntimeError("boom")):
            result = await agent.prompt(
                prompt=[_make_text_block("cause error")],
                session_id=sid,
            )

        assert result.stop_reason == "end_turn"
        # Should have sent error message
        client.session_update.assert_called()

    @pytest.mark.asyncio
    async def test_prompt_preserves_history(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_messages = [MagicMock(), MagicMock()]
        mock_result = _make_mock_result("first response", messages=mock_messages)

        with _mock_code_puppy_agent(mock_result):
            await agent.prompt(
                prompt=[_make_text_block("first")],
                session_id=sid,
            )

        # History should be updated
        assert agent._sessions[sid].message_history == mock_messages


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    """Test cancel method."""

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_session(self, agent):
        # Should not raise
        await agent.cancel(session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_cancel_with_running_task(self, agent):
        # Simulate a running task
        mock_task = MagicMock()
        mock_task.done.return_value = False
        agent._running_tasks["session-1"] = mock_task

        await agent.cancel(session_id="session-1")
        mock_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_already_done_task(self, agent):
        mock_task = MagicMock()
        mock_task.done.return_value = True
        agent._running_tasks["session-2"] = mock_task

        await agent.cancel(session_id="session-2")
        mock_task.cancel.assert_not_called()


# ---------------------------------------------------------------------------
# Extension methods
# ---------------------------------------------------------------------------


class TestExtensionMethods:
    """Test ext_method dispatch."""

    @pytest.mark.asyncio
    async def test_list_agents(self):
        agent, _ = _make_agent_with_client()

        mock_agents = [
            MagicMock(name="code-puppy", display_name="Code Puppy", description="Main agent"),
        ]
        # Fix .name attribute (MagicMock overrides name)
        mock_agents[0].name = "code-puppy"
        mock_agents[0].display_name = "Code Puppy"
        mock_agents[0].description = "Main agent"

        with patch(
            "code_puppy.plugins.acp_gateway.agent_adapter.discover_agents",
            new_callable=AsyncMock,
            return_value=mock_agents,
        ):
            result = await agent.ext_method("x/list-agents", {})

        assert "agents" in result
        assert len(result["agents"]) == 1
        assert result["agents"][0]["name"] == "code-puppy"

    @pytest.mark.asyncio
    async def test_set_agent(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        result = await agent.ext_method("x/set-agent", {
            "session_id": sid,
            "agent_name": "qa-kitten",
        })

        assert result["status"] == "ok"
        assert agent._sessions[sid].agent_name == "qa-kitten"

    @pytest.mark.asyncio
    async def test_set_agent_missing_params(self):
        agent, _ = _make_agent_with_client()
        result = await agent.ext_method("x/set-agent", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_set_agent_unknown_session(self):
        agent, _ = _make_agent_with_client()
        result = await agent.ext_method("x/set-agent", {
            "session_id": "nonexistent",
            "agent_name": "qa-kitten",
        })
        assert "error" in result

    @pytest.mark.asyncio
    async def test_agent_info(self):
        agent, _ = _make_agent_with_client()

        with patch(
            "code_puppy.plugins.acp_gateway.agent_adapter.build_agent_metadata",
            return_value={
                "name": "code-puppy",
                "display_name": "Code Puppy",
                "description": "Main agent",
                "version": "0.1.0",
            },
        ):
            result = await agent.ext_method("x/agent-info", {
                "agent_name": "code-puppy",
            })

        assert result["name"] == "code-puppy"

    @pytest.mark.asyncio
    async def test_agent_info_not_found(self):
        agent, _ = _make_agent_with_client()

        with patch(
            "code_puppy.plugins.acp_gateway.agent_adapter.build_agent_metadata",
            return_value=None,
        ):
            result = await agent.ext_method("x/agent-info", {
                "agent_name": "nonexistent",
            })

        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_extension(self):
        agent, _ = _make_agent_with_client()
        result = await agent.ext_method("x/unknown", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_ext_notification_does_not_raise(self):
        agent, _ = _make_agent_with_client()
        # Should not raise
        await agent.ext_notification("x/some-event", {"key": "value"})


# ---------------------------------------------------------------------------
# Streaming helpers
# ---------------------------------------------------------------------------


class TestStreamingHelpers:
    """Test _send_text, _send_thought, and _stream_tool_events."""

    @pytest.mark.asyncio
    async def test_send_text_calls_session_update(self):
        agent, client = _make_agent_with_client()
        await agent._send_text("sid-1", "Hello")
        client.session_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_text_without_connection(self):
        agent = CodePuppyAgent()
        # Should not raise
        await agent._send_text("sid", "text")

    @pytest.mark.asyncio
    async def test_send_thought_calls_session_update(self):
        agent, client = _make_agent_with_client()
        await agent._send_thought("sid-1", "Thinking...")
        client.session_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_empty_events(self):
        agent, client = _make_agent_with_client()
        await agent._stream_tool_events("sid", [])
        client.session_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_stream_thinking_event(self):
        agent, client = _make_agent_with_client()
        events = [{"type": "thinking", "content": "I am thinking..."}]
        await agent._stream_tool_events("sid", events)
        assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_stream_tool_call_event(self):
        agent, client = _make_agent_with_client()
        events = [{"type": "tool_call", "tool_name": "read_file", "args": {"path": "foo.py"}}]
        await agent._stream_tool_events("sid", events)
        assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_stream_plan_event(self):
        agent, client = _make_agent_with_client()
        events = [{"type": "plan", "steps": [
            {"step": 1, "description": "First"},
            {"step": 2, "description": "Second"},
        ]}]
        await agent._stream_tool_events("sid", events)
        assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_stream_without_connection(self):
        agent = CodePuppyAgent()
        # Should not raise even without connection
        await agent._stream_tool_events("sid", [
            {"type": "thinking", "content": "test"},
        ])


# ---------------------------------------------------------------------------
# Result extraction
# ---------------------------------------------------------------------------


class TestResultExtraction:
    """Test _extract_result_text and _extract_tool_events."""

    def test_extract_text_from_output(self):
        result = MagicMock()
        result.output = "response text"
        assert CodePuppyAgent._extract_result_text(result) == "response text"

    def test_extract_text_from_data_fallback(self):
        result = MagicMock(spec=[])
        result.data = "fallback text"
        assert CodePuppyAgent._extract_result_text(result) == "fallback text"

    def test_extract_text_none(self):
        assert CodePuppyAgent._extract_result_text(None) == ""

    def test_extract_text_str_fallback(self):
        result = MagicMock(spec=[])
        # No .output, no .data — should str()
        text = CodePuppyAgent._extract_result_text(result)
        assert isinstance(text, str)

    def test_extract_tool_events_no_messages(self):
        result = MagicMock()
        result.all_messages.return_value = []
        events = CodePuppyAgent._extract_tool_events(result)
        assert events == []

    def test_extract_tool_events_no_method(self):
        result = MagicMock(spec=[])  # no all_messages
        events = CodePuppyAgent._extract_tool_events(result)
        assert events == []


# ---------------------------------------------------------------------------
# Private helpers for test setup
# ---------------------------------------------------------------------------


def _make_agent_with_client():
    """Create agent + connected mock client pair."""
    agent = CodePuppyAgent(default_agent="code-puppy")
    client = _make_mock_client()
    agent.on_connect(client)
    return agent, client


class _MockPydanticAgent:
    """Fake pydantic-ai Agent that returns a canned result."""

    def __init__(self, result):
        self._result = result

    async def run(self, prompt, message_history=None):
        return self._result


class _MockBaseAgent:
    """Fake Code Puppy BaseAgent for testing."""

    def __init__(self, pydantic_agent):
        self._code_generation_agent = pydantic_agent
        self._message_history = []

    @property
    def code_generation_agent(self):
        return self._code_generation_agent

    def reload_code_generation_agent(self):
        return self._code_generation_agent

    def set_message_history(self, history):
        self._message_history = list(history)

    def get_message_history(self):
        return self._message_history

    def get_full_system_prompt(self):
        return "You are Code Puppy."

    def load_puppy_rules(self):
        return None

    def get_model_name(self):
        return "test-model"


def _mock_code_puppy_agent(mock_result):
    """Context manager that patches ``_run_agent`` on ``CodePuppyAgent``.

    Since the real ``_run_agent`` lazy-imports ``code_puppy.agents`` and
    ``code_puppy.model_utils`` (which may not be resolvable in every test
    environment), we sidestep the problem entirely by replacing the method
    with a coroutine that returns the canned result and updates session
    history, matching the real method's contract.
    """
    tool_events = CodePuppyAgent._extract_tool_events(mock_result)
    result_text = CodePuppyAgent._extract_result_text(mock_result)
    messages = list(mock_result.all_messages()) if hasattr(mock_result, "all_messages") else []

    async def _fake_run_agent(self, session, prompt_text):
        session.message_history = messages
        return result_text, tool_events

    return patch.object(CodePuppyAgent, "_run_agent", _fake_run_agent)


def _mock_code_puppy_agent_error(error):
    """Context manager that patches ``_run_agent`` to raise *error*."""

    async def _failing_run_agent(self, session, prompt_text):
        raise error

    return patch.object(CodePuppyAgent, "_run_agent", _failing_run_agent)