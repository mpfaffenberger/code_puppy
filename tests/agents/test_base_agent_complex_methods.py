"""Tests for BaseAgent complex methods.

This module tests the following complex methods in BaseAgent:
- message_history_processor()
- truncation()
- split_messages_for_protected_summarization()
- summarize_messages()
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentComplexMethods:
    """Test suite for BaseAgent complex methods with basic coverage."""

    @pytest.fixture
    def agent(self):
        """Create a CodePuppyAgent instance for testing."""
        return CodePuppyAgent()

    @pytest.fixture
    def mock_run_context(self):
        """Create a mock RunContext for testing."""
        ctx = MagicMock(spec=RunContext)
        return ctx

    @pytest.fixture
    def sample_messages(self):
        """Create sample messages for testing."""
        return [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there!")]),
        ]

    def test_message_history_processor_no_compaction(self, agent, mock_run_context):
        """Test message_history_processor with messages under threshold - no compaction needed."""
        # Create simple messages that should be under any reasonable threshold
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there!")]),
        ]

        # Mock the spinner and TUI methods to avoid TUI dependencies
        with patch("code_puppy.agents.base_agent.update_spinner_context"):
            with patch("code_puppy.tui_state.is_tui_mode", return_value=False):
                with patch(
                    "code_puppy.tui_state.get_tui_app_instance", return_value=None
                ):
                    result = agent.message_history_processor(mock_run_context, messages)

                    # Should return some processed messages
                    assert len(result) > 0
                    # Should preserve the basic structure
                    assert all(hasattr(msg, "parts") for msg in result)

    def test_truncation_simple(self, agent):
        """Test truncating messages over limit."""
        # Create a message with very long content to trigger truncation
        long_content = "x" * 100000  # Very long message
        messages = [
            ModelRequest(parts=[TextPart(content=long_content)]),
            ModelResponse(parts=[TextPart(content="Short response")]),
        ]

        result = agent.truncation(messages, protected_tokens=1000)

        # Should return something even if truncated
        assert result is not None
        assert len(result) > 0
        # Should always keep the first message (system prompt equivalent)
        assert len(result) >= 1

    def test_split_messages_for_protected_summarization_basic(self, agent):
        """Test basic message splitting functionality."""
        messages = [
            ModelRequest(parts=[TextPart(content="System message")]),  # System message
            ModelResponse(parts=[TextPart(content="Response 1")]),
            ModelRequest(parts=[TextPart(content="Request 2")]),
            ModelResponse(parts=[TextPart(content="Response 2")]),
        ]

        to_summarize, protected = agent.split_messages_for_protected_summarization(
            messages
        )

        # Should return two tuples
        assert isinstance(to_summarize, list)
        assert isinstance(protected, list)

        # System message should always be protected
        assert len(protected) >= 1
        assert protected[0] == messages[0]

        # Should not split if there are very few messages
        short_messages = [ModelRequest(parts=[TextPart(content="Only system")])]
        to_summarize_short, protected_short = (
            agent.split_messages_for_protected_summarization(short_messages)
        )
        assert len(to_summarize_short) == 0
        assert len(protected_short) == 1

    def test_summarize_messages_with_mock(self, agent):
        """Test summarize_messages with mocked summarization to avoid actual LLM calls."""
        # Test the basic path where nothing needs to be summarized
        messages = [
            ModelRequest(parts=[TextPart(content="System message")]),
            ModelResponse(parts=[TextPart(content="Response 1")]),
        ]

        # Mock the run_summarization_sync function to avoid actual LLM calls
        with patch(
            "code_puppy.agents.base_agent.run_summarization_sync"
        ) as mock_summarize:
            mock_summarize.return_value = [
                ModelResponse(parts=[TextPart(content="Mock summary")])
            ]

            compacted, summarized = agent.summarize_messages(
                messages, with_protection=True
            )

            # Should return compacted messages and summarized source
            assert isinstance(compacted, list)
            assert isinstance(summarized, list)

            # Compacted messages should include the system message
            assert len(compacted) >= 1

            # With simple messages, it should return early without calling summarization
            # because there's nothing to summarize yet
            # This is actually the expected behavior for basic coverage

    def test_summarize_messages_without_protection(self, agent):
        """Test summarize_messages with protection disabled."""
        messages = [
            ModelRequest(parts=[TextPart(content="System message")]),
            ModelResponse(parts=[TextPart(content="Response 1")]),
        ]

        # Mock the run_summarization_sync function
        with patch(
            "code_puppy.agents.base_agent.run_summarization_sync"
        ) as mock_summarize:
            mock_summarize.return_value = [
                ModelResponse(parts=[TextPart(content="Mock summary")])
            ]

            compacted, summarized = agent.summarize_messages(
                messages, with_protection=False
            )

            # Should still return valid results
            assert isinstance(compacted, list)
            assert isinstance(summarized, list)

            # Should have called the summarization function
            mock_summarize.assert_called()

    def test_truncation_edge_cases(self, agent):
        """Test truncation with edge cases."""
        # Test single message (empty list would cause IndexError in the method)
        single_message = [ModelRequest(parts=[TextPart(content="Single message")])]
        result = agent.truncation(single_message, protected_tokens=1000)
        assert len(result) >= 1

        # Test with zero protected tokens
        messages = [
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelResponse(parts=[TextPart(content="Response 1")]),
        ]
        result = agent.truncation(messages, protected_tokens=0)
        assert result is not None
        assert len(result) > 0

    def test_split_messages_protection_behavior(self, agent):
        """Test that message splitting properly protects recent messages."""
        # Create messages with varying lengths to test protection logic
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),  # Will be protected
            ModelResponse(parts=[TextPart(content="Short")]),
            ModelRequest(parts=[TextPart(content="Medium length message")]),
            ModelResponse(parts=[TextPart(content="Another medium response")]),
        ]

        to_summarize, protected = agent.split_messages_for_protected_summarization(
            messages
        )

        # Should always protect the system message
        assert messages[0] in protected

        # Should split into two non-overlapping groups
        for msg in protected:
            assert msg not in to_summarize
        for msg in to_summarize:
            assert msg not in protected

    def test_message_history_processor_with_many_messages(
        self, agent, mock_run_context
    ):
        """Test message history processor with many messages to trigger processing."""
        # Create many messages to ensure some processing happens
        messages = []
        for i in range(20):
            messages.append(ModelRequest(parts=[TextPart(content=f"Request {i}")]))
            messages.append(ModelResponse(parts=[TextPart(content=f"Response {i}")]))

        # Mock dependencies
        with patch("code_puppy.agents.base_agent.update_spinner_context"):
            with patch("code_puppy.tui_state.is_tui_mode", return_value=False):
                with patch(
                    "code_puppy.tui_state.get_tui_app_instance", return_value=None
                ):
                    result = agent.message_history_processor(mock_run_context, messages)

                    # Should return processed messages
                    assert isinstance(result, list)
                    assert len(result) > 0
                    # Should preserve message structure
                    assert all(hasattr(msg, "parts") for msg in result)
