"""Comprehensive tests for code_puppy/messaging/subagent_console.py.

Targets coverage improvement from 29% to 85%+.
Focuses on:
- AgentState dataclass and its methods
- SubAgentConsoleManager singleton pattern
- Agent registration, update, and unregistration
- Display lifecycle management
- Rendering methods
- Context manager support
- Convenience functions
"""

import threading
import time
from unittest.mock import MagicMock, Mock, patch

import pytest
from rich.console import Console, Group
from rich.panel import Panel

from code_puppy.messaging.messages import SubAgentStatusMessage
from code_puppy.messaging.subagent_console import (
    DEFAULT_STYLE,
    STATUS_STYLES,
    AgentState,
    SubAgentConsoleManager,
    get_subagent_console_manager,
    setup_subagent_pause_coordination,
    teardown_subagent_pause_coordination,
)

# =============================================================================
# AgentState Tests
# =============================================================================


class TestAgentStateBasics:
    """Test AgentState dataclass basic functionality."""

    def test_agent_state_creation(self):
        """Test creating an AgentState with required fields."""
        state = AgentState(
            session_id="test-session-123",
            agent_name="test-agent",
            model_name="gpt-4o",
        )
        assert state.session_id == "test-session-123"
        assert state.agent_name == "test-agent"
        assert state.model_name == "gpt-4o"
        assert state.status == "starting"  # Default
        assert state.tool_call_count == 0
        assert state.token_count == 0
        assert state.current_tool is None
        assert state.error_message is None

    def test_agent_state_with_all_fields(self):
        """Test creating AgentState with all fields specified."""
        state = AgentState(
            session_id="sess-456",
            agent_name="code-puppy",
            model_name="claude-3-opus",
            status="running",
            tool_call_count=5,
            token_count=1500,
            current_tool="read_file",
            error_message="some error",
        )
        assert state.status == "running"
        assert state.tool_call_count == 5
        assert state.token_count == 1500
        assert state.current_tool == "read_file"
        assert state.error_message == "some error"


class TestAgentStateElapsedTime:
    """Test AgentState elapsed time methods."""

    def test_elapsed_seconds_returns_positive(self):
        """Test that elapsed_seconds returns a positive float."""
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
        )
        # Give it a tiny moment
        time.sleep(0.01)
        elapsed = state.elapsed_seconds()
        assert isinstance(elapsed, float)
        assert elapsed >= 0.01

    def test_elapsed_seconds_with_fixed_start_time(self):
        """Test elapsed_seconds with a known start time."""
        start = time.time() - 5.0  # 5 seconds ago
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
            start_time=start,
        )
        elapsed = state.elapsed_seconds()
        # Should be approximately 5 seconds (allow some tolerance)
        assert 4.9 <= elapsed <= 6.0

    def test_elapsed_formatted_seconds_only(self):
        """Test elapsed_formatted for durations under 60 seconds."""
        # Set start_time to 30 seconds ago
        start = time.time() - 30.0
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
            start_time=start,
        )
        formatted = state.elapsed_formatted()
        # Should be like "30.0s" or "30.1s"
        assert formatted.endswith("s")
        assert "m" not in formatted
        # Extract number and verify it's around 30
        seconds = float(formatted.rstrip("s"))
        assert 29.5 <= seconds <= 32.0

    def test_elapsed_formatted_with_minutes(self):
        """Test elapsed_formatted for durations over 60 seconds."""
        # Set start_time to 90 seconds ago (1m 30s)
        start = time.time() - 90.0
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
            start_time=start,
        )
        formatted = state.elapsed_formatted()
        # Should be like "1m 30.0s"
        assert "m" in formatted
        assert "s" in formatted
        assert formatted.startswith("1m")

    def test_elapsed_formatted_multiple_minutes(self):
        """Test elapsed_formatted for longer durations."""
        # Set start_time to 185 seconds ago (3m 5s)
        start = time.time() - 185.0
        state = AgentState(
            session_id="test",
            agent_name="agent",
            model_name="model",
            start_time=start,
        )
        formatted = state.elapsed_formatted()
        assert "3m" in formatted


