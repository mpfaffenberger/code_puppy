"""Explicit provider routes must serialize typed media without real requests."""

import base64
import json

import httpx2
import pytest
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import override_allow_model_requests

from code_puppy.model_factory import ModelFactory


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model_type,path,part_type",
    [
        ("custom_openai", "/v1/chat/completions", "image_url"),
        ("custom_openai_responses", "/v1/responses", "input_image"),
    ],
)
async def test_explicit_route_serializes_image(model_type, path, part_type):
    requests = []
    image = b"provider-contract-not-a-vision-test"

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        if path.endswith("chat/completions"):
            body = {
                "id": "chat_test",
                "object": "chat.completion",
                "created": 1,
                "model": "contract",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "received"},
                    }
                ],
            }
        else:
            body = {
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "model": "contract",
                "status": "completed",
                "error": None,
                "incomplete_details": None,
                "output": [
                    {
                        "type": "message",
                        "id": "msg_test",
                        "status": "completed",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "received",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            }
        return httpx2.Response(200, json=body)

    config = {
        "contract": {
            "type": model_type,
            "name": "contract",
            "custom_endpoint": {
                "url": "https://contract.invalid/v1",
                "api_key": "test-only",
            },
        }
    }
    model = ModelFactory.get_model("contract", config)
    client = model._provider.client._client
    # Replace the network boundary, retaining the actual factory and serializer.
    client._transport = httpx2.MockTransport(handler)
    client._mounts = {}
    try:
        with override_allow_model_requests(True):
            result = await Agent(model).run(
                ["inspect", BinaryContent(data=image, media_type="image/png")]
            )
        assert result.output == "received"
        assert len(requests) == 1  # No silent protocol fallback or replay.
        assert requests[0][0] == path
        payload = requests[0][1]
        parts = [
            part
            for item in payload.get("messages", payload.get("input", []))
            if isinstance(item.get("content"), list)
            for part in item["content"]
        ]
        images = [part for part in parts if part.get("type") == part_type]
        assert len(images) == 1
        encoded = images[0]["image_url"]
        if isinstance(encoded, dict):
            encoded = encoded["url"]
        assert encoded == "data:image/png;base64," + base64.b64encode(image).decode()
    finally:
        await client.aclose()
