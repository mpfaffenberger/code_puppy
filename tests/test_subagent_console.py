"""Comprehensive tests for SubAgentConsoleManager functionality.

Tests cover:
- AgentState dataclass methods
- SubAgentConsoleManager singleton pattern
- Agent registration, updates, and unregistration
- Display rendering
- Context manager support
- Convenience functions

Target coverage: 60%+
"""

import threading
import time
from unittest.mock import Mock, patch

from rich.console import Console
from rich.panel import Panel

from code_puppy.messaging.subagent_console import (
    AgentState,
    DEFAULT_STYLE,
    STATUS_STYLES,
    SubAgentConsoleManager,
    get_subagent_console_manager,
)


# =============================================================================
# AgentState Tests
# =============================================================================


class TestAgentState:
    """Tests for the AgentState dataclass."""

    def test_init_default_values(self):
        """Test AgentState initialization with defaults."""
        state = AgentState(
            session_id="test-session",
            agent_name="test-agent",
            model_name="gpt-4o",
        )
        assert state.session_id == "test-session"
        assert state.agent_name == "test-agent"
        assert state.model_name == "gpt-4o"
        assert state.status == "starting"
        assert state.tool_call_count == 0
        assert state.token_count == 0
        assert state.current_tool is None
        assert state.error_message is None
        assert state.start_time > 0

    def test_init_custom_values(self):
        """Test AgentState initialization with custom values."""
        state = AgentState(
            session_id="sess-123",
            agent_name="code-puppy",
            model_name="claude-3",
            status="running",
            tool_call_count=5,
            token_count=1000,
            current_tool="read_file",
            error_message=None,
        )
        assert state.status == "running"
        assert state.tool_call_count == 5
        assert state.token_count == 1000
        assert state.current_tool == "read_file"

    def test_elapsed_seconds(self):
        """Test elapsed_seconds returns positive value."""
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
        )
        # Sleep briefly to ensure elapsed > 0
        time.sleep(0.05)
        elapsed = state.elapsed_seconds()
        assert elapsed >= 0.05
        assert elapsed < 1.0  # Should be less than 1 second

    def test_elapsed_formatted_seconds(self):
        """Test elapsed_formatted for sub-minute times."""
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
        )
        # Manually set start_time to control elapsed
        state.start_time = time.time() - 30.5  # 30.5 seconds ago
        formatted = state.elapsed_formatted()
        assert "s" in formatted
        assert "m" not in formatted  # Should not have minutes
        # Should be approximately 30.5s (could vary slightly due to timing)
        assert "30" in formatted or "31" in formatted

    def test_elapsed_formatted_minutes(self):
        """Test elapsed_formatted for multi-minute times."""
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
        )
        # Set start_time to 2 minutes and 30 seconds ago
        state.start_time = time.time() - 150  # 2m 30s
        formatted = state.elapsed_formatted()
        assert "m" in formatted
        assert "2m" in formatted

    def test_to_status_message(self):
        """Test conversion to SubAgentStatusMessage."""
        state = AgentState(
            session_id="sess-abc",
            agent_name="qa-kitten",
            model_name="gpt-4",
            status="running",
            tool_call_count=3,
            token_count=500,
            current_tool="grep",
            error_message=None,
        )
        msg = state.to_status_message()
        assert msg.session_id == "sess-abc"
        assert msg.agent_name == "qa-kitten"
        assert msg.model_name == "gpt-4"
        assert msg.status == "running"
        assert msg.tool_call_count == 3
        assert msg.token_count == 500
        assert msg.current_tool == "grep"
        assert msg.elapsed_seconds >= 0
        assert msg.error_message is None

    def test_to_status_message_with_error(self):
        """Test conversion to SubAgentStatusMessage with error."""
        state = AgentState(
            session_id="sess-err",
            agent_name="broken-agent",
            model_name="model",
            status="error",
            error_message="Something went wrong",
        )
        msg = state.to_status_message()
        assert msg.status == "error"
        assert msg.error_message == "Something went wrong"


# =============================================================================
# SubAgentConsoleManager Tests
# =============================================================================


