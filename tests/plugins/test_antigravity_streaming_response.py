"""AntigravityStreamingResponse tests."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic_ai.models import ModelRequestParameters

from code_puppy.plugins.antigravity_oauth.antigravity_model import (
    AntigravityStreamingResponse,
)


class TestAntigravityStreamingResponse:
    """Test AntigravityStreamingResponse class."""

    @pytest.mark.asyncio
    async def test_streaming_response_properties(self) -> None:
        """Test streaming response properties."""

        async def mock_chunks():
            yield {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}

        params = ModelRequestParameters(
            function_tools=[], allow_text_output=True, output_tools=[]
        )

        stream = AntigravityStreamingResponse(
            model_request_parameters=params,
            _chunks=mock_chunks(),
            _model_name_str="gemini-1.5-pro",
            _provider_name_str="google",
        )

        assert stream.model_name == "gemini-1.5-pro"
        assert stream.provider_name == "google"
        assert isinstance(stream.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_streaming_with_usage_metadata(self) -> None:
        """Test streaming with usage metadata."""

        async def mock_chunks():
            yield {
                "candidates": [{"content": {"parts": [{"text": "Hello"}]}}],
                "usageMetadata": {
                    "promptTokenCount": 5,
                    "candidatesTokenCount": 10,
                },
            }

        params = ModelRequestParameters(
            function_tools=[], allow_text_output=True, output_tools=[]
        )

        stream = AntigravityStreamingResponse(
            model_request_parameters=params,
            _chunks=mock_chunks(),
            _model_name_str="gemini-1.5-pro",
        )

        async for _ in stream._get_event_iterator():
            pass

        assert stream._usage.input_tokens == 5
        assert stream._usage.output_tokens == 10

    @pytest.mark.asyncio
    async def test_streaming_claude_signature_handling(self) -> None:
        """Test streaming signature handling for Claude."""

        async def mock_chunks():
            yield {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": "thinking...",
                                    "thought": True,
                                    "thoughtSignature": "sig123",
                                }
                            ]
                        }
                    }
                ],
                "responseId": "resp-123",
            }

        params = ModelRequestParameters(
            function_tools=[], allow_text_output=True, output_tools=[]
        )

        stream = AntigravityStreamingResponse(
            model_request_parameters=params,
            _chunks=mock_chunks(),
            _model_name_str="claude-3-5-sonnet",
        )

        events = []
        async for event in stream._get_event_iterator():
            events.append(event)

        assert stream.provider_response_id == "resp-123"
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_streaming_gemini_thinking_with_signature(self) -> None:
        """Test streaming thinking block with signature for Gemini."""

        async def mock_chunks():
            yield {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "thinking...", "thought": True},
                                {"text": "Hello", "thoughtSignature": "sig456"},
                            ]
                        }
                    }
                ]
            }

        params = ModelRequestParameters(
            function_tools=[], allow_text_output=True, output_tools=[]
        )

        stream = AntigravityStreamingResponse(
            model_request_parameters=params,
            _chunks=mock_chunks(),
            _model_name_str="gemini-1.5-pro",
        )

        events = []
        async for event in stream._get_event_iterator():
            events.append(event)

        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_streaming_function_call_signature(self) -> None:
        """Test streaming function call with signature for Gemini."""

        async def mock_chunks():
            yield {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "think", "thought": True},
                                {
                                    "functionCall": {
                                        "name": "test_tool",
                                        "args": {"x": 1},
                                    },
                                    "thoughtSignature": "sig789",
                                },
                            ]
                        }
                    }
                ]
            }

        params = ModelRequestParameters(
            function_tools=[], allow_text_output=True, output_tools=[]
        )

        stream = AntigravityStreamingResponse(
            model_request_parameters=params,
            _chunks=mock_chunks(),
            _model_name_str="gemini-1.5-pro",
        )

        events = []
        async for event in stream._get_event_iterator():
            events.append(event)

        assert len(events) >= 2
