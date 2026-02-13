"""Tests for delayed compaction flag behavior in BaseAgent.

This module tests the P0/P1 critical functionality of the delayed compaction
flag system, ensuring the fixes for the following bugs remain stable:

1. BaseAgent.__init__:94 - flag should be instance-level, not global
2. session_commands.py:111 - /compact should reset the flag
3. base_agent.py:761 - should_attempt_delayed_compaction() properly manages flag state

Tests cover:
- Initialization to False for new agent instances
- Setting flag via request_delayed_compaction()
- Flag preservation when tool calls are pending
- Flag reset when it's safe to compact
- Idempotency of multiple requests
"""

from unittest.mock import patch

import pytest

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestCompactionFlags:
    """Test suite for delayed compaction flag management.

    These tests verify that the _delayed_compaction_requested instance variable
    behaves correctly throughout its lifecycle, preventing regression of the
    global-variable bug that caused cross-contamination between sessions.
    """

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test.

        Uses CodePuppyAgent as a concrete implementation of BaseAgent
        to test the abstract class's compaction flag functionality.
        """
        return CodePuppyAgent()

    def test_flag_initialization(self, agent):
        """Flag should initialize to False for new agent instances.

        Regression test for: Instance-level initialization in BaseAgent.__init__:94
        Verifies that _delayed_compaction_requested is always False at startup,
        preventing cross-session contamination that occurred with global flags.
        """
        assert agent._delayed_compaction_requested is False

    def test_request_delayed_compaction_sets_flag(self, agent):
        """request_delayed_compaction() should set flag to True.

        Verifies that calling request_delayed_compaction() properly sets
        the instance flag to True, and logs an informational message.
        """
        with patch("code_puppy.agents.base_agent.emit_info") as mock_emit:
            agent.request_delayed_compaction()

            # Flag should be set
            assert agent._delayed_compaction_requested is True

            # Should have emitted an informational message
            mock_emit.assert_called_once()
            call_str = str(mock_emit.call_args)
            assert "Delayed compaction requested" in call_str or "🔄" in call_str

    def test_should_attempt_delayed_compaction_resets_flag(self, agent):
        """should_attempt_delayed_compaction() clears flag when safe.

        When no pending tool calls exist, should_attempt_delayed_compaction()
        should return True and reset the flag to False. This ensures that
        delayed compaction happens exactly once per request.

        Regression test for: base_agent.py:764 - flag reset logic
        """
        # Set flag to True
        agent._delayed_compaction_requested = True

        # Mock has_pending_tool_calls to return False (safe to compact)
        with patch.object(agent, "has_pending_tool_calls", return_value=False):
            # Call should_attempt_delayed_compaction via get_message_history
            # which is what the actual code does
            result = agent.should_attempt_delayed_compaction()

        # Should return True (safe to compact)
        assert result is True
        # Flag should be reset to False
        assert agent._delayed_compaction_requested is False

    def test_should_attempt_returns_false_when_flag_not_set(self, agent):
        """should_attempt_delayed_compaction() returns False when flag is False.

        When no delayed compaction was requested, should_attempt_delayed_compaction()
        should immediately return False without checking tool calls.
        """
        # Flag should be False initially
        agent._delayed_compaction_requested = False

        with patch.object(agent, "has_pending_tool_calls", return_value=False):
            result = agent.should_attempt_delayed_compaction()

        # Should return False (no request pending)
        assert result is False

        # Flag should remain False
        assert agent._delayed_compaction_requested is False

    def test_should_attempt_returns_false_when_pending_tool_calls(self, agent):
        """should_attempt_delayed_compaction() returns False when tool calls pending.

        When tool calls are pending, the flag should NOT be reset.
        This ensures that delayed compaction waits until all tool calls complete,
        preventing mid-tool-call state corruption.

        Critical regression test for: Proper flag preservation logic
        """
        # Set flag to True
        agent._delayed_compaction_requested = True

        # Mock has_pending_tool_calls to return True (unsafe to compact)
        with patch.object(agent, "has_pending_tool_calls", return_value=True):
            result = agent.should_attempt_delayed_compaction()

        # Should return False (unsafe to compact)
        assert result is False
        # Flag MUST remain True (NOT reset!)
        assert agent._delayed_compaction_requested is True

    def test_multiple_requests_idempotent(self, agent):
        """Multiple request_delayed_compaction() calls are idempotent.

        Calling request_delayed_compaction() multiple times should result
        in the same state: flag is True. No errors, no warnings, no surprises.
        """
        # Call request_delayed_compaction multiple times
        with patch("code_puppy.agents.base_agent.emit_info"):
            agent.request_delayed_compaction()
            agent.request_delayed_compaction()
            agent.request_delayed_compaction()

        # Flag should still be True (not reset, not toggled)
        assert agent._delayed_compaction_requested is True

    def test_request_then_cancel_then_request_again(self, agent):
        """Flag can be set, cleared, and set again safely.

        Tests full lifecycle: request -> clear -> request again.
        Ensures the flag works correctly across multiple cycles.
        """
        # Initial state
        assert agent._delayed_compaction_requested is False

        # First request
        with patch("code_puppy.agents.base_agent.emit_info"):
            agent.request_delayed_compaction()
        assert agent._delayed_compaction_requested is True

        # Check and clear (simulate safe compact)
        with patch.object(agent, "has_pending_tool_calls", return_value=False):
            result = agent.should_attempt_delayed_compaction()
        assert result is True
        assert agent._delayed_compaction_requested is False

        # Second request
        with patch("code_puppy.agents.base_agent.emit_info"):
            agent.request_delayed_compaction()
        assert agent._delayed_compaction_requested is True

    def test_flag_state_survives_multiple_pending_checks(self, agent):
        """Flag persists across multiple should_attempt calls with pending tools.

        When tool calls remain pending over multiple check cycles, the flag
        should not be reset prematurely.
        """
        agent._delayed_compaction_requested = True

        # Check multiple times with pending tool calls
        with patch.object(agent, "has_pending_tool_calls", return_value=True):
            result1 = agent.should_attempt_delayed_compaction()
            result2 = agent.should_attempt_delayed_compaction()
            result3 = agent.should_attempt_delayed_compaction()

        # All checks should return False
        assert result1 is False
        assert result2 is False
        assert result3 is False

        # Flag should STILL be True (never reset)
        assert agent._delayed_compaction_requested is True

    def test_instance_idempotency_different_agents(self):
        """Different agent instances have independent flag states.

        Critial test for: Regression of global variable bug
        Verifies that flag is instance-level, not global. Creating two
        agents and modifying one should not affect the other.
        """
        agent1 = CodePuppyAgent()
        agent2 = CodePuppyAgent()

        # Both start with False
        assert agent1._delayed_compaction_requested is False
        assert agent2._delayed_compaction_requested is False

        # Set flag on agent1
        with patch("code_puppy.agents.base_agent.emit_info"):
            agent1.request_delayed_compaction()

        # agent1 should be True
        assert agent1._delayed_compaction_requested is True
        # agent2 MUST remain False
        assert agent2._delayed_compaction_requested is False

        # Set flag on agent2
        with patch("code_puppy.agents.base_agent.emit_info"):
            agent2.request_delayed_compaction()

        # Both should now be True independently
        assert agent1._delayed_compaction_requested is True
        assert agent2._delayed_compaction_requested is True

        # Reset agent1
        with patch.object(agent1, "has_pending_tool_calls", return_value=False):
            agent1.should_attempt_delayed_compaction()

        # agent1 should be False, but agent2 must remain True
        assert agent1._delayed_compaction_requested is False
        assert agent2._delayed_compaction_requested is True
