"""Pete CMS HTTP client for Code Puppy.

Provides a robust client for interacting with Walmart's Pete enterprise
database web service. Pete enables instant REST API creation against
multiple database engines (BigQuery, DB2, Oracle, PostgreSQL, etc.)
using dynamic SQL or pre-configured Instant API services.

Auth modes:
    - Basic Auth: ``Authorization: Basic <base64(user:pass)>``
    - CID Auth: ``Authorization: CID <credential_id>``
    - Marketplace token (PingFed SSO) for Pete Console operations

See Also:
    https://gecgithub01.walmart.com/pages/zAppDev/Pete/docs/overview/index
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import httpx

from code_puppy.http_utils import get_cert_bundle_path

from code_puppy import __version__
from code_puppy.config import CONFIG_DIR
from code_puppy.plugins.walmart_specific.auth import (
    decode_jwt_without_validation,
    get_puppy_token,
)
from code_puppy.plugins.walmart_specific.rate_limiter import SharedRateLimiter


# =============================================================================
# CONSTANTS
# =============================================================================

# Default Pete cluster (GCP global US production)
DEFAULT_PETE_CLUSTER = "prod.wcnp.gbl.gcp.pete.glb.us.walmart.net"

# Stage cluster for testing
STAGE_PETE_CLUSTER = "stage.wcnp.gbl.gcp.pete.glb.us.walmart.net"

# Pete Console URL
PETE_CONSOLE_URL = "https://pete.walmart.com"

# Pete config file
PETE_CONFIG_FILE = Path(CONFIG_DIR) / "pete.json"

# Known BigQuery predefined database connection names in Pete
# Users can also define their own via the Pete Console
BQ_CONNECTION_PREFIX = "bigquery"


# =============================================================================
# EXCEPTION CLASSES
# =============================================================================


class PeteError(Exception):
    """Base exception for all Pete-related errors."""


class PeteAuthError(PeteError):
    """Raised when authentication fails (401/403)."""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message)


class PeteNotFoundError(PeteError):
    """Raised when a resource is not found (404)."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(message)


