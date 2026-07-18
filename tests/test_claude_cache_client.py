"""Tests for Claude cache client with token refresh on Cloudflare errors."""

import base64
import json
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.claude_cache_client import (
    CACHE_TTL_1H,
    CLAUDE_CLI_USER_AGENT,
    EXTENDED_CACHE_TTL_BETA,
    TOKEN_MAX_AGE_SECONDS,
    TOOL_PREFIX,
    ClaudeCacheAsyncClient,
    _inject_cache_control_in_payload,
)


def _create_jwt(iat: float | None = None, exp: float | None = None) -> str:
    """Create a test JWT with specified claims."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {}
    if iat is not None:
        payload["iat"] = iat
    if exp is not None:
        payload["exp"] = exp

    header_b64 = (
        base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    )
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    signature = "fake_signature"

    return f"{header_b64}.{payload_b64}.{signature}"


class TestJWTAgeDetection:
    """Test JWT age detection for proactive token refresh."""

    def test_get_jwt_age_with_iat(self):
        """Test that JWT age is calculated from iat claim."""
        # Token issued 30 minutes ago
        iat = time.time() - 1800
        token = _create_jwt(iat=iat)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is not None
        assert 1790 <= age <= 1810  # Allow for timing variance

    def test_get_jwt_age_with_exp_only(self):
        """Test that JWT age is calculated from exp claim when iat is missing."""
        # Token expires in 30 minutes (so it's about 30 mins old if 1hr lifetime)
        exp = time.time() + 1800
        token = _create_jwt(exp=exp)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is not None
        # Age should be TOKEN_MAX_AGE_SECONDS - time_until_exp = 3600 - 1800 = 1800
        assert 1790 <= age <= 1810

    def test_get_jwt_age_prefers_iat(self):
        """Test that iat claim is preferred over exp for age calculation."""
        iat = time.time() - 600  # 10 minutes ago
        exp = time.time() + 3000  # expires in 50 minutes
        token = _create_jwt(iat=iat, exp=exp)

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        # Should use iat (10 mins = 600 secs) not exp
        assert age is not None
        assert 590 <= age <= 610

    def test_get_jwt_age_invalid_token(self):
        """Test that invalid tokens return None."""
        client = ClaudeCacheAsyncClient()

        assert client._get_jwt_age_seconds(None) is None
        assert client._get_jwt_age_seconds("") is None
        assert client._get_jwt_age_seconds("not.a.valid.jwt") is None
        assert client._get_jwt_age_seconds("invalid") is None

    def test_get_jwt_age_no_timestamp_claims(self):
        """Test that JWT without timestamp claims returns None."""
        token = _create_jwt()  # No iat or exp

        client = ClaudeCacheAsyncClient()
        age = client._get_jwt_age_seconds(token)

        assert age is None

    def test_should_refresh_token_old(self):
        """Test that old tokens (>1 hour) trigger refresh."""
        # Token issued 2 hours ago
        iat = time.time() - 7200
        token = _create_jwt(iat=iat)

        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is True

    def test_should_refresh_token_fresh(self):
        """Test that fresh tokens (<1 hour) don't trigger refresh."""
        # Token issued 30 minutes ago
        iat = time.time() - 1800
        token = _create_jwt(iat=iat)

        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is False

    def test_should_refresh_token_exactly_1_hour(self):
        """Test that token exactly 1 hour old triggers refresh."""
        # Token issued exactly 1 hour ago
        iat = time.time() - TOKEN_MAX_AGE_SECONDS
        token = _create_jwt(iat=iat)

        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
        )

        client = ClaudeCacheAsyncClient()
        assert client._should_refresh_token(request) is True

    def test_extract_bearer_token(self):
        """Test bearer token extraction from headers."""
        client = ClaudeCacheAsyncClient()

        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
            headers={"Authorization": "Bearer my_token_123"},
        )

        token = client._extract_bearer_token(request)
        assert token == "my_token_123"

    def test_extract_bearer_token_missing(self):
        """Test bearer token extraction when header is missing."""
        client = ClaudeCacheAsyncClient()

        request = httpx.Request(
            "POST",
            "https://api.anthropic.com/v1/messages",
        )

        token = client._extract_bearer_token(request)
        assert token is None


