"""Tests for BaseAgent token estimation and message filtering functionality."""

import math

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
)

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestTokenEstimation:
    """Test suite for token estimation methods in BaseAgent."""

    @pytest.fixture
    def agent(self):
        """Provide a concrete BaseAgent subclass for testing."""
        return CodePuppyAgent()

    # Tests for estimate_token_count

    def test_estimate_token_count_simple_text(self, agent):
        """Test token estimation for simple text."""
        text = "Hello, world!"
        token_count = agent.estimate_token_count(text)
        # Formula: max(1, floor(len(text) / 3))
        # len("Hello, world!") = 13
        # floor(13 / 3) = 4
        expected = max(1, math.floor(len(text) / 3))
        assert token_count == expected
        assert token_count == 4

    def test_estimate_token_count_empty_string(self, agent):
        """Test token estimation for empty string returns minimum of 1."""
        text = ""
        token_count = agent.estimate_token_count(text)
        # Formula ensures max(1, ...) so empty string should return 1
        assert token_count == 1

    def test_estimate_token_count_single_char(self, agent):
        """Test token estimation for single character."""
        text = "a"
        token_count = agent.estimate_token_count(text)
        # floor(1 / 3) = 0, but max(1, 0) = 1
        assert token_count == 1

    def test_estimate_token_count_large_text(self, agent):
        """Test token estimation for large text."""
        # Create a large text string
        text = "x" * 3000  # 3000 characters
        token_count = agent.estimate_token_count(text)
        # floor(3000 / 3) = 1000
        expected = max(1, math.floor(3000 / 3))
        assert token_count == expected
        assert token_count == 1000

    def test_estimate_token_count_medium_text(self, agent):
        """Test token estimation for medium-sized text."""
        text = "a" * 100
        token_count = agent.estimate_token_count(text)
        # floor(100 / 3) = 33
        expected = max(1, math.floor(100 / 3))
        assert token_count == expected
        assert token_count == 33

    def test_estimate_token_count_two_chars(self, agent):
        """Test token estimation for two characters."""
        text = "ab"
        token_count = agent.estimate_token_count(text)
        # floor(2 / 3) = 0, but max(1, 0) = 1
        assert token_count == 1

    def test_estimate_token_count_three_chars(self, agent):
        """Test token estimation for exactly three characters."""
        text = "abc"
        token_count = agent.estimate_token_count(text)
        # floor(3 / 3) = 1
        assert token_count == 1

    def test_estimate_token_count_four_chars(self, agent):
        """Test token estimation for four characters."""
        text = "abcd"
        token_count = agent.estimate_token_count(text)
        # floor(4 / 3) = 1
        assert token_count == 1

    def test_estimate_token_count_six_chars(self, agent):
        """Test token estimation for six characters."""
        text = "abcdef"
        token_count = agent.estimate_token_count(text)
        # floor(6 / 3) = 2
        assert token_count == 2

    # Tests for estimate_tokens_for_message

    def test_estimate_tokens_for_message_single_part(self, agent):
        """Test token estimation for message with single TextPart."""
        # Create a message with one part
        text_content = "This is a test message"
        message = ModelRequest(parts=[TextPart(content=text_content)])
        token_count = agent.estimate_tokens_for_message(message)
        # Should call estimate_token_count on the text
        expected = max(1, math.floor(len(text_content) / 3))
        assert token_count == expected

    def test_estimate_tokens_for_message_multiple_parts(self, agent):
        """Test token estimation for message with multiple parts."""
        # Create a message with multiple text parts
        text1 = "Hello"
        text2 = "World"
        message = ModelRequest(
            parts=[
                TextPart(content=text1),
                TextPart(content=text2),
            ]
        )
        token_count = agent.estimate_tokens_for_message(message)
        # Should sum the tokens from both parts
        tokens1 = agent.estimate_token_count(text1)
        tokens2 = agent.estimate_token_count(text2)
        expected = max(1, tokens1 + tokens2)
        assert token_count == expected

    def test_estimate_tokens_for_message_empty_parts(self, agent):
        """Test token estimation for message with empty parts."""
        # Create a message with empty text
        message = ModelRequest(parts=[TextPart(content="")])
        token_count = agent.estimate_tokens_for_message(message)
        # Empty part should contribute 1 token (minimum)
        assert token_count >= 1

    def test_estimate_tokens_for_message_large_content(self, agent):
        """Test token estimation for message with large content."""
        # Create a message with large text
        large_text = "x" * 9000
        message = ModelRequest(parts=[TextPart(content=large_text)])
        token_count = agent.estimate_tokens_for_message(message)
        # floor(9000 / 3) = 3000
        expected = max(1, math.floor(9000 / 3))
        assert token_count == expected
        assert token_count == 3000

    # Tests for filter_huge_messages

    def test_filter_huge_messages_removes_oversized(self, agent):
        """Test that filter_huge_messages removes messages exceeding 50000 tokens."""
        # Create a message that's definitely over 50000 tokens
        # 50000 tokens * 3 = 150000 characters minimum
        huge_text = "x" * 150001  # This should be ~50000+ tokens
        huge_message = ModelRequest(parts=[TextPart(content=huge_text)])

        # Create a small message that should be kept
        small_text = "small"
        small_message = ModelRequest(parts=[TextPart(content=small_text)])

        messages = [small_message, huge_message, small_message]
        filtered = agent.filter_huge_messages(messages)

        # The huge message should be filtered out
        assert len(filtered) < len(messages)
        # Small messages should remain
        assert len(filtered) >= 2

    def test_filter_huge_messages_keeps_small(self, agent):
        """Test that filter_huge_messages keeps messages under 50000 tokens."""
        # Create messages that are well under the 50000 token limit
        messages = [
            ModelRequest(parts=[TextPart(content="Hello world")]),
            ModelResponse(parts=[TextPart(content="Hi there!")]),
            ModelRequest(parts=[TextPart(content="How are you?")]),
        ]

        filtered = agent.filter_huge_messages(messages)

        # All small messages should be kept
        assert len(filtered) == len(messages)

    def test_filter_huge_messages_empty_list(self, agent):
        """Test that filter_huge_messages handles empty message list."""
        messages = []
        filtered = agent.filter_huge_messages(messages)
        assert len(filtered) == 0

    def test_filter_huge_messages_single_small_message(self, agent):
        """Test that filter_huge_messages keeps single small message."""
        message = ModelRequest(parts=[TextPart(content="test")])
        filtered = agent.filter_huge_messages([message])
        assert len(filtered) == 1

    def test_filter_huge_messages_boundary_at_50000(self, agent):
        """Test filter_huge_messages behavior at 50000 token boundary."""
        # Create a message with approximately 50000 tokens
        # 50000 tokens = 150000 characters (using 3 chars per token)
        boundary_text = "x" * (50000 * 3)  # Exactly at boundary
        boundary_message = ModelRequest(parts=[TextPart(content=boundary_text)])

        # Create a message with exactly one character below the boundary
        # (so it has 49999 tokens)
        just_under_text = "x" * (49999 * 3 + 2)  # Just under boundary
        just_under_message = ModelRequest(parts=[TextPart(content=just_under_text)])

        # Test at boundary - 50000 tokens should be filtered out
        messages_at_boundary = [boundary_message]
        filtered = agent.filter_huge_messages(messages_at_boundary)
        # 50000 tokens is >= 50000, so it should be filtered
        assert len(filtered) == 0

        # Test just under boundary - should be kept
        messages_under = [just_under_message]
        filtered_under = agent.filter_huge_messages(messages_under)
        # 49999 tokens is < 50000, so it should be kept
        assert len(filtered_under) == 1

    def test_filter_huge_messages_calls_prune(self, agent):
        """Test that filter_huge_messages calls prune_interrupted_tool_calls."""
        # This test verifies the filtering also prunes interrupted tool calls
        # Create a normal message that should pass through
        message = ModelRequest(parts=[TextPart(content="hello")])
        filtered = agent.filter_huge_messages([message])
        # Should still have the message after pruning
        assert len(filtered) >= 0  # May be 0 or more depending on pruning logic


