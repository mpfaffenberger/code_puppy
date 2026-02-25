"""DX Documentation MCP client.

This module provides a client for interacting with Walmart's DX documentation
portal via the MCP (Model Context Protocol) JSON-RPC API.

The DX MCP server is available at https://api.dx.walmart.com/mcp and provides
tools for searching and retrieving technical documentation.
"""

import json
import logging
import re
import threading
from typing import List, Optional

import httpx
from pydantic import BaseModel

from code_puppy.plugins.dx_docs.auth import (
    DXAuthError,
    DXTokenExpiredError,
    ensure_authenticated,
)

# Configure logging
logger = logging.getLogger(__name__)

# DX MCP Server endpoint
DX_MCP_ENDPOINT = "https://api.dx.walmart.com/mcp"

# Request timeout in seconds
DEFAULT_TIMEOUT = 30


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class DXError(Exception):
    """Base exception for all DX-related errors."""

    pass


class DXAPIError(DXError):
    """Raised for API errors from the DX MCP server."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class DXNotFoundError(DXError):
    """Raised when a requested resource is not found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class DXRateLimitError(DXError):
    """Raised when rate limited by the API."""

    def __init__(self, message: str = "Rate limited by DX API"):
        super().__init__(message)


# =============================================================================
# MODELS
# =============================================================================


class DXSearchResult(BaseModel):
    """Represents a single search result from DX documentation."""

    page_id: str
    title: str
    url: str
    highlighted: Optional[str] = None


class DXPageContent(BaseModel):
    """Represents the content of a DX documentation page."""

    page_id: str
    title: Optional[str] = None
    content: str
    url: Optional[str] = None


# =============================================================================
# DX MCP CLIENT
# =============================================================================


