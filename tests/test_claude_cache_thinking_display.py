"""Thinking ``display`` / off-switch handling on outgoing Anthropic bodies.

The API only accepts ``display`` while thinking runs (``adaptive`` /
``enabled``). Which "thinking off" shape a model accepts differs per model,
so nothing here names a model: a 400 about ``thinking`` on an off request is
retried once without the key, and the model is remembered.
"""

import json

import httpx2
import pytest

from code_puppy import claude_cache_client
from code_puppy.claude_cache_client import (
    ClaudeCacheAsyncClient,
    _enforce_thinking_display_summary,
)

THINKING_400 = {
    "type": "error",
    "error": {
        "type": "invalid_request_error",
        "message": 'To turn thinking off on this model, send "thinking": '
        '{"type": "between_tools"} instead.',
    },
}


@pytest.fixture(autouse=True)
def _forget_learned_models():
    claude_cache_client._THINKING_OMITTED_WHEN_OFF.clear()
    yield
    claude_cache_client._THINKING_OMITTED_WHEN_OFF.clear()


@pytest.mark.parametrize("thinking_type", ["disabled", "between_tools"])
@pytest.mark.parametrize(
    "model",
    ["claude-sonnet-5-5", "claude-opus-5-5", "claude-sonnet-5", "claude-haiku-4-5"],
)
def test_off_thinking_never_carries_display(model, thinking_type):
    payload = {
        "model": model,
        "thinking": {"type": thinking_type, "display": "summarized"},
    }

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == {"type": thinking_type}


@pytest.mark.parametrize("thinking_type", ["disabled", "between_tools"])
def test_clean_off_shape_is_left_alone(thinking_type):
    payload = {"model": "claude-sonnet-5", "thinking": {"type": thinking_type}}

    assert _enforce_thinking_display_summary(payload) is False
    assert payload["thinking"] == {"type": thinking_type}


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-sonnet-5-5"])
def test_adaptive_still_gets_summarized(model):
    payload = {"model": model, "thinking": {"type": "adaptive"}}

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_enabled_display_behavior_unchanged():
    payload = {
        "model": "claude-opus-4-7",
        "thinking": {"type": "enabled", "budget_tokens": 1024},
    }

    assert _enforce_thinking_display_summary(payload) is True
    assert payload["thinking"] == {
        "type": "enabled",
        "budget_tokens": 1024,
        "display": "summarized",
    }


def test_learned_model_omits_thinking_when_off_and_others_do_not():
    claude_cache_client._THINKING_OMITTED_WHEN_OFF.add("model-a")
    learned = {"model": "model-a", "thinking": {"type": "disabled"}}
    other = {"model": "model-b", "thinking": {"type": "disabled"}}
    thinking_on = {"model": "model-a", "thinking": {"type": "adaptive"}}

    assert _enforce_thinking_display_summary(learned) is True
    assert "thinking" not in learned
    assert _enforce_thinking_display_summary(other) is False
    assert other["thinking"] == {"type": "disabled"}
    _enforce_thinking_display_summary(thinking_on)
    assert thinking_on["thinking"]["type"] == "adaptive"


class _FakeAnthropic:
    """Rejects an off ``thinking`` for the models in ``strict``, like the API."""

    def __init__(self, strict=(), refusal=THINKING_400):
        self.strict = set(strict)
        self.refusal = refusal
        self.bodies = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.bodies.append(body)
        thinking = body.get("thinking", {})
        if body["model"] in self.strict and thinking.get("type") in (
            "disabled",
            "between_tools",
        ):
            return httpx2.Response(400, json=self.refusal)
        return httpx2.Response(200, json={"content": [{"type": "text", "text": "ok"}]})


async def _post(client, model, thinking):
    body = {"model": model, "max_tokens": 8, "messages": []}
    if thinking is not None:
        body["thinking"] = thinking
    return await client.post("https://api.anthropic.com/v1/messages", json=body)


def _client(api):
    return ClaudeCacheAsyncClient(transport=httpx2.MockTransport(api))


@pytest.mark.asyncio
async def test_refused_off_switch_is_retried_once_without_thinking():
    api = _FakeAnthropic(strict={"model-a"})

    async with _client(api) as client:
        response = await _post(client, "model-a", {"type": "disabled"})

    assert response.status_code == 200
    assert [b.get("thinking") for b in api.bodies] == [{"type": "disabled"}, None]


@pytest.mark.asyncio
async def test_retry_is_learned_so_next_call_sends_one_request():
    api = _FakeAnthropic(strict={"model-a"})

    async with _client(api) as client:
        await _post(client, "model-a", {"type": "disabled"})
        api.bodies.clear()
        response = await _post(client, "model-a", {"type": "disabled"})

    assert response.status_code == 200
    assert [b.get("thinking") for b in api.bodies] == [None]


@pytest.mark.asyncio
async def test_model_that_accepts_disabled_is_never_retried_or_changed():
    api = _FakeAnthropic(strict={"model-a"})

    async with _client(api) as client:
        response = await _post(client, "model-b", {"type": "disabled"})

    assert response.status_code == 200
    assert [b.get("thinking") for b in api.bodies] == [{"type": "disabled"}]


@pytest.mark.asyncio
async def test_unrelated_400_is_returned_untouched():
    refusal = {"error": {"type": "invalid_request_error", "message": "max_tokens: bad"}}
    api = _FakeAnthropic(strict={"model-a"}, refusal=refusal)

    async with _client(api) as client:
        response = await _post(client, "model-a", {"type": "disabled"})

    assert response.status_code == 400
    assert response.json() == refusal
    assert len(api.bodies) == 1


@pytest.mark.asyncio
async def test_thinking_400_on_a_thinking_on_request_is_not_retried():
    api = _FakeAnthropic(strict={"model-a"})
    api.strict = set()

    def always_400(request):
        api.bodies.append(json.loads(request.content))
        return httpx2.Response(400, json=THINKING_400)

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(always_400)
    ) as client:
        response = await _post(client, "model-a", {"type": "adaptive"})

    assert response.status_code == 400
    assert len(api.bodies) == 1