class PeteAPIError(PeteError):
    """Raised for other API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PeteSQLError(PeteError):
    """Raised when a SQL execution error occurs within a Pete response."""

    def __init__(
        self,
        message: str,
        sql_code: int | None = None,
        sql_state: str | None = None,
    ):
        super().__init__(message)
        self.sql_code = sql_code
        self.sql_state = sql_state


# =============================================================================
# CONFIGURATION HELPERS
# =============================================================================


def _load_pete_config() -> dict[str, Any]:
    """Load Pete config from disk.

    Returns:
        Configuration dict with cluster, cid, and database preferences.
    """
    if not PETE_CONFIG_FILE.exists():
        return {}
    try:
        with open(PETE_CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_pete_config(config: dict[str, Any]) -> None:
    """Save Pete config to disk.

    Args:
        config: Configuration dict to persist.
    """
    PETE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PETE_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_configured_cluster() -> str:
    """Get the configured Pete cluster hostname.

    Returns:
        Cluster hostname, defaulting to GCP global US production.
    """
    config = _load_pete_config()
    return config.get("cluster", DEFAULT_PETE_CLUSTER)


def get_configured_cid() -> str | None:
    """Get the configured default CID from Pete config.

    Returns:
        CID string or None if not configured.
    """
    config = _load_pete_config()
    return config.get("default_cid")


def get_configured_database() -> str | None:
    """Get the configured default database connection name.

    Returns:
        Database connection name or None if not configured.
    """
    config = _load_pete_config()
    return config.get("default_database")


# =============================================================================
# AUTH HELPERS
# =============================================================================


def _build_basic_auth_header(user: str, password: str) -> str:
    """Build a Basic Auth header value.

    Args:
        user: Username.
        password: Password.

    Returns:
        Header value like ``Basic <base64>``.
    """
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {encoded}"


def _build_cid_auth_header(cid: str) -> str:
    """Build a CID Auth header value.

    Args:
        cid: Pete Credential ID (GUID).

    Returns:
        Header value like ``CID <guid>``.
    """
    return f"CID {cid}"


def _get_marketplace_token() -> str | None:
    """Get the marketplace (PingFed) token for Pete Console operations.

    Returns:
        Token string or None if not available.
    """
    try:
        from code_puppy.config import get_value

        return get_value("marketplace_token")
    except ImportError:
        return None


# =============================================================================
# PETE CLIENT
# =============================================================================


class PeteClient:
    """HTTP client for Pete enterprise database web service.

    Supports dynamic SQL queries (GET/POST), Instant API service
    invocation, and Pete Console operations.

    Example:
        with PeteClient(cid="abc-123-def") as client:
            result = client.dynamic_query(
                database="my_bq_connection",
                sql="SELECT * FROM my_dataset.my_table LIMIT 10",
            )
            print(result)
    """

    def __init__(
        self,
        cluster: str | None = None,
        cid: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        """Initialize Pete client.

        Args:
            cluster: Pete cluster hostname. Defaults to configured or production.
            cid: Pete Credential ID for database auth.
            user: Username for Basic Auth (mutually exclusive with cid).
            password: Password for Basic Auth.
        """
        self.cluster = cluster or get_configured_cluster()
        self.cid = cid or get_configured_cid()
        self.user = user
        self.password = password
        self.base_url = f"https://{self.cluster}"

        user_agent = self._build_user_agent()

        self.client = httpx.Client(
            timeout=60.0,
            verify=get_cert_bundle_path(),  # Walmart CA bundle
            headers={
                "User-Agent": user_agent,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )

        self.rate_limiter = SharedRateLimiter(
            name="pete_api",
            max_requests=30,
            time_window=60,
        )

    def _build_user_agent(self) -> str:
        """Build a custom User-Agent header."""
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
                    )
                    if user_id:
                        user_agent += f" ({user_id})"
        except Exception:
            pass
        return user_agent

    def _get_auth_header(self) -> dict[str, str]:
        """Build auth header based on configured credentials.

        Returns:
            Dict with Authorization header, or empty dict if no creds.
        """
        if self.cid:
            return {"Authorization": _build_cid_auth_header(self.cid)}
        if self.user and self.password:
            return {"Authorization": _build_basic_auth_header(self.user, self.password)}
        return {}

    def _make_request(
        self,
        method: str,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any] | str:
        """Make an HTTP request to Pete.

        Args:
            method: HTTP method.
            endpoint: API endpoint path.
            **kwargs: Additional httpx.request kwargs.

        Returns:
            Parsed JSON response or raw text.

        Raises:
            PeteAuthError: On 401/403.
            PeteNotFoundError: On 404.
            PeteAPIError: On other HTTP errors.
        """
        self.rate_limiter.wait_if_needed()

        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_header())

        try:
            response = self.client.request(method, url, headers=headers, **kwargs)

            if response.status_code in (401, 403):
                raise PeteAuthError(
                    f"Authentication failed (HTTP {response.status_code}). "
                    "Check your CID or credentials."
                )

            if response.status_code == 404:
                raise PeteNotFoundError(f"Resource not found: {endpoint} (HTTP 404)")

            if response.status_code >= 400:
                error_msg = f"Pete API error (HTTP {response.status_code})"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg += f": {error_data['message']}"
                except Exception:
                    error_msg += f": {response.text[:300]}"
                raise PeteAPIError(error_msg, status_code=response.status_code)

            self.rate_limiter.record_request()

            try:
                return response.json()
            except Exception:
                return response.text

        except httpx.HTTPError as e:
            raise PeteAPIError(f"HTTP request failed: {e}")

    # =========================================================================
    # HEALTH & INFO
    # =========================================================================

    def health_check(self) -> dict[str, Any] | str:
        """Check Pete cluster health.

        Returns:
            Health status response.
        """
        return self._make_request("GET", "/pete_health")

    # =========================================================================
    # DYNAMIC SQL - GET (simple single queries)
    # =========================================================================

    def dynamic_query_get(
        self,
        database: str,
        sql: str,
        host_vars: dict[str, Any] | None = None,
        stats: bool = False,
        nulls: bool = False,
        metadata: bool = False,
        rows: int | None = None,
        cid_override: str | None = None,
    ) -> dict[str, Any] | str:
        """Execute a dynamic SQL query via HTTP GET.

        Best for simple, single SELECT statements. SQL injection
        protection means string values must be passed as host variables.

        Args:
            database: Predefined database connection name (e.g. 'my_bq_conn').
            sql: SQL command to execute.
            host_vars: Dict of host variable name -> value for ``:var`` params.
            stats: Return execution statistics.
            nulls: Include NULL values in response.
            metadata: Return column metadata.
            rows: Limit number of rows returned.
            cid_override: Override default CID for this request.

        Returns:
            Pete response dict.
        """
        params: dict[str, Any] = {"q": sql}

        if cid_override:
            params["cid"] = cid_override
        if stats:
            params["_stats"] = "true"
        if nulls:
            params["_nulls"] = "true"
        if metadata:
            params["_metadata"] = "true"
        if rows is not None:
            params["rows"] = rows

        # Host variables go directly as query string params
        if host_vars:
            params.update(host_vars)

        return self._make_request("GET", f"/{database}", params=params)

    # =========================================================================
    # DYNAMIC SQL - POST (complex multi-step queries)
    # =========================================================================

    def dynamic_query_post(
        self,
        database: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        connections: list[dict[str, Any]] | None = None,
        results: dict[str, Any] | None = None,
        header: dict[str, Any] | None = None,
        cid_override: str | None = None,
    ) -> dict[str, Any] | str:
        """Execute dynamic SQL via HTTP POST.

        Supports multiple SQL statements, local connections, host
        variables, and custom result mappings.

        Args:
            database: Optional predefined database name in URL.
            steps: Array of step definitions (sql/uow/threads).
            connections: Optional local connection definitions.
            results: Result mapping (step name -> output tag).
            header: Optional header config (stats, nulls, etc.).
            cid_override: Override default CID.

        Returns:
            Pete response dict.
        """
        endpoint = "/steps"
        if database:
            endpoint = f"/steps/{database}"

        payload: dict[str, Any] = {}
        if header:
            payload["header"] = header
        if connections:
            payload["connections"] = connections
        if steps:
            payload["steps"] = steps
        if results:
            payload["results"] = results

        extra_headers = {}
        if cid_override:
            extra_headers["Authorization"] = _build_cid_auth_header(cid_override)

        return self._make_request("POST", endpoint, json=payload, headers=extra_headers)

    # =========================================================================
    # CONVENIENCE: BigQuery helpers
    # =========================================================================

    def query_bigquery(
        self,
        sql: str,
        database: str | None = None,
        host_vars: dict[str, Any] | None = None,
        rows: int | None = 100,
    ) -> dict[str, Any] | str:
        """Execute a SQL query against BigQuery through Pete.

        Convenience wrapper around dynamic_query_post for BQ.

        Args:
            sql: SQL query to execute.
            database: BQ connection name. Falls back to configured default.
            host_vars: Optional host variables.
            rows: Max rows to return (default 100).

        Returns:
            Pete response dict.
        """
        db = database or get_configured_database()
        if not db:
            raise PeteError(
                "No BigQuery database connection configured. "
                "Set one with pete_configure or pass database= explicitly."
            )

        step: dict[str, Any] = {
            "sql": {
                "name": "bq_query",
                "command": sql,
            }
        }
        if host_vars:
            step["sql"]["host_vars"] = host_vars

        result_map: dict[str, str] = {"data": "bq_query"}

        header_cfg: dict[str, Any] = {"stats": True}
        if rows is not None:
            step["sql"]["rows"] = rows

        return self.dynamic_query_post(
            database=db,
            steps=[step],
            results=result_map,
            header=header_cfg,
        )

    # =========================================================================
    # INSTANT API SERVICES
    # =========================================================================

    def call_service(
        self,
        domain: str,
        service: str,
        path: str,
        version: str = "default",
        method: str = "GET",
        body: dict[str, Any] | None = None,
        path_params: dict[str, str] | None = None,
    ) -> dict[str, Any] | str:
        """Call a Pete Instant API service.

        Args:
            domain: Service domain name.
            service: Service name.
            path: Path defined in the service.
            version: API version (default uses the service's default).
            method: HTTP method.
            body: Request body for POST/PUT.
            path_params: Key-value pairs appended to the path.

        Returns:
            Pete response dict.
        """
        endpoint = f"/service/{domain}/{version}/{service}/{path}"

        if path_params:
            for key, val in path_params.items():
                endpoint += f"/{key}/{val}"

        kwargs: dict[str, Any] = {}
        if body and method in ("POST", "PUT", "PATCH"):
            kwargs["json"] = body

        return self._make_request(method, endpoint, **kwargs)

    # =========================================================================
    # CONTEXT MANAGER
    # =========================================================================

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def close(self):
        """Close the HTTP client."""
        self.client.close()
