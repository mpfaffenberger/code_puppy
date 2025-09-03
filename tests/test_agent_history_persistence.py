"""Tests for agent message history persistence across agent switches."""

import unittest
from unittest.mock import patch

from code_puppy.agents.agent_manager import (
    _AGENT_HISTORIES,
    _restore_agent_history,
    _save_agent_history,
    append_to_current_agent_message_history,
    clear_all_agent_histories,
    get_current_agent_message_history,
    set_current_agent,
)
from code_puppy.agents.base_agent import BaseAgent


class MockAgent(BaseAgent):
    """Mock agent for testing."""

    def __init__(self, name: str, display_name: str = None):
        super().__init__()
        self._name = name
        self._display_name = display_name or name.title()

    @property
    def name(self) -> str:
        return self._name

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def description(self) -> str:
        return f"Test agent {self._name}"

    def get_system_prompt(self) -> str:
        return f"You are {self._name}"

    def get_available_tools(self) -> list:
        return []


class TestAgentHistoryPersistence(unittest.TestCase):
    """Test agent message history persistence functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Clear all agent histories before each test
        clear_all_agent_histories()
        global _AGENT_HISTORIES
        _AGENT_HISTORIES.clear()

    def test_save_agent_history(self):
        """Test saving agent history to persistent storage."""
        agent = MockAgent("test-agent")
        agent.append_to_message_history("message 1")
        agent.append_to_message_history("message 2")
        agent.add_compacted_message_hash("hash1")

        _save_agent_history("test-agent", agent)

        # Check that history was saved
        self.assertIn("test-agent", _AGENT_HISTORIES)
        saved_data = _AGENT_HISTORIES["test-agent"]
        self.assertEqual(len(saved_data["message_history"]), 2)
        self.assertEqual(saved_data["message_history"][0], "message 1")
        self.assertEqual(saved_data["message_history"][1], "message 2")
        self.assertIn("hash1", saved_data["compacted_hashes"])

    def test_restore_agent_history(self):
        """Test restoring agent history from persistent storage."""
        # Set up stored history
        _AGENT_HISTORIES["test-agent"] = {
            "message_history": ["restored 1", "restored 2"],
            "compacted_hashes": {"hash2", "hash3"},
        }

        agent = MockAgent("test-agent")
        self.assertEqual(len(agent.get_message_history()), 0)

        _restore_agent_history("test-agent", agent)

        # Check that history was restored
        history = agent.get_message_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0], "restored 1")
        self.assertEqual(history[1], "restored 2")

        compacted_hashes = agent.get_compacted_message_hashes()
        self.assertIn("hash2", compacted_hashes)
        self.assertIn("hash3", compacted_hashes)

    def test_restore_agent_history_no_stored_data(self):
        """Test restoring agent history when no data is stored."""
        agent = MockAgent("new-agent")

        # Should not raise an error when no stored data exists
        _restore_agent_history("new-agent", agent)

        # Agent should still have empty history
        self.assertEqual(len(agent.get_message_history()), 0)
        self.assertEqual(len(agent.get_compacted_message_hashes()), 0)

    @patch("code_puppy.agents.agent_manager.load_agent_config")
    @patch("code_puppy.agents.agent_manager.on_agent_reload")
    @patch("code_puppy.agents.agent_manager.set_config_value")
    @patch("code_puppy.agents.agent_manager._discover_agents")
    @patch("code_puppy.agents.agent_manager._CURRENT_AGENT_CONFIG", None)
    def test_agent_switching_preserves_history(
        self, mock_discover, mock_set_config, mock_on_reload, mock_load_agent
    ):
        """Test that switching agents preserves each agent's history."""
        # Create mock agents
        agent1 = MockAgent("agent1")
        agent2 = MockAgent("agent2")

        # Mock the agent loading
        def mock_load_side_effect(agent_name):
            if agent_name == "agent1":
                return MockAgent("agent1")
            elif agent_name == "agent2":
                return MockAgent("agent2")
            else:
                raise ValueError(f"Unknown agent: {agent_name}")

        mock_load_agent.side_effect = mock_load_side_effect

        # Simulate first agent usage
        with patch("code_puppy.agents.agent_manager._CURRENT_AGENT_CONFIG", agent1):
            # Add some messages to agent1
            append_to_current_agent_message_history("agent1 message 1")
            append_to_current_agent_message_history("agent1 message 2")

            # Verify agent1 has messages
            history1 = get_current_agent_message_history()
            self.assertEqual(len(history1), 2)

        # Switch to agent2
        result = set_current_agent("agent2")
        self.assertTrue(result)

        # Verify agent1's history was saved
        self.assertIn("agent1", _AGENT_HISTORIES)
        saved_data = _AGENT_HISTORIES["agent1"]
        self.assertEqual(len(saved_data["message_history"]), 2)

        # Simulate agent2 usage
        with patch("code_puppy.agents.agent_manager._CURRENT_AGENT_CONFIG", agent2):
            # Add different messages to agent2
            append_to_current_agent_message_history("agent2 message 1")
            append_to_current_agent_message_history("agent2 message 2")
            append_to_current_agent_message_history("agent2 message 3")

            # Verify agent2 has its own messages
            history2 = get_current_agent_message_history()
            self.assertEqual(len(history2), 3)

        # Switch back to agent1
        result = set_current_agent("agent1")
        self.assertTrue(result)

        # Verify agent2's history was saved
        self.assertIn("agent2", _AGENT_HISTORIES)
        saved_data = _AGENT_HISTORIES["agent2"]
        self.assertEqual(len(saved_data["message_history"]), 3)

        # Verify that both agents' histories are preserved separately
        agent1_data = _AGENT_HISTORIES["agent1"]
        agent2_data = _AGENT_HISTORIES["agent2"]

        self.assertEqual(len(agent1_data["message_history"]), 2)
        self.assertEqual(len(agent2_data["message_history"]), 3)

        # Verify content is different
        self.assertIn("agent1 message 1", agent1_data["message_history"])
        self.assertIn("agent2 message 1", agent2_data["message_history"])
        self.assertNotIn("agent2 message 1", agent1_data["message_history"])
        self.assertNotIn("agent1 message 1", agent2_data["message_history"])

    def test_clear_all_agent_histories(self):
        """Test clearing all agent histories."""
        # Set up some stored histories
        _AGENT_HISTORIES["agent1"] = {
            "message_history": ["msg1"],
            "compacted_hashes": {"hash1"},
        }
        _AGENT_HISTORIES["agent2"] = {
            "message_history": ["msg2"],
            "compacted_hashes": {"hash2"},
        }

        self.assertEqual(len(_AGENT_HISTORIES), 2)

        # Clear all histories
        clear_all_agent_histories()

        # Verify all histories are cleared
        self.assertEqual(len(_AGENT_HISTORIES), 0)


if __name__ == "__main__":
    unittest.main()
