"""Databricks client module.

This module provides a client for interacting with Databricks SQL warehouses
using OAuth authentication with user credentials (U2M - User to Machine).
"""

import json
import os
from pathlib import Path
from typing import Any, Optional

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info, emit_warning

# Databricks SDK imports
try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementState
except ImportError:
    WorkspaceClient = None  # type: ignore
    StatementState = None  # type: ignore

try:
    import sqlparse
except ImportError:
    sqlparse = None  # type: ignore

# Constants
DEFAULT_QUERY_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_MAX_RESULTS = 100
MAX_RESULTS_LIMIT = 10000  # Hard limit to prevent OOM
DATABRICKS_CONFIG_FILE = "databricks.json"


class DatabricksError(Exception):
    """Base exception for Databricks errors."""

    pass


class DatabricksAuthError(DatabricksError):
    """Raised when authentication fails."""

    pass


class DatabricksAPIError(DatabricksError):
    """Raised when Databricks API call fails."""

    pass


class DatabricksNotFoundError(DatabricksError):
    """Raised when a resource is not found."""

    pass


def get_databricks_config_path() -> Path:
    """Get the path to the Databricks config file.

    Returns:
        Path to ~/.code_puppy/databricks.json
    """
    return Path(CONFIG_DIR) / DATABRICKS_CONFIG_FILE


def load_databricks_config() -> Optional[dict[str, Any]]:
    """Load Databricks configuration from file.

    Returns:
        Configuration dictionary or None if not found
    """
    config_path = get_databricks_config_path()
    if not config_path.exists():
        return None

    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        emit_warning(f"Failed to load Databricks config: {e}")
        return None


def save_databricks_config(config: dict[str, Any]) -> bool:
    """Save Databricks configuration to file.

    Args:
        config: Configuration dictionary to save

    Returns:
        True if saved successfully, False otherwise
    """
    config_path = get_databricks_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        emit_warning(f"Failed to save Databricks config: {e}")
        return False


