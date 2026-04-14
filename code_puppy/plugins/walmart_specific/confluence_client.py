"""Session-based Confluence client for Walmart's Confluence instance.

This module provides a robust client for interacting with Confluence using
session-based authentication (cookies loaded from a JSON file).
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from code_puppy import __version__
from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_warning
from code_puppy.plugins.walmart_specific.auth import (
    decode_jwt_without_validation,
    get_puppy_token,
)
from code_puppy.plugins.walmart_specific.rate_limiter import SharedRateLimiter


# =============================================================================
# MODULE-LEVEL STATE
# =============================================================================

# Track if we've already emitted the staleness warning this session
# to avoid spamming the terminal with duplicate warnings
_staleness_warning_emitted = False


def _reset_staleness_warning_flag() -> None:
    """Reset the staleness warning flag. Used for testing."""
    global _staleness_warning_emitted
    _staleness_warning_emitted = False


# =============================================================================
# MODELS
# =============================================================================


class ConfluenceSearchResult(BaseModel):
    """Represents a single search result from Confluence."""

    id: str
    title: str
    space_key: str
    space_name: str
    excerpt: str
    url: str


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class ConfluenceError(Exception):
    """Base exception for all Confluence-related errors."""

    pass


class ConfluenceAuthError(ConfluenceError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class ConfluenceNotFoundError(ConfluenceError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ConfluenceAPIError(ConfluenceError):
    """Raised for other API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# =============================================================================
# CONFLUENCE CLIENT
# =============================================================================