class TestProactiveTokenRefresh:
    """Test proactive token refresh before requests."""

    @pytest.mark.asyncio
    async def test_proactive_refresh_on_old_token(self):
        """Test that old tokens are refreshed proactively before the request."""
        # Token issued 2 hours ago
        iat = time.time() - 7200
        old_token = _create_jwt(iat=iat)

        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            return_value=success_response,
        ) as mock_send:
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new_fresh_token",
            ) as mock_refresh:
                client = ClaudeCacheAsyncClient(
                    headers={"Authorization": f"Bearer {old_token}"}
                )

                request = httpx.Request(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={"Authorization": f"Bearer {old_token}"},
                    content=b'{"model": "claude-3-opus"}',
                )

                response = await client.send(request)

                # Refresh should have been called proactively
                mock_refresh.assert_called_once()

                # Request should succeed
                assert response.status_code == 200

                # Only one request should be made (no retry needed)
                assert mock_send.call_count == 1

    @pytest.mark.asyncio
    async def test_no_proactive_refresh_on_fresh_token(self):
        """Test that fresh tokens don't trigger proactive refresh."""
        # Token issued 30 minutes ago
        iat = time.time() - 1800
        fresh_token = _create_jwt(iat=iat)

        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {"content-type": "application/json"}

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            return_value=success_response,
        ):
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
            ) as mock_refresh:
                client = ClaudeCacheAsyncClient(
                    headers={"Authorization": f"Bearer {fresh_token}"}
                )

                request = httpx.Request(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={"Authorization": f"Bearer {fresh_token}"},
                    content=b'{"model": "claude-3-opus"}',
                )

                await client.send(request)

                # Refresh should NOT be called
                mock_refresh.assert_not_called()


class TestCloudflareErrorDetection:
    """Test detection of Cloudflare HTML error responses."""

    @pytest.mark.asyncio
    async def test_is_cloudflare_html_error_true(self):
        """Test that Cloudflare HTML errors are detected."""
        # Create a mock response with Cloudflare HTML error
        cloudflare_html = (
            "<html>\r\n"
            "<head><title>400 Bad Request</title></head>\r\n"
            "<body>\r\n"
            "<center><h1>400 Bad Request</h1></center>\r\n"
            "<hr><center>cloudflare</center>\r\n"
            "</body>\r\n"
            "</html>"
        )

        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "text/html; charset=utf-8"}
        response._content = cloudflare_html.encode("utf-8")
        response.text = cloudflare_html

        client = ClaudeCacheAsyncClient()
        result = await client._is_cloudflare_html_error(response)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_cloudflare_html_error_false_json(self):
        """Test that JSON responses are not detected as Cloudflare errors."""
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "application/json"}
        response._content = b'{"error": "some error"}'

        client = ClaudeCacheAsyncClient()
        result = await client._is_cloudflare_html_error(response)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_cloudflare_html_error_false_different_html(self):
        """Test that non-Cloudflare HTML is not detected as Cloudflare error."""
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "text/html"}
        response._content = b"<html><body>Some other error</body></html>"
        response.text = "<html><body>Some other error</body></html>"

        client = ClaudeCacheAsyncClient()
        result = await client._is_cloudflare_html_error(response)

        assert result is False

    @pytest.mark.asyncio
    async def test_is_cloudflare_html_error_false_missing_markers(self):
        """Test that HTML without both markers is not detected."""
        # Has cloudflare but not "400 bad request"
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "text/html"}
        response._content = b"<html><body>cloudflare</body></html>"
        response.text = "<html><body>cloudflare</body></html>"

        client = ClaudeCacheAsyncClient()
        result = await client._is_cloudflare_html_error(response)

        assert result is False