class DatabricksClient:
    """Client for interacting with Databricks SQL warehouses.

    Uses OAuth U2M (User to Machine) authentication with user credentials.
    Credentials are expected to be configured via `/databricks_auth` command.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        warehouse_id: Optional[str] = None,
        catalog: Optional[str] = None,
        schema: Optional[str] = None,
    ):
        """Initialize Databricks client.

        Args:
            host: Databricks workspace URL (e.g., https://xxx.cloud.databricks.com)
            warehouse_id: SQL warehouse ID to use for queries
            catalog: Default catalog name
            schema: Default schema name

        Raises:
            DatabricksAuthError: If authentication fails or SDK not available
        """
        if WorkspaceClient is None:
            raise DatabricksAuthError(
                "databricks-sdk is not installed.\n"
                "Please run '/databricks_auth' to install dependencies and authenticate."
            )

        # Load config from file if not provided
        config = load_databricks_config() or {}

        self._host = host or config.get("host") or os.environ.get("DATABRICKS_HOST")
        self._auth_type = (
            config.get("auth_type")
            or os.environ.get("DATABRICKS_AUTH_TYPE")
            or "external-browser"  # Default to browser-based OAuth
        )
        self._warehouse_id = (
            warehouse_id
            or config.get("warehouse_id")
            or os.environ.get("DATABRICKS_WAREHOUSE_ID")
        )
        self._catalog = (
            catalog or config.get("catalog") or os.environ.get("DATABRICKS_CATALOG")
        )
        self._schema = (
            schema or config.get("schema") or os.environ.get("DATABRICKS_SCHEMA")
        )

        if not self._host:
            raise DatabricksAuthError(
                "Databricks host not configured.\n"
                "Please run '/databricks_auth' to configure your Databricks workspace."
            )

        try:
            # Initialize workspace client with OAuth U2M (external-browser) authentication
            # This uses the browser-based OAuth flow which:
            # 1. Opens a browser window for user to authenticate
            # 2. Caches tokens locally at ~/.databricks/token-cache.json
            # 3. Automatically refreshes tokens when they expire
            self._client = WorkspaceClient(host=self._host, auth_type=self._auth_type)

            # Test authentication by getting current user
            current_user = self._client.current_user.me()
            emit_info(f"Authenticated as: {current_user.user_name}")

        except Exception as e:
            raise DatabricksAuthError(
                f"Failed to initialize Databricks client: {e}\n"
                "Please run '/databricks_auth' to authenticate."
            ) from e

    @property
    def host(self) -> str:
        """Get the Databricks workspace URL."""
        return self._host

    @property
    def warehouse_id(self) -> Optional[str]:
        """Get the configured SQL warehouse ID."""
        return self._warehouse_id

    @property
    def catalog(self) -> Optional[str]:
        """Get the default catalog."""
        return self._catalog

    @property
    def schema(self) -> Optional[str]:
        """Get the default schema."""
        return self._schema

    def list_catalogs(self) -> list[dict[str, Any]]:
        """List all accessible catalogs.

        Returns:
            List of catalog dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            catalogs = self._client.catalogs.list()
            return [
                {
                    "name": cat.name,
                    "comment": cat.comment or "",
                    "owner": cat.owner or "",
                }
                for cat in catalogs
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list catalogs: {e}") from e

    def list_schemas(self, catalog_name: Optional[str] = None) -> list[dict[str, Any]]:
        """List all schemas in a catalog.

        Args:
            catalog_name: Catalog name. If None, uses default catalog.

        Returns:
            List of schema dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            catalog = catalog_name or self._catalog
            if not catalog:
                raise DatabricksAPIError(
                    "No catalog specified. Please provide catalog_name or set default catalog."
                )

            schemas = self._client.schemas.list(catalog_name=catalog)
            return [
                {
                    "name": schema.name,
                    "catalog_name": schema.catalog_name,
                    "full_name": f"{schema.catalog_name}.{schema.name}",
                    "comment": schema.comment or "",
                    "owner": schema.owner or "",
                }
                for schema in schemas
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list schemas: {e}") from e

    def list_tables(
        self, catalog_name: Optional[str] = None, schema_name: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """List all tables in a schema.

        Args:
            catalog_name: Catalog name. If None, uses default catalog.
            schema_name: Schema name. If None, uses default schema.

        Returns:
            List of table dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            catalog = catalog_name or self._catalog
            schema = schema_name or self._schema

            if not catalog:
                raise DatabricksAPIError(
                    "No catalog specified. Please provide catalog_name or set default catalog."
                )
            if not schema:
                raise DatabricksAPIError(
                    "No schema specified. Please provide schema_name or set default schema."
                )

            tables = self._client.tables.list(catalog_name=catalog, schema_name=schema)
            return [
                {
                    "name": table.name,
                    "catalog_name": table.catalog_name,
                    "schema_name": table.schema_name,
                    "full_name": f"{table.catalog_name}.{table.schema_name}.{table.name}",
                    "table_type": str(table.table_type) if table.table_type else "",
                    "comment": table.comment or "",
                }
                for table in tables
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list tables: {e}") from e

    def get_table_schema(
        self,
        table_name: str,
        catalog_name: Optional[str] = None,
        schema_name: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get schema for a specific table.

        Args:
            table_name: Table name
            catalog_name: Catalog name. If None, uses default catalog.
            schema_name: Schema name. If None, uses default schema.

        Returns:
            List of column dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
            DatabricksNotFoundError: If table doesn't exist
        """
        try:
            catalog = catalog_name or self._catalog
            schema = schema_name or self._schema

            if not catalog:
                raise DatabricksAPIError(
                    "No catalog specified. Please provide catalog_name or set default catalog."
                )
            if not schema:
                raise DatabricksAPIError(
                    "No schema specified. Please provide schema_name or set default schema."
                )

            full_name = f"{catalog}.{schema}.{table_name}"
            table = self._client.tables.get(full_name=full_name)

            if not table.columns:
                return []

            return [
                {
                    "name": col.name,
                    "type": str(col.type_name) if col.type_name else "",
                    "comment": col.comment or "",
                    "nullable": col.nullable if col.nullable is not None else True,
                    "position": col.position,
                }
                for col in table.columns
            ]
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                raise DatabricksNotFoundError(
                    f"Table '{table_name}' not found in '{catalog}.{schema}'"
                ) from e
            raise DatabricksAPIError(f"Failed to get table schema: {e}") from e

    def list_warehouses(self) -> list[dict[str, Any]]:
        """List all SQL warehouses.

        Returns:
            List of warehouse dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            warehouses = self._client.warehouses.list()
            return [
                {
                    "id": wh.id,
                    "name": wh.name,
                    "state": str(wh.state) if wh.state else "",
                    "cluster_size": wh.cluster_size or "",
                    "auto_stop_mins": wh.auto_stop_mins,
                }
                for wh in warehouses
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list warehouses: {e}") from e

    def _validate_query_safety(self, query: str) -> None:
        """Validate that query is safe (read-only SELECT query).

        Args:
            query: SQL query string to validate

        Raises:
            DatabricksAPIError: If query contains dangerous operations
        """
        if not query.strip():
            raise DatabricksAPIError("Query cannot be empty")

        if not self._is_safe_query(query):
            raise DatabricksAPIError(
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
                "sqlparse not installed - cannot validate query safety.\n"
                "Please run '/databricks_auth' again to install all dependencies."
            )
            return False

        try:
            parsed = sqlparse.parse(query)
            if not parsed:
                emit_warning("Query parsing returned no statements")
                return False

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

            for statement in parsed:
                stmt_type = statement.get_type()

                if stmt_type not in ("SELECT", "WITH", "UNKNOWN"):
                    emit_warning(
                        f"Query validation failed: Statement type '{stmt_type}' is not allowed."
                    )
                    return False

                tokens_list = list(statement.flatten())
                for token in tokens_list:
                    if (
                        token.ttype
                        in (sqlparse.tokens.Keyword.DDL, sqlparse.tokens.Keyword.DML)
                        and token.value.upper() in dangerous_keywords
                    ):
                        emit_warning(
                            f"Query validation failed: Dangerous keyword '{token.value.upper()}' detected."
                        )
                        return False

            return True

        except Exception as e:
            emit_warning(f"Error parsing query for safety check: {e}")
            return False

    def execute_query(
        self, query: str, max_results: int = DEFAULT_MAX_RESULTS
    ) -> dict[str, Any]:
        """Execute a SQL query using the SQL warehouse.

        Only SELECT queries are allowed. Destructive operations are blocked.

        Args:
            query: SQL query string (SELECT only)
            max_results: Maximum number of results to return

        Returns:
            Dictionary containing rows, schema, total_rows, statement_id

        Raises:
            DatabricksAPIError: If the query fails or is unsafe
        """
        if max_results <= 0:
            raise DatabricksAPIError("max_results must be positive")
        if max_results > MAX_RESULTS_LIMIT:
            raise DatabricksAPIError(
                f"max_results too large: {max_results} (max: {MAX_RESULTS_LIMIT})"
            )

        self._validate_query_safety(query)

        if not self._warehouse_id:
            raise DatabricksAPIError(
                "No SQL warehouse configured.\n"
                "Please run '/databricks_auth' to configure a warehouse."
            )

        try:
            # Execute query using statement execution API
            # wait_timeout must be "0s" (don't wait) or "Ns" where N is 5-50 seconds
            # Using "50s" as the maximum allowed synchronous wait time
            response = self._client.statement_execution.execute_statement(
                warehouse_id=self._warehouse_id,
                statement=query,
                wait_timeout="50s",
                row_limit=max_results,
                catalog=self._catalog,
                schema=self._schema,
            )

            # Check statement status
            if response.status and response.status.state != StatementState.SUCCEEDED:
                error_msg = (
                    response.status.error.message
                    if response.status.error
                    else "Unknown error"
                )
                raise DatabricksAPIError(f"Query failed: {error_msg}")

            # Extract results
            rows = []
            schema = []

            if response.manifest and response.manifest.schema:
                schema = [
                    {
                        "name": col.name,
                        "type": str(col.type_name) if col.type_name else "",
                        "position": col.position,
                    }
                    for col in response.manifest.schema.columns or []
                ]

            if response.result and response.result.data_array:
                column_names = [col["name"] for col in schema]
                for row_data in response.result.data_array:
                    row_dict = {}
                    for i, value in enumerate(row_data):
                        if i < len(column_names):
                            row_dict[column_names[i]] = value
                    rows.append(row_dict)

            total_rows = (
                response.manifest.total_row_count if response.manifest else len(rows)
            )

            return {
                "rows": rows,
                "schema": schema,
                "total_rows": total_rows,
                "statement_id": response.statement_id,
            }

        except DatabricksAPIError:
            raise
        except Exception as e:
            raise DatabricksAPIError(f"Query execution failed: {e}") from e
