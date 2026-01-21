"""Tests for the ralph_test plugin and new callback hooks."""

import pytest

from code_puppy.callbacks import (
    clear_callbacks,
    get_callbacks,
    on_agent_response_complete,
    on_register_agents,
    on_register_tools,
    register_callback,
)

# Check if BaseAgent can be imported (requires MCP)
try:
    from code_puppy.agents.base_agent import BaseAgent

    HAS_BASE_AGENT = True
except ImportError:
    HAS_BASE_AGENT = False
    BaseAgent = None  # type: ignore

# Check if ralph_test plugin exists
try:
    from code_puppy.plugins import ralph_test  # noqa: F401

    HAS_RALPH_TEST_PLUGIN = True
except ImportError:
    HAS_RALPH_TEST_PLUGIN = False


class TestRegisterToolsCallback:
    """Tests for the register_tools callback hook."""

    def setup_method(self):
        """Clear callbacks before each test."""
        clear_callbacks("register_tools")

    def teardown_method(self):
        """Clear callbacks after each test."""
        clear_callbacks("register_tools")

    def test_register_tools_callback_returns_empty_list_when_no_callbacks(self):
        """Test that on_register_tools returns empty list when no callbacks registered."""
        result = on_register_tools()
        assert result == []

    def test_register_tools_callback_collects_tool_definitions(self):
        """Test that on_register_tools collects tool definitions from callbacks."""

        def mock_register_func(agent):
            pass

        def provide_tools():
            return [{"name": "test_tool", "register_func": mock_register_func}]

        register_callback("register_tools", provide_tools)
        results = on_register_tools()

        assert len(results) == 1
        assert results[0][0]["name"] == "test_tool"
        assert results[0][0]["register_func"] == mock_register_func

    def test_register_tools_callback_handles_multiple_providers(self):
        """Test that multiple tool providers can register."""

        def provide_tools_1():
            return [{"name": "tool1", "register_func": lambda a: None}]

        def provide_tools_2():
            return [{"name": "tool2", "register_func": lambda a: None}]

        register_callback("register_tools", provide_tools_1)
        register_callback("register_tools", provide_tools_2)

        results = on_register_tools()
        assert len(results) == 2

    def test_register_tools_callback_handles_none_return(self):
        """Test that callbacks returning None don't break collection."""

        def provide_nothing():
            return None

        register_callback("register_tools", provide_nothing)
        results = on_register_tools()

        assert len(results) == 1
        assert results[0] is None


class TestRegisterAgentsCallback:
    """Tests for the register_agents callback hook."""

    def setup_method(self):
        """Clear callbacks before each test."""
        clear_callbacks("register_agents")

    def teardown_method(self):
        """Clear callbacks after each test."""
        clear_callbacks("register_agents")

    def test_register_agents_callback_returns_empty_list_when_no_callbacks(self):
        """Test that on_register_agents returns empty list when no callbacks registered."""
        result = on_register_agents()
        assert result == []

    @pytest.mark.skipif(not HAS_BASE_AGENT, reason="BaseAgent requires MCP")
    def test_register_agents_callback_collects_class_based_agents(self):
        """Test registering agents via class."""

        class MockAgent(BaseAgent):
            @property
            def name(self):
                return "mock-agent"

            @property
            def display_name(self):
                return "Mock Agent"

            @property
            def description(self):
                return "A mock agent"

            def get_system_prompt(self):
                return "You are a mock agent."

            def get_available_tools(self):
                return []

        def provide_agents():
            return [{"name": "mock-agent", "class": MockAgent}]

        register_callback("register_agents", provide_agents)
        results = on_register_agents()

        assert len(results) == 1
        assert results[0][0]["name"] == "mock-agent"
        assert results[0][0]["class"] == MockAgent

    def test_register_agents_callback_collects_json_path_agents(self):
        """Test registering agents via JSON path."""

        def provide_agents():
            return [{"name": "json-agent", "json_path": "/path/to/agent.json"}]

        register_callback("register_agents", provide_agents)
        results = on_register_agents()

        assert len(results) == 1
        assert results[0][0]["name"] == "json-agent"
        assert results[0][0]["json_path"] == "/path/to/agent.json"


