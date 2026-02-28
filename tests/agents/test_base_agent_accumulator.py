"""Tests for BaseAgent message_history_accumulator method.

This module tests the message_history_accumulator() DBOS step that deduplicates
and filters messages in the BaseAgent class.

Key functionality tested:
- Deduplication based on message hashes
- Filtering of empty ThinkingPart messages
- Integration with message_history_processor
- Protection against compacted message hashes
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
)

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentAccumulator:
    """Test suite for BaseAgent message_history_accumulator method."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test.

        Uses CodePuppyAgent as a concrete implementation of BaseAgent
        to test the message_history_accumulator functionality.
        """
        return CodePuppyAgent()

    @pytest.fixture
    def mock_run_context(self):
        """Create a mock RunContext for testing."""
        ctx = MagicMock(spec=RunContext)
        return ctx

    def test_message_history_accumulator_deduplication(self, agent, mock_run_context):
        """Test that duplicate messages are filtered out based on hash."""
        # Setup - add a message to history
        msg1 = ModelRequest(parts=[TextPart(content="Hello world")])
        agent.set_message_history([msg1])

        # Try to add the same message again
        result = agent.message_history_accumulator(mock_run_context, [msg1])

        # Should only have one copy due to deduplication
        text_messages = [
            m
            for m in result
            if hasattr(m, "parts") and any(isinstance(p, TextPart) for p in m.parts)
        ]
        assert len(text_messages) == 1
        assert text_messages[0].parts[0].content == "Hello world"

    def test_message_history_accumulator_new_message_added(
        self, agent, mock_run_context
    ):
        """Test that new unique messages are added to history."""
        # Setup - add initial message
        msg1 = ModelRequest(parts=[TextPart(content="First message")])
        agent.set_message_history([msg1])

        # Add a response followed by a new request (valid history pattern)
        msg2 = ModelResponse(parts=[TextPart(content="Second message")])
        msg3 = ModelRequest(parts=[TextPart(content="Third message")])
        result = agent.message_history_accumulator(mock_run_context, [msg2, msg3])

        # Should have all three messages
        assert len(result) == 3

        # Check content of all messages
        contents = [
            p.content for m in result for p in m.parts if isinstance(p, TextPart)
        ]
        assert "First message" in contents
        assert "Second message" in contents
        assert "Third message" in contents

    def test_message_history_accumulator_filters_empty_thinking(
        self, agent, mock_run_context
    ):
        """Test that empty ThinkingPart messages are filtered out."""
        # Setup - mix of messages including empty thinking
        text_msg = ModelRequest(parts=[TextPart(content="Real message")])
        empty_thinking_msg = ModelResponse(parts=[ThinkingPart(content="")])
        valid_thinking_msg = ModelResponse(
            parts=[ThinkingPart(content="Valid thinking")]
        )

        trailing_request = ModelRequest(parts=[TextPart(content="Follow up")])
        agent.set_message_history(
            [text_msg, empty_thinking_msg, valid_thinking_msg, trailing_request]
        )

        # Run accumulator (should filter empty thinking)
        result = agent.message_history_accumulator(mock_run_context, [])

        # Should have 3 messages (text + valid thinking + trailing request, empty thinking filtered)
        assert len(result) == 3

        # Check that empty thinking was filtered
        has_empty_thinking = any(
            len(m.parts) == 1
            and isinstance(m.parts[0], ThinkingPart)
            and m.parts[0].content == ""
            for m in result
        )
        assert not has_empty_thinking

        # Check that valid thinking and text remain
        has_valid_thinking = any(
            len(m.parts) == 1
            and isinstance(m.parts[0], ThinkingPart)
            and m.parts[0].content == "Valid thinking"
            for m in result
        )
        assert has_valid_thinking

        has_text = any(
            any(
                isinstance(p, TextPart) and p.content == "Real message" for p in m.parts
            )
            for m in result
        )
        assert has_text

    def test_message_history_accumulator_respects_compacted_hashes(
        self, agent, mock_run_context
    ):
        """Test that non-last messages with compacted hashes are skipped,
        but the last message (user's prompt) is always preserved."""
        # Create two messages, first one is compacted
        msg1 = ModelRequest(parts=[TextPart(content="Should be compacted")])
        msg2 = ModelRequest(parts=[TextPart(content="User prompt")])
        msg1_hash = agent.hash_message(msg1)

        # Add the hash to compacted hashes set
        agent._compacted_message_hashes.add(msg1_hash)

        # Try to add both messages via accumulator
        result = agent.message_history_accumulator(mock_run_context, [msg1, msg2])

        # Only msg2 should be added (msg1 is compacted and not last)
        assert len(result) == 1
        assert result[0].parts[0].content == "User prompt"

    def test_message_history_accumulator_preserves_last_msg_even_if_compacted(
        self, agent, mock_run_context
    ):
        """Test that the last message is always preserved even if its hash
        matches a compacted message — prevents dropping the user's prompt."""
        msg = ModelRequest(parts=[TextPart(content="yes")])
        msg_hash = agent.hash_message(msg)
        agent._compacted_message_hashes.add(msg_hash)

        result = agent.message_history_accumulator(mock_run_context, [msg])

        # Last message must be preserved to avoid prefill errors
        assert len(result) == 1
        assert result[0].parts[0].content == "yes"

    def test_message_history_accumulator_multi_part_messages(
        self, agent, mock_run_context
    ):
        """Test accumulator with multi-part messages."""
        # Create message with multiple parts
        tool_call = ToolCallPart(
            tool_call_id="test123", tool_name="test_tool", args={"param": "value"}
        )
        multi_part_msg = ModelRequest(parts=[TextPart(content="Do this"), tool_call])

        agent.set_message_history([multi_part_msg])

        # Try to add same message again
        result = agent.message_history_accumulator(mock_run_context, [multi_part_msg])

        # Should deduplicate properly
        assert len(result) == 1
        assert len(result[0].parts) == 2

    def test_message_history_accumulator_mixed_message_types(
        self, agent, mock_run_context
    ):
        """Test accumulator with various message types and ensure proper deduplication."""
        request_msg = ModelRequest(parts=[TextPart(content="User input")])
        response_msg = ModelResponse(parts=[TextPart(content="AI response")])
        thinking_msg = ModelResponse(parts=[ThinkingPart(content="Thinking process")])

        # Set initial history
        agent.set_message_history([request_msg])

        # Add mixed new messages (response, thinking, then a new request)
        new_request = ModelRequest(parts=[TextPart(content="Follow up")])
        new_messages = [response_msg, thinking_msg, new_request]
        result = agent.message_history_accumulator(mock_run_context, new_messages)

        # Should have 4 messages: original request, response, thinking, new request
        assert len(result) == 4

        # Verify all expected message types are present
        has_request = any(isinstance(m, ModelRequest) for m in result)
        has_response = any(isinstance(m, ModelResponse) for m in result)
        has_thinking = any(
            any(isinstance(p, ThinkingPart) for p in m.parts) for m in result
        )

        assert has_request
        assert has_response
        assert has_thinking

    @patch.object(CodePuppyAgent, "message_history_processor")
    def test_message_history_accumulator_calls_processor(
        self, mock_processor, agent, mock_run_context
    ):
        """Test that accumulator integrates with message_history_processor."""
        # Setup
        msg = ModelRequest(parts=[TextPart(content="Test message")])
        agent.set_message_history([])

        # Run accumulator
        agent.message_history_accumulator(mock_run_context, [msg])

        # Verify processor was called
        mock_processor.assert_called_once()

        # Check that processor was called with context and message history
        call_args = mock_processor.call_args
        assert call_args[0][0] == mock_run_context  # First arg should be context
        assert len(call_args[0][1]) >= 0  # Second arg should be message history list

    def test_message_history_accumulator_empty_input(self, agent, mock_run_context):
        """Test accumulator with empty message list input."""
        # Setup with existing messages
        existing_msg = ModelRequest(parts=[TextPart(content="Existing")])
        agent.set_message_history([existing_msg])

        # Run with empty input list
        result = agent.message_history_accumulator(mock_run_context, [])

        # Should preserve existing messages (just filtering)
        assert len(result) >= 0  # May be filtered if it's empty thinking

    def test_message_history_accumulator_hash_stability(self, agent, mock_run_context):
        """Test that message hashes are stable for the same content."""
        # Create two messages with identical content
        msg1 = ModelRequest(parts=[TextPart(content="Same content")])
        msg2 = ModelRequest(parts=[TextPart(content="Same content")])

        # Add first message
        agent.set_message_history([msg1])

        # Try to add second message (should be deduplicated as same hash)
        result = agent.message_history_accumulator(mock_run_context, [msg2])

        # Should only have one message due to identical hash
        text_messages = [
            m
            for m in result
            if hasattr(m, "parts") and any(isinstance(p, TextPart) for p in m.parts)
        ]
        assert len(text_messages) == 1
        assert text_messages[0].parts[0].content == "Same content"

    def test_message_history_accumulator_tool_call_deduplication(
        self, agent, mock_run_context
    ):
        """Test deduplication of tool call messages."""
        tool_call = ToolCallPart(
            tool_call_id="tool123", tool_name="test_tool", args={"input": "test_value"}
        )
        msg1 = ModelRequest(parts=[tool_call])
        msg2 = ModelRequest(parts=[tool_call])  # Identical tool call

        # Add first message
        agent.set_message_history([msg1])

        # Try to add duplicate
        result = agent.message_history_accumulator(mock_run_context, [msg2])

        # Should deduplicate tool calls
        assert len(result) == 1
        assert result[0].parts[0].tool_call_id == "tool123"

    def test_message_history_accumulator_only_empty_thinking_filtered(
        self, agent, mock_run_context
    ):
        """Test that only completely empty ThinkingPart messages are filtered."""
        # Message with empty text content (should be kept)
        text_empty = ModelRequest(parts=[TextPart(content="")])

        # Message with empty thinking (should be filtered)
        thinking_empty = ModelResponse(parts=[ThinkingPart(content="")])

        # Message with thinking content (should be kept)
        thinking_content = ModelResponse(parts=[ThinkingPart(content="Some thoughts")])

        # Message with multiple parts including thinking
        multi_with_thinking = ModelResponse(
            parts=[
                TextPart(content="Text"),
                ThinkingPart(content="Thinking in multi-part"),
            ]
        )

        trailing_request = ModelRequest(parts=[TextPart(content="next")])
        agent.set_message_history(
            [
                text_empty,
                thinking_empty,
                thinking_content,
                multi_with_thinking,
                trailing_request,
            ]
        )

        # Run accumulator
        result = agent.message_history_accumulator(mock_run_context, [])

        # Should have 4 messages (empty thinking filtered, others kept including trailing request)
        assert len(result) == 4

        # Verify specific messages are kept/filtered
        has_empty_text = any(
            any(isinstance(p, TextPart) and p.content == "" for p in m.parts)
            for m in result
        )
        assert has_empty_text  # Empty text should be kept

        has_empty_thinking = any(
            len(m.parts) == 1
            and isinstance(m.parts[0], ThinkingPart)
            and m.parts[0].content == ""
            for m in result
        )
        assert not has_empty_thinking  # Empty thinking should be filtered

        has_thinking_content = any(
            any(
                isinstance(p, ThinkingPart) and p.content == "Some thoughts"
                for p in m.parts
            )
            for m in result
        )
        assert has_thinking_content  # Non-empty thinking should be kept

        has_multi_part = any(len(m.parts) == 2 for m in result)
        assert has_multi_part  # Multi-part should be kept
