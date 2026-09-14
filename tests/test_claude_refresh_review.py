"""Regression coverage for credential synchronization and isolation."""

import threading
from unittest.mock import AsyncMock, patch

import httpx2
import pytest

from code_puppy import callbacks
from code_puppy.claude_cache_client import ClaudeCacheAsyncClient


@pytest.mark.asyncio
async def test_request_adopts_token_rotated_by_heartbeat():
    seen = []

    def transport(request):
        seen.append(request.headers["authorization"])
        return httpx2.Response(200, json={})

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(transport), apply_claude_code_prefix=True
    ) as client:
        client._oauth_token_provider = AsyncMock(return_value="new-disk-token")
        # The heartbeat has saved a fresh opaque token, but the SDK still
        # holds the old one. An expiry-only hook cannot reconcile the two.
        with patch.object(callbacks, "get_callbacks") as hooks:
            hooks.side_effect = lambda phase: {
                "check_claude_oauth_token_expiry": [lambda: False],
                "refresh_claude_oauth_token": [lambda: "new-disk-token"],
            }.get(phase, [])
            await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"authorization": "Bearer old-sdk-token"},
                json={"model": "claude-sonnet-4-6", "messages": []},
            )

    assert seen == ["Bearer new-disk-token"]


@pytest.mark.asyncio
async def test_auth_recovery_awaits_async_refresh_hook():
    refresh = AsyncMock(return_value="new-token")
    attempts = []

    def transport(request):
        attempts.append(request.headers.get("authorization"))
        return httpx2.Response(401 if len(attempts) == 1 else 200, json={})

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(transport), apply_claude_code_prefix=True
    ) as client:
        with patch.object(callbacks, "get_callbacks") as hooks:
            hooks.side_effect = lambda phase: {
                "check_claude_oauth_token_expiry": [lambda: False],
                "refresh_claude_oauth_token": [refresh],
            }.get(phase, [])
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"authorization": "Bearer old-token"},
                json={},
            )

    assert response.status_code == 200
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_custom_api_key_endpoint_never_receives_claude_oauth_token():
    attempts = []

    def transport(request):
        attempts.append(request.headers.get("x-api-key"))
        return httpx2.Response(401 if len(attempts) == 1 else 200, json={})

    async with ClaudeCacheAsyncClient(
        transport=httpx2.MockTransport(transport)
    ) as client:
        with patch.object(callbacks, "get_callbacks") as hooks:
            hooks.side_effect = lambda phase: {
                "refresh_claude_oauth_token": [lambda: "private-oauth-token"],
            }.get(phase, [])
            await client.post(
                "https://custom-provider.invalid/v1/messages",
                headers={"x-api-key": "custom-api-key"},
                json={},
            )

    assert "private-oauth-token" not in attempts


@pytest.mark.asyncio
async def test_oauth_refuses_foreign_origin_before_loading_credentials():
    provider = AsyncMock(return_value="private-token")
    async with ClaudeCacheAsyncClient(
        apply_claude_code_prefix=True, oauth_token_provider=provider
    ) as client:
        with pytest.raises(ValueError, match="configured HTTPS origin"):
            await client.post("https://untrusted.invalid/v1/messages", json={})
    provider.assert_not_awaited()


@pytest.mark.asyncio
async def test_logout_never_reuses_sdk_token():
    async with ClaudeCacheAsyncClient(
        apply_claude_code_prefix=True,
        oauth_token_provider=AsyncMock(return_value=None),
    ) as client:
        with pytest.raises(ValueError, match="No valid Claude OAuth"):
            await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"authorization": "Bearer logged-out-token"},
                json={},
            )


@pytest.mark.asyncio
async def test_oauth_does_not_follow_redirects():
    seen = []

    def transport(request):
        seen.append(str(request.url))
        return httpx2.Response(307, headers={"location": "https://untrusted.invalid"})

    async with ClaudeCacheAsyncClient(
        apply_claude_code_prefix=True,
        oauth_token_provider=AsyncMock(return_value="token"),
        transport=httpx2.MockTransport(transport),
        follow_redirects=True,
    ) as client:
        response = await client.post("https://api.anthropic.com/v1/messages", json={})
    assert response.status_code == 307
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_rejected_token_is_passed_to_refresh_and_sdk_is_updated():
    seen = []
    refresh = AsyncMock(return_value="new")
    updates = []

    def transport(request):
        seen.append((request.headers["authorization"], request.extensions["trace"]))
        return httpx2.Response(401 if len(seen) == 1 else 200, json={})

    async with ClaudeCacheAsyncClient(
        apply_claude_code_prefix=True,
        oauth_token_provider=AsyncMock(return_value="old"),
        oauth_refresh_callback=refresh,
        token_update_callback=updates.append,
        transport=httpx2.MockTransport(transport),
    ) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            json={},
            extensions={"trace": "keep"},
        )
    assert response.status_code == 200
    assert seen == [("Bearer old", "keep"), ("Bearer new", "keep")]
    refresh.assert_awaited_once_with(rejected_token="old")
    assert updates == ["old", "new"]


@pytest.mark.asyncio
async def test_rate_limit_body_and_headers_are_logged():
    attempts = []

    def transport(request):
        attempts.append(1)
        if len(attempts) == 1:
            return httpx2.Response(
                429,
                headers={
                    "retry-after": "1",
                    "anthropic-ratelimit-input-tokens-remaining": "0",
                },
                json={"error": {"type": "rate_limit_error", "message": "slow down"}},
            )
        return httpx2.Response(200, json={})

    with (
        patch("code_puppy.error_logging.log_error_message") as log_message,
        patch("code_puppy.claude_cache_client.asyncio.sleep", AsyncMock()),
    ):
        async with ClaudeCacheAsyncClient(
            transport=httpx2.MockTransport(transport)
        ) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages", json={}
            )

    assert response.status_code == 200
    log_message.assert_called_once()
    (message,) = log_message.call_args.args
    context = log_message.call_args.kwargs["context"]
    assert "429" in message and "rate_limit_error: slow down" in message
    assert "anthropic-ratelimit-input-tokens-remaining" in context
    assert "retry-after" in context


@pytest.mark.asyncio
async def test_sync_oauth_hooks_do_not_block_event_loop():
    loop_thread = threading.get_ident()
    threads = []

    def refresh():
        threads.append(threading.get_ident())
        return "fresh"

    with patch.object(callbacks, "get_callbacks", return_value=[refresh]):
        assert await callbacks.on_refresh_claude_oauth_token_async() == ["fresh"]
    assert threads and threads[0] != loop_thread
