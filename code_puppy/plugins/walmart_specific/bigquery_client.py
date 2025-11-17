"""BigQuery client module for Walmart.

This module provides a client for interacting with Google BigQuery
using Application Default Credentials from gcloud CLI.
"""

import datetime
import decimal
import json
import math
import os
import platform
import subprocess
import warnings
from typing import Any, Dict, List, Optional

from code_puppy.messaging import emit_info, emit_warning

try:
    from google.cloud import bigquery
    from google.auth.exceptions import DefaultCredentialsError
except ImportError:
    bigquery = None
    DefaultCredentialsError = Exception

try:
    import sqlparse
except ImportError:
    sqlparse = None  # type: ignore

# Constants
DEFAULT_QUERY_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_MAX_RESULTS = 100
MAX_RESULTS_LIMIT = 10000  # Hard limit to prevent OOM


def _get_gcloud_command() -> str:
    """Get the gcloud command path.

    On Windows, tries to find gcloud in standard install location.
    Falls back to 'gcloud' for other platforms or if not found.

    Returns:
        Absolute path to gcloud.cmd on Windows, or 'gcloud' as fallback
    """
    system = platform.system()

    if system == "Windows":
        # Standard Windows installation path
        gcloud_bin_dir = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Google",
            "CloudSDK",
            "google-cloud-sdk",
            "bin",
        )
        gcloud_cmd_path = os.path.join(gcloud_bin_dir, "gcloud.cmd")

        # If gcloud.cmd exists, use absolute path
        if os.path.exists(gcloud_cmd_path):
            return gcloud_cmd_path

    # Fallback to 'gcloud' (works on macOS/Linux, or if in PATH on Windows)
    return "gcloud"


class BigQueryError(Exception):
    """Base exception for BigQuery errors."""

    pass


class BigQueryAuthError(BigQueryError):
    """Raised when authentication fails."""

    pass


class BigQueryAPIError(BigQueryError):
    """Raised when BigQuery API call fails."""

    pass


class BigQueryNotFoundError(BigQueryError):
    """Raised when a resource is not found."""

    pass