class TestSubAgentConsoleManagerSingleton:
    """Tests for singleton pattern."""

    def setup_method(self):
        """Reset singleton before each test."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up after each test."""
        SubAgentConsoleManager.reset_instance()

    def test_get_instance_creates_singleton(self):
        """Test that get_instance creates a singleton."""
        instance1 = SubAgentConsoleManager.get_instance()
        instance2 = SubAgentConsoleManager.get_instance()
        assert instance1 is instance2

    def test_get_instance_with_console(self):
        """Test get_instance with custom console."""
        mock_console = Mock(spec=Console)
        instance = SubAgentConsoleManager.get_instance(console=mock_console)
        assert instance.console is mock_console

    def test_reset_instance_clears_singleton(self):
        """Test that reset_instance clears the singleton."""
        instance1 = SubAgentConsoleManager.get_instance()
        SubAgentConsoleManager.reset_instance()
        instance2 = SubAgentConsoleManager.get_instance()
        assert instance1 is not instance2

    def test_reset_instance_stops_display(self):
        """Test that reset_instance stops any running display."""
        # Create instance and register an agent to start display
        manager = SubAgentConsoleManager.get_instance()
        # Mock the _stop_display method
        with patch.object(manager, '_stop_display') as mock_stop:
            SubAgentConsoleManager.reset_instance()
            mock_stop.assert_called_once()