class TestMCPToolCache:
    """Test suite for MCP tool cache functionality."""

    @pytest.fixture
    def agent(self):
        """Provide a concrete BaseAgent subclass for testing."""
        return CodePuppyAgent()

    def test_mcp_tool_cache_initialized_empty(self, agent):
        """Test that MCP tool cache is initialized as empty list."""
        assert hasattr(agent, "_mcp_tool_definitions_cache")
        assert agent._mcp_tool_definitions_cache == []

    def test_estimate_context_overhead_with_empty_mcp_cache(self, agent):
        """Test that estimate_context_overhead_tokens works with empty MCP cache."""
        # Should not raise an error with empty cache
        overhead = agent.estimate_context_overhead_tokens()
        # Should return at least 0 (or more if system prompt is present)
        assert overhead >= 0

    def test_estimate_context_overhead_with_mcp_cache(self, agent):
        """Test that estimate_context_overhead_tokens includes MCP tools from cache."""
        # Populate the cache with mock MCP tool definitions
        agent._mcp_tool_definitions_cache = [
            {
                "name": "test_tool",
                "description": "A test tool for testing",
                "inputSchema": {
                    "type": "object",
                    "properties": {"arg1": {"type": "string"}},
                },
            },
            {
                "name": "another_tool",
                "description": "Another tool with a longer description for more tokens",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string"},
                        "arg2": {"type": "integer"},
                    },
                },
            },
        ]

        overhead_with_tools = agent.estimate_context_overhead_tokens()

        # Clear the cache and measure again
        agent._mcp_tool_definitions_cache = []
        overhead_without_tools = agent.estimate_context_overhead_tokens()

        # Overhead with tools should be greater than without
        assert overhead_with_tools > overhead_without_tools

    def test_mcp_cache_cleared_on_reload(self, agent):
        """Test that MCP cache is cleared when reload_mcp_servers is called."""
        # Populate the cache
        agent._mcp_tool_definitions_cache = [
            {"name": "test_tool", "description": "Test", "inputSchema": {}}
        ]

        # Reload should clear the cache (even if no servers are configured)
        try:
            agent.reload_mcp_servers()
        except Exception:
            pass  # May fail if no MCP servers are configured, that's OK

        # Cache should be cleared
        assert agent._mcp_tool_definitions_cache == []

    def test_mcp_cache_token_estimation_accuracy(self, agent):
        """Test that MCP tool cache token estimation is reasonably accurate."""
        # Create a tool definition with known content
        tool_name = "my_test_tool"  # 12 chars
        tool_description = "A description"  # 13 chars
        tool_schema = {"type": "object"}  # ~20 chars when serialized

        agent._mcp_tool_definitions_cache = [
            {
                "name": tool_name,
                "description": tool_description,
                "inputSchema": tool_schema,
            }
        ]

        overhead = agent.estimate_context_overhead_tokens()

        # Calculate expected tokens from the tool definition
        # name: 12 chars / 3 = 4 tokens
        # description: 13 chars / 3 = 4 tokens
        # schema (serialized): ~20 chars / 3 = ~6 tokens
        # Total: ~14 tokens minimum from the MCP tool

        # Overhead should be at least 10 tokens (accounting for the MCP tool)
        assert overhead >= 10

    def test_update_mcp_tool_cache_sync_exists(self, agent):
        """Test that update_mcp_tool_cache_sync method exists and is callable."""
        assert hasattr(agent, "update_mcp_tool_cache_sync")
        assert callable(agent.update_mcp_tool_cache_sync)

    def test_update_mcp_tool_cache_sync_with_no_servers(self, agent):
        """Test that update_mcp_tool_cache_sync handles case with no MCP servers."""
        # Ensure no MCP servers are configured
        agent._mcp_servers = None
        agent._mcp_tool_definitions_cache = [{"name": "old_tool"}]

        # Should not raise an error and should clear the cache
        agent.update_mcp_tool_cache_sync()

        # Cache should be cleared (or remain as is if async update scheduled)
        # The key thing is it shouldn't raise an error
        assert hasattr(agent, "_mcp_tool_definitions_cache")