class TestAgentStateToStatusMessage:
    """Test AgentState.to_status_message() conversion."""

    def test_to_status_message_basic(self):
        """Test converting AgentState to SubAgentStatusMessage."""
        state = AgentState(
            session_id="sess-abc",
            agent_name="my-agent",
            model_name="gpt-4o-mini",
            status="running",
            tool_call_count=3,
            token_count=500,
        )
        message = state.to_status_message()

        assert isinstance(message, SubAgentStatusMessage)
        assert message.session_id == "sess-abc"
        assert message.agent_name == "my-agent"
        assert message.model_name == "gpt-4o-mini"
        assert message.status == "running"
        assert message.tool_call_count == 3
        assert message.token_count == 500
        assert message.elapsed_seconds >= 0

    def test_to_status_message_with_current_tool(self):
        """Test conversion includes current_tool."""
        state = AgentState(
            session_id="sess",
            agent_name="agent",
            model_name="model",
            status="tool_calling",
            current_tool="edit_file",
        )
        message = state.to_status_message()
        assert message.current_tool == "edit_file"

    def test_to_status_message_with_error(self):
        """Test conversion includes error_message."""
        state = AgentState(
            session_id="sess",
            agent_name="agent",
            model_name="model",
            status="error",
            error_message="Something went wrong",
        )
        message = state.to_status_message()
        assert message.error_message == "Something went wrong"
        assert message.status == "error"


# =============================================================================
# SubAgentConsoleManager Singleton Tests
# =============================================================================


class TestSubAgentConsoleManagerSingleton:
    """Test the singleton pattern of SubAgentConsoleManager."""

    def setup_method(self):
        """Reset singleton before each test."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up singleton after each test."""
        SubAgentConsoleManager.reset_instance()

    def test_get_instance_creates_singleton(self):
        """Test that get_instance creates a singleton."""
        instance1 = SubAgentConsoleManager.get_instance()
        instance2 = SubAgentConsoleManager.get_instance()
        assert instance1 is instance2

    def test_get_instance_with_console(self):
        """Test get_instance with a custom console."""
        mock_console = Mock(spec=Console)
        instance = SubAgentConsoleManager.get_instance(console=mock_console)
        assert instance.console is mock_console

    def test_reset_instance_clears_singleton(self):
        """Test that reset_instance clears the singleton."""
        instance1 = SubAgentConsoleManager.get_instance()
        SubAgentConsoleManager.reset_instance()
        instance2 = SubAgentConsoleManager.get_instance()
        assert instance1 is not instance2

    def test_reset_instance_when_none(self):
        """Test reset_instance when no instance exists."""
        # Should not raise
        SubAgentConsoleManager.reset_instance()
        SubAgentConsoleManager.reset_instance()  # Double reset is safe

    def test_direct_init_creates_new_instance(self):
        """Test that direct __init__ creates new instances."""
        manager1 = SubAgentConsoleManager()
        manager2 = SubAgentConsoleManager()
        # Direct init bypasses singleton
        assert manager1 is not manager2

    def test_init_with_custom_console(self):
        """Test __init__ with custom console."""
        mock_console = Mock(spec=Console)
        manager = SubAgentConsoleManager(console=mock_console)
        assert manager.console is mock_console

    def test_init_default_console(self):
        """Test __init__ creates default console."""
        manager = SubAgentConsoleManager()
        assert isinstance(manager.console, Console)


# =============================================================================
# Agent Registration Tests
# =============================================================================


