"""Microsoft Graph HTTP client for Code Puppy.

Provides a robust client for interacting with the Microsoft Graph API using
OAuth 2.0 Bearer token authentication with automatic token refresh.

Example:
    with MSGraphClient() as client:
        me = client.get("/me")
        print(f"Hello, {me['displayName']}!")

        messages = client.get("/me/messages", params={"$top": 10})
        for msg in messages.get("value", []):
            print(f"  - {msg['subject']}")

See Also:
    msgraph_auth.py - OAuth 2.0 authentication flow for Microsoft Graph.
    jira_client.py - Similar client pattern for Jira.
    confluence_client.py - Similar client pattern for Confluence.
"""

from __future__ import annotations

from typing import Any

import httpx

from code_puppy import __version__
from code_puppy.messaging import emit_warning
from code_puppy.plugins.walmart_specific.msgraph_auth import (
    MSGRAPH_TOKENS_FILE,
    get_valid_access_token,
)
from code_puppy.plugins.walmart_specific.rate_limiter import SharedRateLimiter


# =============================================================================
# CONSTANTS
# =============================================================================

MSGRAPH_BASE_URL: str = "https://graph.microsoft.com/v1.0"


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class MSGraphError(Exception):
    """Base exception for all Microsoft Graph-related errors."""


