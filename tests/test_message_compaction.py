"""Tests for message history compaction logic.

These tests validate critical token management functionality that prevents
context overflow and ensures important messages are preserved.

Currently testing:
- truncation() - Keeps system message + recent messages within token budget
- Message ordering preservation
- Edge cases (empty, all fit, none fit)
"""

import pytest
from unittest.mock import Mock, patch
from pydantic_ai.messages import (
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
            ModelRequest(parts=[TextPart(content="System")]),  # 100 tokens
            ModelRequest(parts=[TextPart(content="Old 1")]),  # 100 tokens
            ModelRequest(parts=[TextPart(content="Old 2")]),  # 100 tokens
            ModelRequest(parts=[TextPart(content="Recent 1")]),  # 100 tokens
            ModelRequest(parts=[TextPart(content="Recent 2")]),  # 100 tokens
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
            ModelRequest(parts=[TextPart(content="System")]),  # 50
            ModelRequest(parts=[TextPart(content="Old heavy")]),  # 200
            ModelRequest(parts=[TextPart(content="Medium")]),  # 150
            ModelRequest(parts=[TextPart(content="Recent")]),  # 100
            ModelRequest(parts=[TextPart(content="Latest heavy")]),  # 300
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
            ModelRequest(parts=[TextPart(content="System")]),  # 50
            ModelRequest(parts=[TextPart(content="Normal")]),  # 100
            ModelRequest(parts=[TextPart(content="Huge message")]),  # 500
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


class TestFilterHugeMessages:
    """Test filtering of huge messages (>50k tokens)."""

    def test_filters_messages_over_50k_tokens(self):
        """Messages over 50k tokens should be filtered out."""
        agent = MinimalTestAgent()

        # Mock different token sizes
        token_counts = [100, 60000, 1000, 75000, 500]
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),  # 100
            ModelRequest(parts=[TextPart(content="Huge 1")]),  # 60000
            ModelRequest(parts=[TextPart(content="Normal")]),  # 1000
            ModelRequest(parts=[TextPart(content="Huge 2")]),  # 75000
            ModelRequest(parts=[TextPart(content="Small")]),  # 500
        ]

        agent.estimate_tokens_for_message = Mock(
            side_effect=lambda msg: token_counts[messages.index(msg)]
        )

        result = agent.filter_huge_messages(messages)

        # Should keep only messages under 50k tokens
        assert len(result) == 3
        assert result[0].parts[0].content == "System"
        assert result[1].parts[0].content == "Normal"
        assert result[2].parts[0].content == "Small"

    def test_keeps_all_when_none_huge(self):
        """All messages under 50k should be kept."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=1000)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
        ]

        result = agent.filter_huge_messages(messages)

        assert len(result) == 3
        assert result == messages

    def test_filters_all_when_all_huge(self):
        """If all messages are huge, all get filtered."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=60000)

        messages = [
            ModelRequest(parts=[TextPart(content="Huge 1")]),
            ModelRequest(parts=[TextPart(content="Huge 2")]),
            ModelRequest(parts=[TextPart(content="Huge 3")]),
        ]

        result = agent.filter_huge_messages(messages)

        assert len(result) == 0

    def test_boundary_case_exactly_50k(self):
        """Message with exactly 50k tokens should be filtered (< 50k)."""
        agent = MinimalTestAgent()

        token_counts = [1000, 50000, 49999]
        messages = [
            ModelRequest(parts=[TextPart(content="Normal")]),  # 1000
            ModelRequest(parts=[TextPart(content="Exactly 50k")]),  # 50000 (filtered)
            ModelRequest(parts=[TextPart(content="Just under")]),  # 49999 (kept)
        ]

        agent.estimate_tokens_for_message = Mock(
            side_effect=lambda msg: token_counts[messages.index(msg)]
        )

        result = agent.filter_huge_messages(messages)

        assert len(result) == 2
        assert result[0].parts[0].content == "Normal"
        assert result[1].parts[0].content == "Just under"