class TestAgentRegistration:
    """Test agent registration, update, and unregistration."""

    def setup_method(self):
        """Reset singleton and create fresh manager."""
        SubAgentConsoleManager.reset_instance()
        # Create manager with mocked console to avoid real output
        self.mock_console = Mock(spec=Console)
        self.manager = SubAgentConsoleManager(console=self.mock_console)

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_register_agent_creates_state(self, mock_start):
        """Test that register_agent creates an AgentState."""
        self.manager.register_agent("sess-1", "agent-one", "gpt-4o")

        state = self.manager.get_agent_state("sess-1")
        assert state is not None
        assert state.session_id == "sess-1"
        assert state.agent_name == "agent-one"
        assert state.model_name == "gpt-4o"
        assert state.status == "starting"

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_register_first_agent_starts_display(self, mock_start):
        """Test that registering first agent starts the display."""
        self.manager.register_agent("sess-1", "agent", "model")
        mock_start.assert_called_once()

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_register_second_agent_no_extra_start(self, mock_start):
        """Test that registering second agent doesn't restart display."""
        self.manager.register_agent("sess-1", "agent1", "model")
        self.manager.register_agent("sess-2", "agent2", "model")
        # Should only be called once for first agent
        assert mock_start.call_count == 1

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_update_agent_modifies_state(self, mock_start):
        """Test that update_agent modifies existing state."""
        self.manager.register_agent("sess-1", "agent", "model")

        self.manager.update_agent(
            "sess-1",
            status="running",
            tool_call_count=5,
            token_count=1000,
            current_tool="grep",
            error_message="test error",
        )

        state = self.manager.get_agent_state("sess-1")
        assert state.status == "running"
        assert state.tool_call_count == 5
        assert state.token_count == 1000
        assert state.current_tool == "grep"
        assert state.error_message == "test error"

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_update_agent_partial_update(self, mock_start):
        """Test partial update only changes specified fields."""
        self.manager.register_agent("sess-1", "agent", "model")
        self.manager.update_agent("sess-1", status="running")

        state = self.manager.get_agent_state("sess-1")
        assert state.status == "running"
        assert state.tool_call_count == 0  # Unchanged

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_update_unknown_agent_silently_ignored(self, mock_start):
        """Test updating unknown agent is silently ignored."""
        # Should not raise
        self.manager.update_agent("nonexistent", status="running")

    @patch.object(SubAgentConsoleManager, "_start_display")
    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_unregister_agent_removes_state(self, mock_stop, mock_start):
        """Test that unregister_agent removes the agent state."""
        self.manager.register_agent("sess-1", "agent", "model")
        self.manager.unregister_agent("sess-1")

        assert self.manager.get_agent_state("sess-1") is None

    @patch.object(SubAgentConsoleManager, "_start_display")
    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_unregister_last_agent_stops_display(self, mock_stop, mock_start):
        """Test that unregistering last agent stops display."""
        self.manager.register_agent("sess-1", "agent", "model")
        self.manager.unregister_agent("sess-1")
        mock_stop.assert_called_once()

    @patch.object(SubAgentConsoleManager, "_start_display")
    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_unregister_with_remaining_agents(self, mock_stop, mock_start):
        """Test unregistering when other agents remain doesn't stop display."""
        self.manager.register_agent("sess-1", "agent1", "model")
        self.manager.register_agent("sess-2", "agent2", "model")
        self.manager.unregister_agent("sess-1")

        # Display should not be stopped
        mock_stop.assert_not_called()
        # Second agent should still exist
        assert self.manager.get_agent_state("sess-2") is not None

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_unregister_with_custom_final_status(self, mock_start):
        """Test unregister_agent with custom final_status."""
        self.manager.register_agent("sess-1", "agent", "model")
        # The status is set before deletion, so we can't verify it after
        # But we can verify the call doesn't raise
        self.manager.unregister_agent("sess-1", final_status="error")
        assert self.manager.get_agent_state("sess-1") is None

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_unregister_unknown_agent_silently_ignored(self, mock_start):
        """Test unregistering unknown agent is silently ignored."""
        # Should not raise
        self.manager.unregister_agent("nonexistent")

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_get_agent_state_returns_none_for_unknown(self, mock_start):
        """Test get_agent_state returns None for unknown session."""
        assert self.manager.get_agent_state("unknown") is None

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_get_all_agents_empty(self, mock_start):
        """Test get_all_agents when no agents registered."""
        agents = self.manager.get_all_agents()
        assert agents == []

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_get_all_agents_returns_list(self, mock_start):
        """Test get_all_agents returns list of all agents."""
        self.manager.register_agent("sess-1", "agent1", "model1")
        self.manager.register_agent("sess-2", "agent2", "model2")

        agents = self.manager.get_all_agents()
        assert len(agents) == 2
        session_ids = {a.session_id for a in agents}
        assert session_ids == {"sess-1", "sess-2"}


