"""Tests for BaseAgent message processing methods.

This module tests the following message processing methods in BaseAgent:
- stringify_message_part()
- _is_tool_call_part() / _is_tool_return_part()
- filter_huge_messages()
- prune_interrupted_tool_calls()
- estimate_tokens_for_message()
"""

import pytest
from pydantic_ai import BinaryContent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)

from code_puppy.agents.agent_code_puppy import CodePuppyAgent


class TestBaseAgentMessageProcessing:
    """Test suite for BaseAgent message processing methods."""

    @pytest.fixture
    def agent(self):
        """Create a fresh agent instance for each test.

        Uses CodePuppyAgent as a concrete implementation of BaseAgent
        to test the abstract class's message processing functionality.
        """
        return CodePuppyAgent()

    def test_stringify_message_part_text(self, agent):
        """Test stringify_message_part with TextPart."""
        part = TextPart(content="Hello world")
        result = agent.stringify_message_part(part)
        assert "Hello world" in result

    def test_stringify_message_part_tool_call(self, agent):
        """Test stringify_message_part with ToolCallPart."""
        part = ToolCallPart(
            tool_call_id="test123", tool_name="test_tool", args={"param": "value"}
        )
        result = agent.stringify_message_part(part)
        assert "test_tool" in result
        assert "'param': 'value'" in result

    def test_stringify_message_part_tool_return(self, agent):
        """Test stringify_message_part with ToolReturnPart."""
        part = ToolReturnPart(
            tool_call_id="test123",
            tool_name="test_tool",
            content="Tool executed successfully",
        )
        result = agent.stringify_message_part(part)
        assert "Tool executed successfully" in result

    def test_stringify_message_part_thinking(self, agent):
        """Test stringify_message_part with ThinkingPart."""
        part = ThinkingPart(content="Let me think about this...")
        result = agent.stringify_message_part(part)
        assert "Let me think about this..." in result

    def test_stringify_message_part_with_list_content(self, agent):
        """Test stringify_message_part with list content."""

        # Create a mock part with list content
        class MockPart:
            def __init__(self, content):
                self.part_kind = "test"
                self.content = content

        part = MockPart(["Line 1", "Line 2"])
        result = agent.stringify_message_part(part)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_stringify_message_part_with_binary_content(self, agent):
        """Test stringify_message_part with BinaryContent in list."""

        # Create a mock part with BinaryContent in list
        class MockPart:
            def __init__(self, content):
                self.part_kind = "test"
                self.content = content

        binary = BinaryContent(data=b"test data", media_type="application/octet-stream")
        part = MockPart(["Some text", binary])
        result = agent.stringify_message_part(part)
        assert "Some text" in result
        assert "BinaryContent=" in result

    def test_is_tool_call_part_with_tool_call_part(self, agent):
        """Test _is_tool_call_part recognizes ToolCallPart."""
        part = ToolCallPart(tool_call_id="test123", tool_name="test_tool", args={})
        assert agent._is_tool_call_part(part) is True
        assert agent._is_tool_return_part(part) is False

    def test_is_tool_return_part_with_tool_return_part(self, agent):
        """Test _is_tool_return_part recognizes ToolReturnPart."""
        part = ToolReturnPart(
            tool_call_id="test123", tool_name="test_tool", content="Success"
        )
        assert agent._is_tool_return_part(part) is True
        assert agent._is_tool_call_part(part) is False

    def test_is_tool_call_part_with_part_kind(self, agent):
        """Test _is_tool_call_part checks part_kind attribute."""

        # Create mock part with tool-call part kind
        class MockPart:
            def __init__(self, part_kind, tool_name=None, args=None):
                self.part_kind = part_kind
                self.tool_name = tool_name
                self.args = args if args is not None else {}

        # Test with tool-call part kind
        part = MockPart("tool-call", "test_tool", {"param": "value"})
        assert agent._is_tool_call_part(part) is True
        assert agent._is_tool_return_part(part) is False

        # Test with tool_return part kind (underscores)
        part = MockPart("tool_return", "test_tool", {"param": "value"})
        assert agent._is_tool_call_part(part) is True

    def test_is_tool_return_part_with_part_kind(self, agent):
        """Test _is_tool_return_part checks part_kind attribute."""

        # Create mock part with tool-return part kind
        class MockPart:
            def __init__(self, part_kind, tool_call_id=None, content=None):
                self.part_kind = part_kind
                self.tool_call_id = tool_call_id
                self.content = content

        # Test with tool-return part kind
        part = MockPart("tool-return", "test123", "Success")
        assert agent._is_tool_return_part(part) is True
        assert agent._is_tool_call_part(part) is False

        # Test with tool-result part kind
        part = MockPart("tool-result", "test123", "Success")
        assert agent._is_tool_return_part(part) is True

    def test_is_tool_call_part_with_tool_name_args(self, agent):
        """Test _is_tool_call_part detects parts with tool_name and args."""

        class MockPart:
            def __init__(self, tool_name, args):
                self.tool_name = tool_name
                self.args = args

        part = MockPart("test_tool", {"param": "value"})
        assert agent._is_tool_call_part(part) is True
        assert agent._is_tool_return_part(part) is False

    def test_is_tool_return_part_with_tool_call_id_content(self, agent):
        """Test _is_tool_return_part detects parts with tool_call_id and content."""

        class MockPart:
            def __init__(self, tool_call_id, content):
                self.tool_call_id = tool_call_id
                self.content = content

        part = MockPart("test123", "Success")
        assert agent._is_tool_return_part(part) is True
        assert agent._is_tool_call_part(part) is False

    def test_estimate_tokens_for_message_text(self, agent):
        """Test token estimation for text message."""
        message = ModelRequest(parts=[TextPart(content="Hello world")])
        tokens = agent.estimate_tokens_for_message(message)
        assert tokens > 0
        # Should be roughly len(message) / 3
        expected = max(1, len("Hello world") // 3)
        assert abs(tokens - expected) <= 2  # Allow some variance

    def test_estimate_tokens_for_message_multiple_parts(self, agent):
        """Test token estimation for message with multiple parts."""
        message = ModelRequest(
            parts=[
                TextPart(content="Hello"),
                TextPart(content="world"),
                ThinkingPart(content="Thinking"),
            ]
        )
        tokens = agent.estimate_tokens_for_message(message)
        assert tokens > 0
        # Should account for all parts
        expected = max(1, (len("Hello") + len("world") + len("Thinking")) // 3)
        assert abs(tokens - expected) <= 3  # Allow some variance

    def test_estimate_tokens_for_message_tool_call(self, agent):
        """Test token estimation for tool call message."""
        message = ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="test123",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        )
        tokens = agent.estimate_tokens_for_message(message)
        assert tokens > 0

    def test_prune_interrupted_tool_calls_empty_list(self, agent):
        """Test prune_interrupted_tool_calls with empty message list."""
        result = agent.prune_interrupted_tool_calls([])
        assert result == []

    def test_prune_interrupted_tool_calls_no_tool_calls(self, agent):
        """Test prune_interrupted_tool_calls with no tool calls."""
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there")]),
        ]
        result = agent.prune_interrupted_tool_calls(messages)
        assert result == messages  # Should return unchanged

    def test_prune_interrupted_tool_calls_matched_calls(self, agent):
        """Test prune_interrupted_tool_calls with matching tool calls and returns."""
        messages = [
            ModelRequest(parts=[TextPart(content="Run tool")]),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_call_id="call123",
                        tool_name="test_tool",
                        args={"param": "value"},
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_call_id="call123", tool_name="test_tool", content="Success"
                    )
                ]
            ),
        ]
        result = agent.prune_interrupted_tool_calls(messages)
        assert result == messages  # Should return unchanged - everything matched

    def test_prune_interrupted_tool_calls_unmatched_call(self, agent):
        """Test prune_interrupted_tool_calls removes unmatched tool call."""
        messages = [
            ModelRequest(parts=[TextPart(content="Run tool")]),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_call_id="call123",
                        tool_name="test_tool",
                        args={"param": "value"},
                    )
                ]
            ),
            # No corresponding ToolReturnPart - should be pruned
        ]
        result = agent.prune_interrupted_tool_calls(messages)
        # Should drop the tool call message and keep only the text message
        assert len(result) == 1
        assert result[0] == messages[0]

    def test_prune_interrupted_tool_calls_unmatched_return(self, agent):
        """Test prune_interrupted_tool_calls removes unmatched tool return."""
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_call_id="call123", tool_name="test_tool", content="Success"
                    )
                ]
            ),
            # No corresponding ToolCallPart - should be pruned
        ]
        result = agent.prune_interrupted_tool_calls(messages)
        # Should drop the tool return message and keep only the text message
        assert len(result) == 1
        assert result[0] == messages[0]

    def test_filter_huge_messages_small_messages(self, agent):
        """Test filter_huge_messages keeps messages under limit."""
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content="Hi there")]),
            ModelRequest(parts=[TextPart(content="How are you?")]),
        ]
        result = agent.filter_huge_messages(messages)
        assert result == messages  # All messages should be kept

    def test_filter_huge_messages_calls_prune(self, agent):
        """Test filter_huge_messages also calls prune_interrupted_tool_calls."""
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_call_id="call123",
                        tool_name="test_tool",
                        args={"param": "value"},
                    )
                ]
            ),
            # No return - should be pruned
        ]
        result = agent.filter_huge_messages(messages)
        # Should have pruned the unmatched call via prune_interrupted_tool_calls
        assert len(result) == 1
        assert result[0] == messages[0]

    def test_filter_huge_messages_large_content(self, agent):
        """Test filter_huge_messages filters very large messages."""
        # Create a very large message (over 50k tokens)
        large_content = "x" * 200000  # Much larger than 50k tokens
        messages = [
            ModelRequest(parts=[TextPart(content="Hello")]),
            ModelResponse(parts=[TextPart(content=large_content)]),
            ModelRequest(parts=[TextPart(content="Hi")]),
        ]
        result = agent.filter_huge_messages(messages)
        # Should filter out the large message
        assert len(result) == 2
        assert result[0] == messages[0]
        assert result[1] == messages[2]

    def test_estimate_token_count(self, agent):
        """Test the basic token count estimation."""
        # Test various lengths
        assert agent.estimate_token_count("") == 1
        assert agent.estimate_token_count("a") == 1
        assert agent.estimate_token_count("abc") == 1
        assert agent.estimate_token_count("abcdef") == 2
        assert agent.estimate_token_count("abcdefghi") == 3

        # Should always return at least 1
        assert agent.estimate_token_count("x" * 100) >= 1

    def test_stringify_part_known_part_kinds_no_warning(self, agent):
        """Test that _stringify_part does NOT emit warning for known part_kinds."""
        from unittest.mock import patch

        # Test with known part kinds
        known_kinds = ["text", "tool-call", "tool_call", "thinking", "tool-return"]

        for kind in known_kinds:

            class MockPart:
                def __init__(self, pk):
                    self.part_kind = pk
                    self.content = "test content"

            part = MockPart(kind)

            with patch("code_puppy.agents.base_agent.emit_warning") as mock_emit:
                agent._stringify_part(part)
                # Should NOT emit warning for known kinds
                mock_emit.assert_not_called()
