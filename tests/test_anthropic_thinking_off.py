"""The configured thinking mode must reach Anthropic's request body."""

import json
from unittest.mock import patch

import httpx2
import pytest
from pydantic_ai import Agent

from code_puppy.claude_cache_client import ClaudeCacheAsyncClient
from code_puppy.model_factory import ModelFactory, make_model_settings


@pytest.mark.parametrize(
    "model_name, mode, expected_thinking",
    [
        ("claude-opus-5", "off", {"type": "disabled"}),
        ("claude-sonnet-5", "off", {"type": "disabled"}),
        ("claude-opus-5", False, {"type": "disabled"}),
        ("us.anthropic.claude-opus-5-v1:0", "off", {"type": "disabled"}),
        ("anthropic.claude-sonnet-5-v1:0", "off", {"type": "disabled"}),
        ("claude-haiku-5-5", "off", {"type": "disabled"}),
        ("claude-sonnet-5-5", "off", {"type": "between_tools"}),
        ("claude-fable-5", "off", None),
        ("claude-opus-5-5", "off", None),
        ("claude-sonnet-4-5", "off", None),
    ],
)
async def test_thinking_off_request(model_name, mode, expected_thinking):
    """Disable default thinking without sending unsupported off switches."""
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": model_name,
                "content": [{"type": "text", "text": "Hello"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    config = {
        "my-model": {
            "type": "custom_anthropic",
            "name": model_name,
            "custom_endpoint": {
                "url": "https://example.test/v1",
                "api_key": "test-key",
            },
            "supported_settings": ["extended_thinking", "effort"],
        }
    }
    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(respond)
    ) as client:
        with (
            patch.object(ModelFactory, "load_config", return_value=config),
            patch(
                "code_puppy.config.get_effective_model_settings",
                return_value={"extended_thinking": mode, "effort": "max"},
            ),
            patch("code_puppy.config.get_custom_model_settings", return_value={}),
            patch(
                "code_puppy.model_factory.ClaudeCacheAsyncClient", return_value=client
            ),
        ):
            model = ModelFactory.get_model("my-model", config)
            settings = make_model_settings("my-model", max_tokens=1024)
            result = await Agent(model, model_settings=settings).run("Hello")

    assert result.output == "Hello"
    assert len(requests) == 1
    body = requests[0]
    if expected_thinking is None:
        assert "thinking" not in body
    else:
        assert body.get("thinking") == expected_thinking
    assert "output_config" not in body