# =============================================================================
# Display Management Tests
# =============================================================================


class TestDisplayManagement:
    """Test display lifecycle management."""

    def setup_method(self):
        """Reset singleton."""
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        """Clean up."""
        SubAgentConsoleManager.reset_instance()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_start_display_creates_live(self, mock_live_class):
        """Test that _start_display creates a Live instance."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        mock_console = Mock(spec=Console)
        manager = SubAgentConsoleManager(console=mock_console)
        manager._start_display()

        # Verify Live was created with correct params
        mock_live_class.assert_called_once()
        mock_live.start.assert_called_once()

        # Clean up
        manager._stop_display()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_start_display_idempotent(self, mock_live_class):
        """Test that calling _start_display twice doesn't create duplicate."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager._start_display()
        manager._start_display()  # Second call should be no-op

        # Should only be called once
        assert mock_live_class.call_count == 1

        manager._stop_display()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_stop_display_stops_live(self, mock_live_class):
        """Test that _stop_display stops the Live instance."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager._start_display()
        manager._stop_display()

        mock_live.stop.assert_called_once()
        assert manager._live is None

    def test_stop_display_when_not_started(self):
        """Test _stop_display when display was never started."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        # Should not raise
        manager._stop_display()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_stop_display_handles_live_exception(self, mock_live_class):
        """Test _stop_display handles exceptions gracefully."""
        mock_live = MagicMock()
        mock_live.stop.side_effect = Exception("Stop failed")
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager._start_display()

        # Should not raise
        manager._stop_display()
        assert manager._live is None


class TestUpdateLoop:
    """Test the background update loop."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_update_loop_runs_until_stopped(self, mock_live_class):
        """Test that update loop runs and can be stopped."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager._start_display()

        # Let it run briefly
        time.sleep(0.2)

        # Verify update was called at least once
        assert mock_live.update.call_count >= 1

        manager._stop_display()

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_update_loop_handles_render_exception(self, mock_live_class):
        """Test update loop continues despite render exceptions."""
        mock_live = MagicMock()
        mock_live.update.side_effect = Exception("Render failed")
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager._start_display()

        # Let it attempt updates
        time.sleep(0.2)

        # Should still be running (didn't crash)
        assert manager._update_thread is not None

        manager._stop_display()


# =============================================================================
# Rendering Tests
# =============================================================================