class BigQueryClient:
    """Client for interacting with Google BigQuery.

    Uses Application Default Credentials from gcloud CLI.
    Credentials are expected to be set via `gcloud auth application-default login`.
    """

    def __init__(self, project_id: Optional[str] = None):
        """Initialize BigQuery client.

        Args:
            project_id: Optional GCP project ID. If None, uses default from credentials.

        Raises:
            BigQueryAuthError: If credentials are not available
        """
        if bigquery is None:
            raise BigQueryAuthError(
                "google-cloud-bigquery is not installed. \n"
                "Please run '/bigquery_auth' to install dependencies and authenticate."
            )

        # Suppress the quota project warning since we handle it gracefully
        warnings.filterwarnings(
            "ignore",
            message=".*quota project.*",
            category=UserWarning,
        )

        try:
            self._client = bigquery.Client(project=project_id)
            self._project_id = self._client.project
        except DefaultCredentialsError as e:
            raise BigQueryAuthError(
                "No valid credentials found. "
                "Please run '/bigquery_auth' to authenticate with gcloud."
            ) from e
        except Exception as e:
            raise BigQueryAuthError(f"Failed to initialize BigQuery client: {e}") from e

    @property
    def project_id(self) -> str:
        """Get the current project ID."""
        return self._project_id

    def list_projects(self) -> List[Dict[str, Any]]:
        """Get the default/current GCP project.

        Note: This method returns the current/default project only.
        Use list_all_projects() to list all accessible projects.

        Returns:
            List with single project dictionary (current project)
        """
        return [
            {
                "project_id": self._project_id,
                "name": self._project_id,
                "state": "ACTIVE",
                "note": "This is your default project. To work with other projects, specify project_id in commands.",
            }
        ]

    def list_all_projects(self) -> List[Dict[str, Any]]:
        """List all accessible GCP projects using gcloud CLI.

        Uses `gcloud projects list` command which is more reliable than the API.
        This requires gcloud CLI to be installed and authenticated.

        Returns:
            List of project dictionaries with id, name, and state

        Raises:
            BigQueryAPIError: If gcloud command fails
        """
        try:
            emit_info("Using gcloud CLI to list all projects...")

            # Run gcloud projects list with JSON output
            result = subprocess.run(
                [_get_gcloud_command(), "projects", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "Unknown error"
                raise BigQueryAPIError(
                    f"Failed to list projects via gcloud: {error_msg}\n"
                    "Make sure you're authenticated with: /bigquery_auth"
                )

            # Parse JSON output
            projects_data = json.loads(result.stdout)
            projects = []

            for project in projects_data:
                projects.append(
                    {
                        "project_id": project.get("projectId"),
                        "name": project.get("name"),
                        "project_number": project.get("projectNumber"),
                        "state": project.get("lifecycleState", "ACTIVE"),
                    }
                )

            if not projects:
                emit_warning(
                    "No projects found. You may not have access to any GCP projects."
                )

            return projects

        except subprocess.TimeoutExpired:
            raise BigQueryAPIError("Timeout while listing projects. Please try again.")
        except json.JSONDecodeError as e:
            raise BigQueryAPIError(
                f"Failed to parse gcloud output: {e}\n"
                "Please make sure gcloud CLI is properly installed and up to date."
            )
        except FileNotFoundError:
            raise BigQueryAPIError(
                "gcloud CLI is not installed or not in PATH.\n"
                "Please run '/bigquery_auth' to install and authenticate."
            )
        except Exception as e:
            raise BigQueryAPIError(
                f"Failed to list projects: {str(e)}\n"
                "Please make sure you're authenticated with: /bigquery_auth"
            )

    def list_datasets(self, project_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all datasets in a project.

        Args:
            project_id: Optional project ID. If None, uses current project.

        Returns:
            List of dataset dictionaries with dataset_id, project, and full_id

        Raises:
            BigQueryAPIError: If the API call fails
        """
        try:
            project = project_id or self._project_id
            datasets = list(self._client.list_datasets(project=project))

            return [
                {
                    "dataset_id": ds.dataset_id,
                    "project": ds.project,
                    "full_id": f"{ds.project}.{ds.dataset_id}",
                    # DatasetListItem doesn't have location, would need get_dataset() for that
                }
                for ds in datasets
            ]
        except Exception as e:
            raise BigQueryAPIError(f"Failed to list datasets: {e}") from e

    def list_tables(
        self, dataset_id: str, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all tables in a dataset.

        Args:
            dataset_id: Dataset ID
            project_id: Optional project ID. If None, uses current project.

        Returns:
            List of table dictionaries with table_id, table_type, and full_id

        Raises:
            BigQueryAPIError: If the API call fails
            BigQueryNotFoundError: If dataset doesn't exist
        """
        try:
            project = project_id or self._project_id
            dataset_ref = f"{project}.{dataset_id}"
            tables = list(self._client.list_tables(dataset_ref))

            return [
                {
                    "table_id": table.table_id,
                    "table_type": table.table_type,
                    "full_id": f"{table.project}.{table.dataset_id}.{table.table_id}",
                    # TableListItem doesn't have created timestamp, would need get_table() for that
                }
                for table in tables
            ]
        except Exception as e:
            if "not found" in str(e).lower():
                raise BigQueryNotFoundError(
                    f"Dataset '{dataset_id}' not found in project '{project}'"
                ) from e
            raise BigQueryAPIError(f"Failed to list tables: {e}") from e

    def _validate_query_safety(self, query: str) -> None:
        """Validate that query is safe (read-only SELECT query).

        Args:
            query: SQL query string to validate

        Raises:
            BigQueryAPIError: If query contains dangerous operations or is invalid
        """
        if not query.strip():
            raise BigQueryAPIError("Query cannot be empty")

        if not self._is_safe_query(query):
            raise BigQueryAPIError(
                "Only read-only SELECT queries are allowed.\n"
                "Dangerous operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, etc.) are blocked."
            )

    def _is_safe_query(self, query: str) -> bool:
        """Check if a SQL query is safe (SELECT only, no destructive operations).

        Args:
            query: SQL query string to check

        Returns:
            True if query is safe, False otherwise
        """
        if sqlparse is None:
            emit_warning(
                "sqlparse not installed. Install with: uv pip install .[bigquery]"
            )
            return False  # Reject if we can't parse

        try:
            parsed = sqlparse.parse(query)
            if not parsed:
                return False

            # Dangerous keywords that modify or destroy data
            dangerous_keywords = {
                "INSERT",
                "UPDATE",
                "DELETE",
                "DROP",
                "CREATE",
                "ALTER",
                "TRUNCATE",
                "REPLACE",
                "MERGE",
            }

            # Check each statement
            for statement in parsed:
                stmt_type = statement.get_type()

                # Only allow SELECT and WITH (CTEs)
                if stmt_type not in ("SELECT", "WITH", "UNKNOWN"):
                    return False

                # Check tokens for dangerous keywords
                tokens_list = list(statement.flatten())
                for token in tokens_list:
                    if (
                        token.ttype
                        in (sqlparse.tokens.Keyword.DDL, sqlparse.tokens.Keyword.DML)
                        and token.value.upper() in dangerous_keywords
                    ):
                        return False

            return True

        except Exception as e:
            emit_warning(f"Error parsing query for read-only check: {e}")
            return False  # Reject on parse errors (safe default)

    def execute_query(
        self, query: str, max_results: int = DEFAULT_MAX_RESULTS
    ) -> Dict[str, Any]:
        """Execute a BigQuery SQL query.

        Only SELECT queries are allowed. Destructive operations (DELETE, DROP, TRUNCATE, etc.)
        are blocked for safety.

        Args:
            query: SQL query string (SELECT only)
            max_results: Maximum number of results to return (default: 100, max: 10000)

        Returns:
            Dictionary containing:
                - rows: List of row dictionaries
                - schema: List of field definitions
                - total_rows: Total number of rows in result
                - job_id: BigQuery job ID
                - bytes_processed: Bytes processed by query
                - bytes_billed: Bytes billed for query

        Raises:
            BigQueryAPIError: If the query fails or contains dangerous operations
        """
        # Validate max_results
        if max_results <= 0:
            raise BigQueryAPIError("max_results must be positive")
        if max_results > MAX_RESULTS_LIMIT:
            raise BigQueryAPIError(
                f"max_results too large: {max_results} (max: {MAX_RESULTS_LIMIT})"
            )

        # Validate query safety
        self._validate_query_safety(query)

        def serialize_value(value):
            """Convert BigQuery values to JSON-serializable types."""
            if value is None:
                return None
            elif isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
                return value.isoformat()
            elif isinstance(value, decimal.Decimal):
                return float(value)
            elif isinstance(value, float):
                if math.isnan(value):
                    return "NaN"
                elif math.isinf(value):
                    return "Infinity" if value > 0 else "-Infinity"
                return value
            elif isinstance(value, bytes):
                return value.decode("utf-8", errors="replace")
            else:
                return value

        try:
            # Execute query with timeout
            query_job = self._client.query(query, timeout=DEFAULT_QUERY_TIMEOUT_SECONDS)
            results = query_job.result(
                max_results=max_results, timeout=DEFAULT_QUERY_TIMEOUT_SECONDS
            )

            # Convert results to list of dictionaries with serialized values
            rows = [
                {key: serialize_value(value) for key, value in dict(row).items()}
                for row in results
            ]

            # Get schema information
            schema = [
                {
                    "name": field.name,
                    "type": field.field_type,
                    "mode": field.mode,
                }
                for field in results.schema
            ]

            return {
                "rows": rows,
                "schema": schema,
                "total_rows": results.total_rows,
                "job_id": query_job.job_id,
                "bytes_processed": query_job.total_bytes_processed,
                "bytes_billed": query_job.total_bytes_billed,
            }
        except Exception as e:
            raise BigQueryAPIError(f"Query execution failed: {e}") from e

    def get_table_schema(
        self, table_id: str, dataset_id: str, project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get schema for a specific table.

        Args:
            table_id: Table ID
            dataset_id: Dataset ID
            project_id: Optional project ID. If None, uses current project.

        Returns:
            List of field dictionaries with name, type, mode, and description

        Raises:
            BigQueryAPIError: If the API call fails
            BigQueryNotFoundError: If table doesn't exist
        """
        try:
            project = project_id or self._project_id
            table_ref = f"{project}.{dataset_id}.{table_id}"
            table = self._client.get_table(table_ref)

            return [
                {
                    "name": field.name,
                    "type": field.field_type,
                    "mode": field.mode,
                    "description": field.description or "",
                }
                for field in table.schema
            ]
        except Exception as e:
            if "not found" in str(e).lower():
                raise BigQueryNotFoundError(
                    f"Table '{table_id}' not found in '{project}.{dataset_id}'"
                ) from e
            raise BigQueryAPIError(f"Failed to get table schema: {e}") from e