class TestSplitMessagesForProtectedSummarization:
    """Test splitting messages into summarize/protected groups."""

    def test_protects_recent_messages_within_token_limit(self):
        """Most recent messages should be protected up to token limit."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),  # 100
            ModelRequest(parts=[TextPart(content="Old 1")]),  # 100
            ModelRequest(parts=[TextPart(content="Old 2")]),  # 100
            ModelRequest(parts=[TextPart(content="Recent 1")]),  # 100
            ModelRequest(parts=[TextPart(content="Recent 2")]),  # 100
        ]

        # Mock protected token count to 300 (system + 2 recent messages)
        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=300
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        # Should protect: System + Recent 1 + Recent 2
        assert len(protected) == 3
        assert protected[0].parts[0].content == "System"
        assert protected[1].parts[0].content == "Recent 1"
        assert protected[2].parts[0].content == "Recent 2"

        # Should summarize: Old 1 + Old 2
        assert len(to_summarize) == 2
        assert to_summarize[0].parts[0].content == "Old 1"
        assert to_summarize[1].parts[0].content == "Old 2"

    def test_empty_summarize_when_all_protected(self):
        """If all messages fit in protected zone, nothing to summarize."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
        ]

        # Large protected limit
        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=10000
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        assert len(to_summarize) == 0
        assert len(protected) == 2

    def test_system_message_always_protected(self):
        """System message must always be in protected group."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
        ]

        # Very small protected limit (only system message)
        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=100
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        assert len(protected) == 1
        assert protected[0].parts[0].content == "System"
        assert len(to_summarize) == 2

    def test_only_system_message(self):
        """Edge case: only system message exists."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=100)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
        ]

        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=1000
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        assert len(to_summarize) == 0
        assert len(protected) == 1
        assert protected[0].parts[0].content == "System"

    def test_variable_token_sizes(self):
        """Handle messages with different token counts."""
        agent = MinimalTestAgent()

        token_counts = [50, 200, 150, 100, 300]
        messages = [
            ModelRequest(parts=[TextPart(content="System")]),  # 50
            ModelRequest(parts=[TextPart(content="Old heavy")]),  # 200
            ModelRequest(parts=[TextPart(content="Medium")]),  # 150
            ModelRequest(parts=[TextPart(content="Recent")]),  # 100
            ModelRequest(parts=[TextPart(content="Latest")]),  # 300
        ]

        agent.estimate_tokens_for_message = Mock(
            side_effect=lambda msg: token_counts[messages.index(msg)]
        )

        # Protected = 450 (System 50 + Recent 100 + Latest 300)
        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=450
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        assert len(protected) == 3
        assert protected[0].parts[0].content == "System"
        assert protected[1].parts[0].content == "Recent"
        assert protected[2].parts[0].content == "Latest"

        assert len(to_summarize) == 2
        assert to_summarize[0].parts[0].content == "Old heavy"
        assert to_summarize[1].parts[0].content == "Medium"

    def test_chronological_order_preserved(self):
        """Protected messages should maintain chronological order."""
        agent = MinimalTestAgent()
        agent.estimate_tokens_for_message = Mock(return_value=50)

        messages = [
            ModelRequest(parts=[TextPart(content="System")]),
            ModelRequest(parts=[TextPart(content="Message 1")]),
            ModelRequest(parts=[TextPart(content="Message 2")]),
            ModelRequest(parts=[TextPart(content="Message 3")]),
            ModelRequest(parts=[TextPart(content="Message 4")]),
        ]

        # Protected = 200 (System 50 + Message 3 50 + Message 4 50 = 150, can fit one more)
        # Actually: System (50) + Msg4 (50) + Msg3 (50) + Msg2 (50) = 200
        with patch(
            "code_puppy.agents.base_agent.get_protected_token_count", return_value=200
        ):
            to_summarize, protected = agent.split_messages_for_protected_summarization(
                messages
            )

        # Verify chronological order in protected
        assert protected[0].parts[0].content == "System"
        assert protected[1].parts[0].content == "Message 2"
        assert protected[2].parts[0].content == "Message 3"
        assert protected[3].parts[0].content == "Message 4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