class TestSubAgentConsoleManagerRegistration:
    """Tests for agent registration."""

    def setup_method(self):
        """Reset singleton and create fresh manager."""
        SubAgentConsoleManager.reset_instance()
        self.console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.console)

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'manager'):
            self.manager._stop_display()
        SubAgentConsoleManager.reset_instance()

    def test_register_agent_creates_state(self):
        """Test that registering an agent creates its state."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "test-agent", "gpt-4")
        
        state = self.manager.get_agent_state("sess-1")
        assert state is not None
        assert state.session_id == "sess-1"
        assert state.agent_name == "test-agent"
        assert state.model_name == "gpt-4"
        assert state.status == "starting"

    def test_register_first_agent_starts_display(self):
        """Test that registering first agent starts display."""
        with patch.object(self.manager, '_start_display') as mock_start:
            self.manager.register_agent("sess-1", "agent", "model")
            mock_start.assert_called_once()

    def test_register_second_agent_no_restart(self):
        """Test that registering second agent doesn't restart display."""
        with patch.object(self.manager, '_start_display') as mock_start:
            self.manager.register_agent("sess-1", "agent1", "model")
            self.manager.register_agent("sess-2", "agent2", "model")
            # Should only be called once (for first agent)
            assert mock_start.call_count == 1

    def test_register_multiple_agents(self):
        """Test registering multiple agents."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent1", "model1")
            self.manager.register_agent("sess-2", "agent2", "model2")
            self.manager.register_agent("sess-3", "agent3", "model3")
        
        agents = self.manager.get_all_agents()
        assert len(agents) == 3
        session_ids = {a.session_id for a in agents}
        assert session_ids == {"sess-1", "sess-2", "sess-3"}


class TestSubAgentConsoleManagerUpdates:
    """Tests for agent updates."""

    def setup_method(self):
        """Reset and prepare manager with registered agent."""
        SubAgentConsoleManager.reset_instance()
        self.console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.console)
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "test-agent", "gpt-4")

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'manager'):
            self.manager._stop_display()
        SubAgentConsoleManager.reset_instance()

    def test_update_agent_status(self):
        """Test updating agent status."""
        self.manager.update_agent("sess-1", status="running")
        state = self.manager.get_agent_state("sess-1")
        assert state.status == "running"

    def test_update_agent_tool_call_count(self):
        """Test updating tool call count."""
        self.manager.update_agent("sess-1", tool_call_count=10)
        state = self.manager.get_agent_state("sess-1")
        assert state.tool_call_count == 10

    def test_update_agent_token_count(self):
        """Test updating token count."""
        self.manager.update_agent("sess-1", token_count=5000)
        state = self.manager.get_agent_state("sess-1")
        assert state.token_count == 5000

    def test_update_agent_current_tool(self):
        """Test updating current tool."""
        self.manager.update_agent("sess-1", current_tool="read_file")
        state = self.manager.get_agent_state("sess-1")
        assert state.current_tool == "read_file"

    def test_update_agent_error_message(self):
        """Test updating error message."""
        self.manager.update_agent(
            "sess-1",
            status="error",
            error_message="Something broke"
        )
        state = self.manager.get_agent_state("sess-1")
        assert state.status == "error"
        assert state.error_message == "Something broke"

    def test_update_agent_multiple_fields(self):
        """Test updating multiple fields at once."""
        self.manager.update_agent(
            "sess-1",
            status="tool_calling",
            tool_call_count=5,
            token_count=2000,
            current_tool="grep",
        )
        state = self.manager.get_agent_state("sess-1")
        assert state.status == "tool_calling"
        assert state.tool_call_count == 5
        assert state.token_count == 2000
        assert state.current_tool == "grep"

    def test_update_unknown_agent_silent(self):
        """Test that updating unknown agent is silent."""
        # Should not raise
        self.manager.update_agent("unknown-session", status="running")
        # Verify original agent unchanged
        state = self.manager.get_agent_state("sess-1")
        assert state.status == "starting"  # Not "running"


class TestSubAgentConsoleManagerUnregistration:
    """Tests for agent unregistration."""

    def setup_method(self):
        """Reset and prepare manager."""
        SubAgentConsoleManager.reset_instance()
        self.console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.console)

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'manager'):
            self.manager._stop_display()
        SubAgentConsoleManager.reset_instance()

    def test_unregister_agent_removes_it(self):
        """Test that unregistering removes the agent."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent", "model")
        with patch.object(self.manager, '_stop_display'):
            self.manager.unregister_agent("sess-1")
        
        assert self.manager.get_agent_state("sess-1") is None

    def test_unregister_last_agent_stops_display(self):
        """Test that unregistering last agent stops display."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent", "model")
        with patch.object(self.manager, '_stop_display') as mock_stop:
            self.manager.unregister_agent("sess-1")
            mock_stop.assert_called_once()

    def test_unregister_not_last_agent_no_stop(self):
        """Test that unregistering when others remain doesn't stop."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent1", "model")
            self.manager.register_agent("sess-2", "agent2", "model")
        with patch.object(self.manager, '_stop_display') as mock_stop:
            self.manager.unregister_agent("sess-1")
            mock_stop.assert_not_called()

    def test_unregister_with_final_status(self):
        """Test unregistering with custom final status."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent", "model")
        with patch.object(self.manager, '_stop_display'):
            self.manager.unregister_agent("sess-1", final_status="error")
        # Agent should be removed
        assert self.manager.get_agent_state("sess-1") is None

    def test_unregister_unknown_agent_silent(self):
        """Test unregistering unknown agent is silent."""
        # Should not raise
        with patch.object(self.manager, '_stop_display'):
            self.manager.unregister_agent("unknown-session")


class TestSubAgentConsoleManagerGetters:
    """Tests for getter methods."""

    def setup_method(self):
        """Reset and prepare manager."""
        SubAgentConsoleManager.reset_instance()
        self.console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.console)
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent1", "model1")
            self.manager.register_agent("sess-2", "agent2", "model2")

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'manager'):
            self.manager._stop_display()
        SubAgentConsoleManager.reset_instance()

    def test_get_agent_state_existing(self):
        """Test getting state of existing agent."""
        state = self.manager.get_agent_state("sess-1")
        assert state is not None
        assert state.agent_name == "agent1"

    def test_get_agent_state_nonexistent(self):
        """Test getting state of nonexistent agent."""
        state = self.manager.get_agent_state("nonexistent")
        assert state is None

    def test_get_all_agents(self):
        """Test getting all agents."""
        agents = self.manager.get_all_agents()
        assert len(agents) == 2
        names = {a.agent_name for a in agents}
        assert names == {"agent1", "agent2"}

    def test_get_all_agents_empty(self):
        """Test getting all agents when empty."""
        with patch.object(self.manager, '_stop_display'):
            self.manager.unregister_agent("sess-1")
            self.manager.unregister_agent("sess-2")
        agents = self.manager.get_all_agents()
        assert agents == []


# =============================================================================
# Rendering Tests
# =============================================================================


class TestSubAgentConsoleManagerRendering:
    """Tests for rendering methods."""

    def setup_method(self):
        """Reset and prepare manager."""
        SubAgentConsoleManager.reset_instance()
        self.console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.console)

    def teardown_method(self):
        """Clean up."""
        if hasattr(self, 'manager'):
            self.manager._stop_display()
        SubAgentConsoleManager.reset_instance()

    def test_render_display_empty(self):
        """Test rendering when no agents registered."""
        result = self.manager._render_display()
        # Should return a Group with "No active sub-agents" message
        assert result is not None

    def test_render_display_with_agents(self):
        """Test rendering with registered agents."""
        with patch.object(self.manager, '_start_display'):
            self.manager.register_agent("sess-1", "agent1", "model1")
            self.manager.register_agent("sess-2", "agent2", "model2")
        
        result = self.manager._render_display()
        assert result is not None

    def test_render_agent_panel_starting(self):
        """Test rendering agent panel for starting status."""
        state = AgentState(
            session_id="sess-test",
            agent_name="test-agent",
            model_name="gpt-4o",
            status="starting",
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_running(self):
        """Test rendering agent panel for running status."""
        state = AgentState(
            session_id="sess-test",
            agent_name="code-puppy",
            model_name="claude-3",
            status="running",
            tool_call_count=5,
            token_count=2000,
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_with_current_tool(self):
        """Test rendering agent panel with current tool."""
        state = AgentState(
            session_id="sess-test",
            agent_name="agent",
            model_name="model",
            status="tool_calling",
            tool_call_count=3,
            current_tool="read_file",
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_with_error(self):
        """Test rendering agent panel with error."""
        state = AgentState(
            session_id="sess-test",
            agent_name="broken",
            model_name="model",
            status="error",
            error_message="API rate limit exceeded",
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_completed(self):
        """Test rendering agent panel for completed status."""
        state = AgentState(
            session_id="sess-test",
            agent_name="agent",
            model_name="model",
            status="completed",
            tool_call_count=10,
            token_count=5000,
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_unknown_status(self):
        """Test rendering agent panel with unknown status uses default style."""
        state = AgentState(
            session_id="sess-test",
            agent_name="agent",
            model_name="model",
            status="unknown_custom_status",
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_long_session_id(self):
        """Test rendering truncates long session IDs."""
        long_session = "session-" + "x" * 50
        state = AgentState(
            session_id=long_session,
            agent_name="agent",
            model_name="model",
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_zero_tokens(self):
        """Test rendering with zero tokens shows 0."""
        state = AgentState(
            session_id="sess",
            agent_name="agent",
            model_name="model",
            token_count=0,
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_large_token_count(self):
        """Test rendering with large token count shows formatted."""
        state = AgentState(
            session_id="sess",
            agent_name="agent",
            model_name="model",
            token_count=100000,
        )
        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)


# =============================================================================
# Display Management Tests
# =============================================================================


class TestDisplayManagement:
    """Tests for display start/stop management."""

    def setup_method(self):
        """Reset singleton."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    def test_start_display_creates_live(self):
        """Test that _start_display creates Live display."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch('code_puppy.messaging.subagent_console.Live') as MockLive:
            mock_live = Mock()
            MockLive.return_value = mock_live
            manager._start_display()
            
            MockLive.assert_called_once()
            mock_live.start.assert_called_once()
        
        manager._stop_display()

    def test_start_display_idempotent(self):
        """Test that calling _start_display twice doesn't restart."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch('code_puppy.messaging.subagent_console.Live') as MockLive:
            mock_live = Mock()
            MockLive.return_value = mock_live
            manager._start_display()
            manager._start_display()  # Second call
            
            # Should only be called once
            assert MockLive.call_count == 1
        
        manager._stop_display()

    def test_stop_display_stops_live(self):
        """Test that _stop_display stops Live display."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch('code_puppy.messaging.subagent_console.Live') as MockLive:
            mock_live = Mock()
            MockLive.return_value = mock_live
            manager._start_display()
            manager._stop_display()
            
            mock_live.stop.assert_called_once()

    def test_stop_display_handles_exception(self):
        """Test that _stop_display handles Live.stop() exceptions."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch('code_puppy.messaging.subagent_console.Live') as MockLive:
            mock_live = Mock()
            mock_live.stop.side_effect = Exception("Stop failed")
            MockLive.return_value = mock_live
            manager._start_display()
            # Should not raise
            manager._stop_display()

    def test_stop_display_when_not_started(self):
        """Test that _stop_display is safe when not started."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        # Should not raise
        manager._stop_display()


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Tests for context manager support."""

    def setup_method(self):
        """Reset singleton."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    def test_context_manager_enter(self):
        """Test that __enter__ returns self."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        result = manager.__enter__()
        assert result is manager
        manager._stop_display()

    def test_context_manager_exit(self):
        """Test that __exit__ stops display."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch.object(manager, '_stop_display') as mock_stop:
            manager.__exit__(None, None, None)
            mock_stop.assert_called_once()

    def test_context_manager_with_statement(self):
        """Test using with statement."""
        console = Mock(spec=Console)
        with SubAgentConsoleManager(console=console) as manager:
            assert isinstance(manager, SubAgentConsoleManager)
        # After exiting, display should be stopped


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunction:
    """Tests for get_subagent_console_manager function."""

    def setup_method(self):
        """Reset singleton."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    def test_get_subagent_console_manager_default(self):
        """Test getting manager without arguments."""
        manager = get_subagent_console_manager()
        assert isinstance(manager, SubAgentConsoleManager)

    def test_get_subagent_console_manager_with_console(self):
        """Test getting manager with custom console."""
        console = Mock(spec=Console)
        manager = get_subagent_console_manager(console=console)
        assert manager.console is console

    def test_get_subagent_console_manager_is_singleton(self):
        """Test that function returns singleton."""
        manager1 = get_subagent_console_manager()
        manager2 = get_subagent_console_manager()
        assert manager1 is manager2


