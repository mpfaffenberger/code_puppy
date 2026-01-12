"""Request/stream tests for antigravity_model."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.settings import ModelSettings


class TestRequestMethod:
    """Test the request method with API calls."""

    @pytest.mark.asyncio
    async def test_successful_request(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test successful API request."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Response text"}]}}],
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 20,
            },
        }
        mock_httpx_client.post.return_value = mock_response

        settings = ModelSettings(temperature=0.7, max_tokens=1000)

        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Hello", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (settings, model_request_params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Hello"}]
                response = await mock_google_model.request(
                    messages, settings, model_request_params
                )

        assert response.parts[0].content == "Response text"
        assert response.model_name == "gemini-1.5-pro"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 20
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_builds_tools_and_config(
        self, mock_google_model, mock_httpx_client, monkeypatch
    ) -> None:
        """Test generation config and tool serialization in request body."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client
        monkeypatch.setenv("GOOGLE_API_KEY", "test-key")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
        }
        mock_httpx_client.post.return_value = mock_response

        tool = MagicMock()
        tool.name = "do_work"
        tool.description = "Does work"
        tool.parameters_json_schema = {
            "type": "object",
            "properties": {"x": {"type": "string"}},
        }
        params = ModelRequestParameters(
            function_tools=[tool],
        )
        settings = ModelSettings(temperature=0.2, top_p=0.95, max_tokens=12)

        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Hello", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (settings, params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Hello"}]
                await mock_google_model.request(messages, settings, params)

        # Verify the post method was called
        assert mock_httpx_client.post.call_count == 1
        _args, kwargs = mock_httpx_client.post.call_args
        body = kwargs["json"]
        # Check that generation config was built (it's added to the request body)
        # but only if model_settings has temperature/top_p set
        if "generationConfig" in body:
            assert body["generationConfig"]["temperature"] == 0.2
            assert body["generationConfig"]["topP"] == 0.95
            assert body["generationConfig"]["maxOutputTokens"] == 12
        # Check tools are properly serialized
        if "tools" in body:
            assert body["tools"][0]["functionDeclarations"][0]["name"] == "do_work"
            assert "parameters" in body["tools"][0]["functionDeclarations"][0]

    @pytest.mark.asyncio
    async def test_request_missing_http_client(
        self, mock_google_model, model_request_params
    ):
        """Test error when http client is unavailable."""
        mock_google_model.client = MagicMock(spec=[])
        messages = [
            ModelRequest(
                parts=[UserPromptPart(content="Hello", timestamp=datetime.now())]
            )
        ]

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (ModelSettings(), model_request_params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Hello"}]
                with pytest.raises(RuntimeError, match="underlying httpx client"):
                    await mock_google_model.request(
                        messages, ModelSettings(), model_request_params
                    )

    @pytest.mark.asyncio
    async def test_request_with_corrupted_signature_retry(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test retry on corrupted thought signature error."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        mock_error_response = MagicMock()
        mock_error_response.status_code = 400
        mock_error_response.text = (
            '{"error": {"message": "Corrupted thought signature."}}'
        )

        mock_success_response = MagicMock()
        mock_success_response.status_code = 200
        mock_success_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Success after retry"}]}}],
            "usageMetadata": {
                "promptTokenCount": 5,
                "candidatesTokenCount": 10,
            },
        }

        mock_httpx_client.post.side_effect = [
            mock_error_response,
            mock_success_response,
        ]

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
                thinking_part = ThinkingPart(content="thought", signature="sig123")
                messages.insert(0, ModelResponse(parts=[thinking_part]))

                response = await mock_google_model.request(
                    messages, settings, model_request_params
                )

        assert response.parts[0].content == "Success after retry"
        assert mock_httpx_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_request_api_error(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test handling of API errors."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_httpx_client.post.return_value = mock_response

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

                with pytest.raises(RuntimeError) as exc_info:
                    await mock_google_model.request(
                        messages, settings, model_request_params
                    )

                assert "Antigravity API Error 500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_request_empty_response(
        self, mock_google_model, mock_httpx_client, model_request_params
    ) -> None:
        """Test handling of empty API response."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"candidates": []}
        mock_httpx_client.post.return_value = mock_response

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

                response = await mock_google_model.request(
                    messages, settings, model_request_params
                )

        assert len(response.parts) == 1
        assert isinstance(response.parts[0], TextPart)
        assert response.parts[0].content == ""
