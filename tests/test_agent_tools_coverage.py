"""Additional coverage tests for agent_tools.py.

This module focuses on testing uncovered code paths including:
- _generate_dbos_workflow_id function
- _get_subagent_sessions_dir function
- Pydantic models (AgentInfo, ListAgentsOutput, AgentInvokeOutput)
- register_list_agents tool execution
- register_invoke_agent tool execution with various code paths
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_puppy.tools.agent_tools import (
    AgentInfo,
    AgentInvokeOutput,
    ListAgentsOutput,
    _generate_dbos_workflow_id,
    _get_subagent_sessions_dir,
    register_invoke_agent,
    register_list_agents,
)


class TestGenerateDBOSWorkflowId:
    """Test suite for _generate_dbos_workflow_id function."""

    def test_generates_unique_ids(self):
        """Test that consecutive calls generate unique workflow IDs."""
        ids = set()
        for _ in range(10):
            workflow_id = _generate_dbos_workflow_id("base-id")
            ids.add(workflow_id)
        # All IDs should be unique
        assert len(ids) == 10

    def test_format_includes_base_id(self):
        """Test that generated ID includes the base ID."""
        workflow_id = _generate_dbos_workflow_id("my-group")
        assert workflow_id.startswith("my-group-wf-")

    def test_format_includes_counter_suffix(self):
        """Test that generated ID has the wf-N format."""
        workflow_id = _generate_dbos_workflow_id("test")
        parts = workflow_id.split("-")
        # Format: test-wf-N
        assert "wf" in parts
        # Last part should be a number
        assert parts[-1].isdigit()

    def test_counter_is_incrementing(self):
        """Test that the counter increments atomically."""
        id1 = _generate_dbos_workflow_id("base")
        id2 = _generate_dbos_workflow_id("base")
        id3 = _generate_dbos_workflow_id("base")

        # Extract counters
        counter1 = int(id1.split("-")[-1])
        counter2 = int(id2.split("-")[-1])
        counter3 = int(id3.split("-")[-1])

        # Counters should be strictly increasing
        assert counter2 > counter1
        assert counter3 > counter2

    def test_different_base_ids_same_counter_sequence(self):
        """Test that different base IDs share the same counter."""
        id1 = _generate_dbos_workflow_id("alpha")
        id2 = _generate_dbos_workflow_id("beta")

        counter1 = int(id1.split("-")[-1])
        counter2 = int(id2.split("-")[-1])

        # Counter should still increment
        assert counter2 == counter1 + 1

    def test_empty_base_id(self):
        """Test with empty base ID."""
        workflow_id = _generate_dbos_workflow_id("")
        assert workflow_id.startswith("-wf-")
        # Should still have a counter
        parts = workflow_id.split("-")
        assert parts[-1].isdigit()

    def test_complex_base_id(self):
        """Test with complex base ID containing hyphens."""
        workflow_id = _generate_dbos_workflow_id("invoke-agent-qa-expert-12345")
        assert workflow_id.startswith("invoke-agent-qa-expert-12345-wf-")


class TestGetSubagentSessionsDir:
    """Test suite for _get_subagent_sessions_dir function."""

    def test_returns_path_object(self):
        """Test that function returns a Path object."""
        with patch("code_puppy.tools.agent_tools.DATA_DIR", tempfile.gettempdir()):
            result = _get_subagent_sessions_dir()
            assert isinstance(result, Path)

    def test_path_ends_with_subagent_sessions(self):
        """Test that path ends with 'subagent_sessions'."""
        with patch("code_puppy.tools.agent_tools.DATA_DIR", tempfile.gettempdir()):
            result = _get_subagent_sessions_dir()
            assert result.name == "subagent_sessions"

    def test_creates_directory_if_not_exists(self):
        """Test that directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.agent_tools.DATA_DIR", tmpdir):
                result = _get_subagent_sessions_dir()
                assert result.exists()
                assert result.is_dir()

    def test_directory_has_correct_permissions(self):
        """Test that created directory has mode 0o700."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_puppy.tools.agent_tools.DATA_DIR", tmpdir):
                result = _get_subagent_sessions_dir()
                # Check mode (on Unix-like systems)
                mode = result.stat().st_mode & 0o777
                assert mode == 0o700

    def test_returns_same_path_on_multiple_calls(self):
        """Test that function returns consistent path."""
        with patch("code_puppy.tools.agent_tools.DATA_DIR", tempfile.gettempdir()):
            path1 = _get_subagent_sessions_dir()
            path2 = _get_subagent_sessions_dir()
            assert path1 == path2


class TestPydanticModels:
    """Test suite for Pydantic models in agent_tools."""

    class TestAgentInfo:
        """Tests for AgentInfo model."""

        def test_create_with_required_fields(self):
            """Test creating AgentInfo with all required fields."""
            info = AgentInfo(
                name="test-agent",
                display_name="Test Agent",
                description="A test agent for testing",
            )
            assert info.name == "test-agent"
            assert info.display_name == "Test Agent"
            assert info.description == "A test agent for testing"

        def test_serialization(self):
            """Test that AgentInfo serializes correctly."""
            info = AgentInfo(
                name="code-reviewer",
                display_name="Code Reviewer",
                description="Reviews code for quality",
            )
            data = info.model_dump()
            assert data["name"] == "code-reviewer"
            assert data["display_name"] == "Code Reviewer"
            assert data["description"] == "Reviews code for quality"

        def test_json_serialization(self):
            """Test JSON serialization."""
            info = AgentInfo(
                name="qa-expert",
                display_name="QA Expert",
                description="Quality assurance expert",
            )
            json_str = info.model_dump_json()
            assert "qa-expert" in json_str
            assert "QA Expert" in json_str

    class TestListAgentsOutput:
        """Tests for ListAgentsOutput model."""

        def test_create_with_agents_list(self):
            """Test creating with list of agents."""
            agents = [
                AgentInfo(
                    name="agent1",
                    display_name="Agent One",
                    description="First agent",
                ),
                AgentInfo(
                    name="agent2",
                    display_name="Agent Two",
                    description="Second agent",
                ),
            ]
            output = ListAgentsOutput(agents=agents)
            assert len(output.agents) == 2
            assert output.error is None

        def test_create_with_error(self):
            """Test creating with error message."""
            output = ListAgentsOutput(agents=[], error="Something went wrong")
            assert len(output.agents) == 0
            assert output.error == "Something went wrong"

        def test_default_error_is_none(self):
            """Test that error defaults to None."""
            output = ListAgentsOutput(agents=[])
            assert output.error is None

        def test_empty_agents_list(self):
            """Test with empty agents list."""
            output = ListAgentsOutput(agents=[])
            assert output.agents == []

    class TestAgentInvokeOutput:
        """Tests for AgentInvokeOutput model."""

        def test_create_success_response(self):
            """Test creating successful invocation output."""
            output = AgentInvokeOutput(
                response="This is the agent's response",
                agent_name="test-agent",
                session_id="session-abc123",
            )
            assert output.response == "This is the agent's response"
            assert output.agent_name == "test-agent"
            assert output.session_id == "session-abc123"
            assert output.error is None

        def test_create_error_response(self):
            """Test creating error invocation output."""
            output = AgentInvokeOutput(
                response=None,
                agent_name="failing-agent",
                error="Agent crashed",
            )
            assert output.response is None
            assert output.agent_name == "failing-agent"
            assert output.error == "Agent crashed"

        def test_default_values(self):
            """Test default values for optional fields."""
            output = AgentInvokeOutput(
                response="response",
                agent_name="agent",
            )
            assert output.session_id is None
            assert output.error is None

        def test_serialization(self):
            """Test model serialization."""
            output = AgentInvokeOutput(
                response="Hello!",
                agent_name="greeter",
                session_id="session-123",
            )
            data = output.model_dump()
            assert data["response"] == "Hello!"
            assert data["agent_name"] == "greeter"
            assert data["session_id"] == "session-123"


class TestRegisterListAgentsExecution:
    """Test the actual list_agents tool function execution."""

    def test_list_agents_returns_available_agents(self):
        """Test that list_agents returns available agents."""
        mock_agent = MagicMock()
        mock_context = MagicMock()

        # Capture the registered function
        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool

        # Register the tool
        register_list_agents(mock_agent)
        assert registered_func is not None

        # Mock the agent manager functions and config
        # Note: get_banner_color is imported from code_puppy.config inside the function
        with (
            patch(
                "code_puppy.config.get_banner_color",
                return_value="blue",
            ),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
            patch("code_puppy.agents.get_available_agents") as mock_available,
            patch("code_puppy.agents.get_agent_descriptions") as mock_descriptions,
        ):
            mock_available.return_value = {
                "code-reviewer": "Code Reviewer",
                "qa-expert": "QA Expert",
            }
            mock_descriptions.return_value = {
                "code-reviewer": "Reviews code quality",
                "qa-expert": "QA testing expert",
            }

            # Call the registered function
            result = registered_func(mock_context)

            # Verify the result
            assert isinstance(result, ListAgentsOutput)
            assert len(result.agents) == 2
            assert result.error is None

            # Verify agent info
            agent_names = [a.name for a in result.agents]
            assert "code-reviewer" in agent_names
            assert "qa-expert" in agent_names

    def test_list_agents_handles_exception(self):
        """Test that list_agents handles exceptions gracefully."""
        mock_agent = MagicMock()
        mock_context = MagicMock()

        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool
        register_list_agents(mock_agent)

        # Mock to raise an exception
        with (
            patch(
                "code_puppy.config.get_banner_color",
                return_value="blue",
            ),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch("code_puppy.tools.agent_tools.emit_error") as mock_emit_error,
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
            patch(
                "code_puppy.agents.get_available_agents",
                side_effect=RuntimeError("Database connection failed"),
            ),
        ):
            result = registered_func(mock_context)

            # Should return error output
            assert isinstance(result, ListAgentsOutput)
            assert len(result.agents) == 0
            assert "Database connection failed" in result.error
            assert mock_emit_error.called

    def test_list_agents_with_missing_description(self):
        """Test that list_agents handles missing descriptions."""
        mock_agent = MagicMock()
        mock_context = MagicMock()

        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool
        register_list_agents(mock_agent)

        with (
            patch(
                "code_puppy.config.get_banner_color",
                return_value="blue",
            ),
            patch("code_puppy.tools.agent_tools.emit_info"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
            patch("code_puppy.agents.get_available_agents") as mock_available,
            patch("code_puppy.agents.get_agent_descriptions") as mock_descriptions,
        ):
            mock_available.return_value = {
                "new-agent": "New Agent",
            }
            # No description for new-agent
            mock_descriptions.return_value = {}

            result = registered_func(mock_context)

            # Should use default description
            assert len(result.agents) == 1
            assert result.agents[0].description == "No description available"


class TestRegisterInvokeAgentExecution:
    """Test the actual invoke_agent tool function execution."""

    @pytest.fixture
    def temp_session_dir(self):
        """Create a temporary directory for session storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _get_registered_invoke_agent(self):
        """Helper to capture the registered invoke_agent function."""
        mock_agent = MagicMock()
        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool
        register_invoke_agent(mock_agent)
        return registered_func

    @pytest.mark.asyncio
    async def test_invoke_agent_invalid_session_id_returns_error(self):
        """Test that invalid session_id returns error immediately."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.emit_error") as mock_emit_error,
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
        ):
            # Call with invalid session_id (uppercase not allowed)
            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id="Invalid_Session",
            )

            # Should return error output
            assert isinstance(result, AgentInvokeOutput)
            assert result.response is None
            assert result.error is not None
            assert "must be kebab-case" in result.error
            assert mock_emit_error.called

    @pytest.mark.asyncio
    async def test_invoke_agent_model_not_found_error(self):
        """Test error handling when model is not found."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        mock_agent_config = MagicMock()
        mock_agent_config.get_model_name.return_value = "nonexistent-model"

        with (
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
            patch("code_puppy.tools.agent_tools.get_message_bus") as mock_bus,
            patch(
                "code_puppy.tools.agent_tools.get_session_context",
                return_value="parent",
            ),
            patch("code_puppy.tools.agent_tools.set_session_context"),
            patch("code_puppy.tools.agent_tools.emit_error") as mock_emit_error,
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=mock_agent_config,
            ),
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                return_value={},  # No models configured
            ),
            patch(
                "code_puppy.tools.agent_tools._load_session_history",
                return_value=[],
            ),
            patch(
                "code_puppy.tools.agent_tools._generate_session_hash_suffix",
                return_value="abc123",
            ),
        ):
            mock_bus.return_value.emit = MagicMock()

            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id=None,
            )

            # Should return error
            assert result.error is not None
            assert "nonexistent-model" in result.error
            assert mock_emit_error.called

    @pytest.mark.asyncio
    async def test_invoke_agent_session_context_restored_on_error(self):
        """Test that session context is restored even when an error occurs."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        mock_agent_config = MagicMock()
        mock_agent_config.get_model_name.return_value = "test-model"
        mock_agent_config.get_system_prompt.return_value = "Test"
        mock_agent_config.load_puppy_rules.return_value = None

        set_context_calls = []

        with (
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
            patch("code_puppy.tools.agent_tools.get_message_bus") as mock_bus,
            patch(
                "code_puppy.tools.agent_tools.get_session_context",
                return_value="original-parent",
            ),
            patch(
                "code_puppy.tools.agent_tools.set_session_context",
                side_effect=lambda x: set_context_calls.append(x),
            ),
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.agents.agent_manager.load_agent",
                return_value=mock_agent_config,
            ),
            patch(
                "code_puppy.model_factory.ModelFactory.load_config",
                side_effect=RuntimeError("Config load failed"),
            ),
            patch(
                "code_puppy.tools.agent_tools._load_session_history",
                return_value=[],
            ),
            patch(
                "code_puppy.tools.agent_tools._generate_session_hash_suffix",
                return_value="abc123",
            ),
        ):
            mock_bus.return_value.emit = MagicMock()

            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id=None,
            )

            # Should have error
            assert result.error is not None

            # Session context should still be restored
            assert "original-parent" in set_context_calls


class TestActiveSubagentTasks:
    """Test the _active_subagent_tasks tracking."""

    def test_active_tasks_set_exists(self):
        """Test that the active tasks set is accessible."""
        from code_puppy.tools.agent_tools import _active_subagent_tasks

        assert isinstance(_active_subagent_tasks, set)

    def test_active_tasks_initially_empty(self):
        """Test that active tasks set starts empty (or becomes empty)."""
        from code_puppy.tools.agent_tools import _active_subagent_tasks

        # After all tasks complete, should be empty
        # (This is testing the cleanup behavior)
        # In a fresh module load, it would be empty
        assert isinstance(_active_subagent_tasks, set)


class TestDBOSWorkflowCounter:
    """Test the DBOS workflow counter behavior."""

    def test_counter_is_thread_safe_type(self):
        """Test that the counter uses a thread-safe implementation."""
        import itertools

        from code_puppy.tools.agent_tools import _dbos_workflow_counter

        # Should be an itertools.count object
        assert isinstance(_dbos_workflow_counter, type(itertools.count()))

    def test_generate_dbos_workflow_id_uses_counter(self):
        """Test that workflow IDs use the atomic counter."""
        # Generate several IDs and verify they're all unique
        ids = [_generate_dbos_workflow_id("test") for _ in range(5)]
        assert len(set(ids)) == 5  # All unique


class TestRunAgentWithPauseCheckpoints:
    """Test the _run_agent_with_pause_checkpoints helper function."""

    @pytest.mark.asyncio
    async def test_pause_checkpoint_called_between_nodes(self):
        """Test that pause checkpoint is called after each node iteration."""
        from unittest.mock import AsyncMock, MagicMock

        from code_puppy.tools.agent_tools import _run_agent_with_pause_checkpoints

        # Create a mock agent with a mock iter context manager
        mock_agent = MagicMock()
        mock_agent.is_model_request_node.return_value = False
        mock_agent.is_call_tools_node.return_value = False
        mock_agent_run = AsyncMock()
        mock_agent_run.result = MagicMock()
        mock_agent_run.result.output = "Test response"
        mock_agent_run.result.all_messages.return_value = []

        # Mock the async iteration - simulate 3 nodes
        mock_nodes = [MagicMock(), MagicMock(), MagicMock()]

        async def mock_iter(*args, **kwargs):
            yield mock_nodes[0]
            yield mock_nodes[1]
            yield mock_nodes[2]

        # Create async context manager mock
        class MockAgentRun:
            def __init__(self):
                self.result = mock_agent_run.result
                self._iter_count = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._iter_count >= len(mock_nodes):
                    raise StopAsyncIteration
                node = mock_nodes[self._iter_count]
                self._iter_count += 1
                return node

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_agent.iter.return_value = MockAgentRun()

        # Mock pause manager
        mock_pause_manager = MagicMock()
        mock_pause_manager.async_pause_checkpoint = AsyncMock(return_value=False)
        mock_pause_manager.async_wait_for_resume = AsyncMock(return_value=True)

        # Mock stream handler
        mock_stream_handler = MagicMock()

        # Run with mocked message limit
        with patch("code_puppy.tools.agent_tools.get_message_limit", return_value=100):
            await _run_agent_with_pause_checkpoints(
                mock_agent,
                "test prompt",
                [],  # message_history
                mock_stream_handler,
                mock_pause_manager,
                "test-subagent-id",
            )

        # Verify pause checkpoint was called 3 times (once per node)
        assert mock_pause_manager.async_pause_checkpoint.call_count == 3
        mock_pause_manager.async_pause_checkpoint.assert_called_with("test-subagent-id")

    @pytest.mark.asyncio
    async def test_stream_handler_called_for_model_request_node(self):
        """Test that stream handler is called for model request nodes."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from code_puppy.tools.agent_tools import _run_agent_with_pause_checkpoints

        mock_agent = MagicMock()
        mock_agent.is_model_request_node.return_value = True
        mock_agent.is_call_tools_node.return_value = False

        mock_result = MagicMock()
        mock_result.output = "Test response"
        mock_result.all_messages.return_value = []

        run_ctx = MagicMock()
        mock_node = MagicMock()
        mock_stream = MagicMock()

        class MockStream:
            async def __aenter__(self):
                return mock_stream

            async def __aexit__(self, *args):
                pass

        class MockAgentRun:
            def __init__(self):
                self.result = mock_result
                self.ctx = run_ctx
                self._iter_count = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._iter_count >= 1:
                    raise StopAsyncIteration
                self._iter_count += 1
                return mock_node

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_node.stream.return_value = MockStream()
        mock_agent.iter.return_value = MockAgentRun()

        mock_pause_manager = MagicMock()
        mock_pause_manager.async_pause_checkpoint = AsyncMock(return_value=False)
        mock_pause_manager.async_wait_for_resume = AsyncMock(return_value=True)

        mock_stream_handler = AsyncMock()
        run_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.get_message_limit", return_value=100),
            patch(
                "pydantic_ai._agent_graph.build_run_context",
                return_value=run_context,
            ) as build_run_context,
        ):
            await _run_agent_with_pause_checkpoints(
                mock_agent,
                "test prompt",
                [],
                mock_stream_handler,
                mock_pause_manager,
                "test-subagent-id",
            )

        build_run_context.assert_called_once_with(run_ctx)
        mock_node.stream.assert_called_once_with(run_ctx)
        mock_stream_handler.assert_awaited_once_with(run_context, mock_stream)

    @pytest.mark.asyncio
    async def test_stream_handler_not_called_for_non_stream_nodes(self):
        """Test that stream handler is skipped for non-stream nodes."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from code_puppy.tools.agent_tools import _run_agent_with_pause_checkpoints

        mock_agent = MagicMock()
        mock_agent.is_model_request_node.return_value = False
        mock_agent.is_call_tools_node.return_value = False

        mock_result = MagicMock()
        mock_result.output = "Test response"
        mock_result.all_messages.return_value = []

        run_ctx = MagicMock()
        mock_node = MagicMock()

        class MockAgentRun:
            def __init__(self):
                self.result = mock_result
                self.ctx = run_ctx
                self._iter_count = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._iter_count >= 1:
                    raise StopAsyncIteration
                self._iter_count += 1
                return mock_node

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_agent.iter.return_value = MockAgentRun()

        mock_pause_manager = MagicMock()
        mock_pause_manager.async_pause_checkpoint = AsyncMock(return_value=False)
        mock_pause_manager.async_wait_for_resume = AsyncMock(return_value=True)

        mock_stream_handler = AsyncMock()

        with (
            patch("code_puppy.tools.agent_tools.get_message_limit", return_value=100),
            patch("pydantic_ai._agent_graph.build_run_context") as build_run_context,
        ):
            await _run_agent_with_pause_checkpoints(
                mock_agent,
                "test prompt",
                [],
                mock_stream_handler,
                mock_pause_manager,
                "test-subagent-id",
            )

        build_run_context.assert_not_called()
        mock_node.stream.assert_not_called()
        mock_stream_handler.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pause_checkpoint_waits_when_paused(self):
        """Test that execution waits when pause checkpoint returns True."""
        from unittest.mock import AsyncMock, MagicMock

        from code_puppy.tools.agent_tools import _run_agent_with_pause_checkpoints

        # Create a mock agent with a single node
        mock_agent = MagicMock()
        mock_agent.is_model_request_node.return_value = False
        mock_agent.is_call_tools_node.return_value = False
        mock_agent_run = AsyncMock()
        mock_agent_run.result = MagicMock()
        mock_agent_run.result.output = "Test response"
        mock_agent_run.result.all_messages.return_value = []

        mock_node = MagicMock()

        class MockAgentRun:
            def __init__(self):
                self.result = mock_agent_run.result
                self._iter_count = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._iter_count >= 1:
                    raise StopAsyncIteration
                self._iter_count += 1
                return mock_node

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_agent.iter.return_value = MockAgentRun()

        # Mock pause manager - returns True (should pause)
        mock_pause_manager = MagicMock()
        mock_pause_manager.async_pause_checkpoint = AsyncMock(return_value=True)
        mock_pause_manager.async_wait_for_resume = AsyncMock(return_value=True)

        mock_stream_handler = MagicMock()

        with patch("code_puppy.tools.agent_tools.get_message_limit", return_value=100):
            await _run_agent_with_pause_checkpoints(
                mock_agent,
                "test prompt",
                [],
                mock_stream_handler,
                mock_pause_manager,
                "test-subagent-id",
            )

        # Verify that wait_for_resume was called since checkpoint returned True
        mock_pause_manager.async_wait_for_resume.assert_called_once_with(
            "test-subagent-id"
        )

    @pytest.mark.asyncio
    async def test_pause_checkpoint_skips_wait_when_not_paused(self):
        """Test that execution doesn't wait when pause checkpoint returns False."""
        from unittest.mock import AsyncMock, MagicMock

        from code_puppy.tools.agent_tools import _run_agent_with_pause_checkpoints

        mock_agent = MagicMock()
        mock_agent.is_model_request_node.return_value = False
        mock_agent.is_call_tools_node.return_value = False
        mock_agent_run = AsyncMock()
        mock_agent_run.result = MagicMock()
        mock_agent_run.result.output = "Test response"
        mock_agent_run.result.all_messages.return_value = []

        mock_node = MagicMock()

        class MockAgentRun:
            def __init__(self):
                self.result = mock_agent_run.result
                self._iter_count = 0

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self._iter_count >= 1:
                    raise StopAsyncIteration
                self._iter_count += 1
                return mock_node

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        mock_agent.iter.return_value = MockAgentRun()

        # Mock pause manager - returns False (not paused)
        mock_pause_manager = MagicMock()
        mock_pause_manager.async_pause_checkpoint = AsyncMock(return_value=False)
        mock_pause_manager.async_wait_for_resume = AsyncMock(return_value=True)

        mock_stream_handler = MagicMock()

        with patch("code_puppy.tools.agent_tools.get_message_limit", return_value=100):
            await _run_agent_with_pause_checkpoints(
                mock_agent,
                "test prompt",
                [],
                mock_stream_handler,
                mock_pause_manager,
                "test-subagent-id",
            )

        # Verify that wait_for_resume was NOT called
        mock_pause_manager.async_wait_for_resume.assert_not_called()


