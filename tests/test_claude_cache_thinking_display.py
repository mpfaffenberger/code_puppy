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

ENDPOINT = ("api.anthropic.com", None, "/v1/messages")
OTHER_ENDPOINT = ("provider-b.example", None, "/v1/messages")
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
    claude_cache_client._THINKING_OMITTED_WHEN_OFF.add((ENDPOINT, "model-a"))
    learned = {"model": "model-a", "thinking": {"type": "disabled"}}
    other = {"model": "model-b", "thinking": {"type": "disabled"}}
    thinking_on = {"model": "model-a", "thinking": {"type": "adaptive"}}

    assert _enforce_thinking_display_summary(learned, ENDPOINT) is True
    assert "thinking" not in learned
    elsewhere = {"model": "model-a", "thinking": {"type": "disabled"}}
    assert _enforce_thinking_display_summary(elsewhere, OTHER_ENDPOINT) is False
    assert elsewhere["thinking"] == {"type": "disabled"}
    assert _enforce_thinking_display_summary(other, ENDPOINT) is False
    assert other["thinking"] == {"type": "disabled"}
    _enforce_thinking_display_summary(thinking_on, ENDPOINT)
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


async def _post(client, model, thinking, url="https://api.anthropic.com/v1/messages"):
    body = {"model": model, "max_tokens": 8, "messages": []}
    if thinking is not None:
        body["thinking"] = thinking
    return await client.post(url, json=body)


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


@pytest.mark.asyncio
async def test_failed_fallback_is_not_learned():
    bad_signature = {
        "error": {"type": "invalid_request_error", "message": "thinking block bad"}
    }
    api = _FakeAnthropic(strict={"model-a"}, refusal=bad_signature)

    def still_failing(request):
        api(request)
        return httpx2.Response(400, json=bad_signature)

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(still_failing)
    ) as client:
        await _post(client, "model-a", {"type": "disabled"})
        await _post(client, "model-a", {"type": "disabled"})

    assert [b.get("thinking") for b in api.bodies] == [{"type": "disabled"}, None] * 2
    assert not claude_cache_client._THINKING_OMITTED_WHEN_OFF


@pytest.mark.asyncio
async def test_learning_is_scoped_to_the_provider_endpoint():
    api = _FakeAnthropic(strict={"model-a"})
    other_url = "https://provider-b.example/v1/messages"

    async with _client(api) as client:
        await _post(client, "model-a", {"type": "disabled"})
        api.bodies.clear()
        await _post(client, "model-a", {"type": "disabled"}, url=other_url)

    assert [b.get("thinking") for b in api.bodies] == [{"type": "disabled"}, None]


def _oauth_api(old_token_reply):
    sent = []

    def api(request):
        token = request.headers["authorization"].removeprefix("Bearer ")
        thinking = json.loads(request.content).get("thinking")
        sent.append((token, thinking))
        if token == "old":
            return old_token_reply(thinking)
        if thinking:
            return httpx2.Response(400, json=THINKING_400)
        return httpx2.Response(200, json={"content": []})

    return api, sent


def _unauthorized():
    return httpx2.Response(401, json={"error": {"message": "expired"}})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "old_token_reply, expected",
    [
        pytest.param(  # thinking 400 -> omitted request gets 401 -> refresh
            lambda t: httpx2.Response(400, json=THINKING_400) if t else _unauthorized(),
            [("old", "off"), ("old", None), ("new", None)],
            id="thinking-then-auth",
        ),
        pytest.param(  # 401 -> refreshed request gets thinking 400
            lambda t: _unauthorized(),
            [("old", "off"), ("new", "off"), ("new", None)],
            id="auth-then-thinking",
        ),
    ],
)
async def test_thinking_fallback_composes_with_oauth_recovery(
    old_token_reply, expected
):
    api, sent = _oauth_api(old_token_reply)

    async def provide_token():
        return "old"

    async def refresh(rejected_token):
        return "new"

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(api),
        apply_claude_code_prefix=True,
        oauth_token_provider=provide_token,
        oauth_refresh_callback=refresh,
    ) as client:
        response = await _post(client, "model-a", {"type": "disabled"})

    assert response.status_code == 200
    assert [(t, "off" if th else None) for t, th in sent] == expected