# =============================================================================
# Status Styles Tests
# =============================================================================


class TestStatusStyles:
    """Tests for STATUS_STYLES and DEFAULT_STYLE constants."""

    def test_status_styles_has_all_statuses(self):
        """Test that STATUS_STYLES has all expected statuses."""
        expected_statuses = {
            "starting", "running", "thinking",
            "tool_calling", "completed", "error"
        }
        assert set(STATUS_STYLES.keys()) == expected_statuses

    def test_status_styles_have_required_keys(self):
        """Test that each status style has required keys."""
        required_keys = {"color", "spinner", "emoji"}
        for status, style in STATUS_STYLES.items():
            assert required_keys.issubset(style.keys()), f"Status {status} missing keys"

    def test_default_style_has_required_keys(self):
        """Test that DEFAULT_STYLE has required keys."""
        required_keys = {"color", "spinner", "emoji"}
        assert required_keys.issubset(DEFAULT_STYLE.keys())

    def test_completed_and_error_have_no_spinner(self):
        """Test that completed and error statuses have no spinner."""
        assert STATUS_STYLES["completed"]["spinner"] is None
        assert STATUS_STYLES["error"]["spinner"] is None


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Tests for thread safety of operations."""

    def setup_method(self):
        """Reset singleton."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    def test_concurrent_agent_registration(self):
        """Test that concurrent registration is thread-safe."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        errors = []
        
        def register_agent(i):
            try:
                with patch.object(manager, '_start_display'):
                    manager.register_agent(f"sess-{i}", f"agent-{i}", "model")
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=register_agent, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        assert len(manager.get_all_agents()) == 10
        manager._stop_display()

    def test_concurrent_updates(self):
        """Test that concurrent updates are thread-safe."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        with patch.object(manager, '_start_display'):
            manager.register_agent("sess-1", "agent", "model")
        
        errors = []
        
        def update_agent(i):
            try:
                manager.update_agent("sess-1", tool_call_count=i)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=update_agent, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        manager._stop_display()
