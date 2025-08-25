"""
ReopenableAsyncClient - A reopenable httpx.AsyncClient wrapper.

This module provides a ReopenableAsyncClient class that extends httpx.AsyncClient
to support reopening after being closed, which the standard httpx.AsyncClient
doesn't support.
"""

from typing import Optional, Union

import httpx


class ReopenableAsyncClient:
    """
    A wrapper around httpx.AsyncClient that can be reopened after being closed.

    Standard httpx.AsyncClient becomes unusable after calling aclose().
    This class allows you to reopen the client and continue using it.

    Example:
        >>> client = ReopenableAsyncClient(timeout=30.0)
        >>> await client.get("https://httpbin.org/get")
        >>> await client.aclose()
        >>> # Client is now closed, but can be reopened
        >>> await client.reopen()
        >>> await client.get("https://httpbin.org/get")  # Works!

    The client preserves all original configuration when reopening.
    """

    class _StreamWrapper:
        """Async context manager wrapper for streaming responses."""

        def __init__(
            self,
            parent_client: "ReopenableAsyncClient",
            method: str,
            url: Union[str, httpx.URL],
            **kwargs,
        ):
            self.parent_client = parent_client
            self.method = method
            self.url = url
            self.kwargs = kwargs
            self._stream_context = None

        async def __aenter__(self):
            client = await self.parent_client._ensure_client_open()
            self._stream_context = client.stream(self.method, self.url, **self.kwargs)
            return await self._stream_context.__aenter__()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self._stream_context:
                return await self._stream_context.__aexit__(exc_type, exc_val, exc_tb)

    def __init__(self, **kwargs):
        """
        Initialize the ReopenableAsyncClient.

        Args:
            **kwargs: All arguments that would be passed to httpx.AsyncClient()
        """
        self._client_kwargs = kwargs.copy()
        self._client: Optional[httpx.AsyncClient] = None
        self._is_closed = True

    async def _ensure_client_open(self) -> httpx.AsyncClient:
        """
        Ensure the underlying client is open and ready to use.

        Returns:
            The active httpx.AsyncClient instance

        Raises:
            RuntimeError: If client cannot be opened
        """
        if self._is_closed or self._client is None:
            await self._create_client()
        return self._client

    async def _create_client(self) -> None:
        """Create a new httpx.AsyncClient with the stored configuration."""
        if self._client is not None and not self._is_closed:
            # Close existing client first
            await self._client.aclose()

        self._client = httpx.AsyncClient(**self._client_kwargs)
        self._is_closed = False

    async def reopen(self) -> None:
        """
        Explicitly reopen the client after it has been closed.

        This is useful when you want to reuse a client that was previously closed.
        """
        await self._create_client()

    async def aclose(self) -> None:
        """
        Close the underlying httpx.AsyncClient.

        After calling this, the client can be reopened using reopen() or
        automatically when making the next request.
        """
        if self._client is not None and not self._is_closed:
            await self._client.aclose()
            self._is_closed = True

    @property
    def is_closed(self) -> bool:
        """Check if the client is currently closed."""
        return self._is_closed or self._client is None

    # Delegate all httpx.AsyncClient methods to the underlying client

    async def get(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a GET request."""
        client = await self._ensure_client_open()
        return await client.get(url, **kwargs)

    async def post(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a POST request."""
        client = await self._ensure_client_open()
        return await client.post(url, **kwargs)

    async def put(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a PUT request."""
        client = await self._ensure_client_open()
        return await client.put(url, **kwargs)

    async def patch(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a PATCH request."""
        client = await self._ensure_client_open()
        return await client.patch(url, **kwargs)

    async def delete(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a DELETE request."""
        client = await self._ensure_client_open()
        return await client.delete(url, **kwargs)

    async def head(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make a HEAD request."""
        client = await self._ensure_client_open()
        return await client.head(url, **kwargs)

    async def options(self, url: Union[str, httpx.URL], **kwargs) -> httpx.Response:
        """Make an OPTIONS request."""
        client = await self._ensure_client_open()
        return await client.options(url, **kwargs)

    async def request(
        self, method: str, url: Union[str, httpx.URL], **kwargs
    ) -> httpx.Response:
        """Make a request with the specified HTTP method."""
        client = await self._ensure_client_open()
        return await client.request(method, url, **kwargs)

    async def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        """Send a pre-built request."""
        client = await self._ensure_client_open()
        return await client.send(request, **kwargs)

    def build_request(
        self, method: str, url: Union[str, httpx.URL], **kwargs
    ) -> httpx.Request:
        """
        Build a request without sending it.

        Note: This creates a temporary client if none exists, but doesn't keep it open.
        """
        if self._client is None or self._is_closed:
            # Create a temporary client just for building the request
            temp_client = httpx.AsyncClient(**self._client_kwargs)
            try:
                request = temp_client.build_request(method, url, **kwargs)
                return request
            finally:
                # Clean up the temporary client synchronously if possible
                # Note: This might leave a connection open, but it's better than
                # making this method async just for building requests
                pass
        return self._client.build_request(method, url, **kwargs)

    def stream(self, method: str, url: Union[str, httpx.URL], **kwargs):
        """Stream a request. Returns an async context manager."""
        return self._StreamWrapper(self, method, url, **kwargs)

    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        await self._ensure_client_open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    # Properties that don't require an active client
    @property
    def timeout(self) -> Optional[httpx.Timeout]:
        """Get the configured timeout."""
        return self._client_kwargs.get("timeout")

    @property
    def headers(self) -> httpx.Headers:
        """Get the configured headers."""
        if self._client is not None:
            return self._client.headers
        # Return headers from kwargs if client doesn't exist
        headers = self._client_kwargs.get("headers", {})
        return httpx.Headers(headers)

    @property
    def cookies(self) -> httpx.Cookies:
        """Get the current cookies."""
        if self._client is not None and not self._is_closed:
            return self._client.cookies
        # Return empty cookies if client doesn't exist or is closed
        return httpx.Cookies()

    def __repr__(self) -> str:
        """String representation of the client."""
        status = "closed" if self.is_closed else "open"
        return f"<ReopenableAsyncClient [{status}]>"