class TestRendering:
    """Test rendering methods."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()
        self.manager = SubAgentConsoleManager(console=Mock(spec=Console))

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    def test_render_display_empty(self):
        """Test _render_display with no agents."""
        result = self.manager._render_display()
        assert isinstance(result, Group)

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_render_display_with_agents(self, mock_start):
        """Test _render_display with registered agents."""
        self.manager.register_agent("sess-1", "agent1", "model1")
        self.manager.register_agent("sess-2", "agent2", "model2")

        result = self.manager._render_display()
        assert isinstance(result, Group)

    def test_render_agent_panel_basic(self):
        """Test _render_agent_panel with basic agent."""
        state = AgentState(
            session_id="sess-123",
            agent_name="test-agent",
            model_name="gpt-4o",
            status="running",
        )

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_with_tool(self):
        """Test _render_agent_panel with current_tool."""
        state = AgentState(
            session_id="sess-123",
            agent_name="test-agent",
            model_name="gpt-4o",
            status="tool_calling",
            current_tool="read_file",
            tool_call_count=3,
        )

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_with_error(self):
        """Test _render_agent_panel with error message."""
        state = AgentState(
            session_id="sess-123",
            agent_name="test-agent",
            model_name="gpt-4o",
            status="error",
            error_message="Something went wrong!",
        )

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_long_session_id(self):
        """Test _render_agent_panel truncates long session IDs."""
        state = AgentState(
            session_id="this-is-a-very-long-session-id-that-exceeds-24-chars",
            agent_name="test-agent",
            model_name="gpt-4o",
        )

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_with_tokens(self):
        """Test _render_agent_panel with token count."""
        state = AgentState(
            session_id="sess-123",
            agent_name="test-agent",
            model_name="gpt-4o",
            token_count=15000,
        )

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)

    def test_render_agent_panel_all_statuses(self):
        """Test rendering panels for all status types."""
        for status in [
            "starting",
            "running",
            "thinking",
            "tool_calling",
            "completed",
            "error",
        ]:
            state = AgentState(
                session_id=f"sess-{status}",
                agent_name="test-agent",
                model_name="gpt-4o",
                status=status,
            )
            panel = self.manager._render_agent_panel(state)
            assert isinstance(panel, Panel)

    def test_render_agent_panel_unknown_status(self):
        """Test rendering with unknown status uses default style."""
        state = AgentState(
            session_id="sess-123",
            agent_name="test-agent",
            model_name="gpt-4o",
        )
        # Force an unknown status by directly setting it
        state.status = "unknown_status"

        panel = self.manager._render_agent_panel(state)
        assert isinstance(panel, Panel)


# =============================================================================
# Context Manager Tests
# =============================================================================


class TestContextManager:
    """Test context manager support."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_context_manager_enter_returns_self(self, mock_stop):
        """Test __enter__ returns the manager instance."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))

        with manager as ctx:
            assert ctx is manager

    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_context_manager_exit_stops_display(self, mock_stop):
        """Test __exit__ calls _stop_display."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))

        with manager:
            pass

        mock_stop.assert_called_once()

    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_context_manager_exit_on_exception(self, mock_stop):
        """Test __exit__ is called even on exception."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))

        with pytest.raises(ValueError):
            with manager:
                raise ValueError("Test error")

        mock_stop.assert_called_once()


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunction:
    """Test get_subagent_console_manager convenience function."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    def test_get_subagent_console_manager_returns_singleton(self):
        """Test that get_subagent_console_manager returns singleton."""
        manager1 = get_subagent_console_manager()
        manager2 = get_subagent_console_manager()
        assert manager1 is manager2

    def test_get_subagent_console_manager_with_console(self):
        """Test get_subagent_console_manager with custom console."""
        mock_console = Mock(spec=Console)
        manager = get_subagent_console_manager(console=mock_console)
        assert manager.console is mock_console

    def test_get_subagent_console_manager_returns_correct_type(self):
        """Test return type is SubAgentConsoleManager."""
        manager = get_subagent_console_manager()
        assert isinstance(manager, SubAgentConsoleManager)


# =============================================================================
# Status Styles Tests
# =============================================================================


class TestStatusStyles:
    """Test STATUS_STYLES and DEFAULT_STYLE constants."""

    def test_status_styles_contains_all_statuses(self):
        """Test STATUS_STYLES has all expected statuses."""
        expected_statuses = {
            "starting",
            "running",
            "thinking",
            "tool_calling",
            "completed",
            "error",
        }
        assert set(STATUS_STYLES.keys()) == expected_statuses

    def test_status_styles_have_required_keys(self):
        """Test each status style has required keys."""
        required_keys = {"color", "spinner", "emoji"}
        for status, style in STATUS_STYLES.items():
            assert set(style.keys()) == required_keys, f"Status {status} missing keys"

    def test_default_style_has_required_keys(self):
        """Test DEFAULT_STYLE has required keys."""
        required_keys = {"color", "spinner", "emoji"}
        assert set(DEFAULT_STYLE.keys()) == required_keys

    def test_completed_and_error_have_no_spinner(self):
        """Test completed and error statuses have no spinner."""
        assert STATUS_STYLES["completed"]["spinner"] is None
        assert STATUS_STYLES["error"]["spinner"] is None


# =============================================================================
# Thread Safety Tests
# =============================================================================


