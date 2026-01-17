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

        # Create HTTP client with cookies and Walmart proxy for VPN support
        self.client = httpx.Client(
            cookies=self.cookies,
            timeout=30.0,
            verify=False,  # SSL verification disabled for Walmart network
            headers=headers,
            proxy="http://sysproxy.wal-mart.com:8080",
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

    # =========================================================================
    # INCIDENT MANAGEMENT
    # =========================================================================

    def create_incident(
        self,
        short_description: str,
        description: str = "",
        urgency: int = 3,
        impact: int = 3,
        category: str = "",
        subcategory: str = "",
        assignment_group: str = "",
        assigned_to: str = "",
        caller_id: str = "",
        contact_type: str = "",
        cmdb_ci: str = "",
        additional_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new incident in ServiceNow.

        Args:
            short_description: Brief summary of the incident (required)
            description: Detailed description of the incident
            urgency: Urgency level (1=High, 2=Medium, 3=Low). Default: 3
            impact: Impact level (1=High, 2=Medium, 3=Low). Default: 3
            category: Incident category
            subcategory: Incident subcategory
            assignment_group: Name or sys_id of the assignment group
            assigned_to: Username or sys_id of the user to assign the incident to
            caller_id: User ID or sys_id of the caller (defaults to current user)
            contact_type: Channel/method of contact (e.g., "phone", "email", "self-service", "chat")
            cmdb_ci: Configuration Item - name or sys_id of the affected CI
            additional_fields: Any additional fields to set on the incident

        Returns:
            Dictionary containing the created incident data with 'result' key.

        Example:
            result = client.create_incident(
                short_description="Unable to access email",
                description="Getting 401 error when trying to log in",
                urgency=2,
                impact=2,
                category="Software",
                assigned_to="jsmith",
                contact_type="self-service",
                cmdb_ci="Outlook 365",
            )
            print(f"Created incident: {result['result']['number']}")
        """
        payload: dict[str, Any] = {
            "short_description": short_description,
        }

        if description:
            payload["description"] = description
        if urgency:
            payload["urgency"] = str(urgency)
        if impact:
            payload["impact"] = str(impact)
        if category:
            payload["category"] = category
        if subcategory:
            payload["subcategory"] = subcategory
        if assignment_group:
            payload["assignment_group"] = assignment_group
        if assigned_to:
            payload["assigned_to"] = assigned_to
        if caller_id:
            payload["caller_id"] = caller_id
        if contact_type:
            payload["contact_type"] = contact_type
        if cmdb_ci:
            payload["cmdb_ci"] = cmdb_ci

        # Merge any additional fields
        if additional_fields:
            payload.update(additional_fields)

        return self._make_request(
            "POST",
            "/api/now/table/incident",
            json=payload,
        )

    def get_incident(
        self,
        incident_id: str,
    ) -> dict[str, Any]:
        """Get an incident by sys_id or incident number.

        Args:
            incident_id: The incident sys_id or number (e.g., INC0012345)

        Returns:
            Dictionary containing the incident data.

        Example:
            incident = client.get_incident("INC0012345")
            print(f"Status: {incident['result']['state']}")
        """
        if incident_id.upper().startswith("INC"):
            # It's an incident number - search by number
            params = {
                "sysparm_query": f"number={incident_id}",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            }
            return self._make_request("GET", "/api/now/table/incident", params=params)
        else:
            # It's a sys_id - get directly
            params = {"sysparm_display_value": "true"}
            return self._make_request(
                "GET",
                f"/api/now/table/incident/{incident_id}",
                params=params,
            )

    def update_incident(
        self,
        sys_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Update an existing incident.

        Args:
            sys_id: The incident sys_id
            updates: Dictionary of fields to update

        Returns:
            Dictionary containing the updated incident data.

        Example:
            result = client.update_incident(
                sys_id="abc123...",
                updates={"state": "2", "work_notes": "Working on this"}
            )
        """
        return self._make_request(
            "PATCH",
            f"/api/now/table/incident/{sys_id}",
            json=updates,
        )

    def add_incident_comment(
        self,
        sys_id: str,
        comment: str,
        work_notes: bool = False,
    ) -> dict[str, Any]:
        """Add a comment or work note to an incident.

        Args:
            sys_id: The incident sys_id
            comment: The comment text to add
            work_notes: If True, add as work notes (internal). 
                       If False, add as comments (customer-visible).

        Returns:
            Dictionary containing the updated incident data.
        """
        field = "work_notes" if work_notes else "comments"
        return self.update_incident(sys_id, {field: comment})

    def list_my_incidents(
        self,
        state: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        """List incidents assigned to or opened by the current user.

        Args:
            state: Filter by state (e.g., "1"=New, "2"=In Progress, "6"=Resolved)
            limit: Maximum number of incidents to return

        Returns:
            Dictionary containing the list of incidents.
        """
        # Get current user from the session if available
        sysparm_query = "caller_id=javascript:gs.getUserID()^ORassigned_to=javascript:gs.getUserID()"
        if state:
            sysparm_query += f"^state={state}"
        sysparm_query += "^ORDERBYDESCsys_created_on"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,number,short_description,state,priority,urgency,impact,assigned_to,assignment_group,sys_created_on,sys_updated_on",
            "sysparm_display_value": "true",
        }

        return self._make_request("GET", "/api/now/table/incident", params=params)

    # =========================================================================
    # SERVICE CATALOG
    # =========================================================================

    def list_catalog_items(
        self,
        category: str = "",
        query: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        """List available service catalog items.

        Args:
            category: Filter by category name or sys_id
            query: Search query for catalog items
            limit: Maximum number of items to return

        Returns:
            Dictionary containing catalog items.
        """
        sysparm_query = "active=true"
        if category:
            sysparm_query += f"^categoryLIKE{category}"
        if query:
            sysparm_query += f"^nameLIKE{query}^ORshort_descriptionLIKE{query}"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,name,short_description,category,price,delivery_time",
            "sysparm_display_value": "true",
        }

        return self._make_request("GET", "/api/now/table/sc_cat_item", params=params)

    def get_catalog_item(
        self,
        item_id: str,
    ) -> dict[str, Any]:
        """Get details of a service catalog item including its variables.

        Args:
            item_id: The catalog item sys_id

        Returns:
            Dictionary containing catalog item details and variables.
        """
        # Use the Service Catalog API for richer data
        return self._make_request(
            "GET",
            f"/api/sn_sc/servicecatalog/items/{item_id}",
        )

    def submit_catalog_request(
        self,
        item_id: str,
        variables: dict[str, Any] | None = None,
        quantity: int = 1,
        requested_for: str = "",
        special_instructions: str = "",
    ) -> dict[str, Any]:
        """Submit a service catalog request.

        Args:
            item_id: The catalog item sys_id
            variables: Dictionary of variable values (field name -> value)
            quantity: Quantity to order (default: 1)
            requested_for: User sys_id for whom the request is made
            special_instructions: Additional instructions for the request

        Returns:
            Dictionary containing the created request data.

        Example:
            result = client.submit_catalog_request(
                item_id="abc123...",
                variables={"software_name": "VS Code", "justification": "Development"},
                quantity=1,
            )
            print(f"Request created: {result['result']['number']}")
        """
        payload: dict[str, Any] = {
            "sysparm_quantity": quantity,
        }

        if variables:
            payload["variables"] = variables
        if requested_for:
            payload["sysparm_requested_for"] = requested_for
        if special_instructions:
            # This goes into the request, not the payload for the API
            if "variables" not in payload:
                payload["variables"] = {}
            payload["variables"]["special_instructions"] = special_instructions

        return self._make_request(
            "POST",
            f"/api/sn_sc/servicecatalog/items/{item_id}/order_now",
            json=payload,
        )

    def get_request_status(
        self,
        request_id: str,
    ) -> dict[str, Any]:
        """Get the status of a service request.

        Args:
            request_id: The request sys_id or number (e.g., REQ0012345)

        Returns:
            Dictionary containing the request data and status.
        """
        if request_id.upper().startswith("REQ"):
            # It's a request number
            params = {
                "sysparm_query": f"number={request_id}",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            }
            return self._make_request("GET", "/api/now/table/sc_request", params=params)
        else:
            # It's a sys_id
            params = {"sysparm_display_value": "true"}
            return self._make_request(
                "GET",
                f"/api/now/table/sc_request/{request_id}",
                params=params,
            )

    # =========================================================================
    # ASSIGNMENT GROUPS
    # =========================================================================

    def search_assignment_groups(
        self,
        query: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search for assignment groups.

        Args:
            query: Search query string (searches name and description)
            limit: Maximum number of results to return (default: 25)

        Returns:
            Dictionary containing group list.

        Example:
            groups = client.search_assignment_groups("AI Labs")
            for group in groups['result']:
                print(f"{group['name']} - {group['sys_id']}")
        """
        # Build query - only active groups
        sysparm_query = "active=true"
        if query:
            sysparm_query += f"^nameLIKE{query}^ORdescriptionLIKE{query}"
        sysparm_query += "^ORDERBYname"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,name,description,email,manager,type",
            "sysparm_display_value": "true",
        }

        return self._make_request("GET", "/api/now/table/sys_user_group", params=params)

    def get_assignment_group(
        self,
        group_id: str,
    ) -> dict[str, Any]:
        """Get an assignment group by sys_id or name.

        Args:
            group_id: The group sys_id or name

        Returns:
            Dictionary containing group data.
        """
        # Check if it looks like a sys_id (32 char hex) or a name
        if len(group_id) == 32 and all(c in '0123456789abcdef' for c in group_id.lower()):
            # It's a sys_id
            params = {"sysparm_display_value": "true"}
            return self._make_request(
                "GET",
                f"/api/now/table/sys_user_group/{group_id}",
                params=params,
            )
        else:
            # It's a name - search for it
            params = {
                "sysparm_query": f"name={group_id}",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            }
            return self._make_request("GET", "/api/now/table/sys_user_group", params=params)

    # =========================================================================
    # USER SEARCH
    # =========================================================================

    def search_users(
        self,
        query: str = "",
        limit: int = 25,
    ) -> dict[str, Any]:
        """Search for users in ServiceNow.

        Args:
            query: Search query string (searches name, user_name, email)
            limit: Maximum number of results to return (default: 25)

        Returns:
            Dictionary containing user list.

        Example:
            users = client.search_users("John Smith")
            for user in users['result']:
                print(f"{user['name']} ({user['user_name']})")
        """
        # Build query - only active users
        sysparm_query = "active=true"
        if query:
            sysparm_query += f"^nameLIKE{query}^ORuser_nameLIKE{query}^ORemailLIKE{query}"
        sysparm_query += "^ORDERBYname"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,user_name,name,email,title,department,manager,location",
            "sysparm_display_value": "true",
        }

        return self._make_request("GET", "/api/now/table/sys_user", params=params)

    def get_user(
        self,
        user_id: str,
    ) -> dict[str, Any]:
        """Get a user by sys_id or username.

        Args:
            user_id: The user sys_id or username

        Returns:
            Dictionary containing user data.
        """
        # Check if it looks like a sys_id (32 char hex) or a username
        if len(user_id) == 32 and all(c in '0123456789abcdef' for c in user_id.lower()):
            # It's a sys_id
            params = {"sysparm_display_value": "true"}
            return self._make_request(
                "GET",
                f"/api/now/table/sys_user/{user_id}",
                params=params,
            )
        else:
            # It's a username - search for it
            params = {
                "sysparm_query": f"user_name={user_id}",
                "sysparm_limit": 1,
                "sysparm_display_value": "true",
            }
            return self._make_request("GET", "/api/now/table/sys_user", params=params)

    def get_user_groups(
        self,
        user_id: str,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Get the groups that a user is a member of.

        Args:
            user_id: The user sys_id or username
            limit: Maximum number of groups to return (default: 50)

        Returns:
            Dictionary containing group membership list.

        Example:
            memberships = client.get_user_groups("jsmith")
            for m in memberships['result']:
                print(f"Member of: {m['group']['display_value']}")
        """
        # Build query based on whether it's a sys_id or username
        if len(user_id) == 32 and all(c in '0123456789abcdef' for c in user_id.lower()):
            # It's a sys_id
            sysparm_query = f"user={user_id}"
        else:
            # It's a username - use dot-walk
            sysparm_query = f"user.user_name={user_id}"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,user,group",
            "sysparm_display_value": "all",  # Get both value and display_value
        }

        return self._make_request("GET", "/api/now/table/sys_user_grmember", params=params)

    def get_group_members(
        self,
        group_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Get the members of a specific group.

        Args:
            group_id: The group sys_id or name
            limit: Maximum number of members to return (default: 100)

        Returns:
            Dictionary containing group member list.

        Example:
            members = client.get_group_members("GTL AI Labs")
            for m in members['result']:
                print(f"Member: {m['user']['display_value']}")
        """
        # Build query based on whether it's a sys_id or name
        if len(group_id) == 32 and all(c in '0123456789abcdef' for c in group_id.lower()):
            # It's a sys_id
            sysparm_query = f"group={group_id}"
        else:
            # It's a group name - use dot-walk
            sysparm_query = f"group.name={group_id}"

        params = {
            "sysparm_query": sysparm_query,
            "sysparm_limit": limit,
            "sysparm_fields": "sys_id,user,group",
            "sysparm_display_value": "all",  # Get both value and display_value
        }

        return self._make_request("GET", "/api/now/table/sys_user_grmember", params=params)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close the HTTP client."""
        self.client.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()
