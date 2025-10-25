"""Unit tests for code_puppy.reopenable_async_client module."""
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx

from code_puppy.reopenable_async_client import ReopenableAsyncClient


class TestReopenableAsyncClientInit:
    """Test ReopenableAsyncClient initialization."""
    
    def test_init_default(self):
        """Test initialization with no arguments."""
        client = ReopenableAsyncClient()
        
        assert client._client_kwargs == {}
        assert client._client is None
        assert client.is_closed is True
    
    def test_init_with_timeout(self):
        """Test initialization with timeout."""
        client = ReopenableAsyncClient(timeout=30.0)
        
        assert client._client_kwargs == {"timeout": 30.0}
        assert client.timeout == 30.0
    
    def test_init_with_headers(self):
        """Test initialization with headers."""
        headers = {"User-Agent": "test"}
        client = ReopenableAsyncClient(headers=headers)
        
        assert "headers" in client._client_kwargs
        assert client._client_kwargs["headers"] == headers


class TestIsClosedProperty:
    """Test is_closed property."""
    
    def test_is_closed_initially(self):
        """Test client is closed initially."""
        client = ReopenableAsyncClient()
        
        assert client.is_closed is True
    
    async def test_is_closed_after_open(self):
        """Test client is not closed after opening."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient'):
            await client._ensure_client_open()
            
            assert client.is_closed is False


class TestClientCreation:
    """Test client creation and reopening."""
    
    async def test_create_client(self):
        """Test creating a new client."""
        client = ReopenableAsyncClient(timeout=10.0)
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            await client._create_client()
            
            assert client._client is not None
            assert client._is_closed is False
            mock_async_client.assert_called_once_with(timeout=10.0)
    
    async def test_reopen(self):
        """Test reopening a closed client."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            await client.reopen()
            
            assert client._client is not None
            assert client.is_closed is False


class TestAclose:
    """Test closing the client."""
    
    async def test_aclose(self):
        """Test closing the client."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_instance.aclose = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            await client._create_client()
            await client.aclose()
            
            assert client.is_closed is True
            mock_instance.aclose.assert_called_once()
    
    async def test_aclose_when_already_closed(self):
        """Test closing when already closed."""
        client = ReopenableAsyncClient()
        
        # Should not raise
        await client.aclose()
        
        assert client.is_closed is True


class TestHTTPMethods:
    """Test HTTP method delegation."""
    
    async def test_get(self):
        """Test GET request."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_response = Mock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_async_client.return_value = mock_instance
            
            response = await client.get("https://example.com")
            
            assert response is mock_response
            mock_instance.get.assert_called_once_with("https://example.com")
    
    async def test_post(self):
        """Test POST request."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_response = Mock()
            mock_instance.post = AsyncMock(return_value=mock_response)
            mock_async_client.return_value = mock_instance
            
            response = await client.post("https://example.com", json={"key": "value"})
            
            assert response is mock_response
    
    async def test_request_method(self):
        """Test generic request method."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_response = Mock()
            mock_instance.request = AsyncMock(return_value=mock_response)
            mock_async_client.return_value = mock_instance
            
            response = await client.request("GET", "https://example.com")
            
            assert response is mock_response


class TestContextManager:
    """Test context manager support."""
    
    async def test_context_manager(self):
        """Test using client as async context manager."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient') as mock_async_client:
            mock_instance = AsyncMock()
            mock_instance.aclose = AsyncMock()
            mock_async_client.return_value = mock_instance
            
            async with client as c:
                assert c is client
                assert c.is_closed is False
            
            # Should be closed after exiting context
            assert client.is_closed is True


class TestProperties:
    """Test client properties."""
    
    def test_timeout_property(self):
        """Test timeout property."""
        client = ReopenableAsyncClient(timeout=30.0)
        
        assert client.timeout == 30.0
    
    def test_headers_property_no_client(self):
        """Test headers property when no client exists."""
        headers = {"User-Agent": "test"}
        client = ReopenableAsyncClient(headers=headers)
        
        result = client.headers
        
        assert isinstance(result, httpx.Headers)
    
    def test_cookies_property_closed(self):
        """Test cookies property when client is closed."""
        client = ReopenableAsyncClient()
        
        cookies = client.cookies
        
        assert isinstance(cookies, httpx.Cookies)


class TestRepr:
    """Test string representation."""
    
    def test_repr_closed(self):
        """Test repr when client is closed."""
        client = ReopenableAsyncClient()
        
        repr_str = repr(client)
        
        assert "closed" in repr_str
        assert "ReopenableAsyncClient" in repr_str
    
    async def test_repr_open(self):
        """Test repr when client is open."""
        client = ReopenableAsyncClient()
        
        with patch.object(httpx, 'AsyncClient'):
            await client._ensure_client_open()
            
            repr_str = repr(client)
            
            assert "open" in repr_str
