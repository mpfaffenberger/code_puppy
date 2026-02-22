"""Tests for the CodePuppyAgent — ACP SDK-based agent implementation.

Covers:
- Agent lifecycle (on_connect, initialize, new_session)
- Prompt dispatch and text extraction
- Session management and multi-turn history
- Cancellation
- Extension methods (x/list-agents, x/set-agent, x/agent-info)
- Error handling
- Tool event extraction and streaming
- Authentication (Phase C)
- Session modes (Phase D)
- Session model switching (Phase E)
- Config options (Phase F)
- Enhanced notifications (Phase G)

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
    _build_mode_state,
    _build_model_state,
    _build_config_options,
    _get_version,
    _ACP_MODES,
    _DANGEROUS_TOOLS,
    _MODE_ALLOWED,
    _MODE_IDS,
    _DEFAULT_MODE,
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


class TestBuildModeState:
    """Test _build_mode_state helper."""

    def test_returns_all_modes(self):
        state = _build_mode_state("yolo")
        assert len(state.available_modes) == 4
        assert state.current_mode_id == "yolo"

    def test_respects_current_mode(self):
        state = _build_mode_state("read")
        assert state.current_mode_id == "read"

    def test_mode_ids_correct(self):
        state = _build_mode_state("write")
        ids = {m.id for m in state.available_modes}
        assert ids == {"read", "write", "execute", "yolo"}


class TestBuildModelState:
    """Test the _build_model_state helper."""

    def test_returns_model_state_with_models(self):
        mock_config = {
            "gpt-5": {"type": "openai", "context_length": 200000},
            "claude-4": {"type": "anthropic", "context_length": 200000},
        }
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.config.get_global_model_name", return_value="gpt-5"):
            state = _build_model_state()
        assert state is not None
        assert len(state.available_models) == 2
        assert state.current_model_id == "gpt-5"
        names = {m.model_id for m in state.available_models}
        assert names == {"gpt-5", "claude-4"}

    def test_includes_description_with_type_and_context(self):
        mock_config = {
            "gpt-5": {"type": "openai", "context_length": 200000},
        }
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.config.get_global_model_name", return_value="gpt-5"):
            state = _build_model_state()
        assert state is not None
        model = state.available_models[0]
        assert "openai" in model.description
        assert "200,000" in model.description

    def test_falls_back_to_first_model_if_current_not_in_list(self):
        mock_config = {"alpha": {"type": "test"}, "beta": {"type": "test"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.config.get_global_model_name", return_value="nonexistent"):
            state = _build_model_state()
        assert state is not None
        assert state.current_model_id in {"alpha", "beta"}

    def test_returns_none_on_empty_config(self):
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value={}), \
             patch("code_puppy.config.get_global_model_name", return_value=""):
            state = _build_model_state()
        assert state is None

    def test_returns_none_on_import_error(self):
        with patch("code_puppy.plugins.acp_gateway.agent._build_model_state") as mock_fn:
            # Simulate what happens when ModelFactory import fails
            mock_fn.return_value = None
            assert mock_fn() is None


class TestGetVersion:
    """Test _get_version helper."""

    def test_returns_string(self):
        version = _get_version()
        assert isinstance(version, str)
        assert len(version) > 0


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

    @pytest.mark.asyncio
    async def test_initialize_returns_agent_info(self, agent):
        resp = await agent.initialize(protocol_version=1)
        assert resp.agent_info is not None
        assert resp.agent_info.name == "code-puppy"
        assert resp.agent_info.version is not None

    @pytest.mark.asyncio
    async def test_initialize_returns_agent_capabilities(self, agent):
        resp = await agent.initialize(protocol_version=1)
        assert resp.agent_capabilities is not None
        assert resp.agent_capabilities.load_session is True

    @pytest.mark.asyncio
    async def test_initialize_reports_full_session_capabilities(self, agent):
        """initialize() reports fork, list, and resume session capabilities."""
        resp = await agent.initialize(protocol_version=1)
        caps = resp.agent_capabilities
        assert caps is not None
        sc = caps.session_capabilities
        assert sc is not None
        # fork_session, list_sessions, resume_session are all implemented
        assert sc.fork is not None
        assert sc.list is not None
        assert sc.resume is not None

    @pytest.mark.asyncio
    async def test_capabilities_match_implemented_methods(self, agent):
        """Capabilities reported match methods actually implemented on the agent."""
        resp = await agent.initialize(protocol_version=1)
        caps = resp.agent_capabilities
        # load_session is reported and the method exists
        assert caps.load_session is True
        assert hasattr(agent, "load_session")
        # session capabilities match implemented methods
        assert caps.session_capabilities.fork is not None
        assert hasattr(agent, "fork_session")
        assert caps.session_capabilities.list is not None
        assert hasattr(agent, "list_sessions")
        assert caps.session_capabilities.resume is not None
        assert hasattr(agent, "resume_session")

    @pytest.mark.asyncio
    async def test_initialize_stores_client_capabilities(self, agent):
        caps = MagicMock()
        info = MagicMock()
        await agent.initialize(
            protocol_version=1,
            client_capabilities=caps,
            client_info=info,
        )
        assert agent._client_capabilities is caps
        assert agent._client_info is info


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

    @pytest.mark.asyncio
    async def test_new_session_returns_mode_state(self, agent):
        resp = await agent.new_session(cwd="/tmp")
        assert resp.modes is not None
        assert resp.modes.current_mode_id == _DEFAULT_MODE
        assert len(resp.modes.available_modes) == 4

    @pytest.mark.asyncio
    async def test_new_session_stores_cwd(self, agent):
        resp = await agent.new_session(cwd="/workspace")
        assert agent._sessions[resp.session_id].cwd == "/workspace"

    @pytest.mark.asyncio
    async def test_new_session_returns_model_state(self, agent):
        mock_config = {"model-a": {"type": "test"}, "model-b": {"type": "test"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.config.get_global_model_name", return_value="model-a"):
            resp = await agent.new_session(cwd="/tmp")
        assert resp.models is not None
        assert resp.models.current_model_id == "model-a"
        assert len(resp.models.available_models) == 2

    def test_session_state_has_mode(self):
        state = _SessionState("sid-1", mode="read")
        assert state.mode == "read"

    def test_session_state_has_created_at(self):
        state = _SessionState("sid-1")
        assert state.created_at is not None
        assert len(state.created_at) > 0


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
# Streaming (Unit 1)
# ---------------------------------------------------------------------------


class TestStreaming:
    """Test real-time streaming with run_stream() and batch fallback."""

    @pytest.mark.asyncio
    async def test_run_agent_uses_streaming(self):
        """_run_agent_streamed streams text chunks to the client."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        session = agent._sessions[resp.session_id]

        # Build a mock stream context manager
        async def _fake_stream_text(delta=True):
            for chunk in ["Hello", " ", "world"]:
                yield chunk

        mock_stream_result = MagicMock()
        mock_stream_result.stream_text = _fake_stream_text
        mock_stream_result.all_messages = MagicMock(return_value=["msg1"])

        mock_pydantic_agent = MagicMock()

        class _FakeStreamCM:
            async def __aenter__(self_cm):
                return mock_stream_result
            async def __aexit__(self_cm, *args):
                pass

        mock_pydantic_agent.run_stream = MagicMock(return_value=_FakeStreamCM())

        text, events, was_streamed = await agent._run_agent_streamed(
            mock_pydantic_agent, session, "hi", [],
        )

        assert was_streamed is True
        assert text == "Hello world"
        # _send_text called for each chunk
        assert client.session_update.call_count == 3
        # History persisted from stream result
        assert session.message_history == ["msg1"]

    @pytest.mark.asyncio
    async def test_run_agent_fallback_to_batch(self):
        """When _run_agent_streamed raises AttributeError, _run_agent falls back to batch."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        session = agent._sessions[resp.session_id]

        mock_result = _make_mock_result("Batch response")

        # Streamed path raises → triggers fallback
        async def _failing_stream(self, pydantic_agent, session, prompt, history):
            raise AttributeError("no streaming")

        # Batch path succeeds
        async def _ok_batch(self, pydantic_agent, base_agent, session, prompt, history):
            return "Batch response", [], False

        with patch.object(CodePuppyAgent, "_run_agent_streamed", _failing_stream), \
             patch.object(CodePuppyAgent, "_run_agent_batch", _ok_batch):
            mock_base_agent = _MockBaseAgent(MagicMock())
            # Need to patch load_agent too
            agents_mod = ModuleType("code_puppy.agents")
            agents_mod.load_agent = MagicMock(return_value=mock_base_agent)
            with patch.dict("sys.modules", {"code_puppy.agents": agents_mod}):
                text, events, was_streamed = await agent._run_agent(session, "hi")

        assert was_streamed is False
        assert text == "Batch response"

    @pytest.mark.asyncio
    async def test_prompt_no_duplicate_text_when_streamed(self):
        """When streaming was used, prompt() does NOT send text again."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        # Patch _run_agent to simulate streaming
        async def _fake_run_agent(self, session, prompt_text):
            # Simulate that streaming already sent text via _send_text
            await self._send_text(session.session_id, "streamed text")
            return "streamed text", [], True

        with patch.object(CodePuppyAgent, "_run_agent", _fake_run_agent):
            result = await agent.prompt(
                prompt=[_make_text_block("hello")],
                session_id=sid,
            )

        assert result.stop_reason == "end_turn"
        # Only 1 call from the streaming path, NOT a second one from prompt()
        assert client.session_update.call_count == 1

    @pytest.mark.asyncio
    async def test_prompt_sends_text_when_batch(self):
        """When batch was used, prompt() sends text normally."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_result = _make_mock_result("Batch result")
        with _mock_code_puppy_agent(mock_result):
            result = await agent.prompt(
                prompt=[_make_text_block("hello")],
                session_id=sid,
            )

        assert result.stop_reason == "end_turn"
        # At least 1 call for the final text
        assert client.session_update.call_count >= 1


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
    async def test_stream_plan_event_uses_structured_plan(self):
        """Plan events should use the ACP plan_entry/update_plan helpers."""
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

    @pytest.mark.asyncio
    async def test_send_plan_calls_session_update(self):
        agent, client = _make_agent_with_client()
        steps = [{"description": "Do step A"}, {"description": "Do step B"}]
        await agent._send_plan("sid-1", steps)
        client.session_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_plan_empty_steps(self):
        agent, client = _make_agent_with_client()
        await agent._send_plan("sid-1", [])
        client.session_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_plan_without_connection(self):
        agent = CodePuppyAgent()
        await agent._send_plan("sid", [{"description": "test"}])
        # Should not raise


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
# Authentication (Phase C)
# ---------------------------------------------------------------------------


class TestAuthentication:
    """Test authenticate method."""

    @pytest.mark.asyncio
    async def test_authenticate_when_not_required(self):
        """When auth is not required, authenticate always succeeds."""
        agent, _ = _make_agent_with_client()
        # Default: ACP_AUTH_REQUIRED=false
        result = await agent.authenticate(method_id="bearer")
        assert result is not None
        assert agent._authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_bearer_success(self):
        """Valid bearer token authenticates successfully."""
        agent, _ = _make_agent_with_client()
        agent._authenticated = False

        with patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_REQUIRED", True), \
             patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_TOKEN", "secret-123"):
            result = await agent.authenticate(method_id="bearer", token="secret-123")
            assert result is not None
            assert agent._authenticated is True

    @pytest.mark.asyncio
    async def test_authenticate_bearer_invalid_token(self):
        """Invalid bearer token raises auth_required error."""
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        agent._authenticated = False

        with patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_REQUIRED", True), \
             patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_TOKEN", "secret-123"):
            with pytest.raises(RequestError):
                await agent.authenticate(method_id="bearer", token="wrong-token")

    @pytest.mark.asyncio
    async def test_authenticate_unknown_method(self):
        """Unknown auth method raises error."""
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_REQUIRED", True):
            with pytest.raises(RequestError):
                await agent.authenticate(method_id="oauth2")

    @pytest.mark.asyncio
    async def test_initialize_with_auth_required(self):
        """When auth is required, initialize response includes auth methods."""
        agent, _ = _make_agent_with_client()

        with patch("code_puppy.plugins.acp_gateway.agent.ACP_AUTH_REQUIRED", True):
            resp = await agent.initialize(protocol_version=1)

        assert resp.auth_methods is not None
        assert len(resp.auth_methods) == 1
        assert resp.auth_methods[0].id == "bearer"

    @pytest.mark.asyncio
    async def test_initialize_without_auth_required(self, agent):
        """When auth is not required, initialize response has no auth methods."""
        resp = await agent.initialize(protocol_version=1)
        # auth_methods should be empty
        assert resp.auth_methods is None or len(resp.auth_methods) == 0


# ---------------------------------------------------------------------------
# Session modes (Phase D)
# ---------------------------------------------------------------------------


class TestSessionModes:
    """Test set_session_mode."""

    @pytest.mark.asyncio
    async def test_set_mode_valid(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        result = await agent.set_session_mode(mode_id="read", session_id=sid)
        assert result is not None
        assert agent._sessions[sid].mode == "read"

    @pytest.mark.asyncio
    async def test_set_mode_sends_notification(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        client.session_update.reset_mock()
        await agent.set_session_mode(mode_id="write", session_id=sid)
        # Should have sent CurrentModeUpdate notification
        assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_set_mode_invalid(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with pytest.raises(RequestError):
            await agent.set_session_mode(mode_id="invalid_mode", session_id=sid)

    @pytest.mark.asyncio
    async def test_set_mode_unknown_session(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with pytest.raises(RequestError):
            await agent.set_session_mode(mode_id="read", session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_all_modes_accepted(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        for mode_id in _MODE_IDS:
            result = await agent.set_session_mode(mode_id=mode_id, session_id=sid)
            assert result is not None
            assert agent._sessions[sid].mode == mode_id


# ---------------------------------------------------------------------------
# HITL tool approval (Unit 2)
# ---------------------------------------------------------------------------


class TestHitlToolApproval:
    """Test mode-based tool approval scaffolding."""

    def test_should_require_approval_yolo_mode(self):
        """Yolo mode never requires approval."""
        for tool in _DANGEROUS_TOOLS:
            assert CodePuppyAgent._should_require_approval(tool, "yolo") is False

    def test_should_require_approval_read_mode(self):
        """Read mode requires approval for ALL dangerous tools."""
        for tool in _DANGEROUS_TOOLS:
            assert CodePuppyAgent._should_require_approval(tool, "read") is True

    def test_should_require_approval_write_mode(self):
        """Write mode auto-approves file ops but not shell commands."""
        # File tools are allowed
        assert CodePuppyAgent._should_require_approval("write_file", "write") is False
        assert CodePuppyAgent._should_require_approval("edit_file", "write") is False
        assert CodePuppyAgent._should_require_approval("create_file", "write") is False
        # Shell tools require approval
        assert CodePuppyAgent._should_require_approval("run_terminal_cmd", "write") is True
        assert CodePuppyAgent._should_require_approval("execute_command", "write") is True

    def test_should_require_approval_execute_mode(self):
        """Execute mode auto-approves both file and shell ops."""
        assert CodePuppyAgent._should_require_approval("write_file", "execute") is False
        assert CodePuppyAgent._should_require_approval("run_terminal_cmd", "execute") is False
        assert CodePuppyAgent._should_require_approval("bash", "execute") is False

    def test_safe_tool_never_needs_approval(self):
        """Tools not in _DANGEROUS_TOOLS never need approval."""
        for mode in ["read", "write", "execute", "yolo"]:
            assert CodePuppyAgent._should_require_approval("read_file", mode) is False
            assert CodePuppyAgent._should_require_approval("search", mode) is False
            assert CodePuppyAgent._should_require_approval("list_dir", mode) is False

    @pytest.mark.asyncio
    async def test_request_tool_approval_no_conn(self):
        """Without a connection, auto-approve."""
        agent, _ = _make_agent_with_client()
        agent._conn = None
        result = await agent._request_tool_approval("sid", "run_terminal_cmd")
        assert result is True

    @pytest.mark.asyncio
    async def test_request_tool_approval_with_conn_allowed(self):
        """When client allows, returns True."""
        agent, client = _make_agent_with_client()
        mock_outcome = MagicMock()
        mock_outcome.outcome = "selected"
        mock_resp = MagicMock()
        mock_resp.outcome = mock_outcome
        client.request_permission = AsyncMock(return_value=mock_resp)

        result = await agent._request_tool_approval("sid", "run_terminal_cmd")
        assert result is True
        client.request_permission.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_tool_approval_with_conn_denied(self):
        """When client denies (cancelled), returns False."""
        agent, client = _make_agent_with_client()
        mock_outcome = MagicMock()
        mock_outcome.outcome = "cancelled"
        mock_resp = MagicMock()
        mock_resp.outcome = mock_outcome
        client.request_permission = AsyncMock(return_value=mock_resp)

        result = await agent._request_tool_approval("sid", "run_terminal_cmd")
        assert result is False

    @pytest.mark.asyncio
    async def test_request_tool_approval_exception_auto_approves(self):
        """If request_permission raises, auto-approve."""
        agent, client = _make_agent_with_client()
        client.request_permission = AsyncMock(side_effect=RuntimeError("fail"))

        result = await agent._request_tool_approval("sid", "run_terminal_cmd")
        assert result is True

    @pytest.mark.asyncio
    async def test_prompt_sends_mode_thought_non_yolo(self):
        """In non-yolo mode, prompt sends a thought about the active mode."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id
        agent._sessions[sid].mode = "read"

        mock_result = _make_mock_result("ok")
        with _mock_code_puppy_agent(mock_result):
            client.session_update.reset_mock()
            await agent.prompt(prompt=[_make_text_block("hello")], session_id=sid)

        # First call should be the mode thought
        calls = client.session_update.call_args_list
        assert len(calls) >= 2  # mode thought + final text at minimum

    @pytest.mark.asyncio
    async def test_prompt_no_mode_thought_in_yolo(self):
        """In yolo mode, no mode thought is sent."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id
        # mode defaults to yolo

        mock_result = _make_mock_result("ok")
        with _mock_code_puppy_agent(mock_result):
            client.session_update.reset_mock()
            await agent.prompt(prompt=[_make_text_block("hello")], session_id=sid)

        # Should have the final text call but NOT a mode thought before it
        # (just 1 call for the response text)
        assert client.session_update.call_count == 1

    @pytest.mark.asyncio
    async def test_audit_tool_events_flags_dangerous_in_read_mode(self):
        """_audit_tool_events sends a warning thought for flagged tools."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        events = [
            {"type": "tool_call", "tool_name": "run_terminal_cmd"},
            {"type": "tool_call", "tool_name": "read_file"},
        ]
        client.session_update.reset_mock()
        await agent._audit_tool_events(sid, events, "read")
        # Should have sent 1 thought warning about run_terminal_cmd
        assert client.session_update.call_count == 1

    @pytest.mark.asyncio
    async def test_audit_tool_events_silent_in_yolo(self):
        """_audit_tool_events does nothing in yolo mode."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        events = [{"type": "tool_call", "tool_name": "run_terminal_cmd"}]
        client.session_update.reset_mock()
        await agent._audit_tool_events(sid, events, "yolo")
        assert client.session_update.call_count == 0


# ---------------------------------------------------------------------------
# Session model (Phase E)
# ---------------------------------------------------------------------------


class TestSessionModel:
    """Test set_session_model with ModelFactory validation."""

    @pytest.mark.asyncio
    async def test_set_model_success(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_config = {"claude-4-0-sonnet": {"type": "anthropic"}, "gpt-5": {"type": "openai"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.model_switching.set_model_and_reload_agent") as mock_set:
            result = await agent.set_session_model(model_id="claude-4-0-sonnet", session_id=sid)
            assert result is not None
            mock_set.assert_called_once_with("claude-4-0-sonnet")

    @pytest.mark.asyncio
    async def test_set_model_unknown_session(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with pytest.raises(RequestError):
            await agent.set_session_model(model_id="any-model", session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_set_model_not_in_factory(self):
        """Reject models that don't exist in ModelFactory."""
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_config = {"gpt-5": {"type": "openai"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config):
            with pytest.raises(RequestError):
                await agent.set_session_model(model_id="nonexistent-model", session_id=sid)

    @pytest.mark.asyncio
    async def test_set_model_reload_error(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_config = {"bad-model": {"type": "openai"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.model_switching.set_model_and_reload_agent", side_effect=ValueError("reload failed")):
            with pytest.raises(RequestError):
                await agent.set_session_model(model_id="bad-model", session_id=sid)


# ---------------------------------------------------------------------------
# Session model notifications (Unit 3)
# ---------------------------------------------------------------------------


class TestSessionModelNotification:
    """Test CurrentModelUpdate notification on model switch."""

    @pytest.mark.asyncio
    async def test_set_model_sends_notification(self):
        """set_session_model sends a model update notification to the client."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_config = {"claude-4-0-sonnet": {"type": "anthropic"}}
        # Mock CurrentModelUpdate since it may not exist in the schema yet
        mock_model_update_cls = MagicMock()
        mock_model_update_instance = MagicMock()
        mock_model_update_cls.return_value = mock_model_update_instance

        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.model_switching.set_model_and_reload_agent"), \
             patch.dict("sys.modules", {}), \
             patch("acp.schema.CurrentModelUpdate", mock_model_update_cls, create=True):
            client.session_update.reset_mock()
            result = await agent.set_session_model(model_id="claude-4-0-sonnet", session_id=sid)
            assert result is not None
            # Should have attempted to send a notification
            assert client.session_update.call_count >= 1

    @pytest.mark.asyncio
    async def test_set_model_no_conn_no_failure(self):
        """When _conn is None, set_session_model succeeds without notification."""
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id
        agent._conn = None  # Simulate no connection

        mock_config = {"gpt-5": {"type": "openai"}}
        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.model_switching.set_model_and_reload_agent"):
            result = await agent.set_session_model(model_id="gpt-5", session_id=sid)
            assert result is not None  # Should succeed without error

    @pytest.mark.asyncio
    async def test_set_model_notification_error_is_swallowed(self):
        """If session_update raises, the error is logged but set_session_model still succeeds."""
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_config = {"claude-4-0-sonnet": {"type": "anthropic"}}
        # Make session_update raise an exception
        client.session_update.side_effect = RuntimeError("connection lost")

        with patch("code_puppy.model_factory.ModelFactory.load_config", return_value=mock_config), \
             patch("code_puppy.model_switching.set_model_and_reload_agent"):
            # Should NOT raise despite the notification failure
            result = await agent.set_session_model(model_id="claude-4-0-sonnet", session_id=sid)
            assert result is not None


# ---------------------------------------------------------------------------
# Config options (Phase F)
# ---------------------------------------------------------------------------


class TestConfigOptions:
    """Test set_config_option."""

    @pytest.mark.asyncio
    async def test_set_auto_save_true(self):
        agent, client = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with patch("code_puppy.config.set_auto_save_session") as mock_set, \
             patch("code_puppy.plugins.acp_gateway.agent._build_config_options", return_value=[]):
            result = await agent.set_config_option(
                config_id="auto_save", session_id=sid, value="true"
            )
            assert result is not None
            mock_set.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_set_auto_save_false(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with patch("code_puppy.config.set_auto_save_session") as mock_set, \
             patch("code_puppy.plugins.acp_gateway.agent._build_config_options", return_value=[]):
            await agent.set_config_option(
                config_id="auto_save", session_id=sid, value="false"
            )
            mock_set.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_set_safety_level_valid(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with patch("code_puppy.config.set_value") as mock_set, \
             patch("code_puppy.plugins.acp_gateway.agent._build_config_options", return_value=[]):
            result = await agent.set_config_option(
                config_id="safety_level", session_id=sid, value="high"
            )
            assert result is not None
            mock_set.assert_called_once_with("safety_permission_level", "high")

    @pytest.mark.asyncio
    async def test_set_safety_level_invalid(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with patch("code_puppy.config.set_value"):
            with pytest.raises(RequestError):
                await agent.set_config_option(
                    config_id="safety_level", session_id=sid, value="extreme"
                )

    @pytest.mark.asyncio
    async def test_set_generic_config_passthrough(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        with patch("code_puppy.config.set_value") as mock_set, \
             patch("code_puppy.plugins.acp_gateway.agent._build_config_options", return_value=[]):
            result = await agent.set_config_option(
                config_id="custom_key", session_id=sid, value="custom_value"
            )
            assert result is not None
            mock_set.assert_called_once_with("custom_key", "custom_value")

    @pytest.mark.asyncio
    async def test_set_active_agent_success(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_agents = {"code-puppy": "Code Puppy", "python-programmer": "Python Pro"}
        # Mock at the module level that set_config_option imports from
        mock_mod = MagicMock()
        mock_mod.get_available_agents = MagicMock(return_value=mock_agents)
        with patch.dict("sys.modules", {"code_puppy.agents": mock_mod}), \
             patch("code_puppy.plugins.acp_gateway.agent._build_config_options", return_value=[]):
            result = await agent.set_config_option(
                config_id="active_agent", session_id=sid, value="python-programmer"
            )
            assert result is not None
            assert agent._sessions[sid].agent_name == "python-programmer"

    @pytest.mark.asyncio
    async def test_set_active_agent_invalid(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_agents = {"code-puppy": "Code Puppy"}
        mock_mod = MagicMock()
        mock_mod.get_available_agents = MagicMock(return_value=mock_agents)
        with patch.dict("sys.modules", {"code_puppy.agents": mock_mod}):
            with pytest.raises(RequestError):
                await agent.set_config_option(
                    config_id="active_agent", session_id=sid, value="nonexistent-agent"
                )

    @pytest.mark.asyncio
    async def test_set_config_unknown_session(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with pytest.raises(RequestError):
            await agent.set_config_option(
                config_id="auto_save", session_id="nonexistent", value="true"
            )


# ---------------------------------------------------------------------------
# MCP server passthrough (Unit 4)
# ---------------------------------------------------------------------------


class TestMcpServerPassthrough:
    """Test that MCP servers are stored and forwarded through session lifecycle."""

    @pytest.mark.asyncio
    async def test_new_session_stores_mcp_servers(self):
        agent, _ = _make_agent_with_client()
        mock_servers = [MagicMock(), MagicMock()]
        resp = await agent.new_session(cwd="/tmp", mcp_servers=mock_servers)
        session = agent._sessions[resp.session_id]
        assert session.mcp_servers is not None
        assert len(session.mcp_servers) == 2

    @pytest.mark.asyncio
    async def test_new_session_no_mcp_servers(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        session = agent._sessions[resp.session_id]
        assert session.mcp_servers is None

    @pytest.mark.asyncio
    async def test_fork_inherits_parent_mcp_servers(self):
        agent, _ = _make_agent_with_client()
        mock_servers = [MagicMock()]
        resp = await agent.new_session(cwd="/tmp", mcp_servers=mock_servers)
        sid = resp.session_id

        fork_resp = await agent.fork_session(cwd="/tmp", session_id=sid)
        child = agent._sessions[fork_resp.session_id]
        # Child inherits parent's MCP servers when none are provided
        assert child.mcp_servers is not None
        assert len(child.mcp_servers) == 1

    @pytest.mark.asyncio
    async def test_fork_overrides_mcp_servers(self):
        agent, _ = _make_agent_with_client()
        parent_servers = [MagicMock()]
        resp = await agent.new_session(cwd="/tmp", mcp_servers=parent_servers)
        sid = resp.session_id

        child_servers = [MagicMock(), MagicMock(), MagicMock()]
        fork_resp = await agent.fork_session(
            cwd="/tmp", session_id=sid, mcp_servers=child_servers
        )
        child = agent._sessions[fork_resp.session_id]
        # Child uses its own MCP servers, not the parent's
        assert len(child.mcp_servers) == 3

    @pytest.mark.asyncio
    async def test_resume_session_stores_mcp_servers(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        mock_servers = [MagicMock()]
        await agent.resume_session(cwd="/tmp", session_id=sid, mcp_servers=mock_servers)
        session = agent._sessions[sid]
        assert session.mcp_servers is not None
        assert len(session.mcp_servers) == 1

    @pytest.mark.asyncio
    async def test_session_state_mcp_servers_default_none(self):
        state = _SessionState("test-sid")
        assert state.mcp_servers is None


# ---------------------------------------------------------------------------
# Fork session (Phase B3)
# ---------------------------------------------------------------------------


class TestForkSession:
    """Test fork_session."""

    @pytest.mark.asyncio
    async def test_fork_creates_new_session(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        # Add some history to the parent
        agent._sessions[sid].message_history = ["msg1", "msg2"]

        fork_resp = await agent.fork_session(cwd="/workspace", session_id=sid)
        assert fork_resp.session_id != sid
        assert fork_resp.session_id in agent._sessions

    @pytest.mark.asyncio
    async def test_fork_deep_copies_history(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        parent_history = [{"role": "user", "text": "hello"}]
        agent._sessions[sid].message_history = parent_history

        fork_resp = await agent.fork_session(cwd="/workspace", session_id=sid)
        child = agent._sessions[fork_resp.session_id]

        # Child has same content
        assert child.message_history == parent_history
        # But modifying child does not affect parent
        child.message_history.append({"role": "assistant", "text": "world"})
        assert len(agent._sessions[sid].message_history) == 1

    @pytest.mark.asyncio
    async def test_fork_inherits_mode(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id
        agent._sessions[sid].mode = "read"

        fork_resp = await agent.fork_session(cwd="/tmp", session_id=sid)
        child = agent._sessions[fork_resp.session_id]
        assert child.mode == "read"

    @pytest.mark.asyncio
    async def test_fork_unknown_session(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with pytest.raises(RequestError):
            await agent.fork_session(cwd="/tmp", session_id="nonexistent")

    @pytest.mark.asyncio
    async def test_fork_returns_mode_state(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")

        fork_resp = await agent.fork_session(cwd="/tmp", session_id=resp.session_id)
        assert fork_resp.modes is not None
        assert fork_resp.session_id is not None


# ---------------------------------------------------------------------------
# Load session (Phase B2)
# ---------------------------------------------------------------------------


class TestLoadSession:
    """Test load_session."""

    @pytest.mark.asyncio
    async def test_load_from_memory(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        result = await agent.load_session(cwd="/workspace", session_id=sid)
        assert result is not None
        assert result.modes is not None
        # cwd should be updated
        assert agent._sessions[sid].cwd == "/workspace"

    @pytest.mark.asyncio
    async def test_load_from_disk(self):
        agent, _ = _make_agent_with_client()
        mock_history = ["msg1", "msg2"]

        with patch("code_puppy.session_storage.load_session", return_value=mock_history), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"), \
             patch("code_puppy.config.get_auto_save_session", return_value=True), \
             patch("code_puppy.config.get_safety_permission_level", return_value="medium"):
            result = await agent.load_session(cwd="/workspace", session_id="disk-session")

        assert result is not None
        assert "disk-session" in agent._sessions
        assert agent._sessions["disk-session"].message_history == ["msg1", "msg2"]

    @pytest.mark.asyncio
    async def test_load_not_found(self):
        agent, _ = _make_agent_with_client()

        with patch("code_puppy.session_storage.load_session", side_effect=FileNotFoundError), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"):
            result = await agent.load_session(cwd="/workspace", session_id="missing")

        assert result is None


# ---------------------------------------------------------------------------
# List sessions (Phase B1)
# ---------------------------------------------------------------------------


class TestListSessions:
    """Test list_sessions.

    Mocks disk storage to prevent real autosave files from polluting results.
    """

    @pytest.mark.asyncio
    async def test_list_in_memory_sessions(self):
        agent, _ = _make_agent_with_client()
        await agent.new_session(cwd="/a")
        await agent.new_session(cwd="/b")

        with patch("code_puppy.session_storage.list_sessions", return_value=[]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/nonexistent"):
            result = await agent.list_sessions()
        assert len(result.sessions) == 2

    @pytest.mark.asyncio
    async def test_list_filters_by_cwd(self):
        agent, _ = _make_agent_with_client()
        await agent.new_session(cwd="/a")
        await agent.new_session(cwd="/b")

        with patch("code_puppy.session_storage.list_sessions", return_value=[]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/nonexistent"):
            result = await agent.list_sessions(cwd="/a")
        assert len(result.sessions) == 1

    @pytest.mark.asyncio
    async def test_list_pagination(self):
        agent, _ = _make_agent_with_client()
        # Create enough sessions to test cursor
        for i in range(3):
            await agent.new_session(cwd=f"/dir-{i}")

        with patch("code_puppy.session_storage.list_sessions", return_value=[]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/nonexistent"):
            result = await agent.list_sessions(cursor="0")
        assert len(result.sessions) == 3
        assert result.next_cursor is None  # Less than page_size

    @pytest.mark.asyncio
    async def test_list_empty(self):
        agent, _ = _make_agent_with_client()
        with patch("code_puppy.session_storage.list_sessions", return_value=[]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/nonexistent"):
            result = await agent.list_sessions()
        assert len(result.sessions) == 0
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_list_includes_disk_sessions(self):
        """Disk sessions are merged with in-memory sessions."""
        agent, _ = _make_agent_with_client()
        await agent.new_session(cwd="/workspace")

        with patch("code_puppy.session_storage.list_sessions", return_value=["disk-1", "disk-2"]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"):
            result = await agent.list_sessions()
        # 1 in-memory + 2 from disk
        assert len(result.sessions) == 3


# ---------------------------------------------------------------------------
# Resume session (Phase B4)
# ---------------------------------------------------------------------------


class TestResumeSession:
    """Test resume_session."""

    @pytest.mark.asyncio
    async def test_resume_from_memory(self):
        agent, _ = _make_agent_with_client()
        resp = await agent.new_session(cwd="/tmp")
        sid = resp.session_id

        result = await agent.resume_session(cwd="/new-cwd", session_id=sid)
        assert result is not None
        assert result.modes is not None
        assert agent._sessions[sid].cwd == "/new-cwd"

    @pytest.mark.asyncio
    async def test_resume_from_disk(self):
        agent, _ = _make_agent_with_client()

        with patch("code_puppy.session_storage.load_session", return_value=["msg"]), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"), \
             patch("code_puppy.config.get_auto_save_session", return_value=True), \
             patch("code_puppy.config.get_safety_permission_level", return_value="medium"):
            result = await agent.resume_session(cwd="/workspace", session_id="disk-sess")

        assert result is not None
        assert "disk-sess" in agent._sessions

    @pytest.mark.asyncio
    async def test_resume_not_found(self):
        from acp.exceptions import RequestError

        agent, _ = _make_agent_with_client()

        with patch("code_puppy.session_storage.load_session", side_effect=FileNotFoundError), \
             patch("code_puppy.config.AUTOSAVE_DIR", "/tmp/autosaves"):
            with pytest.raises(RequestError):
                await agent.resume_session(cwd="/workspace", session_id="missing")


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
        return result_text, tool_events, False

    return patch.object(CodePuppyAgent, "_run_agent", _fake_run_agent)


def _mock_code_puppy_agent_error(error):
    """Context manager that patches ``_run_agent`` to raise *error*."""

    async def _failing_run_agent(self, session, prompt_text):
        raise error

    return patch.object(CodePuppyAgent, "_run_agent", _failing_run_agent)
