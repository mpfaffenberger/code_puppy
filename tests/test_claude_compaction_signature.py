"""The Claude OAuth identity must stay a standalone system block.

Compaction summaries ride the user channel, so the identity never merges with
them; the splitter still repairs a merged system string defensively.
"""

import json

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai import Agent
from pydantic_ai.messages import (
    CompactionPart,
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
    ["\n\nAppended instructions: preserved", " extra instructions", "\n"],
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
            model,
            system_prompt=SIGNATURE,
            instructions="Actual agent instructions",
            model_settings={"max_tokens": 1024},
        )
        history = [
            ModelRequest(parts=[SystemPromptPart(SIGNATURE)]),
            ModelRequest(
                parts=[
                    CompactionPart(
                        "Summary: preserved",
                        metadata={"pydantic-ai-harness.compaction.summary.v1": True},
                    )
                ]
            ),
            ModelRequest(parts=[UserPromptPart("earlier")]),
            ModelResponse(parts=[TextPart("earlier reply")]),
        ]
        await agent.run("continue", message_history=history)
    assert len(captured) == 1
    system = captured[0]["system"]
    # pydantic-ai adds its own block explaining the ``<system>`` tag after the
    # leading system prompts on profiles without inline system prompts; the
    # signature stays a standalone first block and nothing is merged into it.
    assert system[0] == {"type": "text", "text": SIGNATURE}
    assert system[-1] == {"type": "text", "text": "Actual agent instructions"}
    assert all(
        block["text"].startswith("\n\nMid-conversation system messages")
        for block in system[1:-1]
    )
    user_text = json.dumps(captured[0]["messages"])
    assert "<conversation_summary>" in user_text
    assert "Summary: preserved" in user_text
