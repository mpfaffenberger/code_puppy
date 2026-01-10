"""Comprehensive test coverage for ReopenableAsyncClient.

Tests the reopenable HTTP client wrapper including:
- Initialization and configuration
- Client lifecycle (open/close/reopen)
- HTTP method delegation (GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS)
- Stream handling
- Async context manager support
- Properties and state inspection
- Edge cases and error conditions
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import httpx

from code_puppy.reopenable_async_client import ReopenableAsyncClient


class TestReopenableAsyncClientInitialization:
    """Test client initialization and configuration."""

    def test_init_with_default_client_class(self):
        """Test initialization with default httpx.AsyncClient."""
        client = ReopenableAsyncClient()
        assert client._client_class == httpx.AsyncClient
        assert client._client is None
        assert client._is_closed is True
        assert client.is_closed is True

    def test_init_with_custom_client_class(self):
        """Test initialization with custom client class."""
        mock_client_class = Mock()
        client = ReopenableAsyncClient(client_class=mock_client_class)
        assert client._client_class == mock_client_class

    def test_init_with_timeout_kwarg(self):
        """Test initialization with timeout parameter."""
        client = ReopenableAsyncClient(timeout=30.0)
        assert client._client_kwargs["timeout"] == 30.0

    def test_init_with_headers_kwarg(self):
        """Test initialization with headers parameter."""
        headers = {"User-Agent": "test"}
        client = ReopenableAsyncClient(headers=headers)
        assert client._client_kwargs["headers"] == headers

    def test_init_with_multiple_kwargs(self):
        """Test initialization with multiple parameters."""
        client = ReopenableAsyncClient(
            timeout=30.0,
            headers={"User-Agent": "test"},
            verify=False,
        )
        assert client._client_kwargs["timeout"] == 30.0
        assert client._client_kwargs["headers"] == {"User-Agent": "test"}
        assert client._client_kwargs["verify"] is False

    def test_init_preserves_kwargs_as_copy(self):
        """Test that initialization preserves kwargs as a copy."""
        kwargs = {"timeout": 30.0}
        client = ReopenableAsyncClient(**kwargs)
        # Verify it's a copy, not the same object
        assert client._client_kwargs is not kwargs
        assert client._client_kwargs == kwargs


class TestClientLifecycle:
    """Test client open/close/reopen lifecycle."""

    async def test_ensure_client_open_creates_client_when_none(self):
        """Test _ensure_client_open creates client when none exists."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            result = await client._ensure_client_open()
            assert result is mock_client
            assert client._client is mock_client
            assert client._is_closed is False

    async def test_ensure_client_open_reuses_open_client(self):
        """Test _ensure_client_open reuses existing open client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        result = await client._ensure_client_open()
        assert result is mock_client

    async def test_ensure_client_open_recreates_closed_client(self):
        """Test _ensure_client_open recreates client when closed."""
        old_mock_client = AsyncMock(spec=httpx.AsyncClient)
        new_mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=new_mock_client):
            client = ReopenableAsyncClient()
            client._client = old_mock_client
            client._is_closed = True

            result = await client._ensure_client_open()
            assert result is new_mock_client
            assert client._client is new_mock_client
            assert client._is_closed is False

    async def test_create_client_initializes_client(self):
        """Test _create_client initializes underlying client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient(timeout=30.0)
            await client._create_client()

            assert client._client is mock_client
            assert client._is_closed is False

    async def test_create_client_with_custom_kwargs(self):
        """Test _create_client passes stored kwargs."""
        mock_client_class = AsyncMock(spec=httpx.AsyncClient)
        client = ReopenableAsyncClient(
            client_class=mock_client_class,
            timeout=30.0,
            headers={"X-Test": "value"},
        )

        await client._create_client()

        mock_client_class.assert_called_once_with(
            timeout=30.0,
            headers={"X-Test": "value"},
        )

    async def test_reopen_creates_new_client(self):
        """Test reopen explicitly creates new client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            await client.reopen()

            assert client._client is mock_client
            assert client._is_closed is False

    async def test_aclose_closes_client(self):
        """Test aclose closes the underlying client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        await client.aclose()

        mock_client.aclose.assert_called_once()
        assert client._is_closed is True

    async def test_aclose_when_already_closed(self):
        """Test aclose when client is already closed."""
        client = ReopenableAsyncClient()
        assert client._is_closed is True

        # Should not raise error
        await client.aclose()
        assert client._is_closed is True

    async def test_aclose_when_client_is_none(self):
        """Test aclose when no client exists."""
        client = ReopenableAsyncClient()
        assert client._client is None

        # Should not raise error
        await client.aclose()

    async def test_create_client_closes_existing_open_client(self):
        """Test _create_client closes existing open client before creating new one."""
        old_client = AsyncMock(spec=httpx.AsyncClient)
        new_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=new_client):
            client = ReopenableAsyncClient()
            client._client = old_client
            client._is_closed = False

            await client._create_client()

            # Old client should be closed
            old_client.aclose.assert_called_once()
            # New client should be set
            assert client._client is new_client