class DXClient:
    """Client for DX documentation MCP server.

    This client communicates with the DX MCP server using JSON-RPC 2.0
    protocol over HTTP. It provides methods for searching documentation
    and retrieving page content.

    Example:
        client = DXClient()
        results = client.search("WCNP platforms")
        for result in results:
            print(f"{result.title}: {result.url}")
            content = client.get_page_content(result.page_id)
            print(content.content)
    """

    def __init__(self, endpoint: str = DX_MCP_ENDPOINT, timeout: int = DEFAULT_TIMEOUT):
        """Initialize the DX client.

        Args:
            endpoint: The MCP server endpoint URL.
            timeout: Request timeout in seconds.
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self._request_id = 0
        self._id_lock = threading.Lock()  # Thread-safe request ID counter

    def _get_headers(self) -> dict:
        """Get the required headers for MCP API calls.

        Returns:
            Dict with all required headers.

        Raises:
            DXAuthError: If authentication is not available.
        """
        token = ensure_authenticated()
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",  # Critical!
            "Authorization": f"Bearer {token}",
        }

    def _next_request_id(self) -> int:
        """Get the next request ID for JSON-RPC (thread-safe)."""
        with self._id_lock:
            self._request_id += 1
            return self._request_id

    def _extract_text_content(self, result: dict) -> List[str]:
        """Extract text content from MCP response.

        Args:
            result: Raw MCP result containing a 'content' list.

        Returns:
            List of text strings from content items with type='text'.
        """
        return [
            item.get("text", "")
            for item in result.get("content", [])
            if item.get("type") == "text" and item.get("text")
        ]

    def _call_tool(self, tool_name: str, arguments: dict) -> dict:
        """Call an MCP tool via JSON-RPC.

        Args:
            tool_name: Name of the MCP tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            The result from the MCP tool.

        Raises:
            DXAPIError: If the API call fails.
            DXAuthError: If authentication fails.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        logger.debug(f"Calling MCP tool '{tool_name}' with args: {arguments}")

        try:
            response = httpx.post(
                self.endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
            )

            # Handle HTTP errors
            if response.status_code == 401:
                raise DXTokenExpiredError(
                    "Authentication failed. Token may have expired."
                )
            elif response.status_code == 403:
                raise DXAuthError("Access forbidden. Check your permissions.")
            elif response.status_code == 404:
                raise DXNotFoundError(f"Tool '{tool_name}' not found.")
            elif response.status_code == 429:
                raise DXRateLimitError()
            elif response.status_code == 400:
                # This often means missing Accept header
                raise DXAPIError(
                    "Bad request - ensure Accept header includes 'text/event-stream'",
                    status_code=400,
                )
            elif response.status_code >= 400:
                raise DXAPIError(
                    f"API error: {response.text}",
                    status_code=response.status_code,
                )

            # Parse JSON-RPC response
            result = response.json()

            # Check for JSON-RPC error
            if "error" in result:
                error = result["error"]
                raise DXAPIError(
                    f"MCP error: {error.get('message', 'Unknown error')}",
                    details=error,
                )

            return result.get("result", {})

        except httpx.TimeoutException:
            raise DXAPIError(f"Request timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise DXAPIError(f"Request failed: {e}")

    def _parse_search_results(self, result: dict) -> List[DXSearchResult]:
        """Parse search results from MCP response.

        The search tool returns results in a specific format that needs parsing.

        Args:
            result: Raw result from the search tool.

        Returns:
            List of DXSearchResult objects.
        """
        results = []

        for text in self._extract_text_content(result):
            # Parse the text - it's a JSON array of result strings
            try:
                result_strings = json.loads(text)
                if isinstance(result_strings, list):
                    for result_str in result_strings:
                        parsed = self._parse_single_result(result_str)
                        if parsed:
                            results.append(parsed)
            except json.JSONDecodeError:
                # Try parsing as a single result string
                parsed = self._parse_single_result(text)
                if parsed:
                    results.append(parsed)

        return results

    def _parse_single_result(self, result_str: str) -> Optional[DXSearchResult]:
        """Parse a single search result string.

        Args:
            result_str: A result string like "pageId: xxx, title: yyy, ..."

        Returns:
            DXSearchResult or None if parsing fails.
        """
        if not result_str or not isinstance(result_str, str):
            logger.debug(f"Skipping invalid result: {result_str!r}")
            return None

        # Extract fields using regex
        page_id_match = re.search(r"pageId:\s*([^,]+)", result_str)
        title_match = re.search(r"title:\s*([^,]+?)(?:,\s*highlighted:|$)", result_str)
        url_match = re.search(r"url=\s*(\S+)", result_str)
        highlighted_match = re.search(r"highlighted:\s*(.+?)(?:,\s*url=|$)", result_str)

        if not page_id_match:
            logger.warning(f"Failed to parse pageId from result: {result_str[:100]}...")
            return None

        return DXSearchResult(
            page_id=page_id_match.group(1).strip(),
            title=title_match.group(1).strip() if title_match else "Untitled",
            url=url_match.group(1).strip() if url_match else "",
            highlighted=highlighted_match.group(1).strip()
            if highlighted_match
            else None,
        )

    def _parse_page_content(self, result: dict, page_id: str) -> DXPageContent:
        """Parse page content from MCP response.

        Args:
            result: Raw result from the getPageContent tool.
            page_id: The page ID that was requested.

        Returns:
            DXPageContent object.
        """
        content_parts = []
        for text in self._extract_text_content(result):
            # The content might be JSON-escaped
            if text.startswith('"') and text.endswith('"'):
                try:
                    text = json.loads(text)
                except json.JSONDecodeError:
                    pass
            content_parts.append(text)

        return DXPageContent(
            page_id=page_id,
            content="".join(content_parts),
        )

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def search(self, query: str) -> List[DXSearchResult]:
        """Search DX documentation.

        Note: This is a keyword-based search, NOT semantic search.
        For best results, try multiple keyword variations.

        Args:
            query: Search query string.

        Returns:
            List of DXSearchResult objects.

        Raises:
            DXAPIError: If the search fails.
            DXAuthError: If authentication fails.
        """
        result = self._call_tool("search", {"searchQuery": query})
        return self._parse_search_results(result)

    def get_page_content(self, page_id: str) -> DXPageContent:
        """Get the full content of a documentation page.

        Args:
            page_id: The page ID (from search results).

        Returns:
            DXPageContent object with the page content.

        Raises:
            DXNotFoundError: If the page is not found.
            DXAPIError: If the request fails.
            DXAuthError: If authentication fails.
        """
        result = self._call_tool("getPageContent", {"id": page_id})

        # Check for errors in the result
        if result.get("isError"):
            raise DXNotFoundError(f"Page not found: {page_id}")

        return self._parse_page_content(result, page_id)

    def get_document_content(self, document_id: str) -> DXPageContent:
        """Get the content of a document by ID.

        Args:
            document_id: The document ID.

        Returns:
            DXPageContent object with the document content.

        Raises:
            DXNotFoundError: If the document is not found.
            DXAPIError: If the request fails.
        """
        result = self._call_tool("getDocumentContent", {"id": document_id})

        if result.get("isError"):
            raise DXNotFoundError(f"Document not found: {document_id}")

        return self._parse_page_content(result, document_id)

    def get_tags(self) -> List[str]:
        """Get all available tags in the DX documentation system.

        Returns:
            List of tag names.

        Raises:
            DXAPIError: If the request fails.
        """
        result = self._call_tool("getTags", {})

        tags = []
        for text in self._extract_text_content(result):
            try:
                parsed_tags = json.loads(text)
                if isinstance(parsed_tags, list):
                    tags.extend(parsed_tags)
            except json.JSONDecodeError:
                pass

        return tags

    def get_page_metadata(
        self, external_id: str, external_type: str = "github"
    ) -> dict:
        """Get metadata for a page by external ID.

        Args:
            external_id: The external ID of the page.
            external_type: The type of external ID (default: "github").

        Returns:
            Dict with page metadata.

        Raises:
            DXNotFoundError: If the page is not found.
            DXAPIError: If the request fails.
        """
        result = self._call_tool(
            "getPageMetadata",
            {"externalId": external_id, "externalType": external_type},
        )

        if result.get("isError"):
            raise DXNotFoundError(f"Page metadata not found: {external_id}")

        return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_dx_client() -> DXClient:
    """Get a DX client instance.

    Returns:
        DXClient: A configured DX client.
    """
    return DXClient()