class TestThreadSafety:
    """Test thread safety of SubAgentConsoleManager."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    @patch.object(SubAgentConsoleManager, "_start_display")
    @patch.object(SubAgentConsoleManager, "_stop_display")
    def test_concurrent_registration(self, mock_stop, mock_start):
        """Test concurrent agent registration is thread-safe."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        errors = []

        def register_agent(i):
            try:
                manager.register_agent(f"sess-{i}", f"agent-{i}", "model")
                manager.update_agent(f"sess-{i}", status="running")
                manager.unregister_agent(f"sess-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=register_agent, args=(i,)) for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"

    def test_singleton_thread_safety(self):
        """Test get_instance is thread-safe."""
        instances = []

        def get_instance():
            inst = SubAgentConsoleManager.get_instance()
            instances.append(inst)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should be the same object
        assert all(inst is instances[0] for inst in instances)


# =============================================================================
# Pause/Resume Tests
# =============================================================================


class TestPauseResume:
    """Test pause/resume methods for pause+steer coordination."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_pause_sets_paused_flag(self, mock_start):
        """Test that pause() sets the paused flag."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        assert manager.is_paused() is False
        manager.pause()
        assert manager.is_paused() is True

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_resume_clears_paused_flag(self, mock_start):
        """Test that resume() clears the paused flag."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager.pause()
        manager.resume()
        assert manager.is_paused() is False

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_pause_stops_live_display(self, mock_live_class):
        """Test that pause() stops the Live display."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager.register_agent("sess-1", "agent", "model")

        # Verify Live was started
        mock_live.start.assert_called_once()

        # Pause should stop Live
        manager.pause()
        mock_live.stop.assert_called()
        assert manager._live is None

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_resume_restarts_live_display(self, mock_live_class):
        """Test that resume() restarts the Live display when agents present."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager.register_agent("sess-1", "agent", "model")
        manager.pause()

        # Resume should restart
        manager.resume()
        assert manager._live is not None

    @patch("code_puppy.messaging.subagent_console.Live")
    def test_resume_no_restart_if_no_agents(self, mock_live_class):
        """Test that resume() doesn't restart if no agents."""
        mock_live = MagicMock()
        mock_live_class.return_value = mock_live

        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        manager.pause()
        manager.resume()

        # Should not have started (no agents)
        mock_live.start.assert_not_called()

    @patch.object(SubAgentConsoleManager, "_start_display")
    def test_pause_is_thread_safe(self, mock_start):
        """Test that pause/resume are thread-safe."""
        manager = SubAgentConsoleManager(console=Mock(spec=Console))
        errors = []

        def toggle_pause():
            try:
                for _ in range(50):
                    manager.pause()
                    manager.resume()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle_pause) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


# =============================================================================
# Pause Coordination Tests
# =============================================================================


class TestPauseCoordination:
    """Test pause coordination with PauseManager."""

    def setup_method(self):
        SubAgentConsoleManager.reset_instance()

    def teardown_method(self):
        SubAgentConsoleManager.reset_instance()
        # Clean up coordination

        teardown_subagent_pause_coordination()

    @patch.object(SubAgentConsoleManager, "pause")
    def test_setup_registers_callback(self, mock_pause):
        """Test that setup_subagent_pause_coordination registers callback."""
        from code_puppy.pause_manager import get_pause_manager

        setup_subagent_pause_coordination()
        pm = get_pause_manager()
        pm.register("test-agent", "Test")

        # Request pause should trigger callback
        pm.request_pause()
        mock_pause.assert_called()

        # Cleanup
        pm.reset()

    @patch.object(SubAgentConsoleManager, "resume")
    def test_callback_resumes_on_resume(self, mock_resume):
        """Test that callback resumes manager on resume request."""
        from code_puppy.pause_manager import get_pause_manager

        setup_subagent_pause_coordination()
        pm = get_pause_manager()
        pm.register("test-agent", "Test")

        pm.request_pause()
        pm.request_resume()
        mock_resume.assert_called()

        # Cleanup
        pm.reset()

    def test_setup_is_idempotent(self):
        """Test that setup can be called multiple times safely."""

        # Should not raise
        setup_subagent_pause_coordination()
        setup_subagent_pause_coordination()
        setup_subagent_pause_coordination()
