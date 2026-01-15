"""Message mapping tests for antigravity_model."""

from __future__ import annotations

import base64
from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolReturnPart,
    UserPromptPart,
)


class TestMessageMapping:
    """Test _map_messages method with various message types."""

    @pytest.mark.asyncio
    async def test_map_empty_messages(self, mock_google_model, model_request_params):
        """Test mapping empty message list."""
        messages = []
        system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert system_instruction is None
        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"] == [{"text": ""}]

    @pytest.mark.asyncio
    async def test_map_system_prompt(self, mock_google_model, model_request_params):
        """Test mapping system prompt messages."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="You are helpful")])]

        with patch.object(mock_google_model, "_get_instructions", return_value=None):
            system_instruction, contents = await mock_google_model._map_messages(
                messages, model_request_params
            )

        assert system_instruction is not None
        assert len(system_instruction["parts"]) == 1
        assert system_instruction["parts"][0]["text"] == "You are helpful"
        assert contents[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_map_instructions_injected(
        self, mock_google_model, model_request_params
    ):
        """Test that injected instructions are prepended to system parts."""
        messages = [ModelRequest(parts=[SystemPromptPart(content="Base system")])]

        with patch.object(
            mock_google_model, "_get_instructions", return_value="Injected"
        ):
            system_instruction, _contents = await mock_google_model._map_messages(
                messages, model_request_params
            )

        assert system_instruction is not None
        assert system_instruction["parts"][0]["text"] == "Injected"
        assert system_instruction["parts"][1]["text"] == "Base system"

    @pytest.mark.asyncio
    async def test_map_user_prompt(self, mock_google_model, model_request_params):
        """Test mapping user prompt messages."""
        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Hello", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
            mock_map.return_value = [{"text": "Hello"}]
            _system_instruction, contents = await mock_google_model._map_messages(
                messages, model_request_params
            )

        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"] == [{"text": "Hello"}]

    @pytest.mark.asyncio
    async def test_map_tool_return_part(self, mock_google_model, model_request_params):
        """Test mapping tool return parts."""
        messages = [
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="test_tool",
                        content="test result",
                        tool_call_id="call_123",
                    )
                ]
            )
        ]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        part = contents[0]["parts"][0]
        assert "function_response" in part
        assert part["function_response"]["name"] == "test_tool"
        assert part["function_response"]["id"] == "call_123"

    @pytest.mark.asyncio
    async def test_map_retry_prompt_without_tool(
        self, mock_google_model, model_request_params
    ):
        """Test mapping retry prompt without tool name."""
        messages = [
            ModelRequest(
                parts=[RetryPromptPart(content="Please try again", tool_name=None)]
            )
        ]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        part = contents[0]["parts"][0]
        assert "text" in part

    @pytest.mark.asyncio
    async def test_map_retry_prompt_with_tool(
        self, mock_google_model, model_request_params
    ):
        """Test mapping retry prompt with tool name."""
        messages = [
            ModelRequest(
                parts=[
                    RetryPromptPart(
                        content="Invalid parameter",
                        tool_name="test_tool",
                        tool_call_id="call_123",
                    )
                ]
            )
        ]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        part = contents[0]["parts"][0]
        assert "function_response" in part
        assert part["function_response"]["name"] == "test_tool"
        assert "response" in part["function_response"]
        assert "error" in part["function_response"]["response"]

    @pytest.mark.asyncio
    async def test_map_model_response_with_text(
        self, mock_google_model, model_request_params
    ):
        """Test mapping model response with text parts."""
        messages = [ModelResponse(parts=[TextPart(content="Hello from AI")])]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        assert contents[0]["role"] == "model"
        assert len(contents[0]["parts"]) == 1
        assert contents[0]["parts"][0]["text"] == "Hello from AI"

    @pytest.mark.asyncio
    async def test_map_file_part_with_bytes(
        self, mock_google_model, model_request_params
    ):
        """Test mapping file part with bytes data via user prompt."""
        image_data = b"fake_image_data"
        messages = [
            ModelRequest(
                parts=[
                    UserPromptPart(content="Check this image", timestamp=datetime.now())
                ]
            )
        ]

        with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
            # Mock _map_user_prompt to return parts with bytes data
            mock_map.return_value = [
                {"text": "Check this image"},
                {
                    "inline_data": {
                        "data": image_data,
                        "mime_type": "image/jpeg",
                    }
                },
            ]
            _system_instruction, contents = await mock_google_model._map_messages(
                messages, model_request_params
            )

        # Check that bytes were converted to base64 string
        assert len(contents[0]["parts"]) == 2
        part = contents[0]["parts"][1]
        assert "inline_data" in part
        assert isinstance(part["inline_data"]["data"], str)
        assert part["inline_data"]["data"] == base64.b64encode(image_data).decode(
            "utf-8"
        )

    @pytest.mark.asyncio
    async def test_merge_consecutive_user_messages(
        self, mock_google_model, model_request_params
    ):
        """Test that consecutive user messages are merged."""
        messages = [
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="tool1",
                        content="result1",
                        tool_call_id="call_1",
                    )
                ]
            ),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="tool2",
                        content="result2",
                        tool_call_id="call_2",
                    )
                ]
            ),
        ]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert len(contents[0]["parts"]) == 2

    @pytest.mark.asyncio
    async def test_merge_consecutive_model_messages(
        self, mock_google_model, model_request_params
    ):
        """Test that consecutive model messages are merged."""
        messages = [
            ModelResponse(parts=[TextPart(content="Part 1")]),
            ModelResponse(parts=[TextPart(content="Part 2")]),
        ]

        _system_instruction, contents = await mock_google_model._map_messages(
            messages, model_request_params
        )

        assert len(contents) == 1
        assert contents[0]["role"] == "model"
        assert len(contents[0]["parts"]) == 2
