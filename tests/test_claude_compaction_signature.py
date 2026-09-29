"""Compaction must not merge the OAuth identity with the summary on the wire."""

import json

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from code_puppy.claude_cache_client import (
    CLAUDE_CODE_SYSTEM_PROMPT as SIGNATURE,
)
from code_puppy.claude_cache_client import ClaudeCacheAsyncClient


@pytest.mark.parametrize("as_blocks", [False, True])
@pytest.mark.parametrize(
    "suffix",
    ["\n\nSummary of prior conversation: preserved", " extra instructions", "\n"],
)
def test_split_merged_signature_preserves_content_and_metadata(as_blocks, suffix):
    merged = SIGNATURE + suffix
    cache = {"type": "ephemeral", "ttl": "1h"}
    system = (
        [
            {"type": "text", "text": merged, "cache_control": cache},
            {"type": "text", "text": "Agent instructions"},
        ]
        if as_blocks
        else merged
    )
    original = {"system": system, "messages": [], "model": "claude-sonnet-5"}
    result = ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(
        json.dumps(original).encode()
    )
    assert result is not None
    data = json.loads(result)
    assert data["system"][0] == {"type": "text", "text": SIGNATURE}
    assert data["system"][1]["text"] == suffix
    if as_blocks:
        assert data["system"][1]["cache_control"] == cache
        assert data["system"][2] == system[1]
    assert data["messages"] == original["messages"]
    assert ClaudeCacheAsyncClient._ensure_claude_code_system_prompt(result) is None


@pytest.mark.asyncio
async def test_real_sdk_compacted_history_has_standalone_signature():
    captured = []

    def transport(request):
        captured.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "offline-test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async with ClaudeCacheAsyncClient(
        apply_claude_code_prefix=True, transport=httpx2.MockTransport(transport)
    ) as client:
        sdk = AsyncAnthropic(
            auth_token="offline-placeholder", http_client=client, max_retries=0
        )
        model = AnthropicModel(
            "claude-sonnet-5", provider=AnthropicProvider(anthropic_client=sdk)
        )
        agent = Agent(
            model, system_prompt=SIGNATURE, instructions="Actual agent instructions"
        )
        history = [
            ModelRequest(
                parts=[
                    SystemPromptPart(SIGNATURE),
                    SystemPromptPart("Summary: preserved"),
                ]
            ),
            ModelRequest(parts=[UserPromptPart("earlier")]),
            ModelResponse(parts=[TextPart("earlier reply")]),
        ]
        await agent.run("continue", message_history=history)
    assert len(captured) == 1
    assert captured[0]["system"] == [
        {"type": "text", "text": SIGNATURE},
        {"type": "text", "text": "\n\nSummary: preserved"},
        {"type": "text", "text": "Actual agent instructions"},
    ]