class TestHTTPMethods:
    """Test HTTP method delegation."""

    async def test_get_method(self):
        """Test GET method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.get("https://example.com/test")

            assert response is mock_response
            mock_client.get.assert_called_once_with("https://example.com/test")

    async def test_get_method_with_kwargs(self):
        """Test GET method with additional kwargs."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.get(
                "https://example.com/test",
                params={"key": "value"},
                headers={"X-Custom": "header"},
            )

            assert response is mock_response
            mock_client.get.assert_called_once_with(
                "https://example.com/test",
                params={"key": "value"},
                headers={"X-Custom": "header"},
            )

    async def test_post_method(self):
        """Test POST method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.post(
                "https://example.com/test",
                json={"data": "value"},
            )

            assert response is mock_response
            mock_client.post.assert_called_once_with(
                "https://example.com/test",
                json={"data": "value"},
            )

    async def test_put_method(self):
        """Test PUT method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.put.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.put(
                "https://example.com/test",
                json={"data": "value"},
            )

            assert response is mock_response
            mock_client.put.assert_called_once()

    async def test_patch_method(self):
        """Test PATCH method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.patch.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.patch(
                "https://example.com/test",
                json={"data": "value"},
            )

            assert response is mock_response
            mock_client.patch.assert_called_once()

    async def test_delete_method(self):
        """Test DELETE method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.delete.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.delete("https://example.com/test")

            assert response is mock_response
            mock_client.delete.assert_called_once()

    async def test_head_method(self):
        """Test HEAD method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.head.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.head("https://example.com/test")

            assert response is mock_response
            mock_client.head.assert_called_once()

    async def test_options_method(self):
        """Test OPTIONS method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.options.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.options("https://example.com/test")

            assert response is mock_response
            mock_client.options.assert_called_once()

    async def test_request_method(self):
        """Test generic request method delegation."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.request(
                "PATCH",
                "https://example.com/test",
                json={"data": "value"},
            )

            assert response is mock_response
            mock_client.request.assert_called_once_with(
                "PATCH",
                "https://example.com/test",
                json={"data": "value"},
            )

    async def test_send_method(self):
        """Test send method delegation."""
        mock_request = Mock(spec=httpx.Request)
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.send.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.send(mock_request)

            assert response is mock_response
            mock_client.send.assert_called_once_with(mock_request)

    async def test_send_method_with_kwargs(self):
        """Test send method with additional kwargs."""
        mock_request = Mock(spec=httpx.Request)
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.send.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            response = await client.send(mock_request, stream=True)

            assert response is mock_response
            mock_client.send.assert_called_once_with(mock_request, stream=True)


class TestBuildRequest:
    """Test build_request method."""

    def test_build_request_with_open_client(self):
        """Test build_request delegates to open client."""
        mock_request = Mock(spec=httpx.Request)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.build_request.return_value = mock_request

        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        result = client.build_request("GET", "https://example.com")

        assert result is mock_request
        mock_client.build_request.assert_called_once_with(
            "GET",
            "https://example.com",
        )

    def test_build_request_with_closed_client(self):
        """Test build_request creates temporary client when closed."""
        mock_request = Mock(spec=httpx.Request)
        mock_temp_client = MagicMock(spec=httpx.AsyncClient)
        mock_temp_client.build_request.return_value = mock_request

        with patch("httpx.AsyncClient", return_value=mock_temp_client):
            client = ReopenableAsyncClient()
            result = client.build_request("GET", "https://example.com")

            assert result is mock_request
            mock_temp_client.build_request.assert_called_once()

    def test_build_request_with_kwargs(self):
        """Test build_request with additional kwargs."""
        mock_request = Mock(spec=httpx.Request)
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.build_request.return_value = mock_request

        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        result = client.build_request(
            "POST",
            "https://example.com",
            json={"data": "value"},
            headers={"X-Test": "header"},
        )

        assert result is mock_request
        mock_client.build_request.assert_called_once_with(
            "POST",
            "https://example.com",
            json={"data": "value"},
            headers={"X-Test": "header"},
        )


class TestStreamMethod:
    """Test stream method and _StreamWrapper."""

    def test_stream_returns_wrapper(self):
        """Test stream method returns _StreamWrapper."""
        client = ReopenableAsyncClient()
        wrapper = client.stream("GET", "https://example.com")

        assert isinstance(wrapper, ReopenableAsyncClient._StreamWrapper)
        assert wrapper.parent_client is client
        assert wrapper.method == "GET"
        assert wrapper.url == "https://example.com"

    def test_stream_wrapper_with_kwargs(self):
        """Test stream method preserves kwargs in wrapper."""
        client = ReopenableAsyncClient()
        wrapper = client.stream(
            "GET",
            "https://example.com",
            params={"key": "value"},
        )

        assert wrapper.kwargs == {"params": {"key": "value"}}

    async def test_stream_wrapper_enter_opens_client(self):
        """Test _StreamWrapper.__aenter__ ensures client is open."""
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = AsyncMock()
        mock_stream_ctx.__aexit__.return_value = None

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            wrapper = client.stream("GET", "https://example.com")

            async with wrapper:
                mock_client.stream.assert_called_once_with(
                    "GET",
                    "https://example.com",
                )
                mock_stream_ctx.__aenter__.assert_called_once()

    async def test_stream_wrapper_exit_propagates(self):
        """Test _StreamWrapper.__aexit__ propagates to stream context."""
        mock_response = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = mock_response
        mock_stream_ctx.__aexit__.return_value = False

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            wrapper = client.stream("GET", "https://example.com")

            async with wrapper:
                pass

            mock_stream_ctx.__aexit__.assert_called_once()

    async def test_stream_wrapper_exit_with_no_context(self):
        """Test _StreamWrapper.__aexit__ when context is None."""
        client = ReopenableAsyncClient()
        wrapper = client.stream("GET", "https://example.com")
        wrapper._stream_context = None

        # Should not raise error
        result = await wrapper.__aexit__(None, None, None)
        assert result is None


class TestContextManager:
    """Test async context manager support."""

    async def test_aenter_opens_client(self):
        """Test __aenter__ ensures client is open."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()

            async with client as ctx:
                assert ctx is client
                assert client._is_closed is False

    async def test_aexit_closes_client(self):
        """Test __aexit__ closes client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()

            async with client:
                assert client._is_closed is False

            # After exiting context, client should be closed
            assert client._is_closed is True
            mock_client.aclose.assert_called_once()

    async def test_context_manager_multiple_uses(self):
        """Test context manager can be used multiple times."""
        mock_client1 = AsyncMock(spec=httpx.AsyncClient)
        mock_client2 = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", side_effect=[mock_client1, mock_client2]):
            client = ReopenableAsyncClient()

            # First use
            async with client:
                assert client._is_closed is False
            assert client._is_closed is True

            # Second use
            async with client:
                assert client._is_closed is False
            assert client._is_closed is True

    async def test_context_manager_with_exception(self):
        """Test context manager closes client even on exception."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()

            try:
                async with client:
                    raise ValueError("Test error")
            except ValueError:
                pass

            # Client should still be closed
            assert client._is_closed is True
            mock_client.aclose.assert_called_once()


