"""Tests for error handling in agent_manager.py.

This module tests error paths and edge cases in the agent manager:
- get_agent() with invalid agent names
- load_agent() error handling for missing agents
- Validation edge cases and malformed inputs
- Agent not found scenarios
- Fallback behavior when agents are unavailable

Focuses on ensuring proper exception handling and graceful error recovery.
"""

from unittest.mock import MagicMock, patch

import pytest

from code_puppy.agents.agent_manager import (
    get_current_agent,
    load_agent,
    set_current_agent,
)
from code_puppy.agents.base_agent import BaseAgent


class TestAgentManagerErrors:
    """Test suite for agent manager error handling."""

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_invalid_name(self, mock_discover):
        """Test load_agent with completely invalid agent name."""
        # Mock empty registry (no agents available)
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(
                ValueError, match="Agent 'nonexistent-agent-12345' not found"
            ):
                load_agent("nonexistent-agent-12345")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_empty_string(self, mock_discover):
        """Test load_agent with empty string agent name."""
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(ValueError, match="Agent '' not found"):
                load_agent("")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_none_input(self, mock_discover):
        """Test load_agent with None input."""
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            # This should raise a ValueError when None is not found in registry
            with pytest.raises(ValueError, match="Agent 'None' not found"):
                load_agent(None)

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_whitespace_only(self, mock_discover):
        """Test load_agent with whitespace-only agent name."""
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(ValueError, match="Agent '   ' not found"):
                load_agent("   ")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_special_characters(self, mock_discover):
        """Test load_agent with special characters in agent name."""
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(
                ValueError,
                match=r"Agent 'agent@#\$%\^&\*\(\)' not found and no fallback available",
            ):
                load_agent("agent@#$%^&*()")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_fallback_behavior(self, mock_discover):
        """Test load_agent fallback to code-puppy when requested agent not found."""
        mock_discover.return_value = None

        # Mock registry with only code-puppy available
        mock_agent_class = MagicMock(spec=BaseAgent)
        mock_agent_class.return_value.name = "code-puppy"

        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"code-puppy": mock_agent_class},
        ):
            # Should fallback to code-puppy instead of raising error
            result = load_agent("nonexistent-agent")
            assert result is not None
            mock_agent_class.assert_called_once()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_no_fallback_available(self, mock_discover):
        """Test load_agent when neither requested agent nor fallback is available."""
        mock_discover.return_value = None
        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(
                ValueError,
                match="Agent 'missing-agent' not found and no fallback available",
            ):
                load_agent("missing-agent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_corrupted_registry_entry(self, mock_discover):
        """Test load_agent when registry entry is corrupted."""
        mock_discover.return_value = None

        # Mock registry with corrupted entry (neither class nor string)
        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY", {"bad-agent": 12345}
        ):
            # This should raise an error when trying to instantiate the corrupted entry
            with pytest.raises((TypeError, AttributeError)):
                load_agent("bad-agent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager.get_current_agent_name")
    @patch("code_puppy.agents.agent_manager._CURRENT_AGENT", None)
    def test_get_current_agent_no_fallback(self, mock_get_name, mock_discover):
        """Test get_current_agent when no agents are available at all."""
        mock_get_name.return_value = "nonexistent-agent"
        mock_discover.return_value = None

        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(
                ValueError,
                match="Agent 'nonexistent-agent' not found and no fallback available",
            ):
                get_current_agent()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager._save_session_data")
    def test_set_current_agent_nonexistent(self, mock_save, mock_discover):
        """Test set_current_agent with nonexistent agent name."""
        mock_discover.return_value = None

        # Mock registry with only code-puppy available
        mock_agent_class = MagicMock(spec=BaseAgent)
        mock_agent_class.return_value.name = "code-puppy"
        mock_agent_class.return_value.get_message_history.return_value = []
        mock_agent_class.return_value.set_message_history.return_value = None
        mock_agent_class.return_value.id = "test-id"

        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"code-puppy": mock_agent_class},
        ):
            with patch(
                "code_puppy.agents.agent_manager.get_current_agent"
            ) as mock_current:
                mock_current.return_value = None

                # Should return False when agent not found (but fallback available)
                result = set_current_agent("nonexistent-agent")
                assert result is True  # Returns True because fallback succeeds
                mock_agent_class.assert_called_once()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_very_long_name(self, mock_discover):
        """Test load_agent with extremely long agent name."""
        mock_discover.return_value = None
        long_name = "a" * 1000  # 1000 character agent name

        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(ValueError, match=f"Agent '{long_name}' not found"):
                load_agent(long_name)

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_unicode_characters(self, mock_discover):
        """Test load_agent with unicode characters in agent name."""
        mock_discover.return_value = None
        unicode_name = "🐶-测试-🐕"  # Unicode characters

        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            with pytest.raises(ValueError, match=f"Agent '{unicode_name}' not found"):
                load_agent(unicode_name)

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_case_sensitivity(self, mock_discover):
        """Test that agent names are case sensitive."""
        mock_discover.return_value = None
        mock_agent_class = MagicMock(spec=BaseAgent)
        mock_agent_class.return_value.name = "Code-Puppy"

        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"Code-Puppy": mock_agent_class},
        ):
            # Different case should not match
            with pytest.raises(ValueError, match="Agent 'code-puppy' not found"):
                load_agent("code-puppy")

            # Exact case should work
            result = load_agent("Code-Puppy")
            assert result is not None
            mock_agent_class.assert_called_once()

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_discovery_failure(self, mock_discover):
        """Test load_agent when agent discovery fails."""
        # Mock discovery to raise an exception
        mock_discover.side_effect = Exception("Discovery failed")

        with patch("code_puppy.agents.agent_manager._AGENT_REGISTRY", {}):
            # Should propagate the discovery exception
            with pytest.raises(Exception, match="Discovery failed"):
                load_agent("test-agent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_json_agent_invalid_path(self, mock_discover):
        """Test load_agent when JSON agent path is invalid."""
        mock_discover.return_value = None

        # Mock registry with invalid JSON agent path
        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"json-agent": "/invalid/path/agent.json"},
        ):
            # JSONAgent converts FileNotFoundError to ValueError
            with pytest.raises(ValueError, match="Failed to load JSON agent config"):
                load_agent("json-agent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_instantiation_failure(self, mock_discover):
        """Test load_agent when agent class instantiation fails."""
        mock_discover.return_value = None

        # Mock agent class that fails to instantiate
        mock_agent_class = MagicMock(spec=BaseAgent)
        mock_agent_class.side_effect = RuntimeError("Agent initialization failed")

        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"failing-agent": mock_agent_class},
        ):
            with pytest.raises(RuntimeError, match="Agent initialization failed"):
                load_agent("failing-agent")

    @patch("code_puppy.agents.agent_manager._discover_agents")
    def test_load_agent_malformed_json_path(self, mock_discover):
        """Test load_agent with malformed JSON agent path."""
        mock_discover.return_value = None

        # Mock registry with malformed path (not a string)
        with patch(
            "code_puppy.agents.agent_manager._AGENT_REGISTRY",
            {"bad-json-agent": {"not": "a-string"}},
        ):
            with pytest.raises((TypeError, AttributeError)):
                load_agent("bad-json-agent")
