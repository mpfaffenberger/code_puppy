"""Minimal smoke tests for ReopenableAsyncClient.

Trimmed from a much larger suite (round 5 test reduction) while keeping the
core lifecycle and method-delegation paths covered.
"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from code_puppy.reopenable_async_client import ReopenableAsyncClient


def test_init_defaults_and_kwargs():
    client = ReopenableAsyncClient(timeout=30.0, headers={"User-Agent": "test"})
    assert client._client_class is httpx.AsyncClient
    assert client._client is None
    assert client.is_closed is True
    assert client._client_kwargs["timeout"] == 30.0
    assert client._client_kwargs == {"timeout": 30.0, "headers": {"User-Agent": "test"}}
    # kwargs are copied, not aliased
    kwargs = {"timeout": 5.0}
    other = ReopenableAsyncClient(**kwargs)
    assert other._client_kwargs is not kwargs


def test_custom_client_class():
    mock_class = Mock()
    client = ReopenableAsyncClient(client_class=mock_class)
    assert client._client_class is mock_class


@pytest.mark.asyncio
async def test_ensure_client_open_creates_and_reuses():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    with patch("httpx.AsyncClient", return_value=mock_client):
        client = ReopenableAsyncClient()
        created = await client._ensure_client_open()
        assert created is mock_client
        assert client._is_closed is False
        # Reuse the open client without creating a new one
        again = await client._ensure_client_open()
        assert again is mock_client
        assert httpx.AsyncClient.call_count == 1


@pytest.mark.asyncio
async def test_reopen_and_aclose_lifecycle():
    first = AsyncMock(spec=httpx.AsyncClient)
    second = AsyncMock(spec=httpx.AsyncClient)
    with patch("httpx.AsyncClient", side_effect=[first, second]):
        client = ReopenableAsyncClient()
        await client._ensure_client_open()
        assert client._client is first
        await client.aclose()
        assert client._is_closed is True
        assert first.aclose.await_count == 1
        # Reopen creates a fresh underlying client
        await client.reopen()
        assert client._client is second
        assert client._is_closed is False


@pytest.mark.asyncio
async def test_http_methods_delegate_to_client():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    with patch("httpx.AsyncClient", return_value=mock_client):
        client = ReopenableAsyncClient()
        await client.get("https://example.com")
        await client.post("https://example.com", json={})
        await client.request("PATCH", "https://example.com")
        assert mock_client.get.await_count == 1
        assert mock_client.post.await_count == 1
        assert mock_client.request.await_count == 1


def test_build_request_with_closed_client_uses_temp_client():
    with patch("httpx.Client") as temp_cls:
        temp_cls.return_value.build_request.return_value = "built"
        client = ReopenableAsyncClient()
        result = client.build_request("GET", "https://example.com")
        assert result == "built"
        temp_cls.return_value.close.assert_called_once()


@pytest.mark.asyncio
async def test_stream_wrapper_and_context_manager():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    stream_cm = mock_client.stream.return_value
    stream_cm.__aenter__.return_value = "stream"
    with patch("httpx.AsyncClient", return_value=mock_client):
        client = ReopenableAsyncClient()
        async with client as opened:
            assert opened is client
        assert mock_client.aclose.await_count == 1
        # stream() returns an async CM that opens the client
        client._is_closed = True
        wrapper = client.stream("GET", "https://example.com")
        async with wrapper as s:
            assert s == "stream"
        assert mock_client.stream.called


def test_properties_and_repr():
    client = ReopenableAsyncClient(timeout=15.0)
    assert client.timeout == 15.0
    assert "closed" in repr(client)
    assert isinstance(client.headers, httpx.Headers)
    assert isinstance(client.cookies, httpx.Cookies)
