"""Other providers' reasoning must never reach Anthropic as assistant text."""

import json

import httpx2
import pytest
from anthropic import AsyncAnthropic
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from code_puppy.agents._foreign_thinking import strip_foreign_thinking
from code_puppy.agents._model_message_transform import build_model_message_transform

GEMINI_THOUGHT = "Gemini private reasoning"


def _history() -> list:
    """Shape of a Gemini-authored session (Code Puppy's Gemini model labels
    thinking with the model name and a thought signature)."""
    return [
        ModelRequest(parts=[UserPromptPart("review the PR")]),
        ModelResponse(
            parts=[
                ThinkingPart(
                    GEMINI_THOUGHT, signature="g-sig", provider_name="gemini-3.8-flash"
                ),
                ToolCallPart("read_file", {"path": "a.py"}, tool_call_id="t1"),
            ],
            provider_name="google",
        ),
        ModelRequest(
            parts=[ToolReturnPart("read_file", "contents", tool_call_id="t1")]
        ),
        ModelResponse(parts=[ThinkingPart("only reasoning", provider_name="google")]),
        ModelResponse(parts=[TextPart("Recommend approval.")]),
    ]


def _anthropic(captured: list) -> AnthropicModel:
    def transport(request: httpx2.Request) -> httpx2.Response:
        captured.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "offline",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    sdk = AsyncAnthropic(
        api_key="offline-placeholder",
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport)),
        max_retries=0,
    )
    return AnthropicModel(
        "claude-sonnet-5", provider=AnthropicProvider(anthropic_client=sdk)
    )


@pytest.mark.asyncio
async def test_anthropic_request_carries_findings_but_not_foreign_reasoning():
    captured: list = []
    history = _history()
    agent = Agent(
        _anthropic(captured),
        capabilities=[build_model_message_transform("code-puppy")],
    )

    await agent.run("final review", message_history=history)

    wire = json.dumps(captured[0]["messages"])
    assert GEMINI_THOUGHT not in wire
    assert "<thinking>" not in wire
    assert "only reasoning" not in wire
    assert "read_file" in wire and "contents" in wire
    assert "Recommend approval." in wire
    # Stored history is untouched: switching back to Gemini keeps its reasoning.
    assert history[1].parts[0].content == GEMINI_THOUGHT


def test_native_signed_anthropic_thinking_is_kept():
    model = _anthropic([])
    native = ThinkingPart(
        "claude reasoning", signature="a-sig", provider_name=model.system
    )
    unsigned = ThinkingPart("interrupted", provider_name=model.system)
    messages = [ModelResponse(parts=[native, unsigned, TextPart("done")])]

    cleaned = strip_foreign_thinking(messages, model)

    assert cleaned[0].parts == [native, TextPart("done")]


def test_non_anthropic_models_receive_history_unchanged():
    history = _history()
    model = FunctionModel(lambda _messages, _info: ModelResponse(parts=[]))

    assert strip_foreign_thinking(history, model) is history
