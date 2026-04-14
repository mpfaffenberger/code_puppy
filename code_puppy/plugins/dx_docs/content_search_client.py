"""DX Content Search Client for Tech Assistant Service.

This module provides a client for semantic/vector search of Walmart's
internal technical documentation via the Tech Assistant Service MCP endpoint.

Unlike the keyword-based DX MCP server, this uses AI embeddings for
semantic search - better for natural language questions like
"Why is my Kafka consumer lagging?" even without exact keyword matches.

Endpoint: https://tech-assistant-service.hub.walmart.com/api/mcp
Protocol: JSON-RPC 2.0 over HTTP (same as client.py)
"""

import json
import logging
import threading
from typing import Any, List, Optional

import httpx

from code_puppy.http_utils import get_cert_bundle_path
from pydantic import BaseModel

from code_puppy.plugins.dx_docs.auth import (
    DXAuthError,
    DXTokenExpiredError,
    ensure_authenticated,
)

# Configure logging
logger = logging.getLogger(__name__)

# Tech Assistant Service MCP endpoint (supports PingFed Bearer tokens)
CONTENT_SEARCH_ENDPOINT = "https://tech-assistant-service.hub.walmart.com/api/mcp"

# Request timeout in seconds
DEFAULT_TIMEOUT = 60

# Valid product filters for content search
VALID_PRODUCTS = frozenset(
    [
        "kafka",
        "wcnp",
        "looper",
        "concord",
        "azure",
        "elementai",
        "element",  # Alias for elementai
    ]
)


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class ContentSearchError(Exception):
    """Base exception for content search errors."""

    pass


