"""Tests for Claude cache client with token refresh on Cloudflare errors."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.claude_cache_client import ClaudeCacheAsyncClient


class TestCloudflareErrorDetection:
    """Test detection of Cloudflare HTML error responses."""

    def test_is_cloudflare_html_error_true(self):
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
        result = client._is_cloudflare_html_error(response)

        assert result is True

    def test_is_cloudflare_html_error_false_json(self):
        """Test that JSON responses are not detected as Cloudflare errors."""
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "application/json"}
        response._content = b'{"error": "some error"}'

        client = ClaudeCacheAsyncClient()
        result = client._is_cloudflare_html_error(response)

        assert result is False

    def test_is_cloudflare_html_error_false_different_html(self):
        """Test that non-Cloudflare HTML is not detected as Cloudflare error."""
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "text/html"}
        response._content = b"<html><body>Some other error</body></html>"
        response.text = "<html><body>Some other error</body></html>"

        client = ClaudeCacheAsyncClient()
        result = client._is_cloudflare_html_error(response)

        assert result is False

    def test_is_cloudflare_html_error_false_missing_markers(self):
        """Test that HTML without both markers is not detected."""
        # Has cloudflare but not "400 bad request"
        response = Mock(spec=httpx.Response)
        response.headers = {"content-type": "text/html"}
        response._content = b"<html><body>cloudflare</body></html>"
        response.text = "<html><body>cloudflare</body></html>"

        client = ClaudeCacheAsyncClient()
        result = client._is_cloudflare_html_error(response)

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

                # Verify refresh was called
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

                # Verify refresh was called
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