class ConfluenceClient:
    """Session-based Confluence client.

    Uses cookies loaded from a JSON file to authenticate with Confluence.
    Supports CQL search, page retrieval, and title-based search.

    Example:
        client = ConfluenceClient()
        results = client.search_content("type=page AND space=MYSPACE")
        page = client.get_page_by_id("123456789")
    """

    DEFAULT_BASE_URL = "https://confluence.walmart.com"
    DEFAULT_SESSION_FILE = Path(CONFIG_DIR) / "confluence.json"
    STALENESS_THRESHOLD = timedelta(hours=12)

    def __init__(self, session_file_path: str | None = None):
        """Initialize the Confluence client.

        Args:
            session_file_path: Path to the session JSON file. If None, uses
                ~/.code_puppy/confluence.json by default.

        Raises:
            ConfluenceError: If session file is missing or invalid.
        """
        self.session_file_path = (
            Path(session_file_path) if session_file_path else self.DEFAULT_SESSION_FILE
        )
        self.session_data = self._load_session()
        self.base_url = self.session_data.get("base_url", self.DEFAULT_BASE_URL)
        self.cookies = self.session_data.get("cookies", {})

        # Check if session is stale
        self._check_staleness()

        # Build custom User-Agent with version and user_id from puppy token
        user_agent = self._build_user_agent()

        # Create HTTP client with cookies (SSL verification disabled for Walmart network)
        self.client = httpx.Client(
            cookies=self.cookies,
            timeout=30.0,
            # verify omitted - uses system CA bundle
            headers={"User-Agent": user_agent},
        )

        # Initialize shared rate limiter (20 requests per minute, shared across all instances)
        self.rate_limiter = SharedRateLimiter(
            name="confluence_api",
            max_requests=20,
            time_window=60,
        )

    def _load_session(self) -> dict[str, Any]:
        """Load and validate the session file.

        Returns:
            Dictionary containing session data (base_url, cookies, timestamp).

        Raises:
            ConfluenceError: If session file is missing or invalid.
        """
        if not self.session_file_path.exists():
            raise ConfluenceError(
                f"Session file not found: {self.session_file_path}\n"
                "Confluence authentication required."
            )

        try:
            with open(self.session_file_path, "r") as f:
                session_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfluenceError(
                f"Invalid JSON in session file: {self.session_file_path}\n{e}"
            )
        except Exception as e:
            raise ConfluenceError(
                f"Failed to load session file: {self.session_file_path}\n{e}"
            )

        # Validate required fields
        if "cookies" not in session_data:
            raise ConfluenceError(
                f"Session file missing 'cookies' field: {self.session_file_path}"
            )

        if not isinstance(session_data["cookies"], dict):
            raise ConfluenceError(
                f"Invalid 'cookies' field in session file: {self.session_file_path}"
            )

        return session_data

    def _check_staleness(self) -> None:
        """Check if the session is stale and emit a warning if needed.

        A session is considered stale if it's older than STALENESS_THRESHOLD (12 hours).
        Only emits the warning once per process to avoid spamming the terminal.
        """
        global _staleness_warning_emitted

        # Skip if we've already warned this session
        if _staleness_warning_emitted:
            return

        timestamp_str = self.session_data.get("timestamp")
        if not timestamp_str:
            emit_warning("Session file has no timestamp. Consider refreshing.")
            _staleness_warning_emitted = True
            return

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - timestamp

            if age > self.STALENESS_THRESHOLD:
                hours_old = age.total_seconds() / 3600
                emit_warning(
                    f"Confluence session is {hours_old:.1f} hours old. "
                    "Session may be stale, consider re-authenticating."
                )
                _staleness_warning_emitted = True
        except ValueError:
            emit_warning(f"Invalid timestamp format in session file: {timestamp_str}")
            _staleness_warning_emitted = True

    def _build_user_agent(self) -> str:
        """Build a custom User-Agent header with version and user_id.

        Returns:
            User-Agent string in format: 'Code Puppy Walmart Internal Version {version} ({user_id})'
            Falls back to 'Code Puppy Walmart Internal Version {version}' if user_id cannot be determined.
        """
        # Start with version
        user_agent = f"Code Puppy Walmart Internal Version {__version__}"

        # Try to get user_id from puppy token
        try:
            token = get_puppy_token()
            if token:
                decoded = decode_jwt_without_validation(token)
                if decoded:
                    # Common JWT claims for user identity: sub, user_id, userId, uid
                    user_id = (
                        decoded.get("sub")
                        or decoded.get("user_id")
                        or decoded.get("userId")
                        or decoded.get("uid")
                    )
                    if user_id:
                        user_agent += f" ({user_id})"
        except Exception:
            # Silently fall back to version-only if token decoding fails
            pass

        return user_agent

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Confluence API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/rest/api/content/123")
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            JSON response as a dictionary.

        Raises:
            ConfluenceAuthError: If authentication fails (401/403).
            ConfluenceNotFoundError: If resource is not found (404).
            ConfluenceAPIError: For other API errors.
        """
        # Wait if rate limit is exceeded (shared across all Code Puppy instances)
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.client.request(method, url, **kwargs)

            # Handle authentication errors
            if response.status_code in (401, 403):
                raise ConfluenceAuthError(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Confluence re-authentication required."
                )

            # Handle not found errors
            if response.status_code == 404:
                raise ConfluenceNotFoundError(
                    f"Resource not found: {endpoint} (HTTP 404)"
                )

            # Handle other HTTP errors
            if response.status_code >= 400:
                error_msg = f"Confluence API error (HTTP {response.status_code})"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f": {error_data['message']}"
                except Exception:
                    error_msg += f": {response.text[:200]}"

                raise ConfluenceAPIError(error_msg, status_code=response.status_code)

            # Record successful request for rate limiting (only count successful requests)
            self.rate_limiter.record_request()

            # Return JSON response
            return response.json()

        except httpx.HTTPError as e:
            raise ConfluenceAPIError(f"HTTP request failed: {e}")

    def search_content(
        self,
        cql: str,
        limit: int = 25,
        start: int = 0,
    ) -> dict[str, Any]:
        """Search for Confluence content using CQL (Confluence Query Language).

        Args:
            cql: CQL query string (e.g., "type=page AND space=MYSPACE")
            limit: Maximum number of results to return (default: 25)
            start: Starting index for pagination (default: 0)

        Returns:
            Dictionary containing search results with 'results', 'size', 'start', etc.

        Example:
            results = client.search_content(
                "type=page AND title~'my page'",
                limit=10
            )
            for page in results['results']:
                print(page['title'])
        """
        params = {
            "cql": cql,
            "limit": limit,
            "start": start,
        }

        return self._make_request(
            "GET",
            "/rest/api/content/search",
            params=params,
        )

    def get_page_by_id(
        self,
        page_id: str,
        expand: str = "version,space",
    ) -> dict[str, Any]:
        """Get a Confluence page by its ID.

        Args:
            page_id: The Confluence page ID
            expand: Comma-separated list of properties to expand
                (default: "version,space")

        Returns:
            Dictionary containing page metadata.

        Example:
            page = client.get_page_by_id("123456789")
            print(f"Title: {page['title']}")
            print(f"Space: {page['space']['key']}")
        """
        params = {"expand": expand}

        return self._make_request(
            "GET",
            f"/rest/api/content/{page_id}",
            params=params,
        )

    def get_page_content(
        self,
        page_id: str,
        expand: str = "body.storage,version,space",
    ) -> dict[str, Any]:
        """Get a Confluence page with full content.

        Args:
            page_id: The Confluence page ID
            expand: Comma-separated list of properties to expand
                (default: "body.storage,version,space")

        Returns:
            Dictionary containing page metadata and full content.

        Example:
            page = client.get_page_content("123456789")
            html_content = page['body']['storage']['value']
            print(f"Title: {page['title']}")
            print(f"Content: {html_content}")
        """
        params = {"expand": expand}

        return self._make_request(
            "GET",
            f"/rest/api/content/{page_id}",
            params=params,
        )

    def search_by_title(
        self,
        title: str,
        space_key: str | None = None,
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search for Confluence pages by title.

        Args:
            title: Page title (supports partial matching with '~')
            space_key: Optional space key to restrict search (e.g., "ENG")
            limit: Maximum number of results to return (default: 25)

        Returns:
            Dictionary containing search results.

        Example:
            # Exact match
            results = client.search_by_title("My Page Title")

            # Partial match
            results = client.search_by_title("~my page")

            # Search in specific space
            results = client.search_by_title("My Page", space_key="ENG")
        """
        # Build CQL query
        if title.startswith("~"):
            # Partial match
            cql = f"type=page AND title~'{title[1:]}'"
        else:
            # Exact match
            cql = f"type=page AND title='{title}'"

        # Add space restriction if provided
        if space_key:
            cql += f" AND space='{space_key}'"

        return self.search_content(cql, limit=limit)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close the HTTP client."""
        self.client.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()
