"""Integration-style tests for antigravity_model."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.settings import ModelSettings

from code_puppy.plugins.antigravity_oauth.antigravity_model import (
    _antigravity_content_model_response,
)


class TestIntegrationScenarios:
    """Integration tests for complex scenarios."""

    @pytest.mark.asyncio
    async def test_full_conversation_flow(
        self, mock_google_model, mock_httpx_client
    ) -> None:
        """Test full conversation flow with multiple message types."""
        mock_google_model.client._api_client._async_httpx_client = mock_httpx_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "thinking...", "thought": True},
                            {
                                "functionCall": {
                                    "name": "process_data",
                                    "args": {"data": "test"},
                                }
                            },
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 50,
                "candidatesTokenCount": 25,
            },
            "requestId": "req-123",
        }
        mock_httpx_client.post.return_value = mock_response

        messages = [
            ModelRequest(parts=[SystemPromptPart(content="Be helpful")]),
            ModelRequest(
                parts=[UserPromptPart(content="Hello", timestamp=datetime.now())]
            ),
            ModelResponse(parts=[TextPart(content="Hi there")]),
            ModelRequest(
                parts=[
                    ToolReturnPart(
                        tool_name="get_data",
                        content="result",
                        tool_call_id="call_1",
                    )
                ]
            ),
        ]

        settings = ModelSettings(temperature=0.5, max_tokens=500)
        params = ModelRequestParameters(
            function_tools=[],
            allow_text_output=True,
        )

        with patch.object(mock_google_model, "prepare_request") as mock_prepare:
            mock_prepare.return_value = (settings, params)
            with patch.object(mock_google_model, "_map_user_prompt") as mock_map:
                mock_map.return_value = [{"text": "Hello"}]

                response = await mock_google_model.request(messages, settings, params)

        assert len(response.parts) >= 1
        assert response.usage.input_tokens == 50
        assert response.usage.output_tokens == 25
        assert response.provider_response_id == "req-123"

    def test_claude_vs_gemini_signature_protocols(self) -> None:
        """Test difference between Claude and Gemini signature protocols.

        Both try original signatures first. Bypass only happens on error retry.
        - Claude: signature goes ON the thinking block
        - Gemini: signature goes on the NEXT part after thinking
        """
        model_response = ModelResponse(
            parts=[
                ThinkingPart(content="thinking", signature="original_sig_123"),
                ToolCallPart(tool_name="tool", args={}),
            ]
        )

        claude_result = _antigravity_content_model_response(
            model_response, provider_name="anthropic", model_name="claude-3-5-sonnet"
        )

        gemini_result = _antigravity_content_model_response(
            model_response, provider_name="google", model_name="gemini-1.5-pro"
        )

        # Claude: signature ON the thinking block (original, bypass only on error)
        assert len(claude_result["parts"]) == 2
        assert claude_result["parts"][0]["thought"] is True
        assert claude_result["parts"][0]["thoughtSignature"] == "original_sig_123"
        assert "function_call" in claude_result["parts"][1]

        # Gemini: signature on NEXT part (function call)
        assert "thoughtSignature" not in gemini_result["parts"][0]
        assert gemini_result["parts"][1]["thoughtSignature"] == "original_sig_123"
