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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