class TestTokenRefreshOnCloudflareError:
    """Test that token refresh is triggered on Cloudflare errors."""

    @pytest.mark.asyncio
    async def test_refresh_on_cloudflare_400(self):
        """Test that a Cloudflare 400 error triggers token refresh."""
        cloudflare_html = (
            "<html>\r\n"
            "<head><title>400 Bad Request</title></head>\r\n"
            "<body>\r\n"
            "<center><h1>400 Bad Request</h1></center>\r\n"
            "<hr><center>cloudflare</center>\r\n"
            "</body>\r\n"
            "</html>"
        )

        # Create a mock response for the initial failed request
        failed_response = Mock(spec=httpx.Response)
        failed_response.status_code = 400
        failed_response.headers = {"content-type": "text/html; charset=utf-8"}
        failed_response._content = cloudflare_html.encode("utf-8")
        failed_response.text = cloudflare_html
        failed_response.aclose = AsyncMock()

        # Create a mock response for the successful retry
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {"content-type": "application/json"}
        success_response._content = b'{"result": "success"}'

        # Mock the parent send method to return failed then success
        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock
        ) as mock_send:
            mock_send.side_effect = [failed_response, success_response]

            # Mock the refresh function
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new_token_123",
            ) as mock_refresh:
                # Mock stored token expiry check to prevent proactive refresh
                # (we want to test the Cloudflare error path, not proactive refresh)
                with patch.object(
                    ClaudeCacheAsyncClient,
                    "_check_stored_token_expiry",
                    return_value=False,
                ):
                    client = ClaudeCacheAsyncClient(
                        headers={"Authorization": "Bearer old_token"}
                    )

                    # Create a mock request
                    request = httpx.Request(
                        "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={"Authorization": "Bearer old_token"},
                        content=b'{"model": "claude-3-opus"}',
                    )

                    # Send the request
                    response = await client.send(request)

                    # Verify refresh was called (once, for the Cloudflare error)
                    mock_refresh.assert_called_once()

                    # Verify we got the success response
                    assert response.status_code == 200

                    # Verify send was called twice (initial + retry)
                    assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_no_refresh_on_json_400(self):
        """Test that a JSON 400 error does not trigger token refresh."""
        # Create a mock response for a non-Cloudflare 400 error
        response = Mock(spec=httpx.Response)
        response.status_code = 400
        response.headers = {"content-type": "application/json"}
        response._content = b'{"error": {"type": "invalid_request_error"}}'

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock, return_value=response
        ):
            with patch.object(
                ClaudeCacheAsyncClient, "_refresh_claude_oauth_token"
            ) as mock_refresh:
                # Mock stored token expiry check to prevent proactive refresh
                with patch.object(
                    ClaudeCacheAsyncClient,
                    "_check_stored_token_expiry",
                    return_value=False,
                ):
                    client = ClaudeCacheAsyncClient(
                        headers={"Authorization": "Bearer token"}
                    )

                    request = httpx.Request(
                        "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={"Authorization": "Bearer token"},
                        content=b'{"model": "claude-3-opus"}',
                    )

                    result = await client.send(request)

                    # Refresh should NOT be called for non-Cloudflare 400s
                    mock_refresh.assert_not_called()
                    assert result.status_code == 400

    @pytest.mark.asyncio
    async def test_refresh_on_401(self):
        """Test that a 401 error triggers token refresh."""
        # Create a mock response for 401
        failed_response = Mock(spec=httpx.Response)
        failed_response.status_code = 401
        failed_response.headers = {"content-type": "application/json"}
        failed_response._content = b'{"error": {"type": "authentication_error"}}'
        failed_response.aclose = AsyncMock()

        # Create a mock response for the successful retry
        success_response = Mock(spec=httpx.Response)
        success_response.status_code = 200
        success_response.headers = {"content-type": "application/json"}
        success_response._content = b'{"result": "success"}'

        with patch.object(
            httpx.AsyncClient, "send", new_callable=AsyncMock
        ) as mock_send:
            mock_send.side_effect = [failed_response, success_response]

            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new_token_456",
            ) as mock_refresh:
                # Mock stored token expiry check to prevent proactive refresh
                # (we want to test the 401 error path, not proactive refresh)
                with patch.object(
                    ClaudeCacheAsyncClient,
                    "_check_stored_token_expiry",
                    return_value=False,
                ):
                    client = ClaudeCacheAsyncClient(
                        headers={"Authorization": "Bearer old_token"}
                    )

                    request = httpx.Request(
                        "POST",
                        "https://api.anthropic.com/v1/messages",
                        headers={"Authorization": "Bearer old_token"},
                        content=b'{"model": "claude-3-opus"}',
                    )

                    response = await client.send(request)

                    # Verify refresh was called (once, for the 401 error)
                    mock_refresh.assert_called_once()

                    # Verify we got the success response
                    assert response.status_code == 200

                    # Verify send was called twice
                    assert mock_send.call_count == 2

    @pytest.mark.asyncio
    async def test_no_infinite_retry_loop(self):
        """Test that we don't retry infinitely on auth errors."""
        # Create a mock response that always returns 401
        failed_response = Mock(spec=httpx.Response)
        failed_response.status_code = 401
        failed_response.headers = {"content-type": "application/json"}
        failed_response._content = b'{"error": {"type": "authentication_error"}}'
        failed_response.aclose = AsyncMock()

        with patch.object(
            httpx.AsyncClient,
            "send",
            new_callable=AsyncMock,
            return_value=failed_response,
        ) as mock_send:
            with patch.object(
                ClaudeCacheAsyncClient,
                "_refresh_claude_oauth_token",
                return_value="new_token",
            ):
                client = ClaudeCacheAsyncClient(
                    headers={"Authorization": "Bearer token"}
                )

                request = httpx.Request(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={"Authorization": "Bearer token"},
                    content=b'{"model": "claude-3-opus"}',
                )

                response = await client.send(request)

                # Should only retry once (initial + 1 retry)
                # The retry should have the extension flag set, preventing further retries
                assert mock_send.call_count == 2
                assert response.status_code == 401


