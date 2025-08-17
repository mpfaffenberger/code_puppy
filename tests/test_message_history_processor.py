from unittest.mock import patch, MagicMock

from code_puppy.message_history_processor import (
    stringify_message_part,
    estimate_tokens_for_message,
    summarize_message,
)


class MockPart:
    def __init__(self, content=None, tool_name=None, args=None):
        self.content = content
        self.tool_name = tool_name
        self.args = args


class MockMessage:
    def __init__(self, parts, role="user"):
        self.parts = parts
        self.role = role


def test_stringify_message_part_with_string_content():
    part = MockPart(content="Hello, world!")
    result = stringify_message_part(part)
    assert result == "Hello, world!"


def test_stringify_message_part_with_dict_content():
    part = MockPart(content={"key": "value"})
    result = stringify_message_part(part)
    assert result == '{"key": "value"}'


def test_stringify_message_part_with_tool_call():
    part = MockPart(tool_name="test_tool", args={"param": "value"})
    result = stringify_message_part(part)
    assert "test_tool" in result
    assert "param" in result
    assert "value" in result


def test_stringify_message_part_with_content_and_tool_call():
    part = MockPart(
        content="Hello, world!", tool_name="test_tool", args={"param": "value"}
    )
    result = stringify_message_part(part)
    # Should contain both content and tool call info
    assert "Hello, world!" in result
    assert "test_tool" in result
    assert "param" in result
    assert "value" in result


@patch("code_puppy.message_history_processor.get_tokenizer_for_model")
@patch("code_puppy.message_history_processor.get_model_name")
def test_estimate_tokens_for_message(mock_get_model_name, mock_get_tokenizer):
    # Mock the tokenizer to return a predictable number of tokens
    mock_tokenizer = MagicMock()
    mock_tokenizer.encode.return_value = [1, 2, 3, 4, 5]  # 5 tokens
    mock_get_tokenizer.return_value = mock_tokenizer
    mock_get_model_name.return_value = "test-model"

    # Create a mock message with one part
    part = MockPart(content="test content")
    message = MockMessage([part])

    # Test the function
    result = estimate_tokens_for_message(message)

    # Should return the number of tokens (5) but at least 1
    assert result == 5

    # Verify the tokenizer was called with the stringified content
    mock_tokenizer.encode.assert_called_with("test content")


@patch("code_puppy.message_history_processor.get_tokenizer_for_model")
@patch("code_puppy.message_history_processor.get_model_name")
def test_estimate_tokens_for_message_minimum(mock_get_model_name, mock_get_tokenizer):
    # Mock the tokenizer to return an empty list (0 tokens)
    mock_tokenizer = MagicMock()
    mock_tokenizer.encode.return_value = []  # 0 tokens
    mock_get_tokenizer.return_value = mock_tokenizer
    mock_get_model_name.return_value = "test-model"

    # Create a mock message with one part
    part = MockPart(content="")
    message = MockMessage([part])

    # Test the function
    result = estimate_tokens_for_message(message)

    # Should return at least 1 token
    assert result == 1


@patch("code_puppy.message_history_processor.SUMMARIZATION_AVAILABLE", True)
@patch("code_puppy.message_history_processor.get_summarization_agent")
def test_summarize_message(mock_get_summarization_agent):
    # Mock the summarization agent to return a predictable result
    mock_result = MagicMock()
    mock_result.output = "Summarized content"
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value = mock_result
    mock_get_summarization_agent.return_value = mock_agent

    # Create a proper ModelRequest message with content
    from pydantic_ai.messages import ModelRequest, TextPart

    part = TextPart("Long message content that should be summarized")
    message = ModelRequest([part])

    # Test the function
    result = summarize_message(message)

    # Verify the summarization agent was called with the right prompt
    mock_agent.run_sync.assert_called_once()
    call_args = mock_agent.run_sync.call_args[0][0]
    assert "Please summarize the following user message:" in call_args
    assert "Long message content that should be summarized" in call_args

    # Verify the result has the summarized content
    assert len(result.parts) == 1
    assert hasattr(result.parts[0], "content")
    assert result.parts[0].content == "Summarized content"

    # Verify it's still a ModelRequest
    assert isinstance(result, ModelRequest)


@patch("code_puppy.message_history_processor.SUMMARIZATION_AVAILABLE", True)
@patch("code_puppy.message_history_processor.get_summarization_agent")
def test_summarize_message_with_tool_call(mock_get_summarization_agent):
    # Mock the summarization agent to return a predictable result
    mock_result = MagicMock()
    mock_result.output = "Summarized content"
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value = mock_result
    mock_get_summarization_agent.return_value = mock_agent

    # Create a proper ModelRequest message with a tool call - should not be summarized
    from pydantic_ai.messages import ModelRequest, ToolCallPart

    part = ToolCallPart(tool_name="test_tool", args={"param": "value"})
    message = ModelRequest([part])

    # Test the function
    result = summarize_message(message)

    # Should return the original message unchanged
    assert result == message

    # Verify the summarization agent was not called
    mock_agent.run_sync.assert_not_called()


@patch("code_puppy.message_history_processor.SUMMARIZATION_AVAILABLE", True)
@patch("code_puppy.message_history_processor.get_summarization_agent")
def test_summarize_message_system_role(mock_get_summarization_agent):
    # Mock the summarization agent to return a predictable result
    mock_result = MagicMock()
    mock_result.output = "Summarized content"
    mock_agent = MagicMock()
    mock_agent.run_sync.return_value = mock_result
    mock_get_summarization_agent.return_value = mock_agent

    # Create a proper ModelRequest system message - should not be summarized
    from pydantic_ai.messages import ModelRequest, TextPart

    part = TextPart("System message content")
    # Create a ModelRequest with instructions to simulate a system message
    message = ModelRequest([part])
    message.instructions = "System instructions"

    # Test the function
    result = summarize_message(message)

    # Should return the original message unchanged
    assert result == message

    # Verify the summarization agent was not called
    mock_agent.run_sync.assert_not_called()


@patch("code_puppy.message_history_processor.SUMMARIZATION_AVAILABLE", True)
@patch("code_puppy.message_history_processor.get_summarization_agent")
def test_summarize_message_error_handling(mock_get_summarization_agent):
    # Create a mock agent that raises an exception when run_sync is called
    mock_agent = MagicMock()
    mock_agent.run_sync.side_effect = Exception("Summarization failed")
    mock_get_summarization_agent.return_value = mock_agent

    # Create a proper ModelRequest message with content
    from pydantic_ai.messages import ModelRequest, TextPart

    part = TextPart("Message content")
    message = ModelRequest([part])

    # Test the function
    result = summarize_message(message)

    # Should return the original message unchanged on error
    assert result == message

    # Verify the summarization agent was called
    mock_agent.run_sync.assert_called_once()
