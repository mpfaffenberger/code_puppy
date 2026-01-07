"""Session-based Jira client for Walmart's internal Jira instance.

Provides a robust client for interacting with Jira using session-based
authentication (cookies loaded from ~/.code_puppy/jira.json).

Example:
    with JiraClient() as client:
        issue = client.get_issue("PROJ-123")
        results = client.search_issues("project = PROJ AND status = Open")

See Also:
    jira_auth.py - Browser-based authentication to obtain session cookies.
    confluence_client.py - Similar client pattern for Confluence.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from code_puppy import __version__
from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_warning
from code_puppy.plugins.walmart_specific.auth import (
    decode_jwt_without_validation,
    get_puppy_token,
)
from code_puppy.plugins.walmart_specific.rate_limiter import SharedRateLimiter


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class JiraError(Exception):
    """Base exception for all Jira-related errors."""


class JiraAuthError(JiraError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class JiraNotFoundError(JiraError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class JiraAPIError(JiraError):
    """Raised for other API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


# =============================================================================
# JIRA CLIENT
# =============================================================================


class JiraClient:
    """Session-based Jira client.

    Uses cookies loaded from a JSON file to authenticate with Jira.
    Supports issue retrieval, JQL search, issue creation/update, and transitions.

    Example:
        client = JiraClient()
        issue = client.get_issue("PROJ-123")
        results = client.search_issues("project = PROJ")
    """

    DEFAULT_BASE_URL: str = "https://jira.walmart.com"
    DEFAULT_SESSION_FILE: Path = Path(CONFIG_DIR) / "jira.json"
    STALENESS_THRESHOLD: timedelta = timedelta(hours=12)

    def __init__(self, session_file_path: str | None = None):
        """Initialize the Jira client.

        Args:
            session_file_path: Path to the session JSON file. If None, uses
                ~/.code_puppy/jira.json by default.

        Raises:
            JiraError: If session file is missing or invalid.
        """
        self.session_file_path = (
            Path(session_file_path) if session_file_path else self.DEFAULT_SESSION_FILE
        )
        self.session_data = self._load_session()
        self.base_url = self.session_data.get("base_url", self.DEFAULT_BASE_URL)
        self.cookies = self.session_data.get(
            "all_cookies", self.session_data.get("cookies", {})
        )

        self._check_staleness()

        user_agent = self._build_user_agent()

        self.client = httpx.Client(
            cookies=self.cookies,
            timeout=30.0,
            verify=False,  # Walmart internal certs
            headers={
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        self.rate_limiter = SharedRateLimiter(
            name="jira_api",
            max_requests=20,
            time_window=60,
        )

    def _load_session(self) -> dict[str, Any]:
        """Load and validate the session file.

        Returns:
            Dictionary containing session data.

        Raises:
            JiraError: If session file is missing or invalid.
        """
        if not self.session_file_path.exists():
            raise JiraError(
                f"Session file not found: {self.session_file_path}\n"
                "Jira authentication required."
            )

        try:
            with open(self.session_file_path) as f:
                session_data = json.load(f)
        except json.JSONDecodeError as e:
            raise JiraError(
                f"Invalid JSON in session file: {self.session_file_path}\n{e}"
            ) from e
        except OSError as e:
            raise JiraError(
                f"Failed to load session file: {self.session_file_path}\n{e}"
            ) from e

        cookies = session_data.get("all_cookies", session_data.get("cookies"))
        if not cookies:
            raise JiraError(
                f"Session file missing 'cookies' field: {self.session_file_path}"
            )

        if not isinstance(cookies, dict):
            raise JiraError(
                f"Invalid 'cookies' field in session file: {self.session_file_path}"
            )

        return session_data

    def _check_staleness(self) -> None:
        """Emit a warning if the session is older than STALENESS_THRESHOLD."""
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
                    f"Jira session is {hours_old:.1f} hours old. "
                    "Session may be stale, consider re-authenticating."
                )
        except ValueError:
            emit_warning(f"Invalid timestamp format in session file: {timestamp_str}")

    def _build_user_agent(self) -> str:
        """Build User-Agent header with version and user_id."""
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
        except Exception:  # noqa: BLE001
            pass  # Silently fall back to version-only

        return user_agent

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the Jira API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE).
            endpoint: API endpoint (e.g., "/rest/api/2/issue/PROJ-123").
            **kwargs: Additional arguments to pass to httpx.request.

        Returns:
            JSON response as a dictionary.

        Raises:
            JiraAuthError: If authentication fails (401/403).
            JiraNotFoundError: If resource is not found (404).
            JiraAPIError: For other API errors.
        """
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}{endpoint}"

        try:
            response = self.client.request(method, url, **kwargs)

            if response.status_code in (401, 403):
                raise JiraAuthError(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Jira re-authentication required."
                )

            if response.status_code == 404:
                raise JiraNotFoundError(f"Resource not found: {endpoint} (HTTP 404)")

            if response.status_code >= 400:
                error_msg = f"Jira API error (HTTP {response.status_code})"
                try:
                    error_data = response.json()
                    if "errorMessages" in error_data:
                        error_msg += f": {'; '.join(error_data['errorMessages'])}"
                    elif "message" in error_data:
                        error_msg += f": {error_data['message']}"
                except Exception:  # noqa: BLE001
                    error_msg += f": {response.text[:200]}"

                raise JiraAPIError(error_msg, status_code=response.status_code)

            self.rate_limiter.record_request()

            # Handle empty responses (204 No Content)
            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

        except httpx.HTTPError as e:
            raise JiraAPIError(f"HTTP request failed: {e}") from e

    # =========================================================================
    # PROJECT DISCOVERY
    # =========================================================================

    def list_projects(
        self,
        max_results: int = 50,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """List available Jira projects.

        Use this to discover project keys before constructing JQL queries.
        Project keys are short uppercase identifiers (e.g., 'PROJ', 'MYPROJ')
        that should be used in JQL instead of long project names.

        Args:
            max_results: Maximum number of projects to return. Defaults to 50.
            start_at: Index of the first project to return. Defaults to 0.

        Returns:
            Dictionary containing:
                - projects: List of project objects with key, name, id
                - total: Total number of projects available
                - maxResults: Number of results returned

        Example:
            projects = client.list_projects()
            for p in projects['projects']:
                print(f"{p['key']}: {p['name']}")
        """
        params = {
            "maxResults": min(max_results, 50),
            "startAt": start_at,
        }

        # Use the project search endpoint for better results
        response = self._make_request(
            "GET",
            "/rest/api/2/project",
            params=params,
        )

        # The /rest/api/2/project endpoint returns a list directly
        if isinstance(response, list):
            projects = response
            return {
                "projects": [
                    {
                        "key": p.get("key"),
                        "name": p.get("name"),
                        "id": p.get("id"),
                        "projectTypeKey": p.get("projectTypeKey"),
                    }
                    for p in projects[:max_results]
                ],
                "total": len(projects),
                "maxResults": min(len(projects), max_results),
            }

        return response

    def search_projects(
        self,
        query: str,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search for Jira projects by name or key.

        Args:
            query: Search string to match against project names or keys.
            max_results: Maximum number of projects to return. Defaults to 20.

        Returns:
            Dictionary containing matching projects.

        Example:
            results = client.search_projects("financial")
            for p in results['projects']:
                print(f"{p['key']}: {p['name']}")
        """
        params = {
            "query": query,
            "maxResults": min(max_results, 50),
        }

        response = self._make_request(
            "GET",
            "/rest/api/2/project/search",
            params=params,
        )

        # Handle both list and paginated responses
        if isinstance(response, list):
            return {
                "projects": [
                    {
                        "key": p.get("key"),
                        "name": p.get("name"),
                        "id": p.get("id"),
                    }
                    for p in response[:max_results]
                ],
                "total": len(response),
            }

        # Paginated response format
        values = response.get("values", [])
        return {
            "projects": [
                {
                    "key": p.get("key"),
                    "name": p.get("name"),
                    "id": p.get("id"),
                }
                for p in values
            ],
            "total": response.get("total", len(values)),
        }

    # =========================================================================
    # ISSUE RETRIEVAL
    # =========================================================================

    def get_issue(
        self,
        issue_key: str,
        fields: list[str] | None = None,
        expand: str | None = None,
    ) -> dict[str, Any]:
        """Get a Jira issue by key.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").
            fields: List of fields to return. If None, returns all fields.
            expand: Comma-separated list of entities to expand.

        Returns:
            Dictionary containing issue data.

        Example:
            issue = client.get_issue("PROJ-123")
            print(f"Summary: {issue['fields']['summary']}")
            print(f"Status: {issue['fields']['status']['name']}")
        """
        params: dict[str, Any] = {}
        if fields:
            params["fields"] = ",".join(fields)
        if expand:
            params["expand"] = expand

        return self._make_request(
            "GET",
            f"/rest/api/2/issue/{issue_key}",
            params=params if params else None,
        )

    def search_issues(
        self,
        jql: str,
        max_results: int = 50,
        start_at: int = 0,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search for issues using JQL (Jira Query Language).

        Args:
            jql: JQL query string (e.g., "project = PROJ AND status = Open").
            max_results: Maximum number of results to return (default: 50).
            start_at: Index of first result for pagination (default: 0).
            fields: List of fields to return. If None, returns navigable fields.

        Returns:
            Dictionary containing search results with 'issues', 'total', etc.

        Example:
            results = client.search_issues(
                "project = PROJ AND status = Open",
                max_results=10
            )
            for issue in results['issues']:
                print(f"{issue['key']}: {issue['fields']['summary']}")
        """
        payload: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
        }
        if fields:
            payload["fields"] = fields

        return self._make_request("POST", "/rest/api/2/search", json=payload)

    # =========================================================================
    # ISSUE CREATION AND UPDATES
    # =========================================================================

    def create_issue(
        self,
        project_key: str,
        issue_type: str,
        summary: str,
        description: str | None = None,
        **extra_fields: Any,
    ) -> dict[str, Any]:
        """Create a new Jira issue.

        Args:
            project_key: Project key (e.g., "PROJ").
            issue_type: Issue type name (e.g., "Story", "Bug", "Task").
            summary: Issue summary/title.
            description: Issue description (optional).
            **extra_fields: Additional fields as keyword arguments.

        Returns:
            Dictionary containing created issue data (id, key, self).

        Example:
            issue = client.create_issue(
                project_key="PROJ",
                issue_type="Story",
                summary="Implement user login",
                description="As a user, I want to log in...",
                labels=["backend", "auth"],
            )
            print(f"Created: {issue['key']}")
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "issuetype": {"name": issue_type},
            "summary": summary,
        }

        if description:
            fields["description"] = description

        fields.update(extra_fields)

        return self._make_request("POST", "/rest/api/2/issue", json={"fields": fields})

    def update_issue(
        self,
        issue_key: str,
        fields: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing Jira issue.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").
            fields: Dictionary of fields to set directly.
            update: Dictionary of field operations (add, set, remove).

        Returns:
            Empty dictionary on success (Jira returns 204 No Content).

        Example:
            # Simple field update
            client.update_issue("PROJ-123", fields={"summary": "New title"})

            # Add a label
            client.update_issue(
                "PROJ-123",
                update={"labels": [{"add": "urgent"}]}
            )
        """
        payload: dict[str, Any] = {}
        if fields:
            payload["fields"] = fields
        if update:
            payload["update"] = update

        return self._make_request("PUT", f"/rest/api/2/issue/{issue_key}", json=payload)

    # =========================================================================
    # COMMENTS
    # =========================================================================

    def add_comment(
        self,
        issue_key: str,
        body: str,
    ) -> dict[str, Any]:
        """Add a comment to an issue.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").
            body: Comment text.

        Returns:
            Dictionary containing created comment data.

        Example:
            comment = client.add_comment("PROJ-123", "This is ready for review.")
            print(f"Comment added: {comment['id']}")
        """
        return self._make_request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/comment",
            json={"body": body},
        )

    def get_comments(
        self,
        issue_key: str,
        max_results: int = 50,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """Get comments for an issue.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").
            max_results: Maximum number of comments to return.
            start_at: Index of first comment for pagination.

        Returns:
            Dictionary containing comments with 'comments', 'total', etc.
        """
        params = {
            "maxResults": max_results,
            "startAt": start_at,
        }
        return self._make_request(
            "GET",
            f"/rest/api/2/issue/{issue_key}/comment",
            params=params,
        )

    # =========================================================================
    # TRANSITIONS
    # =========================================================================

    def get_transitions(self, issue_key: str) -> dict[str, Any]:
        """Get available transitions for an issue.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").

        Returns:
            Dictionary containing available transitions.

        Example:
            transitions = client.get_transitions("PROJ-123")
            for t in transitions['transitions']:
                print(f"{t['id']}: {t['name']}")
        """
        return self._make_request("GET", f"/rest/api/2/issue/{issue_key}/transitions")

    def transition_issue(
        self,
        issue_key: str,
        transition_id: str,
        comment: str | None = None,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Transition an issue to a new status.

        Args:
            issue_key: The issue key (e.g., "PROJ-123").
            transition_id: ID of the transition to execute.
            comment: Optional comment to add with the transition.
            fields: Optional fields to set during transition.

        Returns:
            Empty dictionary on success.

        Example:
            # Get transitions first
            transitions = client.get_transitions("PROJ-123")
            done_transition = next(
                t for t in transitions['transitions'] if t['name'] == 'Done'
            )

            # Execute transition
            client.transition_issue(
                "PROJ-123",
                done_transition['id'],
                comment="Completed implementation."
            )
        """
        payload: dict[str, Any] = {"transition": {"id": transition_id}}

        if comment:
            payload["update"] = {"comment": [{"add": {"body": comment}}]}

        if fields:
            payload["fields"] = fields

        return self._make_request(
            "POST",
            f"/rest/api/2/issue/{issue_key}/transitions",
            json=payload,
        )

    # =========================================================================
    # CONTEXT MANAGER AND CLEANUP
    # =========================================================================

    def __enter__(self) -> JiraClient:
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - close the HTTP client."""
        self.client.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