class TestToolPrefixing:
    """Test tool name prefixing/unprefixing for Claude Code OAuth compatibility."""

    def test_prefix_tool_names_basic(self):
        """Test that tool names are prefixed correctly."""
        body = json.dumps(
            {
                "model": "claude-3",
                "tools": [
                    {"name": "read_file", "description": "Read a file"},
                    {"name": "edit_file", "description": "Edit a file"},
                ],
                "messages": [{"role": "user", "content": "Hello"}],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is not None
        data = json.loads(result)
        assert data["tools"][0]["name"] == f"{TOOL_PREFIX}read_file"
        assert data["tools"][1]["name"] == f"{TOOL_PREFIX}edit_file"

    def test_prefix_tool_names_already_prefixed(self):
        """Test that already-prefixed tools are not double-prefixed."""
        body = json.dumps(
            {
                "tools": [
                    {"name": f"{TOOL_PREFIX}read_file", "description": "Read a file"},
                ],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        # Should return None since nothing was modified
        assert result is None

    def test_prefix_tool_names_no_tools(self):
        """Test that bodies without tools return None."""
        body = json.dumps(
            {
                "model": "claude-3",
                "messages": [{"role": "user", "content": "Hello"}],
            }
        ).encode()

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is None

    def test_prefix_tool_names_invalid_json(self):
        """Test that invalid JSON returns None."""
        body = b"not valid json"

        client = ClaudeCacheAsyncClient()
        result = client._prefix_tool_names(body)

        assert result is None

    def test_apply_claude_code_prefix_defaults_to_false(self):
        """Default constructor must NOT opt into Claude Code OAuth prefixing.

        This is the regression guard for the bug where custom_anthropic models
        were having tool names mangled with ``cp_`` even though they're not
        talking to the Claude Code OAuth endpoint.
        """
        client = ClaudeCacheAsyncClient()
        assert client._apply_claude_code_prefix is False

    def test_apply_claude_code_prefix_opt_in(self):
        """Plugins (claude_code_oauth) opt in explicitly via constructor flag."""
        client = ClaudeCacheAsyncClient(apply_claude_code_prefix=True)
        assert client._apply_claude_code_prefix is True


class TestHeaderTransformation:
    """Test header transformation for Claude Code OAuth compatibility."""

    def test_transform_headers_sets_user_agent(self):
        """Test that user-agent is set correctly."""
        headers = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert headers["user-agent"] == CLAUDE_CLI_USER_AGENT

    def test_transform_headers_adds_oauth_beta(self):
        """Test that oauth beta is always added."""
        headers = {}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "oauth-2025-04-20" in headers["anthropic-beta"]
        assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]

    def test_transform_headers_keeps_claude_code_beta_if_present(self):
        """Test that claude-code beta is kept if it was in the incoming headers."""
        headers = {
            "anthropic-beta": "claude-code-20250219,interleaved-thinking-2025-05-14"
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "claude-code-20250219" in headers["anthropic-beta"]

    def test_transform_headers_excludes_claude_code_beta_if_not_present(self):
        """Test that claude-code beta is not added if it wasn't requested."""
        headers = {"anthropic-beta": "interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "claude-code-20250219" not in headers["anthropic-beta"]

    def test_transform_headers_removes_x_api_key(self):
        """Test that x-api-key is removed."""
        headers = {
            "x-api-key": "secret",
            "anthropic-beta": "interleaved-thinking-2025-05-14",
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "x-api-key" not in headers
        assert "X-API-Key" not in headers

    def test_transform_headers_preserves_extra_betas(self):
        """Extra betas (e.g. context-1m) should survive the transform."""
        headers = {
            "anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14,context-1m-2025-08-07"
        }

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert "context-1m-2025-08-07" in headers["anthropic-beta"]
        assert "oauth-2025-04-20" in headers["anthropic-beta"]
        assert "interleaved-thinking-2025-05-14" in headers["anthropic-beta"]

    def test_transform_headers_no_duplicate_required_betas(self):
        """Required betas should not be duplicated in the output."""
        headers = {"anthropic-beta": "oauth-2025-04-20,interleaved-thinking-2025-05-14"}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        beta_str = headers["anthropic-beta"]
        assert beta_str.count("oauth-2025-04-20") == 1
        assert beta_str.count("interleaved-thinking-2025-05-14") == 1


class TestUrlBetaParam:
    """Test URL beta query parameter addition."""

    def test_add_beta_query_param(self):
        """Test that beta=true is added to URL."""
        url = httpx.URL("https://api.anthropic.com/v1/messages")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        assert "beta=true" in str(new_url)

    def test_add_beta_query_param_preserves_existing(self):
        """Test that existing query params are preserved."""
        url = httpx.URL("https://api.anthropic.com/v1/messages?foo=bar")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        assert "foo=bar" in str(new_url)
        assert "beta=true" in str(new_url)

    def test_add_beta_query_param_not_duplicated(self):
        """Test that beta param is not duplicated if already present."""
        url = httpx.URL("https://api.anthropic.com/v1/messages?beta=true")

        new_url = ClaudeCacheAsyncClient._add_beta_query_param(url)

        # Should be unchanged
        assert str(new_url).count("beta") == 1


class TestSendAppliesPrefixConditionally:
    """End-to-end: ``send()`` only prefixes tool names when the flag is on.

    These tests are the actual regression guard for the bug: custom_anthropic
    routes through ``ClaudeCacheAsyncClient`` without ``apply_claude_code_prefix``
    set, so tool names sent over the wire must remain verbatim.
    """

    @pytest.mark.asyncio
    async def test_send_does_not_prefix_when_flag_off(self):
        """custom_anthropic path: tool names go out clean (no ``cp_`` prefix)."""
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            captured["url"] = str(request.url)
            response = Mock(spec=httpx.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            # Default: apply_claude_code_prefix=False (custom_anthropic case)
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"}
            )
            request = httpx.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "tools": [
                            {"name": "read_file", "description": "read"},
                            {"name": "edit_file", "description": "edit"},
                        ],
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ).encode(),
            )

            await client.send(request)

        assert "body" in captured, "send did not run our fake transport"
        sent = json.loads(captured["body"])
        tool_names = [t["name"] for t in sent["tools"]]
        assert tool_names == ["read_file", "edit_file"], (
            f"custom_anthropic path must not prefix tool names, got {tool_names}"
        )
        assert TOOL_PREFIX not in captured["body"].decode("utf-8")

    @pytest.mark.asyncio
    async def test_send_does_prefix_when_flag_on(self):
        """claude_code OAuth path: tool names get the ``cp_`` prefix."""
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            response = Mock(spec=httpx.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"},
                apply_claude_code_prefix=True,
            )
            request = httpx.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(
                    {
                        "model": "claude-3-opus",
                        "tools": [
                            {"name": "read_file", "description": "read"},
                        ],
                        "messages": [{"role": "user", "content": "hi"}],
                    }
                ).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        tool_names = [t["name"] for t in sent["tools"]]
        assert tool_names == [f"{TOOL_PREFIX}read_file"]


def _sample_payload() -> dict:
    """A representative /v1/messages payload with all three cache targets."""
    return {
        "model": "claude-sonnet-4-5",
        "system": "You are a helpful pup.",
        "tools": [
            {"name": "read_file", "description": "read"},
            {"name": "edit_file", "description": "edit"},
        ],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "yo"}]},
            {"role": "user", "content": [{"type": "text", "text": "do stuff"}]},
        ],
    }


