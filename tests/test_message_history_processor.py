from unittest.mock import patch

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)

from code_puppy.message_history_processor import (
    deduplicate_tool_returns,
    message_history_accumulator,
    prune_interrupted_tool_calls,
)


def test_prune_interrupted_tool_calls_perfect_pairs():
    """Test that perfect 1:1 tool call/return pairs are preserved."""
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="result",
                    tool_call_id="call_1",
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_2",
                    tool_name="another_tool",
                    args={"param2": "value2"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="another_tool",
                    content="result2",
                    tool_call_id="call_2",
                )
            ]
        ),
    ]

    result = prune_interrupted_tool_calls(messages)
    assert len(result) == 4  # All messages should be preserved
    assert result == messages


def test_prune_interrupted_tool_calls_orphaned_call():
    """Test that orphaned tool calls (no return) are pruned."""
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        # Missing tool return for call_1
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_2",
                    tool_name="another_tool",
                    args={"param2": "value2"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="another_tool",
                    content="result2",
                    tool_call_id="call_2",
                )
            ]
        ),
    ]

    result = prune_interrupted_tool_calls(messages)
    # Only the perfect pair (call_2 + return) should remain
    assert len(result) == 2
    assert result[0].parts[0].tool_call_id == "call_2"  # call_2 tool call
    assert result[1].parts[0].tool_call_id == "call_2"  # call_2 tool return


def test_prune_interrupted_tool_calls_orphaned_return():
    """Test that orphaned tool returns (no call) are pruned."""
    messages = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="unknown_tool",  # tool name for orphaned return
                    content="orphaned result",
                    tool_call_id="call_1",
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_2",
                    tool_name="another_tool",
                    args={"param2": "value2"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="another_tool",
                    content="result2",
                    tool_call_id="call_2",
                )
            ]
        ),
    ]

    result = prune_interrupted_tool_calls(messages)
    # Only the perfect pair (call_2 + return) should remain
    assert len(result) == 2
    assert result[0].parts[0].tool_call_id == "call_2"  # call_2 tool call
    assert result[1].parts[0].tool_call_id == "call_2"  # call_2 tool return


def test_prune_interrupted_tool_calls_multiple_returns_violation():
    """Test the critical case: multiple tool returns for one tool call violates 1:1 ratio."""
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="first result",
                    tool_call_id="call_1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="second result",
                    tool_call_id="call_1",  # Duplicate return for same call_id!
                )
            ]
        ),
        # Add a valid pair to ensure it's preserved
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_2",
                    tool_name="valid_tool",
                    args={"param2": "value2"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="valid_tool",
                    content="valid result",
                    tool_call_id="call_2",
                )
            ]
        ),
    ]

    result = prune_interrupted_tool_calls(messages)
    # After deduplication, call_1 should have perfect 1:1 ratio (duplicate return removed)
    # So both call_1 and call_2 pairs should be preserved (4 messages total)
    assert len(result) == 4

    # Verify that call_1 only appears twice (1 call + 1 return) after deduplication
    call_1_parts = [
        part
        for msg in result
        for part in msg.parts
        if hasattr(part, "tool_call_id") and part.tool_call_id == "call_1"
    ]
    assert (
        len(call_1_parts) == 2
    )  # Should have exactly 1 call + 1 return after deduplication

    # Verify that call_2 also appears twice (1 call + 1 return)
    call_2_parts = [
        part
        for msg in result
        for part in msg.parts
        if hasattr(part, "tool_call_id") and part.tool_call_id == "call_2"
    ]
    assert len(call_2_parts) == 2  # Should have exactly 1 call + 1 return


def test_prune_interrupted_tool_calls_multiple_calls_violation():
    """Test multiple tool calls for one return violates 1:1 ratio."""
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",  # Duplicate call with same ID!
                    tool_name="test_tool",
                    args={"param": "different_value"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="single result",
                    tool_call_id="call_1",
                )
            ]
        ),
    ]

    result = prune_interrupted_tool_calls(messages)
    # All messages should be pruned since call_1 violates 1:1 ratio
    assert len(result) == 0


def test_prune_interrupted_tool_calls_mixed_content():
    """Test that non-tool messages are preserved when tool calls are valid."""
    messages = [
        ModelRequest(parts=[TextPart("User text message")]),
        ModelResponse(
            parts=[
                TextPart("AI response"),
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                ),
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="result",
                    tool_call_id="call_1",
                )
            ]
        ),
        ModelResponse(parts=[TextPart("Final AI response")]),
    ]

    result = prune_interrupted_tool_calls(messages)
    assert len(result) == 4  # All messages preserved
    assert result == messages


def test_prune_interrupted_tool_calls_empty_list():
    """Test that empty message list is handled gracefully."""
    result = prune_interrupted_tool_calls([])
    assert result == []


def test_prune_interrupted_tool_calls_no_tool_messages():
    """Test that messages without tool calls are preserved unchanged."""
    messages = [
        ModelRequest(parts=[TextPart("User message")]),
        ModelResponse(parts=[TextPart("AI response")]),
        ModelRequest(parts=[TextPart("Another user message")]),
    ]

    result = prune_interrupted_tool_calls(messages)
    assert len(result) == 3
    assert result == messages


def test_deduplicate_tool_returns_basic():
    """Test that deduplicate_tool_returns removes duplicate tool returns."""
    messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="first result",
                    tool_call_id="call_1",
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="duplicate result",  # This should be removed
                    tool_call_id="call_1",
                )
            ]
        ),
    ]

    result = deduplicate_tool_returns(messages)

    # Should have 2 messages: the tool call and the first tool return
    assert len(result) == 2

    # Check that only the first return is kept
    tool_returns = [
        part
        for msg in result
        for part in msg.parts
        if hasattr(part, "part_kind") and part.part_kind == "tool-return"
    ]
    assert len(tool_returns) == 1
    assert tool_returns[0].content == "first result"


@patch("code_puppy.message_history_processor.get_message_history")
@patch("code_puppy.message_history_processor.set_message_history")
@patch("code_puppy.message_history_processor.message_history_processor")
def test_message_history_accumulator_calls_deduplicator(
    mock_processor, mock_set_history, mock_get_history
):
    """Test that message_history_accumulator calls deduplicate_tool_returns."""
    # Setup mock return values
    existing_messages = [ModelRequest(parts=[TextPart("existing message")])]
    mock_get_history.return_value = existing_messages

    new_messages = [
        ModelResponse(
            parts=[
                ToolCallPart(
                    tool_call_id="call_1",
                    tool_name="test_tool",
                    args={"param": "value"},
                )
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test_tool",
                    content="result",
                    tool_call_id="call_1",
                )
            ]
        ),
    ]

    # Call the accumulator
    message_history_accumulator(new_messages)

    # Verify that set_message_history was called (indicating deduplication happened)
    assert mock_set_history.called

    # Verify that message_history_processor was called at the end
    assert mock_processor.called
