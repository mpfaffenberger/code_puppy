"""Power BI HTTP client for Code Puppy.

Provides a robust client for interacting with the Power BI REST API using
OAuth 2.0 Bearer token authentication with automatic token refresh.

Example:
    with PowerBIClient() as client:
        workspaces = client.get("/groups")
        for ws in workspaces.get("value", []):
            print(f"  - {ws['name']}")

See Also:
    powerbi_auth.py - OAuth 2.0 authentication flow for Power BI.
    msgraph_client.py - Similar client pattern for Microsoft Graph.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import httpx

from code_puppy import __version__
from code_puppy.messaging import emit_warning
from code_puppy.plugins.walmart_specific.powerbi_auth import (
    POWERBI_TOKENS_FILE,
    get_valid_access_token,
)
from code_puppy.plugins.walmart_specific.rate_limiter import SharedRateLimiter


# =============================================================================
# CONSTANTS
# =============================================================================

POWERBI_BASE_URL: str = "https://api.powerbi.com/v1.0/myorg"


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class PowerBIError(Exception):
    """Base exception for all Power BI-related errors."""


class PowerBIAuthError(PowerBIError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class PowerBINotFoundError(PowerBIError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class PowerBIAPIError(PowerBIError):
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


class PowerBIThrottledError(PowerBIError):
    """Raised when rate limited by Power BI (429)."""

    def __init__(
        self,
        message: str = "Rate limited by Power BI",
        retry_after: int | None = None,
    ):
        super().__init__(message)
        self.retry_after = retry_after


# =============================================================================
# POWER BI CLIENT
# =============================================================================


class PowerBIClient:
    """Power BI API client with automatic token refresh.

    Uses OAuth 2.0 Bearer token authentication loaded from the tokens file.
    Automatically refreshes expired tokens using MSAL.

    Example:
        client = PowerBIClient()
        workspaces = client.get("/groups")
        print(f"Found {len(workspaces.get('value', []))} workspaces")

        # With context manager (recommended)
        with PowerBIClient() as client:
            reports = client.get("/reports")
    """

    def __init__(self):
        """Initialize the Power BI client.

        Raises:
            PowerBIAuthError: If no valid tokens are available.
        """
        self._access_token: str | None = None
        self._ensure_valid_token()

        user_agent = f"Code Puppy Walmart Internal Version {__version__}"

        self.client = httpx.Client(
            timeout=60.0,  # Power BI queries can be slow
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        # Initialize shared rate limiter
        # Power BI has rate limits, using conservative defaults
        self.rate_limiter = SharedRateLimiter(
            name="powerbi_api",
            max_requests=60,
            time_window=60,
        )

    def _ensure_valid_token(self) -> None:
        """Ensure we have a valid access token, refreshing if necessary.

        Raises:
            PowerBIAuthError: If no valid token is available.
        """
        token = get_valid_access_token()

        if not token:
            if not POWERBI_TOKENS_FILE.exists():
                raise PowerBIAuthError(
                    f"No Power BI tokens found at {POWERBI_TOKENS_FILE}.\n"
                    "Run /powerbi_auth to authenticate."
                )
            raise PowerBIAuthError(
                "Failed to get valid Power BI access token.\n"
                "Token may have expired. Run /powerbi_auth to re-authenticate."
            )

        self._access_token = token

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authorization headers with current access token."""
        return {"Authorization": f"Bearer {self._access_token}"}

    def _parse_error_response(self, response: httpx.Response) -> tuple[str, str | None]:
        """Parse Power BI error response."""
        error_code: str | None = None
        error_msg = f"Power BI API error (HTTP {response.status_code})"

        try:
            # Check for Power BI error info header
            error_info = response.headers.get("x-powerbi-error-info")
            if error_info:
                error_msg += f": {error_info}"
                error_code = error_info
            else:
                error_data = response.json()
                if "error" in error_data:
                    error_obj = error_data["error"]
                    error_code = error_obj.get("code")
                    message = error_obj.get("message", "")
                    if message:
                        error_msg += f": {message}"
        except Exception:
            error_msg += f": {response.text[:200]}"

        return error_msg, error_code

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Power BI API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            endpoint: API endpoint (e.g., "/groups", "/reports").
            **kwargs: Additional arguments to pass to httpx.request.

        Returns:
            JSON response as a dictionary.

        Raises:
            PowerBIAuthError: If authentication fails (401/403).
            PowerBINotFoundError: If resource is not found (404).
            PowerBIThrottledError: If rate limited (429).
            PowerBIAPIError: For other API errors.
        """
        self._ensure_valid_token()
        self.rate_limiter.wait_if_needed()

        url = f"{POWERBI_BASE_URL}{endpoint}"

        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_headers())

        try:
            response = self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code == 401:
                emit_warning("Access token may be expired, attempting refresh...")
                self._access_token = None
                self._ensure_valid_token()
                headers.update(self._get_auth_headers())
                response = self.client.request(method, url, headers=headers, **kwargs)

                if response.status_code == 401:
                    raise PowerBIAuthError(
                        "Authentication failed (HTTP 401). "
                        "Run /powerbi_auth to re-authenticate."
                    )

            if response.status_code == 403:
                error_msg, _ = self._parse_error_response(response)
                raise PowerBIAuthError(
                    f"Access denied (HTTP 403). {error_msg}\n"
                    "Check that you have access to this resource."
                )

            if response.status_code == 404:
                raise PowerBINotFoundError(f"Resource not found: {endpoint} (HTTP 404)")

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                retry_seconds = int(retry_after) if retry_after else None
                raise PowerBIThrottledError(
                    f"Rate limited by Power BI. "
                    f"Retry after {retry_seconds or 'unknown'} seconds.",
                    retry_after=retry_seconds,
                )

            if response.status_code >= 400:
                error_msg, error_code = self._parse_error_response(response)
                raise PowerBIAPIError(
                    error_msg,
                    status_code=response.status_code,
                    error_code=error_code,
                )

            self.rate_limiter.record_request()

            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

        except httpx.HTTPError as e:
            raise PowerBIAPIError(f"HTTP request failed: {e}") from e

    # =========================================================================
    # HTTP METHOD HELPERS
    # =========================================================================

    def get(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a GET request to the Power BI API."""
        return self._make_request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a POST request to the Power BI API."""
        return self._make_request("POST", endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a PATCH request to the Power BI API."""
        return self._make_request("PATCH", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make a DELETE request to the Power BI API."""
        return self._make_request("DELETE", endpoint, **kwargs)

    # =========================================================================
    # DAX QUERY EXECUTION
    # =========================================================================

    def execute_dax_query(
        self,
        dataset_id: str,
        dax_query: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Execute a DAX query against a Power BI dataset.

        Args:
            dataset_id: The dataset ID to query.
            dax_query: The DAX query to execute.
            workspace_id: Optional workspace ID (uses My Workspace if not specified).

        Returns:
            Query results with tables and rows.

        Example:
            results = client.execute_dax_query(
                dataset_id="abc123",
                dax_query="EVALUATE TOPN(10, 'Sales')"
            )
        """
        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
        else:
            endpoint = f"/datasets/{dataset_id}/executeQueries"

        payload = {
            "queries": [{"query": dax_query}],
            "serializerSettings": {"includeNulls": True},
        }

        return self.post(endpoint, json=payload)

    def get_table_data(
        self,
        dataset_id: str,
        table_name: str,
        workspace_id: str | None = None,
        top_n: int = 1000,
    ) -> list[dict[str, Any]]:
        """Get all rows from a table using DAX EVALUATE.

        Args:
            dataset_id: The dataset ID.
            table_name: Name of the table to query.
            workspace_id: Optional workspace ID.
            top_n: Maximum number of rows to return.

        Returns:
            List of row dictionaries with cleaned column names.
        """
        dax = f"EVALUATE TOPN({top_n}, '{table_name}')"
        result = self.execute_dax_query(dataset_id, dax, workspace_id)

        rows = []
        if "results" in result:
            raw_rows = result["results"][0]["tables"][0].get("rows", [])
            for row in raw_rows:
                # Clean up column names (remove brackets and table prefixes)
                clean_row = {}
                for key, value in row.items():
                    # Remove [TableName] prefix and brackets
                    clean_key = key.strip("[]").split("[")[-1].strip("]")
                    if "RowNumber" not in key:  # Skip internal row numbers
                        clean_row[clean_key] = value
                rows.append(clean_row)

        return rows

    # =========================================================================
    # EXPORT HELPERS
    # =========================================================================

    def export_to_csv(
        self,
        data: list[dict[str, Any]],
        output_path: str | Path,
    ) -> Path:
        """Export data to a CSV file.

        Args:
            data: List of row dictionaries.
            output_path: Path to save the CSV file.

        Returns:
            Path to the created CSV file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if not data:
            output_path.write_text("")
            return output_path

        fieldnames = list(data[0].keys())

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

        return output_path

    def export_to_json(
        self,
        data: list[dict[str, Any]],
        output_path: str | Path,
    ) -> Path:
        """Export data to a JSON file.

        Args:
            data: List of row dictionaries.
            output_path: Path to save the JSON file.

        Returns:
            Path to the created JSON file.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

        return output_path

    # =========================================================================
    # CONTEXT MANAGER
    # =========================================================================

    def __enter__(self) -> PowerBIClient:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - close the HTTP client."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
