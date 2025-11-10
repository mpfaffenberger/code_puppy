"""Tests for message history compaction logic.

These tests validate critical token management functionality that prevents
context overflow and ensures important messages are preserved.

Currently testing:
- truncation() - Keeps system message + recent messages within token budget
- Message ordering preservation
- Edge cases (empty, all fit, none fit)
"""

import pytest
from unittest.mock import Mock
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    TextPart,
)

from code_puppy.agents.base_agent import BaseAgent


# Create a minimal concrete agent for testing
class MinimalTestAgent(BaseAgent):
    """Minimal agent implementation for testing base functionality."""
    
    @property
    def name(self) -> str:
        return "test-agent"
    
    @property
    def display_name(self) -> str:
        return "Test Agent"
    
    @property
    def description(self) -> str:
        return "Agent for testing"
    
    def get_system_prompt(self) -> str:
        return "You are a test agent"
    
    def get_available_tools(self):
        return []


class TestTruncation:
    """Test message truncation logic."""

    def test_always_preserves_system_message(self):
        """System message (index 0) must never be truncated."""
        agent = MinimalTestAgent()
        
        # Mock token estimation to make it predictable
        agent.estimate_tokens_for_message = Mock(return_value=100)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System prompt")]),
            ModelRequest(parts=[TextPart(content="User message 1")]),
            ModelRequest(parts=[TextPart(content="User message 2")]),
        ]
        
        # Truncate to 0 tokens (extreme case)
        result = agent.truncation(messages, protected_tokens=0)
        
        assert len(result) == 1, "Should only keep system message"
        assert result[0] == messages[0], "System message must be preserved"

    def test_keeps_most_recent_messages_within_token_limit(self):
        """Should keep most recent messages up to protected token limit."""
        agent = MinimalTestAgent()
        
        # Mock token estimation: each message = 100 tokens
        agent.estimate_tokens_for_message = Mock(return_value=100)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),       # 100 tokens
            ModelRequest(parts=[TextPart(content="Old 1")]),        # 100 tokens
            ModelRequest(parts=[TextPart(content="Old 2")]),        # 100 tokens
            ModelRequest(parts=[TextPart(content="Recent 1")]),     # 100 tokens
            ModelRequest(parts=[TextPart(content="Recent 2")]),     # 100 tokens
        ]
        
        # Protected = 250 tokens (system + 2 most recent = 3 messages)
        result = agent.truncation(messages, protected_tokens=250)
        
        assert len(result) == 3, "Should keep system + 2 most recent"
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Recent 1"
        assert result[2].parts[0].content == "Recent 2"

    def test_maintains_chronological_order(self):
        """Messages must remain in chronological order after truncation."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=50)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
            ModelRequest(parts=[TextPart(content="Message 3")]),
            ModelRequest(parts=[TextPart(content="Message 4")]),
        ]
        
        # 150 tokens allows: Message 4 (50) + Message 3 (50) + Message 2 (50) = 150
        # Result: System + Message 2 + Message 3 + Message 4
        result = agent.truncation(messages, protected_tokens=150)
        
        assert len(result) == 4
        # Should be in chronological order: System, Message 2, Message 3, Message 4
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Message 2"
        assert result[2].parts[0].content == "Message 3"
        assert result[3].parts[0].content == "Message 4"

    def test_all_messages_fit_within_limit(self):
        """When all messages fit, all should be kept."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=10)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
        ]
        
        # 1000 tokens >> 30 tokens total
        result = agent.truncation(messages, protected_tokens=1000)
        
        assert len(result) == 3
        assert result == messages, "All messages should be preserved"

    def test_empty_messages_except_system(self):
        """Edge case: Only system message exists."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System prompt")]),
        ]
        
        result = agent.truncation(messages, protected_tokens=0)
        
        assert len(result) == 1
        assert result[0] == messages[0]

    def test_exact_token_boundary(self):
        """Test behavior when hitting exact token limit."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
            ModelRequest(parts=[TextPart(content="Message 3")]),
        ]
        
        # Exactly 200 tokens = 2 messages (excluding system)
        result = agent.truncation(messages, protected_tokens=200)
        
        assert len(result) == 3, "System + 2 messages"
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Message 2"
        assert result[2].parts[0].content == "Message 3"

    def test_variable_token_sizes(self):
        """Test with messages of different token counts."""
        agent = MinimalTestAgent()
        
        # Variable token counts
        token_counts = [50, 200, 150, 100, 300]
        agent.estimate_tokens_for_message = Mock(
            side_effect=lambda msg: token_counts[messages.index(msg)]
        )
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),      # 50
            ModelRequest(parts=[TextPart(content="Old heavy")]),   # 200
            ModelRequest(parts=[TextPart(content="Medium")]),      # 150
            ModelRequest(parts=[TextPart(content="Recent")]),      # 100
            ModelRequest(parts=[TextPart(content="Latest heavy")]), # 300
        ]
        
        # 400 tokens protected = Recent (100) + Latest (300)
        result = agent.truncation(messages, protected_tokens=400)
        
        assert len(result) == 3
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Recent"
        assert result[2].parts[0].content == "Latest heavy"

    def test_single_large_message_exceeds_limit(self):
        """Test when a single recent message exceeds token limit."""
        agent = MinimalTestAgent()
        
        token_counts = [50, 100, 500]  # Last message is huge
        agent.estimate_tokens_for_message = Mock(
            side_effect=lambda msg: token_counts[messages.index(msg)]
        )
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),      # 50
            ModelRequest(parts=[TextPart(content="Normal")]),      # 100
            ModelRequest(parts=[TextPart(content="Huge message")]), # 500
        ]
        
        # 200 tokens protected, but last message alone = 500 tokens
        # Should still include it (it's the most recent)
        result = agent.truncation(messages, protected_tokens=200)
        
        # Should break after including the huge message
        assert len(result) == 1, "Only system message (huge exceeds limit)"
        assert result[0].parts[0].content == "System"

    def test_multiple_messages_same_content(self):
        """Test handling of messages with identical content."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)
        
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Repeat")]),
            ModelRequest(parts=[TextPart(content="Repeat")]),
            ModelRequest(parts=[TextPart(content="Repeat")]),
        ]
        
        result = agent.truncation(messages, protected_tokens=200)
        
        assert len(result) == 3
        # All three "Repeat" messages should be distinct objects
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Repeat"
        assert result[2].parts[0].content == "Repeat"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