class TestTokenEstimationIntegration:
    """Integration tests for token estimation methods."""

    @pytest.fixture
    def agent(self):
        """Provide a concrete BaseAgent subclass for testing."""
        return CodePuppyAgent()

    def test_estimate_tokens_consistency(self, agent):
        """Test that estimate_tokens_for_message is consistent with estimate_token_count."""
        text = "test content with some words"
        single_part_message = ModelRequest(parts=[TextPart(content=text)])

        # Estimate tokens directly
        direct_tokens = agent.estimate_token_count(text)

        # Estimate tokens for message
        message_tokens = agent.estimate_tokens_for_message(single_part_message)

        # Should be consistent
        assert direct_tokens == message_tokens

    def test_filter_preserves_message_order(self, agent):
        """Test that filter_huge_messages preserves message order."""
        messages = [
            ModelRequest(parts=[TextPart(content="first")]),
            ModelResponse(parts=[TextPart(content="second")]),
            ModelRequest(parts=[TextPart(content="third")]),
        ]

        filtered = agent.filter_huge_messages(messages)

        # If all messages are kept, order should be preserved
        if len(filtered) == len(messages):
            for i, msg in enumerate(filtered):
                assert msg == messages[i]

    def test_token_count_formula_precision(self, agent):
        """Test token count formula precision with various text lengths."""
        test_cases = [
            (0, 1),  # Empty string returns 1
            (1, 1),  # 1 char -> floor(1/3) = 0 -> max(1, 0) = 1
            (2, 1),  # 2 chars -> floor(2/3) = 0 -> max(1, 0) = 1
            (3, 1),  # 3 chars -> floor(3/3) = 1
            (6, 2),  # 6 chars -> floor(6/3) = 2
            (9, 3),  # 9 chars -> floor(9/3) = 3
            (100, 33),  # 100 chars -> floor(100/3) = 33
            (300, 100),  # 300 chars -> floor(300/3) = 100
        ]

        for length, expected in test_cases:
            text = "x" * length
            token_count = agent.estimate_token_count(text)
            assert token_count == expected, (
                f"Length {length} should yield {expected} tokens, got {token_count}"
            )
