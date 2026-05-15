"""Regression tests for Claude Code OAuth reauthentication retry behavior."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.claude_cache_client import ClaudeCacheAsyncClient
from code_puppy.plugins.claude_code_oauth.register_callbacks import (
    _reauthenticate_after_expired_oauth,
)

CLOUDFLARE_400_HTML = b"""
<html>
<head><title>400 Bad Request</title></head>
<body>
<center><h1>400 Bad Request</h1></center>
<hr><center>cloudflare</center>
</body>
</html>
"""


@pytest.mark.asyncio
async def test_cloudflare_400_refresh_failure_runs_oauth_callback_and_retries():
    failed_response = Mock(spec=httpx.Response)
    failed_response.status_code = 400
    failed_response.headers = {"content-type": "text/html; charset=utf-8"}
    failed_response._content = CLOUDFLARE_400_HTML
    failed_response.aclose = AsyncMock()

    success_response = Mock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}

    reauth_callback = Mock(return_value="fresh_oauth_token")

    with (
        patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[failed_response, success_response],
        ) as mock_send,
        patch.object(
            ClaudeCacheAsyncClient,
            "_refresh_claude_oauth_token",
            return_value=None,
        ),
    ):
        client = ClaudeCacheAsyncClient(
            oauth_reauthentication_callback=reauth_callback,
        )
        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            content=b'{"model":"claude-opus-4-7"}',
        )

        response = await client.send(request)

    assert response is success_response
    reauth_callback.assert_called_once_with()
    assert mock_send.call_count == 2

    retry_request = mock_send.call_args_list[1].args[0]
    assert retry_request.headers["Authorization"] == "Bearer fresh_oauth_token"


@pytest.mark.asyncio
async def test_auth_retry_does_not_run_oauth_callback_when_refresh_succeeds():
    failed_response = Mock(spec=httpx.Response)
    failed_response.status_code = 401
    failed_response.headers = {"content-type": "application/json"}
    failed_response.aclose = AsyncMock()

    success_response = Mock(spec=httpx.Response)
    success_response.status_code = 200
    success_response.headers = {"content-type": "application/json"}

    reauth_callback = Mock(return_value="should_not_be_used")

    with (
        patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            side_effect=[failed_response, success_response],
        ),
        patch.object(
            ClaudeCacheAsyncClient,
            "_refresh_claude_oauth_token",
            return_value="refreshed_token",
        ),
    ):
        client = ClaudeCacheAsyncClient(
            oauth_reauthentication_callback=reauth_callback,
        )
        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            content=b'{"model":"claude-opus-4-7"}',
        )

        response = await client.send(request)

    assert response is success_response
    reauth_callback.assert_not_called()


def test_claude_code_reauth_helper_ignores_non_prefixed_models():
    with (
        patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
        ) as mock_auth,
        patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks.get_valid_access_token"
        ) as mock_token,
    ):
        token = _reauthenticate_after_expired_oauth("claude-opus-4-7")

    assert token is None
    mock_auth.assert_not_called()
    mock_token.assert_not_called()


def test_claude_code_reauth_helper_runs_flow_for_prefixed_models():
    with (
        patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks._perform_authentication"
        ) as mock_auth,
        patch(
            "code_puppy.plugins.claude_code_oauth.register_callbacks.get_valid_access_token",
            return_value="new_oauth_token",
        ),
        patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_warning"),
        patch("code_puppy.plugins.claude_code_oauth.register_callbacks.emit_success"),
    ):
        token = _reauthenticate_after_expired_oauth("claude-code-claude-opus-4-7")

    assert token == "new_oauth_token"
    mock_auth.assert_called_once_with()