class TestAgentResponseCompleteCallback:
    """Tests for the agent_response_complete callback hook."""

    def setup_method(self):
        """Clear callbacks before each test."""
        clear_callbacks("agent_response_complete")

    def teardown_method(self):
        """Clear callbacks after each test."""
        clear_callbacks("agent_response_complete")

    @pytest.mark.asyncio
    async def test_agent_response_complete_returns_empty_when_no_callbacks(self):
        """Test that on_agent_response_complete returns empty list when no callbacks."""
        results = await on_agent_response_complete(
            agent_name="test-agent",
            response_text="Hello world",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_agent_response_complete_triggers_async_callbacks(self):
        """Test that async callbacks are properly awaited."""
        callback_data = {}

        async def capture_completion(
            agent_name, response_text, session_id=None, metadata=None
        ):
            callback_data["agent_name"] = agent_name
            callback_data["response_text"] = response_text
            callback_data["session_id"] = session_id
            callback_data["metadata"] = metadata

        register_callback("agent_response_complete", capture_completion)

        await on_agent_response_complete(
            agent_name="my-agent",
            response_text="Task completed",
            session_id="session-123",
            metadata={"model": "gpt-4"},
        )

        assert callback_data["agent_name"] == "my-agent"
        assert callback_data["response_text"] == "Task completed"
        assert callback_data["session_id"] == "session-123"
        assert callback_data["metadata"] == {"model": "gpt-4"}

    @pytest.mark.asyncio
    async def test_agent_response_complete_triggers_sync_callbacks(self):
        """Test that sync callbacks also work."""
        callback_data = {}

        def capture_completion(
            agent_name, response_text, session_id=None, metadata=None
        ):
            callback_data["agent_name"] = agent_name
            callback_data["response_text"] = response_text

        register_callback("agent_response_complete", capture_completion)

        await on_agent_response_complete(
            agent_name="sync-agent",
            response_text="Sync response",
        )

        assert callback_data["agent_name"] == "sync-agent"
        assert callback_data["response_text"] == "Sync response"

    @pytest.mark.asyncio
    async def test_agent_response_complete_detects_completion_signal(self):
        """Test detecting Ralph's COMPLETE signal in response."""
        detected_complete = []

        async def check_for_complete(
            agent_name, response_text, session_id=None, metadata=None
        ):
            if response_text and "<promise>COMPLETE</promise>" in response_text:
                detected_complete.append(agent_name)

        register_callback("agent_response_complete", check_for_complete)

        # Response without completion signal
        await on_agent_response_complete(
            agent_name="agent1",
            response_text="Still working...",
        )
        assert len(detected_complete) == 0

        # Response WITH completion signal
        await on_agent_response_complete(
            agent_name="agent2",
            response_text="All done! <promise>COMPLETE</promise>",
        )
        assert len(detected_complete) == 1
        assert detected_complete[0] == "agent2"


@pytest.mark.skipif(
    not HAS_BASE_AGENT or not HAS_RALPH_TEST_PLUGIN,
    reason="Plugin requires BaseAgent and ralph_test plugin to be installed",
)
class TestRalphTestPluginIntegration:
    """Integration tests for the ralph_test plugin."""

    def test_ralph_test_plugin_loads_successfully(self):
        """Test that the ralph_test plugin loads without errors."""
        # Import should trigger callback registration
        from code_puppy.plugins.ralph_test import register_callbacks  # noqa: F401

        # Verify callbacks were registered
        tools_callbacks = get_callbacks("register_tools")
        agents_callbacks = get_callbacks("register_agents")
        complete_callbacks = get_callbacks("agent_response_complete")

        # Check that our plugin's callbacks are in there
        assert any(
            cb.__module__ == "code_puppy.plugins.ralph_test.register_callbacks"
            for cb in tools_callbacks
        )
        assert any(
            cb.__module__ == "code_puppy.plugins.ralph_test.register_callbacks"
            for cb in agents_callbacks
        )
        assert any(
            cb.__module__ == "code_puppy.plugins.ralph_test.register_callbacks"
            for cb in complete_callbacks
        )

    def test_ralph_test_plugin_provides_dummy_tool(self):
        """Test that the plugin provides the dummy echo tool."""
        from code_puppy.plugins.ralph_test.register_callbacks import _provide_tools

        tools = _provide_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "ralph_test_echo"
        assert callable(tools[0]["register_func"])

    def test_ralph_test_plugin_provides_dummy_agent(self):
        """Test that the plugin provides the dummy agent."""
        from code_puppy.plugins.ralph_test.register_callbacks import (
            DummyRalphTestAgent,
            _provide_agents,
        )

        agents = _provide_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "ralph-test-dummy"
        assert agents[0]["class"] == DummyRalphTestAgent

    def test_dummy_agent_has_correct_properties(self):
        """Test that the dummy agent is properly configured."""
        from code_puppy.plugins.ralph_test.register_callbacks import DummyRalphTestAgent

        agent = DummyRalphTestAgent()
        assert agent.name == "ralph-test-dummy"
        assert agent.display_name == "Ralph Test Dummy 🧪"
        assert "test" in agent.description.lower()
        assert "ralph_test_echo" in agent.get_available_tools()

    @pytest.mark.asyncio
    async def test_ralph_test_plugin_logs_completions(self):
        """Test that the plugin logs agent completions."""
        from code_puppy.plugins.ralph_test.register_callbacks import (
            _on_agent_complete,
            clear_response_log,
            get_response_log,
        )

        clear_response_log()

        await _on_agent_complete(
            agent_name="test-agent",
            response_text="Test response",
            session_id="test-session",
            metadata={"model": "test-model"},
        )

        log = get_response_log()
        assert len(log) == 1
        assert log[0]["agent_name"] == "test-agent"
        assert log[0]["session_id"] == "test-session"