class MSGraphAuthError(MSGraphError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class MSGraphNotFoundError(MSGraphError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class MSGraphAPIError(MSGraphError):
    """Raised for other API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class MSGraphThrottledError(MSGraphError):
    """Raised when rate limited by Microsoft Graph (429)."""

    def __init__(
        self,
        message: str = "Rate limited by Microsoft Graph",
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after


# =============================================================================
# MICROSOFT GRAPH CLIENT
# =============================================================================


class MSGraphClient:
    """Microsoft Graph API client with automatic token refresh.

    Uses OAuth 2.0 Bearer token authentication loaded from the tokens file.
    Automatically refreshes expired tokens using the refresh token.

    Example:
        client = MSGraphClient()
        me = client.get("/me")
        print(f"Logged in as: {me['displayName']}")

        # With context manager (recommended)
        with MSGraphClient() as client:
            events = client.get("/me/events", params={"$top": 5})
    """

    def __init__(self):
        """Initialize the Microsoft Graph client.

        Raises:
            MSGraphAuthError: If no valid tokens are available.
        """
        self._access_token: str | None = None
        self._ensure_valid_token()

        user_agent = f"Code Puppy Walmart Internal Version {__version__}"

        self.client = httpx.Client(
            timeout=30.0,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        # Initialize shared rate limiter
        # MS Graph has complex throttling, using 100 req/min as a safe default
        self.rate_limiter = SharedRateLimiter(
            name="msgraph_api",
            max_requests=100,
            time_window=60,
        )

    def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token, refreshing if necessary.

        Raises:
            MSGraphAuthError: If no valid token is available.
        """
        token = get_valid_access_token()

        if not token:
            if not MSGRAPH_TOKENS_FILE.exists():
                raise MSGraphAuthError(
                    f"No Microsoft Graph tokens found at {MSGRAPH_TOKENS_FILE}.\n"
                    "Microsoft Graph authentication required."
                )
            raise MSGraphAuthError(
                "Failed to get valid Microsoft Graph access token.\n"
                "Token may have expired. Microsoft Graph re-authentication required."
            )

        self._access_token = token

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with current access token.

        Returns:
            Dict with Authorization header.
        """
        return {"Authorization": f"Bearer {self._access_token}"}

    def _parse_error_response(self, response: httpx.Response) -> tuple[str, str | None]:
        """Parse Microsoft Graph error response.

        MS Graph returns errors in format:
        {
            "error": {
                "code": "ErrorCode",
                "message": "Human readable message"
            }
        }

        Args:
            response: HTTP response with error status.

        Returns:
            Tuple of (error_message, error_code).
        """
        error_code: str | None = None
        error_msg = f"Microsoft Graph API error (HTTP {response.status_code})"

        try:
            error_data = response.json()
            if "error" in error_data:
                error_obj = error_data["error"]
                error_code = error_obj.get("code")
                message = error_obj.get("message", "")
                if message:
                    error_msg += f": {message}"
                if error_code:
                    error_msg += f" [Code: {error_code}]"
        except Exception:  # noqa: BLE001
            error_msg += f": {response.text[:200]}"

        return error_msg, error_code

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Microsoft Graph API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint (e.g., "/me", "/me/messages").
            **kwargs: Additional arguments to pass to httpx.request.

        Returns:
            JSON response as a dictionary.

        Raises:
            MSGraphAuthError: If authentication fails (401/403).
            MSGraphNotFoundError: If resource is not found (404).
            MSGraphThrottledError: If rate limited (429).
            MSGraphAPIError: For other API errors.
        """
        # Ensure we have a valid token (may refresh if expired)
        self._ensure_valid_token()

        # Wait if our local rate limit is exceeded
        self.rate_limiter.wait_if_needed()

        # Build full URL
        url = f"{MSGRAPH_BASE_URL}{endpoint}"

        # Merge auth headers with any provided headers
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_headers())

        try:
            response = self.client.request(method, url, headers=headers, **kwargs)

            # Handle authentication errors
            if response.status_code == 401:
                # Try refreshing token once
                emit_warning("Access token may be expired, attempting refresh...")
                self._access_token = None
                self._ensure_valid_token()

                # Retry the request with new token
                headers.update(self._get_auth_headers())
                response = self.client.request(method, url, headers=headers, **kwargs)

                if response.status_code == 401:
                    raise MSGraphAuthError(
                        "Authentication failed (HTTP 401). "
                        "Microsoft Graph re-authentication required."
                    )

            if response.status_code == 403:
                error_msg, _ = self._parse_error_response(response)
                raise MSGraphAuthError(
                    f"Access denied (HTTP 403). {error_msg}\n"
                    "Check that your app has the required permissions."
                )

            # Handle not found
            if response.status_code == 404:
                raise MSGraphNotFoundError(f"Resource not found: {endpoint} (HTTP 404)")

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_seconds = int(retry_after) if retry_after else None
                raise MSGraphThrottledError(
                    f"Rate limited by Microsoft Graph. "
                    f"Retry after {retry_seconds or 'unknown'} seconds.",
                    retry_after=retry_seconds,
                )

            # Handle other HTTP errors
            if response.status_code >= 400:
                error_msg, error_code = self._parse_error_response(response)
                raise MSGraphAPIError(
                    error_msg,
                    status_code=response.status_code,
                    error_code=error_code,
                )

            # Record successful request for rate limiting
            self.rate_limiter.record_request()

            # Handle empty responses (204 No Content)
            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

        except httpx.HTTPError as e:
            raise MSGraphAPIError(f"HTTP request failed: {e}") from e

    # =========================================================================
    # HTTP METHOD HELPERS
    # =========================================================================

    def get(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a GET request to the Microsoft Graph API.

        Args:
            endpoint: API endpoint (e.g., "/me", "/me/messages").
            **kwargs: Additional arguments (params, headers, etc.).

        Returns:
            JSON response as a dictionary.

        Example:
            # Get current user
            me = client.get("/me")

            # Get messages with query parameters
            messages = client.get("/me/messages", params={
                "$top": 10,
                "$select": "subject,from,receivedDateTime"
            })
        """
        return self._make_request("GET", endpoint, **kwargs)

    def post(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a POST request to the Microsoft Graph API.

        Args:
            endpoint: API endpoint (e.g., "/me/messages").
            **kwargs: Additional arguments (json, data, headers, etc.).

        Returns:
            JSON response as a dictionary.

        Example:
            # Create a calendar event
            event = client.post("/me/events", json={
                "subject": "Team Meeting",
                "start": {"dateTime": "2024-01-15T10:00:00", "timeZone": "UTC"},
                "end": {"dateTime": "2024-01-15T11:00:00", "timeZone": "UTC"},
            })
        """
        return self._make_request("POST", endpoint, **kwargs)

    def patch(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a PATCH request to the Microsoft Graph API.

        Args:
            endpoint: API endpoint (e.g., "/me/events/{id}").
            **kwargs: Additional arguments (json, data, headers, etc.).

        Returns:
            JSON response as a dictionary.

        Example:
            # Update an event
            client.patch(f"/me/events/{event_id}", json={
                "subject": "Updated Meeting Title"
            })
        """
        return self._make_request("PATCH", endpoint, **kwargs)

    def delete(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make a DELETE request to the Microsoft Graph API.

        Args:
            endpoint: API endpoint (e.g., "/me/events/{id}").
            **kwargs: Additional arguments (headers, etc.).

        Returns:
            Empty dictionary on success (204 No Content).

        Example:
            # Delete an event
            client.delete(f"/me/events/{event_id}")
        """
        return self._make_request("DELETE", endpoint, **kwargs)

    # =========================================================================
    # PAGINATION HELPERS
    # =========================================================================

    def get_all_pages(
        self,
        endpoint: str,
        max_pages: int = 10,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Get all pages of results from a paginated endpoint.

        Microsoft Graph uses @odata.nextLink for pagination. This method
        follows those links to collect all results.

        Args:
            endpoint: API endpoint (e.g., "/me/messages").
            max_pages: Maximum number of pages to fetch (default: 10).
            **kwargs: Additional arguments (params, headers, etc.).

        Returns:
            List of all items from all pages.

        Example:
            # Get all messages (up to max_pages)
            all_messages = client.get_all_pages("/me/messages")
        """
        all_items: list[dict[str, Any]] = []
        pages_fetched = 0

        # Make initial request
        response = self.get(endpoint, **kwargs)
        items = response.get("value", [])
        all_items.extend(items)
        pages_fetched += 1

        # Follow @odata.nextLink pagination
        next_link = response.get("@odata.nextLink")

        while next_link and pages_fetched < max_pages:
            # Extract the path from the full URL
            if next_link.startswith(MSGRAPH_BASE_URL):
                next_endpoint = next_link[len(MSGRAPH_BASE_URL) :]
            else:
                # Assume it's already a relative path
                next_endpoint = next_link

            response = self.get(next_endpoint)
            items = response.get("value", [])
            all_items.extend(items)
            pages_fetched += 1

            next_link = response.get("@odata.nextLink")

        return all_items

    # =========================================================================
    # CONTEXT MANAGER AND CLEANUP
    # =========================================================================

    def __enter__(self) -> MSGraphClient:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - close the HTTP client."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
