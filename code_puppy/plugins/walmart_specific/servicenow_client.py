"""Session-based ServiceNow client for Walmart's ServiceNow instance.

This module provides a robust client for interacting with ServiceNow's
Table API using session-based authentication (cookies loaded from a JSON file).
Primarily focused on searching and retrieving Knowledge Base articles.
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
# MODELS
# =============================================================================


class KBArticleSearchResult(BaseModel):
    """Represents a single knowledge article search result."""

    sys_id: str
    number: str
    short_description: str
    text: str | None = None
    category: str | None = None
    kb_knowledge_base: str | None = None
    workflow_state: str | None = None
    url: str | None = None


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class ServiceNowError(Exception):
    """Base exception for all ServiceNow-related errors."""

    pass


class ServiceNowAuthError(ServiceNowError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class ServiceNowNotFoundError(ServiceNowError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class ServiceNowAPIError(ServiceNowError):
    """Raised for other API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# =============================================================================
# SERVICENOW CLIENT
# =============================================================================


class ServiceNowClient:
    """Session-based ServiceNow client.

    Uses cookies loaded from a JSON file to authenticate with ServiceNow.
    Supports searching and retrieving Knowledge Base articles via the Table API.

    Example:
        client = ServiceNowClient()
        results = client.search_kb_articles("password reset")
        article = client.get_kb_article_by_id("sys_id_here")
    """

    DEFAULT_BASE_URL = "https://walmartglobal.service-now.com"
    DEFAULT_SESSION_FILE = Path(CONFIG_DIR) / "servicenow.json"
    STALENESS_THRESHOLD = timedelta(hours=12)
    KB_TABLE = "kb_knowledge"

    def __init__(self, session_file_path: str | None = None):
        """Initialize the ServiceNow client.

        Args:
            session_file_path: Path to the session JSON file. If None, uses
                ~/.code_puppy/servicenow.json by default.

        Raises:
            ServiceNowError: If session file is missing or invalid.
        """
        self.session_file_path = (
            Path(session_file_path) if session_file_path else self.DEFAULT_SESSION_FILE
        )
        self.session_data = self._load_session()
        self.base_url = self.session_data.get("base_url", self.DEFAULT_BASE_URL)
        
        # Use all_cookies if available (more complete), otherwise fall back to cookies
        self.cookies = self.session_data.get("all_cookies", self.session_data.get("cookies", {}))

        # Check if session is stale
        self._check_staleness()

        # Build custom User-Agent with version and user_id from puppy token
        user_agent = self._build_user_agent()
        
        # Extract X-UserToken if available (ServiceNow uses this for API auth)
        # The g_ck token is the CSRF token needed for REST API calls
        x_user_token = self.cookies.pop("g_ck", None)  # Remove from cookies, use as header
        
        # Build headers
        headers = {
            "User-Agent": user_agent,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if x_user_token:
            headers["X-UserToken"] = x_user_token

        # Create HTTP client with cookies
        self.client = httpx.Client(
            cookies=self.cookies,
            timeout=30.0,
            verify=False,  # SSL verification disabled for Walmart network
            headers=headers,
        )

        # Initialize shared rate limiter (20 requests per minute)
        self.rate_limiter = SharedRateLimiter(
            name="servicenow_api",
            max_requests=20,
            time_window=60,
        )

    def _load_session(self) -> dict[str, Any]:
        """Load and validate the session file.

        Returns:
            Dictionary containing session data (base_url, cookies, timestamp).

        Raises:
            ServiceNowError: If session file is missing or invalid.
        """
        if not self.session_file_path.exists():
            raise ServiceNowError(
                f"Session file not found: {self.session_file_path}\n"
                "ServiceNow authentication required."
            )

        try:
            with open(self.session_file_path, "r") as f:
                session_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ServiceNowError(
                f"Invalid JSON in session file: {self.session_file_path}\n{e}"
            )
        except Exception as e:
            raise ServiceNowError(
                f"Failed to load session file: {self.session_file_path}\n{e}"
            )

        # Validate required fields
        if "cookies" not in session_data:
            raise ServiceNowError(
                f"Session file missing 'cookies' field: {self.session_file_path}"
            )

        if not isinstance(session_data["cookies"], dict):
            raise ServiceNowError(
                f"Invalid 'cookies' field in session file: {self.session_file_path}"
            )

        return session_data

    def _check_staleness(self) -> None:
        """Check if the session is stale and emit a warning if needed."""
        timestamp_str = self.session_data.get("timestamp")
        if not timestamp_str:
            emit_warning("Session file has no timestamp. Consider refreshing.")
            return

        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - timestamp

            if age > self.STALENESS_THRESHOLD:
                hours_old = age.total_seconds() / 3600
                emit_warning(
                    f"ServiceNow session is {hours_old:.1f} hours old. "
                    "Session may be stale, consider re-authenticating."
                )
        except ValueError:
            emit_warning(f"Invalid timestamp format in session file: {timestamp_str}")

    def _build_user_agent(self) -> str:
        """Build a custom User-Agent header with version and user_id."""
        user_agent = f"Code Puppy Walmart Internal Version {__version__}"

        try:
            token = get_puppy_token()
            if token:
                decoded = decode_jwt_without_validation(token)
                if decoded:
                    user_id = (
                        decoded.get("sub")
                        or decoded.get("user_id")
                        or decoded.get("userId")
                        or decoded.get("uid")
                    )
                    if user_id:
                        user_agent += f" ({user_id})"
        except Exception:
            pass

        return user_agent

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the ServiceNow API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, etc.)
            endpoint: API endpoint (e.g., "/api/now/table/kb_knowledge")
            **kwargs: Additional arguments to pass to httpx.request

        Returns:
            JSON response as a dictionary.

        Raises:
            ServiceNowAuthError: If authentication fails (401/403).
            ServiceNowNotFoundError: If resource is not found (404).
            ServiceNowAPIError: For other API errors.
        """
        # Wait if rate limit is exceeded
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.client.request(method, url, **kwargs)

            # Handle authentication errors
            if response.status_code in (401, 403):
                raise ServiceNowAuthError(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "ServiceNow re-authentication required."
                )

            # Handle not found errors
            if response.status_code == 404:
                raise ServiceNowNotFoundError(
                    f"Resource not found: {endpoint} (HTTP 404)"
                )

            # Handle other HTTP errors
            if response.status_code >= 400:
                error_msg = f"ServiceNow API error (HTTP {response.status_code})"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_detail = error_data["error"]
                        if isinstance(error_detail, dict):
                            error_msg += f": {error_detail.get('message', '')}"
                        else:
                            error_msg += f": {error_detail}"
                except Exception:
                    error_msg += f": {response.text[:200]}"

                raise ServiceNowAPIError(error_msg, status_code=response.status_code)

            # Record successful request for rate limiting
            self.rate_limiter.record_request()

            return response.json()

        except httpx.HTTPError as e:
            raise ServiceNowAPIError(f"HTTP request failed: {e}")

    def search_kb_articles(
        self,
        query: str,
        limit: int = 25,
        offset: int = 0,
        workflow_state: str = "published",
    ) -> dict[str, Any]:
        """Search for Knowledge Base articles.

        Args:
            query: Search query string (searches short_description and text)
            limit: Maximum number of results to return (default: 25)
            offset: Starting index for pagination (default: 0)
            workflow_state: Filter by workflow state (default: "published")

        Returns:
            Dictionary containing search results with 'result' array.

        Example:
            results = client.search_kb_articles("password reset", limit=10)
            for article in results['result']:
                print(article['short_description'])
        """
        # Build the query string for ServiceNow
        # Use CONTAINS queries for text search
        sysparm_query = f"short_descriptionLIKE{query}^ORtextLIKE{query}"
        if workflow_state:
            sysparm_query += f"^workflow_state={workflow_state}"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_offset": offset,
            "sysparm_fields": "sys_id,number,short_description,text,kb_category,kb_knowledge_base,workflow_state,sys_updated_on",
            "sysparm_display_value": "true",
        }

        return self._make_request(
            "GET",
            f"/api/now/table/{self.KB_TABLE}",
            params=params,
        )

    def get_kb_article_by_id(
        self,
        sys_id: str,
    ) -> dict[str, Any]:
        """Get a Knowledge Base article by its sys_id.

        Args:
            sys_id: The ServiceNow sys_id of the article

        Returns:
            Dictionary containing article data.

        Example:
            article = client.get_kb_article_by_id("abc123...")
            print(f"Title: {article['result']['short_description']}")
        """
        params = {
            "sysparm_display_value": "true",
        }

        return self._make_request(
            "GET",
            f"/api/now/table/{self.KB_TABLE}/{sys_id}",
            params=params,
        )

    def get_kb_article_by_number(
        self,
        number: str,
    ) -> dict[str, Any]:
        """Get a Knowledge Base article by its article number (e.g., KB0012345).

        Args:
            number: The Knowledge Base article number

        Returns:
            Dictionary containing article data.

        Example:
            article = client.get_kb_article_by_number("KB0012345")
            print(f"Title: {article['result'][0]['short_description']}")
        """
        params = {
            "sysparm_query": f"number={number}",
            "sysparm_limit": 1,
            "sysparm_display_value": "true",
        }

        return self._make_request(
            "GET",
            f"/api/now/table/{self.KB_TABLE}",
            params=params,
        )

    def list_kb_categories(self, limit: int = 50) -> dict[str, Any]:
        """List available Knowledge Base categories.

        Args:
            limit: Maximum number of categories to return (default: 50)

        Returns:
            Dictionary containing category list.
        """
        params = {
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,label,value",
        }

        return self._make_request(
            "GET",
            "/api/now/table/kb_category",
            params=params,
        )

    def search_kb_by_category(
        self,
        category: str,
        query: str = "",
        limit: int = 25,
        workflow_state: str = "published",
    ) -> dict[str, Any]:
        """Search for Knowledge Base articles within a specific category.

        Args:
            category: Category name or sys_id
            query: Optional search query string
            limit: Maximum number of results (default: 25)
            workflow_state: Filter by workflow state (default: "published")

        Returns:
            Dictionary containing search results.
        """
        # kb_category is a reference field - try matching by sys_id first,
        # then fall back to LIKE query on the display value
        if len(category) == 32 and category.isalnum():
            # Looks like a sys_id
            sysparm_query = f"kb_category={category}"
        else:
            # Treat as a display name - use LIKE query
            sysparm_query = f"kb_categoryLIKE{category}"
        
        if query:
            sysparm_query += f"^short_descriptionLIKE{query}^ORtextLIKE{query}"
        if workflow_state:
            sysparm_query += f"^workflow_state={workflow_state}"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,number,short_description,text,kb_category,kb_knowledge_base,workflow_state,sys_updated_on",
            "sysparm_display_value": "true",
        }

        return self._make_request(
            "GET",
            f"/api/now/table/{self.KB_TABLE}",
            params=params,
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close the HTTP client."""
        self.client.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()