class TestProperties:
    """Test client properties."""

    def test_is_closed_when_closed(self):
        """Test is_closed property returns True when closed."""
        client = ReopenableAsyncClient()
        assert client.is_closed is True

    def test_is_closed_when_open(self):
        """Test is_closed property returns False when open."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        assert client.is_closed is False

    def test_timeout_from_kwargs(self):
        """Test timeout property from initialization kwargs."""
        client = ReopenableAsyncClient(timeout=30.0)
        assert client.timeout == 30.0

    def test_timeout_when_not_set(self):
        """Test timeout property when not set."""
        client = ReopenableAsyncClient()
        assert client.timeout is None

    def test_headers_from_open_client(self):
        """Test headers property from open client."""
        mock_headers = httpx.Headers({"X-Test": "value"})
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.headers = mock_headers

        client = ReopenableAsyncClient()
        client._client = mock_client

        assert client.headers is mock_headers

    def test_headers_from_kwargs_when_no_client(self):
        """Test headers property from kwargs when no client exists."""
        headers_dict = {"X-Test": "value"}
        client = ReopenableAsyncClient(headers=headers_dict)

        headers = client.headers
        assert isinstance(headers, httpx.Headers)
        assert headers["X-Test"] == "value"

    def test_headers_empty_when_no_kwargs_or_client(self):
        """Test headers property returns empty headers when not configured."""
        client = ReopenableAsyncClient()
        headers = client.headers

        assert isinstance(headers, httpx.Headers)
        assert len(headers) == 0

    def test_cookies_from_open_client(self):
        """Test cookies property from open client."""
        mock_cookies = httpx.Cookies({"session": "abc123"})
        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.cookies = mock_cookies

        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        assert client.cookies is mock_cookies

    def test_cookies_empty_when_closed(self):
        """Test cookies property returns empty cookies when client is closed."""
        client = ReopenableAsyncClient()
        cookies = client.cookies

        assert isinstance(cookies, httpx.Cookies)
        assert len(cookies) == 0

    def test_cookies_empty_when_no_client(self):
        """Test cookies property returns empty cookies when no client exists."""
        mock_client = MagicMock(spec=httpx.AsyncClient)

        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = True

        cookies = client.cookies
        assert isinstance(cookies, httpx.Cookies)
        assert len(cookies) == 0


class TestStringRepresentation:
    """Test string representation of client."""

    def test_repr_when_closed(self):
        """Test __repr__ when client is closed."""
        client = ReopenableAsyncClient()
        repr_str = repr(client)

        assert "ReopenableAsyncClient" in repr_str
        assert "closed" in repr_str

    def test_repr_when_open(self):
        """Test __repr__ when client is open."""
        mock_client = MagicMock(spec=httpx.AsyncClient)
        client = ReopenableAsyncClient()
        client._client = mock_client
        client._is_closed = False

        repr_str = repr(client)
        assert "ReopenableAsyncClient" in repr_str
        assert "open" in repr_str


class TestEdgeCases:
    """Test edge cases and error conditions."""

    async def test_request_after_reopen(self):
        """Test making request after reopening client."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()

            # Make initial request
            response1 = await client.get("https://example.com/1")
            assert response1 is mock_response

            # Close
            await client.aclose()
            assert client.is_closed is True

            # Reopen
            await client.reopen()
            assert client.is_closed is False

            # Make request on reopened client
            response2 = await client.get("https://example.com/2")
            assert response2 is mock_response

    async def test_multiple_close_calls(self):
        """Test calling aclose multiple times."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            await client._ensure_client_open()

            # Close multiple times
            await client.aclose()
            await client.aclose()
            await client.aclose()

            # Only called once on actual client
            assert mock_client.aclose.call_count == 1

    async def test_reopen_after_context_exit(self):
        """Test reopening client after using as context manager."""
        mock_client1 = AsyncMock(spec=httpx.AsyncClient)
        mock_client2 = AsyncMock(spec=httpx.AsyncClient)
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client2.get.return_value = mock_response

        with patch("httpx.AsyncClient", side_effect=[mock_client1, mock_client2]):
            client = ReopenableAsyncClient()

            # Use as context manager
            async with client:
                pass

            # Reopen explicitly
            await client.reopen()
            response = await client.get("https://example.com")

            assert response is mock_response
            assert client.is_closed is False

    async def test_httpx_url_type(self):
        """Test using httpx.URL type for URLs."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            url = httpx.URL("https://example.com")

            response = await client.get(url)

            assert response is mock_response
            mock_client.get.assert_called_once_with(url)

    async def test_concurrent_ensure_open_calls(self):
        """Test multiple concurrent _ensure_client_open calls."""
        import asyncio

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        call_count = 0

        def increment_and_return_client(**kwargs):
            nonlocal call_count
            call_count += 1
            return mock_client

        with patch("httpx.AsyncClient", side_effect=increment_and_return_client):
            client = ReopenableAsyncClient()

            # Create multiple concurrent tasks
            tasks = [client._ensure_client_open() for _ in range(3)]
            results = await asyncio.gather(*tasks)

            # All should return the same client
            assert all(r is mock_client for r in results)
            # Client should be created only once per ensure_open check
            assert call_count >= 1

    async def test_build_request_preserves_configuration(self):
        """Test build_request uses stored configuration."""
        mock_request = Mock(spec=httpx.Request)
        mock_temp_client = MagicMock(spec=httpx.AsyncClient)
        mock_temp_client.build_request.return_value = mock_request

        with patch("httpx.AsyncClient", return_value=mock_temp_client) as mock_class:
            custom_headers = {"X-Auth": "token123"}
            client = ReopenableAsyncClient(
                timeout=42.0,
                headers=custom_headers,
                verify=False,
            )

            # Call build_request when no client exists
            client.build_request("GET", "https://example.com")

            # Should have created client with correct kwargs
            mock_class.assert_called_with(
                timeout=42.0,
                headers=custom_headers,
                verify=False,
            )


class TestStreamWrapperEdgeCases:
    """Test edge cases in _StreamWrapper."""

    async def test_stream_wrapper_with_exception_in_context(self):
        """Test stream wrapper handles exception during streaming."""
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = AsyncMock()
        mock_stream_ctx.__aexit__.return_value = False

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()
            wrapper = client.stream("GET", "https://example.com")

            try:
                async with wrapper:
                    raise ValueError("Stream error")
            except ValueError:
                pass

            # Exit should still be called
            mock_stream_ctx.__aexit__.assert_called_once()

    async def test_stream_wrapper_with_client_recreation(self):
        """Test stream wrapper when client needs to be recreated."""
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = AsyncMock()
        mock_stream_ctx.__aexit__.return_value = None

        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            client = ReopenableAsyncClient()

            # Close client before streaming
            await client._ensure_client_open()
            await client.aclose()

            # Now stream should recreate client
            wrapper = client.stream("GET", "https://example.com")
            async with wrapper:
                assert client.is_closed is False