def _collect_markers(data: dict) -> list[dict]:
    """Return every cache_control marker in a payload/body dict."""
    markers = []
    for block in data.get("system") or []:
        if isinstance(block, dict) and "cache_control" in block:
            markers.append(block["cache_control"])
    for tool in data.get("tools") or []:
        if isinstance(tool, dict) and "cache_control" in tool:
            markers.append(tool["cache_control"])
    for message in data.get("messages") or []:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "cache_control" in block:
                    markers.append(block["cache_control"])
    return markers


class TestCacheTtlWireInjection:
    """Wire-body path: ClaudeCacheAsyncClient._inject_cache_control."""

    def test_default_ttl_omitted(self):
        """No TTL requested -> plain ephemeral markers (Anthropic 5m default)."""
        body = json.dumps(_sample_payload()).encode()

        result = ClaudeCacheAsyncClient._inject_cache_control(body)

        assert result is not None
        markers = _collect_markers(json.loads(result))
        assert len(markers) == 3  # system + tools + last message
        assert all(m == {"type": "ephemeral"} for m in markers)

    def test_1h_ttl_stamped_on_all_breakpoints(self):
        """ttl='1h' -> every marker carries the extended TTL."""
        body = json.dumps(_sample_payload()).encode()

        result = ClaudeCacheAsyncClient._inject_cache_control(body, CACHE_TTL_1H)

        assert result is not None
        markers = _collect_markers(json.loads(result))
        assert len(markers) == 3
        assert all(m == {"type": "ephemeral", "ttl": "1h"} for m in markers)

    def test_1h_ttl_on_system_list(self):
        """System already in content-block form also gets the TTL."""
        payload = _sample_payload()
        payload["system"] = [{"type": "text", "text": "You are a helpful pup."}]
        body = json.dumps(payload).encode()

        result = ClaudeCacheAsyncClient._inject_cache_control(body, CACHE_TTL_1H)

        data = json.loads(result)
        assert data["system"][-1]["cache_control"] == {
            "type": "ephemeral",
            "ttl": "1h",
        }


