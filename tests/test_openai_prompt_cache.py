from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from code_puppy.openai_prompt_cache import (
    CACHE_ANCHOR,
    CacheAwareChatModel,
    CacheAwareResponsesModel,
    add_cache_boundary,
    preserve_openai_cache_tokens,
)


@pytest.fixture
def openai_provider():
    client = AsyncOpenAI(
        api_key="test",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda _: None)),
    )
    return OpenAIProvider(openai_client=client)


@pytest.mark.asyncio
async def test_responses_preserves_instructions_and_marks_one_boundary(
    openai_provider,
):
    model = CacheAwareResponsesModel("gpt-5.6-sol", provider=openai_provider)
    messages = [
        ModelRequest(
            parts=[UserPromptPart(add_cache_boundary("current task"))],
            instructions="developer instructions",
        )
    ]

    instructions, mapped = await model._map_messages(
        messages, {}, ModelRequestParameters()
    )

    assert instructions == "developer instructions"
    content = mapped[0]["content"]
    assert content[0]["text"] == CACHE_ANCHOR
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert content[1]["text"] == "current task"
    assert sum("prompt_cache_breakpoint" in item for item in content) == 1


@pytest.mark.asyncio
async def test_chat_preserves_system_message_and_attachment_order(openai_provider):
    model = CacheAwareChatModel("gpt-5.6", provider=openai_provider)
    attachment = SimpleNamespace(name="attachment")
    payload = add_cache_boundary(["current task", attachment])
    assert payload[:3] == [CACHE_ANCHOR, payload[1], "current task"]
    assert payload[3] is attachment

    # Use strings for the mapper request; attachment ordering itself is covered
    # above without constructing a provider-specific binary content object.
    messages = [
        ModelRequest(
            parts=[
                SystemPromptPart("system instructions"),
                UserPromptPart(add_cache_boundary("current task")),
            ]
        )
    ]
    mapped = await model._map_messages(messages, ModelRequestParameters())

    assert mapped[0] == {"role": "system", "content": "system instructions"}
    content = mapped[1]["content"]
    assert content[0]["text"] == CACHE_ANCHOR
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert content[1]["text"] == "current task"


@pytest.mark.parametrize(
    ("details", "expected_read", "expected_write"),
    [
        (SimpleNamespace(cached_tokens=900, cache_write_tokens=250), 900, 250),
        (SimpleNamespace(cached_tokens=0, cache_write_tokens=0), 0, 0),
        (SimpleNamespace(), None, None),
    ],
)
def test_cache_usage_preserves_values_zero_and_missing(
    details, expected_read, expected_write
):
    mapped = RequestUsage()
    raw = SimpleNamespace(usage=SimpleNamespace(input_tokens_details=details))

    preserve_openai_cache_tokens(mapped, raw)

    if expected_read is None:
        assert "cache_read_tokens" not in mapped.details
    else:
        assert mapped.cache_read_tokens == expected_read
        assert mapped.details["cache_read_tokens"] == expected_read
    if expected_write is None:
        assert "cache_write_tokens" not in mapped.details
    else:
        assert mapped.cache_write_tokens == expected_write
        assert mapped.details["cache_write_tokens"] == expected_write
