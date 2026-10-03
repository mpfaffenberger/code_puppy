"""Provider response aliases must not discard measured request usage."""

import json

import httpx2 as httpx
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from code_puppy.agents._model_message_transform import build_model_message_transform
from code_puppy.context_accounting import context_tokens, model_names


@pytest.mark.parametrize("streaming", [False, True])
async def test_real_anthropic_response_alias_anchors_and_survives_resume(streaming):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["model"] == "claude-sonnet-4-5"
        if streaming:
            events = [
                (
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": "msg_alias",
                            "type": "message",
                            "role": "assistant",
                            "model": "claude-sonnet-4-5-20250929",
                            "content": [],
                            "stop_reason": None,
                            "stop_sequence": None,
                            "usage": {"input_tokens": 5000, "output_tokens": 0},
                        },
                    },
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "hello"},
                    },
                ),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                (
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": 7},
                    },
                ),
                ("message_stop", {"type": "message_stop"}),
            ]
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="".join(
                    f"event: {event}\ndata: {json.dumps(data)}\n\n"
                    for event, data in events
                ),
            )
        return httpx.Response(
            200,
            json={
                "id": "msg_alias",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5-20250929",
                "content": [{"type": "text", "text": "hello"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 5000, "output_tokens": 7},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        model = AnthropicModel(
            "claude-sonnet-4-5",
            provider=AnthropicProvider(
                anthropic_client=AsyncAnthropic(api_key="test", http_client=client)
            ),
        )

        async def consume(ctx, events):
            async for event in events:
                pass

        result = await Agent(
            model, capabilities=[build_model_message_transform("alias-test")]
        ).run("hello", event_stream_handler=consume if streaming else None)
    history = result.all_messages()
    assert history[-1].model_name == "claude-sonnet-4-5-20250929"
    assert context_tokens(history, model_names(model)) == 5007
    loaded = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json(history)
    )
    assert context_tokens(loaded, model_names(model)) == 5007
    assert context_tokens(loaded, "claude-sonnet-4-5-20250929") < 5000
    assert context_tokens(loaded, "different-model") < 5000


@pytest.mark.parametrize("changed", ["candidate", "router", "missing", "malformed"])
def test_request_identity_requires_same_router_and_candidates(changed):
    from pydantic_ai.messages import (
        ModelRequest,
        ModelResponse,
        TextPart,
        UserPromptPart,
    )
    from pydantic_ai.usage import RequestUsage

    from code_puppy.context_accounting import record_anchor

    prefix = [ModelRequest(parts=[UserPromptPart("hello")])]
    response = ModelResponse(
        parts=[TextPart("done")],
        model_name="provider-alias",
        usage=RequestUsage(input_tokens=5000, output_tokens=7),
    )
    names = frozenset({"router", "candidate-a", "candidate-b"})
    record_anchor(prefix, response, request_model=names)
    history = [*prefix, response]
    assert context_tokens(history, names) == 5007
    if changed == "candidate":
        names = frozenset({"router", "candidate-a", "candidate-c"})
    elif changed == "router":
        names = frozenset({"other-router", "candidate-a", "candidate-b"})
    elif changed == "missing":
        response.metadata["context_anchor"].pop("request_models")
    else:
        response.metadata["context_anchor"]["request_models"] = "router"
    assert context_tokens(history, names) < 5000
