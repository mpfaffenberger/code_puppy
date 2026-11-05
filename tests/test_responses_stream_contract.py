"""Actual Responses SSE parser must retain image-bearing requests."""

import base64
import json

import httpx2
import pytest
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import override_allow_model_requests

from code_puppy.model_factory import ModelFactory


@pytest.mark.asyncio
async def test_responses_stream_serializes_image_and_reads_text_events():
    requests = []
    image = b"stream-image-contract"
    message = {
        "type": "message",
        "id": "msg_stream",
        "status": "in_progress",
        "role": "assistant",
        "content": [],
    }
    content = {"type": "output_text", "text": "", "annotations": []}
    completed_message = {
        **message,
        "status": "completed",
        "content": [{**content, "text": "received"}],
    }
    completed = {
        "id": "resp_stream",
        "object": "response",
        "created_at": 1,
        "model": "opaque-server-model",
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "output": [completed_message],
    }
    events = [
        {
            "type": "response.created",
            "response": {**completed, "output": [], "status": "in_progress"},
        },
        {"type": "response.output_item.added", "output_index": 0, "item": message},
        {
            "type": "response.content_part.added",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "part": content,
        },
        {
            "type": "response.output_text.delta",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "delta": "received",
        },
        {
            "type": "response.output_text.done",
            "output_index": 0,
            "content_index": 0,
            "item_id": "msg_stream",
            "text": "received",
        },
        {
            "type": "response.output_item.done",
            "output_index": 0,
            "item": completed_message,
        },
        {"type": "response.completed", "response": completed},
    ]
    wire = "".join(
        f"event: {event['type']}\ndata: {json.dumps({**event, 'sequence_number': index})}\n\n"
        for index, event in enumerate(events)
    )

    def handler(request):
        requests.append((request.url.path, json.loads(request.content)))
        return httpx2.Response(
            200, content=wire.encode(), headers={"content-type": "text/event-stream"}
        )

    model = ModelFactory.get_model(
        "vision-stream",
        {
            "vision-stream": {
                "type": "custom_openai_responses",
                "name": "opaque-server-model",
                "custom_endpoint": {
                    "url": "https://stream.invalid/v1",
                    "api_key": "test-only",
                },
            }
        },
    )
    client = model._provider.client._client
    client._transport = httpx2.MockTransport(handler)
    client._mounts = {}
    try:
        with override_allow_model_requests(True):
            async with Agent(model).run_stream(
                ["inspect", BinaryContent(data=image, media_type="image/png")]
            ) as result:
                chunks = [chunk async for chunk in result.stream_text()]
                assert await result.get_output() == "received"
        assert chunks[-1] == "received"
        assert len(requests) == 1
        path, payload = requests[0]
        assert path == "/v1/responses"
        assert payload["stream"] is True
        parts = [
            part
            for item in payload["input"]
            if isinstance(item.get("content"), list)
            for part in item["content"]
        ]
        images = [part for part in parts if part["type"] == "input_image"]
        assert len(images) == 1
        assert images[0]["image_url"] == (
            "data:image/png;base64," + base64.b64encode(image).decode()
        )
    finally:
        await client.aclose()