class TestCacheTtlPayloadInjection:
    """SDK payload path: _inject_cache_control_in_payload."""

    def test_default_ttl_omitted(self):
        payload = _sample_payload()

        _inject_cache_control_in_payload(payload)

        markers = _collect_markers(payload)
        assert len(markers) == 3
        assert all(m == {"type": "ephemeral"} for m in markers)

    def test_1h_ttl_stamped_on_all_breakpoints(self):
        payload = _sample_payload()

        _inject_cache_control_in_payload(payload, CACHE_TTL_1H)

        markers = _collect_markers(payload)
        assert len(markers) == 3
        assert all(m == {"type": "ephemeral", "ttl": "1h"} for m in markers)

    def test_existing_markers_not_overwritten(self):
        """Pre-existing cache_control survives (no double-stamping)."""
        payload = _sample_payload()
        payload["tools"][-1]["cache_control"] = {"type": "ephemeral"}

        _inject_cache_control_in_payload(payload, CACHE_TTL_1H)

        assert payload["tools"][-1]["cache_control"] == {"type": "ephemeral"}


class TestCacheTtlPrefixStability:
    """Consecutive requests must keep the cached prefix byte-stable.

    The moving breakpoint may only ever land on the FINAL content block of
    the FINAL message — touching anything earlier would rewrite the prefix
    and defeat caching entirely (issue #640).
    """

    @pytest.mark.parametrize("ttl", [None, CACHE_TTL_1H])
    def test_only_final_block_of_final_message_marked(self, ttl):
        first = _sample_payload()
        _inject_cache_control_in_payload(first, ttl)

        # Next turn: same conversation plus the assistant reply + new user msg
        second = _sample_payload()
        second["messages"] = [
            {"role": m["role"], "content": [dict(b) for b in m["content"]]}
            for m in _sample_payload()["messages"]
        ] + [
            {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
            {"role": "user", "content": [{"type": "text", "text": "more"}]},
        ]
        _inject_cache_control_in_payload(second, ttl)

        for payload in (first, second):
            for message in payload["messages"][:-1]:
                for block in message["content"]:
                    assert "cache_control" not in block
            last_content = payload["messages"][-1]["content"]
            for block in last_content[:-1]:
                assert "cache_control" not in block
            assert "cache_control" in last_content[-1]

        # The shared prefix (request 1's messages sans its moving marker)
        # serializes identically inside request 2.
        def _strip_markers(messages):
            return [
                {
                    "role": m["role"],
                    "content": [
                        {k: v for k, v in b.items() if k != "cache_control"}
                        for b in m["content"]
                    ],
                }
                for m in messages
            ]

        prefix_len = len(first["messages"])
        assert _strip_markers(second["messages"])[:prefix_len] == _strip_markers(
            first["messages"]
        )


class TestExtendedCacheTtlBetaHeader:
    """1h TTL requires the extended-cache-ttl beta on the wire."""

    def test_beta_added_for_1h_ttl(self):
        headers = {}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers, CACHE_TTL_1H)

        assert EXTENDED_CACHE_TTL_BETA in headers["anthropic-beta"]

    def test_beta_not_added_by_default(self):
        headers = {}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers)

        assert EXTENDED_CACHE_TTL_BETA not in headers["anthropic-beta"]

    def test_beta_not_duplicated(self):
        headers = {"anthropic-beta": EXTENDED_CACHE_TTL_BETA}

        ClaudeCacheAsyncClient._transform_headers_for_claude_code(headers, CACHE_TTL_1H)

        assert headers["anthropic-beta"].count(EXTENDED_CACHE_TTL_BETA) == 1