class ContentSearchAPIError(ContentSearchError):
    """Raised for API errors from the content search server."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or {}


class ContentSearchSSEError(ContentSearchError):
    """Raised for HTTP streaming errors (legacy, kept for compatibility)."""

    pass


# =============================================================================
# MODELS
# =============================================================================


class ContentSearchResult(BaseModel):
    """Represents a single result from semantic content search."""

    title: str
    content: str
    url: Optional[str] = None
    source: Optional[str] = None
    score: Optional[float] = None
    product: Optional[str] = None


# =============================================================================
# DX CONTENT SEARCH CLIENT
# =============================================================================


class DXContentSearchClient:
    """Client for semantic content search via Tech Assistant Service.

    This client communicates with the Tech Assistant Service using
    JSON-RPC 2.0 over HTTP with PingFed Bearer token authentication.

    Example:
        client = DXContentSearchClient()
        results = client.search_tech_content(
            "Why is my Kafka consumer lagging?",
            product="kafka"
        )
        for result in results:
            print(f"{result.title}: {result.content[:100]}...")
    """

    def __init__(
        self,
        endpoint: str = CONTENT_SEARCH_ENDPOINT,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        """Initialize the content search client.

        Args:
            endpoint: The Tech Assistant Service MCP endpoint URL.
            timeout: Request timeout in seconds.
        """
        self.endpoint = endpoint
        self.timeout = timeout
        self._request_id = 0
        self._id_lock = threading.Lock()

    def _get_headers(self) -> dict:
        """Get the required headers for API calls.

        Returns:
            Dict with all required headers.

        Raises:
            DXAuthError: If authentication is not available.
        """
        token = ensure_authenticated()
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "CALLER_INTERFACE": "WIBEY_CLI",  # Required header for Tech Assistant
        }

    def _next_request_id(self) -> int:
        """Get the next request ID for JSON-RPC (thread-safe)."""
        with self._id_lock:
            self._request_id = (self._request_id + 1) % (2**31)
            return self._request_id

    def _call_tool(
        self,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        """Call an MCP tool via HTTP POST and return the response.

        Args:
            tool_name: Name of the MCP tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            The result from the MCP tool.

        Raises:
            ContentSearchAPIError: If the API call fails.
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

        logger.debug(f"Calling tool '{tool_name}' with args: {arguments}")

        try:
            response = httpx.post(
                self.endpoint,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
                verify=get_cert_bundle_path(),  # Walmart CA bundle
            )

            # Handle HTTP errors
            if response.status_code == 401:
                raise DXTokenExpiredError(
                    "Authentication failed. Token may have expired."
                )
            elif response.status_code == 403:
                raise DXAuthError("Access forbidden. Check your permissions.")
            elif response.status_code == 429:
                raise ContentSearchAPIError(
                    "Rate limited by content search API",
                    status_code=429,
                )
            elif response.status_code >= 400:
                raise ContentSearchAPIError(
                    f"API error: {response.status_code} - {response.text[:200]}",
                    status_code=response.status_code,
                )

            # Parse JSON response
            return self._parse_response(response)

        except httpx.TimeoutException:
            raise ContentSearchAPIError(f"Request timed out after {self.timeout}s")
        except httpx.RequestError as e:
            raise ContentSearchAPIError(f"Request failed: {e}")

    def _parse_response(self, response: httpx.Response) -> dict:
        """Parse the HTTP response and extract the result.

        Args:
            response: httpx Response object.

        Returns:
            The result dict from the JSON-RPC response.

        Raises:
            ContentSearchAPIError: If parsing fails or response contains error.
        """
        try:
            data = response.json()
        except json.JSONDecodeError as e:
            # Response might be SSE format, try to parse it
            text = response.text
            if text.startswith("data:"):
                # Extract JSON from SSE-style response
                try:
                    json_str = text.split("data:", 1)[1].strip()
                    # Handle multiple data: lines
                    if "\ndata:" in json_str:
                        json_str = json_str.split("\n")[0]
                    data = json.loads(json_str)
                except (json.JSONDecodeError, IndexError):
                    raise ContentSearchAPIError(
                        f"Failed to parse response: {e}. Response: {text[:200]}"
                    )
            else:
                raise ContentSearchAPIError(
                    f"Failed to parse JSON response: {e}. Response: {text[:200]}"
                )

        # Handle JSON-RPC error
        if "error" in data:
            error = data["error"]
            raise ContentSearchAPIError(
                f"MCP error: {error.get('message', 'Unknown error')}",
                details=error,
            )

        # Extract result
        result = data.get("result", {})

        # Extract text content from MCP response format
        content_parts: List[str] = []
        for item in result.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                content_parts.append(item["text"])

        # If we collected content parts, add them to result
        if content_parts:
            result["_collected_text"] = content_parts

        return result

    def _parse_search_results(
        self,
        result: dict,
    ) -> List[ContentSearchResult]:
        """Parse search results from the API response.

        The content search returns results that may be in various formats.
        This method handles the common formats and extracts structured results.

        Args:
            result: Raw result from the tool call.

        Returns:
            List of ContentSearchResult objects.
        """
        results: List[ContentSearchResult] = []
        collected_text = result.get("_collected_text", [])

        for text in collected_text:
            # Try to parse as JSON (array of results or single result)
            try:
                parsed = json.loads(text)

                # Handle array of results
                if isinstance(parsed, list):
                    for item in parsed:
                        parsed_result = self._parse_single_result(item)
                        if parsed_result:
                            results.append(parsed_result)
                # Handle single result object
                elif isinstance(parsed, dict):
                    parsed_result = self._parse_single_result(parsed)
                    if parsed_result:
                        results.append(parsed_result)

            except json.JSONDecodeError:
                # Not JSON - try to extract as plain text result
                if text.strip():
                    results.append(
                        ContentSearchResult(
                            title="Search Result",
                            content=text.strip(),
                        )
                    )

        return results

    def _parse_single_result(
        self,
        data: Any,
    ) -> Optional[ContentSearchResult]:
        """Parse a single result object.

        Args:
            data: Dict or other data representing a search result.

        Returns:
            ContentSearchResult or None if parsing fails.
        """
        if not isinstance(data, dict):
            return None

        # Extract fields with fallbacks for different field names
        # Use None first to check if any real value exists
        raw_title = data.get("title") or data.get("name") or data.get("heading")
        raw_content = (
            data.get("content")
            or data.get("text")
            or data.get("snippet")
            or data.get("body")
        )

        # Require at least some meaningful content or title
        if not raw_content and not raw_title:
            return None

        url = data.get("url") or data.get("link") or data.get("href")
        source = data.get("source") or data.get("origin")
        score = data.get("score") or data.get("relevance")
        product = data.get("product") or data.get("category")

        return ContentSearchResult(
            title=str(raw_title) if raw_title else "Untitled",
            content=str(raw_content) if raw_content else "",
            url=str(url) if url else None,
            source=str(source) if source else None,
            score=float(score) if score is not None else None,
            product=str(product) if product else None,
        )

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def search_tech_content(
        self,
        query: str,
        product: Optional[str] = None,
    ) -> List[ContentSearchResult]:
        """Semantic search of internal tech documentation.

        Uses AI embeddings to find semantically similar content - works well
        for natural language questions even without exact keyword matches.

        Args:
            query: Natural language search query.
            product: Optional product filter. Valid values:
                - kafka: Kafka documentation
                - wcnp: Walmart Cloud Native Platform
                - looper: Looper/application lifecycle
                - concord: Concord workflow orchestration
                - azure: Azure cloud documentation
                - elementai: Element AI / LLM Gateway docs

        Returns:
            List of ContentSearchResult objects.

        Raises:
            ContentSearchAPIError: If the search fails.
            DXAuthError: If authentication fails.
        """
        # Validate query
        if not query or not query.strip():
            raise ContentSearchAPIError("Query cannot be empty")

        if len(query) > 2000:
            raise ContentSearchAPIError(
                "Query exceeds maximum length of 2000 characters"
            )

        # Normalize and validate product filter
        effective_product = None
        if product:
            normalized = product.lower().strip()
            if normalized == "element":
                normalized = "elementai"

            if normalized in VALID_PRODUCTS:
                effective_product = normalized
            else:
                logger.warning(
                    f"Invalid product filter '{product}', ignoring. "
                    f"Valid options: {', '.join(sorted(VALID_PRODUCTS))}"
                )

        # Build query - include product context for better semantic matching
        if effective_product:
            search_query = f"[{effective_product}] {query}"
        else:
            search_query = query

        result = self._call_tool("ask", {"query": search_query})
        return self._parse_search_results(result)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def get_content_search_client() -> DXContentSearchClient:
    """Get a content search client instance.

    Returns:
        DXContentSearchClient: A configured content search client.
    """
    return DXContentSearchClient()
