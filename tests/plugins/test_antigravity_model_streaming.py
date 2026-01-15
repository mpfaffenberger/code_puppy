"""Streaming request tests for antigravity_model."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest
from pydantic_ai.messages import ModelRequest, UserPromptPart
from pydantic_ai.settings import ModelSettings


class TestStreamingMethod:
    """Test the request_stream method."""

    @pytest.mark.asyncio
    async def test_streaming_success(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test successful streaming request."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        def mock_stream(*args, **kwargs):
            class MockStream:
                status_code = 200

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return

                async def aiter_lines(self):
                    yield 'data: {"candidates": [{"content": {"parts": [{"text": "Hello"}]}}]}'
                    yield 'data: {"candidates": [{"content": {"parts": [{"text": " world"}]}}]}'

            return MockStream()

        mock_httpx_client.stream = mock_stream

        settings = ModelSettings()
        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Test", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (settings, model_request_params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Test"}]

                async with mock_google_model.request_stream(
                    messages, settings, model_request_params
                ) as stream:
                    chunks = []
                    async for chunk in stream._get_event_iterator():
                        chunks.append(chunk)

        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_streaming_corrupted_signature_retry(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test streaming with corrupted signature retry."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        call_count = 0

        def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            class MockStream:
                def __init__(self, should_fail):
                    self.should_fail = should_fail

                @property
                def status_code(self):
                    return 400 if call_count == 1 else 200

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return

                async def aread(self):
                    return b'{"error": {"message": "Corrupted thought signature."}}'

                async def aiter_lines(self):
                    if not self.should_fail:
                        yield 'data: {"candidates": [{"content": {"parts": [{"text": "Success"}]}}]}'

            return MockStream(call_count == 1)

        mock_httpx_client.stream = mock_stream

        settings = ModelSettings()
        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Test", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (settings, model_request_params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Test"}]
                with patch(
                    "code_puppy.plugins.antigravity_oauth.antigravity_model._backfill_thought_signatures"
                ):
                    async with mock_google_model.request_stream(
                        messages, settings, model_request_params
                    ) as stream:
                        chunks = []
                        async for chunk in stream._get_event_iterator():
                            chunks.append(chunk)

        assert call_count == 2
        assert len(chunks) > 0
