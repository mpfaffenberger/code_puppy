"""Additional flow-focused tests for Antigravity transport."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from code_puppy.plugins.antigravity_oauth import transport
from code_puppy.plugins.antigravity_oauth.transport import AntigravityClient


@pytest.fixture
def antigravity_client() -> AntigravityClient:
    return AntigravityClient(project_id="test-project", model_name="gemini-pro")


@pytest.fixture
def fallback_endpoint(monkeypatch: pytest.MonkeyPatch) -> str:
    endpoint = "https://fallback.test"
    monkeypatch.setattr(transport, "ANTIGRAVITY_ENDPOINT_FALLBACKS", [endpoint])
    return endpoint


@pytest.mark.asyncio
async def test_send_wraps_request_and_sets_headers(
    antigravity_client: AntigravityClient,
    fallback_endpoint: str,
) -> None:
    response = httpx.Response(
        status_code=200,
        content=b'{"response": {"message": "ok"}}',
    )

    request = httpx.Request(
        "POST",
        "/v1/models/gemini-pro:generateContent",
        content=b'{"contents": []}',
        headers={
            "Authorization": "Bearer token",
            "User-Agent": "sdk-agent",
            "X-Goog-Api-Key": "secret",
            "Client-Metadata": "old",
            "Accept": "application/json",
        },
    )

    with patch.object(
        httpx.AsyncClient, "send", AsyncMock(return_value=response)
    ) as mock_send:
        unwrapped = await antigravity_client.send(request)

    assert unwrapped.json() == {"message": "ok"}

    sent_request = mock_send.call_args[0][0]
    assert sent_request.url.host == fallback_endpoint.replace("https://", "")
    assert sent_request.headers["authorization"] == "Bearer token"
    assert sent_request.headers["user-agent"].startswith("antigravity/")
    assert sent_request.headers["x-goog-api-key"] == ""
    assert sent_request.headers["accept"] == "text/event-stream"


@pytest.mark.asyncio
async def test_send_retries_rate_limit_with_delay(
    antigravity_client: AntigravityClient,
    fallback_endpoint: str,
) -> None:
    rate_limited = httpx.Response(
        status_code=429,
        content=(
            b'{"error": {"details": [{"@type": '
            b'"type.googleapis.com/google.rpc.RetryInfo", '
            b'"retryDelay": "0.5s"}]}}'
        ),
    )
    success = httpx.Response(
        status_code=200,
        content=b'{"response": {"message": "ok"}}',
    )

    request = httpx.Request(
        "POST",
        "/v1/models/gemini-pro:generateContent",
        content=b'{"contents": []}',
    )

    with patch.object(
        httpx.AsyncClient,
        "send",
        AsyncMock(side_effect=[rate_limited, success]),
    ):
        with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
            response = await antigravity_client.send(request)

    assert response.status_code == 200
    sleep_mock.assert_awaited_once()
    assert sleep_mock.call_args[0][0] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_send_passes_through_when_no_body(
    antigravity_client: AntigravityClient,
) -> None:
    response = httpx.Response(status_code=204)
    request = httpx.Request("POST", "https://example.com/api/no-body")

    with patch.object(
        httpx.AsyncClient, "send", AsyncMock(return_value=response)
    ) as mock_send:
        result = await antigravity_client.send(request)

    assert result.status_code == 204
    assert mock_send.call_args[0][0].url == request.url