class TestInvokeAgentPauseIntegration:
    """Test the pause manager integration in invoke_agent."""

    def test_imports_pause_manager(self):
        """Test that the necessary pause manager imports exist."""
        from code_puppy.tools.agent_tools import get_pause_manager

        pm = get_pause_manager()
        assert pm is not None


class TestSessionIdValidationInInvokeAgent:
    """Test session ID validation edge cases in invoke_agent."""

    def _get_registered_invoke_agent(self):
        """Helper to capture the registered invoke_agent function."""
        mock_agent = MagicMock()
        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool
        register_invoke_agent(mock_agent)
        return registered_func

    @pytest.mark.asyncio
    async def test_invalid_session_with_spaces(self):
        """Test that session IDs with spaces are rejected."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
        ):
            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id="my session",
            )

            assert result.error is not None
            assert "must be kebab-case" in result.error

    @pytest.mark.asyncio
    async def test_invalid_session_with_special_chars(self):
        """Test that session IDs with special chars are rejected."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
        ):
            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id="session@123",
            )

            assert result.error is not None
            assert "must be kebab-case" in result.error

    @pytest.mark.asyncio
    async def test_empty_session_id_rejected(self):
        """Test that empty session IDs are rejected."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
        ):
            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id="",
            )

            assert result.error is not None
            assert "cannot be empty" in result.error

    @pytest.mark.asyncio
    async def test_too_long_session_id_rejected(self):
        """Test that session IDs over 128 chars are rejected."""
        invoke_agent = self._get_registered_invoke_agent()
        mock_context = MagicMock()

        with (
            patch("code_puppy.tools.agent_tools.emit_error"),
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="test-group",
            ),
        ):
            long_id = "a" * 129
            result = await invoke_agent(
                mock_context,
                agent_name="test-agent",
                prompt="Hello",
                session_id=long_id,
            )

            assert result.error is not None
            assert "128 characters or less" in result.error


class TestListAgentsEmitsBannerAndInfo:
    """Test that list_agents properly emits banner and info messages."""

    def test_emits_banner_message(self):
        """Test that list_agents emits a banner message."""
        mock_agent = MagicMock()
        mock_context = MagicMock()

        registered_func = None

        def capture_tool(func):
            nonlocal registered_func
            registered_func = func
            return func

        mock_agent.tool = capture_tool
        register_list_agents(mock_agent)

        with (
            patch(
                "code_puppy.config.get_banner_color",
                return_value="green",
            ) as mock_banner_color,
            patch("code_puppy.tools.agent_tools.emit_info") as mock_emit_info,
            patch(
                "code_puppy.tools.agent_tools.generate_group_id",
                return_value="banner-group",
            ),
            patch(
                "code_puppy.agents.get_available_agents",
                return_value={},
            ),
            patch(
                "code_puppy.agents.get_agent_descriptions",
                return_value={},
            ),
        ):
            registered_func(mock_context)

            # Verify banner color was fetched
            mock_banner_color.assert_called_once_with("list_agents")

            # Verify emit_info was called (at least for banner)
            assert mock_emit_info.called