class TestSendAppliesCacheTtl:
    """End-to-end: a client built with cache_ttl='1h' stamps body + header."""

    @pytest.mark.asyncio
    async def test_send_stamps_1h_ttl_and_beta(self):
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            captured["beta"] = request.headers.get("anthropic-beta", "")
            response = Mock(spec=httpx.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"},
                apply_claude_code_prefix=True,
                cache_ttl=CACHE_TTL_1H,
            )
            request = httpx.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(_sample_payload()).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        markers = _collect_markers(sent)
        assert markers, "expected cache_control markers on the wire"
        assert all(m == {"type": "ephemeral", "ttl": "1h"} for m in markers)
        assert EXTENDED_CACHE_TTL_BETA in captured["beta"]

    @pytest.mark.asyncio
    async def test_send_defaults_to_5m_without_cache_ttl(self):
        captured: dict = {}

        async def fake_send(self, request, *args, **kwargs):
            captured["body"] = bytes(request.content)
            captured["beta"] = request.headers.get("anthropic-beta", "")
            response = Mock(spec=httpx.Response)
            response.status_code = 200
            response.headers = {"content-type": "application/json"}
            response._content = b"{}"
            return response

        with (
            patch.object(httpx.AsyncClient, "send", new=fake_send),
            patch.object(
                ClaudeCacheAsyncClient,
                "_check_stored_token_expiry",
                return_value=False,
            ),
        ):
            client = ClaudeCacheAsyncClient(
                headers={"Authorization": "Bearer some_token"},
                apply_claude_code_prefix=True,
            )
            request = httpx.Request(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={"Authorization": "Bearer some_token"},
                content=json.dumps(_sample_payload()).encode(),
            )

            await client.send(request)

        sent = json.loads(captured["body"])
        markers = _collect_markers(sent)
        assert markers
        assert all(m == {"type": "ephemeral"} for m in markers)
        assert EXTENDED_CACHE_TTL_BETA not in captured["beta"]


class TestPluginCacheTtlResolution:
    """claude-code-* models ALWAYS get 1h; nothing else does (issue #640)."""

    def test_claude_code_prefix_gets_1h(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _resolve_cache_ttl,
        )

        assert _resolve_cache_ttl("claude-code-claude-opus-4-7") == CACHE_TTL_1H
        assert _resolve_cache_ttl("claude-code-claude-haiku-4-5") == CACHE_TTL_1H

    def test_non_prefixed_models_keep_default(self):
        from code_puppy.plugins.claude_code_oauth.register_callbacks import (
            _resolve_cache_ttl,
        )

        assert _resolve_cache_ttl("claude-sonnet-4-5") is None
        assert _resolve_cache_ttl("my-custom-anthropic") is None
