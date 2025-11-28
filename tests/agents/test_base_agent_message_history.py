"""Tests for BaseAgent message history management methods.

This module tests the following message history methods in BaseAgent:
- get_message_history()
- set_message_history()
- append_to_message_history()
- extend_message_history()
- clear_message_history()
"""

import pytest

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestMessageHistoryManagement:
    """Test suite for BaseAgent message history management methods."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test.

        Uses CodePuppyAgent as a concrete implementation of BaseAgent
        to test the abstract class's message history functionality.
        """
        return CodePuppyAgent()

    def test_get_empty_message_history(self, agent):
        """Test that a new agent has an empty message history.

        Verifies that newly created agents start with no messages,
        ensuring a clean slate for conversation tracking.
        """
        history = agent.get_message_history()
        assert isinstance(history, list)
        assert len(history) == 0
        assert history == []

    def test_set_message_history(self, agent):
        """Test setting the message history with a list of messages.

        Verifies that set_message_history() replaces the entire history
        with the provided list and subsequent get_message_history()
        returns the exact list that was set.
        """
        test_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]

        agent.set_message_history(test_messages)
        retrieved_history = agent.get_message_history()

        assert retrieved_history == test_messages
        assert len(retrieved_history) == 3
        assert retrieved_history[0]["role"] == "user"
        assert retrieved_history[1]["role"] == "assistant"
        assert retrieved_history[2]["content"] == "How are you?"

    def test_set_message_history_empty_list(self, agent):
        """Test setting message history to an empty list.

        Verifies that set_message_history() accepts an empty list
        and properly clears any existing history.
        """
        # First, add some messages
        initial_messages = [{"role": "user", "content": "test"}]
        agent.set_message_history(initial_messages)
        assert len(agent.get_message_history()) == 1

        # Now set to empty list
        agent.set_message_history([])
        assert agent.get_message_history() == []
        assert len(agent.get_message_history()) == 0

    def test_append_to_message_history(self, agent):
        """Test appending a single message to history.

        Verifies that append_to_message_history() adds one message
        to the end of the existing history without replacing it.
        """
        message1 = {"role": "user", "content": "First message"}
        message2 = {"role": "assistant", "content": "First response"}

        agent.append_to_message_history(message1)
        assert len(agent.get_message_history()) == 1
        assert agent.get_message_history()[0] == message1

        agent.append_to_message_history(message2)
        assert len(agent.get_message_history()) == 2
        assert agent.get_message_history()[1] == message2

    def test_append_to_empty_history(self, agent):
        """Test appending to an initially empty history.

        Verifies that append_to_message_history() works correctly
        when the history is empty, creating a single-message history.
        """
        assert len(agent.get_message_history()) == 0

        message = {"role": "user", "content": "First message ever"}
        agent.append_to_message_history(message)

        assert len(agent.get_message_history()) == 1
        assert agent.get_message_history()[0] == message

    def test_extend_message_history(self, agent):
        """Test extending message history with multiple messages.

        Verifies that extend_message_history() adds multiple messages
        to the existing history without replacing it.
        """
        initial_message = {"role": "user", "content": "Starting message"}
        agent.append_to_message_history(initial_message)

        new_messages = [
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Follow-up 1"},
            {"role": "assistant", "content": "Response 2"},
        ]

        agent.extend_message_history(new_messages)

        full_history = agent.get_message_history()
        assert len(full_history) == 4
        assert full_history[0] == initial_message
        assert full_history[1:] == new_messages

    def test_extend_with_empty_list(self, agent):
        """Test extending history with an empty list.

        Verifies that extend_message_history() accepts an empty list
        and doesn't modify the existing history.
        """
        initial_messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Message 2"},
        ]
        agent.set_message_history(initial_messages)

        # Extend with empty list
        agent.extend_message_history([])

        # History should be unchanged
        assert agent.get_message_history() == initial_messages
        assert len(agent.get_message_history()) == 2

    def test_extend_empty_history(self, agent):
        """Test extending an empty history with messages.

        Verifies that extend_message_history() works correctly
        when the history is initially empty.
        """
        assert len(agent.get_message_history()) == 0

        messages_to_add = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Message 2"},
        ]

        agent.extend_message_history(messages_to_add)

        assert agent.get_message_history() == messages_to_add
        assert len(agent.get_message_history()) == 2

    def test_clear_message_history(self, agent):
        """Test clearing all messages from history.

        Verifies that clear_message_history() removes all messages
        and leaves the history empty.
        """
        # Add messages first
        messages = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Message 2"},
            {"role": "user", "content": "Message 3"},
        ]
        agent.set_message_history(messages)
        assert len(agent.get_message_history()) == 3

        # Clear the history
        agent.clear_message_history()

        assert len(agent.get_message_history()) == 0
        assert agent.get_message_history() == []

    def test_clear_empty_history(self, agent):
        """Test clearing an already empty history.

        Verifies that clear_message_history() is idempotent
        and can be called on an empty history safely.
        """
        assert len(agent.get_message_history()) == 0

        # Clear already empty history
        agent.clear_message_history()

        assert len(agent.get_message_history()) == 0
        assert agent.get_message_history() == []

    def test_message_history_multiple_operations(self, agent):
        """Test a sequence of message history operations.

        Verifies that multiple operations (set, append, extend, clear)
        work correctly in sequence and maintain expected state.
        """
        # Start with empty history
        assert len(agent.get_message_history()) == 0

        # Set initial messages
        initial_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        agent.set_message_history(initial_messages)
        assert len(agent.get_message_history()) == 2

        # Append a message
        agent.append_to_message_history({"role": "user", "content": "How are you?"})
        assert len(agent.get_message_history()) == 3

        # Extend with multiple messages
        new_messages = [
            {"role": "assistant", "content": "I'm good!"},
            {"role": "user", "content": "Great!"},
        ]
        agent.extend_message_history(new_messages)
        assert len(agent.get_message_history()) == 5

        # Verify final state
        final_history = agent.get_message_history()
        assert final_history[0]["content"] == "Hello"
        assert final_history[1]["content"] == "Hi"
        assert final_history[2]["content"] == "How are you?"
        assert final_history[3]["content"] == "I'm good!"
        assert final_history[4]["content"] == "Great!"

        # Clear all messages
        agent.clear_message_history()
        assert len(agent.get_message_history()) == 0

    def test_set_overwrites_previous_history(self, agent):
        """Test that set_message_history() completely replaces old history.

        Verifies that calling set_message_history() doesn't append
        to existing history but completely replaces it.
        """
        # Set initial history
        first_history = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Message 2"},
        ]
        agent.set_message_history(first_history)
        assert len(agent.get_message_history()) == 2

        # Set new history
        second_history = [
            {"role": "user", "content": "New Message 1"},
            {"role": "user", "content": "New Message 2"},
            {"role": "user", "content": "New Message 3"},
        ]
        agent.set_message_history(second_history)

        # Should have exactly the new history, not a combination
        assert len(agent.get_message_history()) == 3
        assert agent.get_message_history() == second_history
        assert agent.get_message_history()[0]["content"] == "New Message 1"

    def test_history_preserves_message_content(self, agent):
        """Test that message content is preserved exactly as provided.

        Verifies that the agent doesn't modify, serialize, or alter
        the content of messages stored in the history.
        """
        # Test with various message structures
        messages = [
            {"role": "user", "content": "Simple text"},
            {
                "role": "assistant",
                "content": "Complex structure",
                "metadata": {"timestamp": 12345, "source": "test"},
                "nested": ["item1", "item2"],
            },
            {"role": "user", "content": ""},  # Empty content
        ]

        agent.set_message_history(messages)
        retrieved = agent.get_message_history()

        # Verify exact preservation
        assert retrieved == messages
        assert retrieved[1]["metadata"]["timestamp"] == 12345
        assert retrieved[1]["nested"] == ["item1", "item2"]
        assert retrieved[2]["content"] == ""

    def test_multiple_agents_independent_histories(self):
        """Test that different agent instances maintain independent histories.

        Verifies that message history is instance-specific and
        not shared between different agent instances.
        """
        agent1 = CodePuppyAgent()
        agent2 = CodePuppyAgent()

        messages1 = [{"role": "user", "content": "Agent 1 message"}]
        messages2 = [
            {"role": "user", "content": "Agent 2 message 1"},
            {"role": "assistant", "content": "Agent 2 message 2"},
        ]

        agent1.set_message_history(messages1)
        agent2.set_message_history(messages2)

        # Verify they have different histories
        assert agent1.get_message_history() == messages1
        assert agent2.get_message_history() == messages2
        assert agent1.get_message_history() != agent2.get_message_history()

        # Modify one agent's history
        agent1.append_to_message_history({"role": "assistant", "content": "Response"})

        # Verify the other agent's history is unchanged
        assert len(agent1.get_message_history()) == 2
        assert len(agent2.get_message_history()) == 2
        assert agent2.get_message_history() == messages2
