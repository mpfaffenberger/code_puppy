"""Databricks client module.

This module provides a client for interacting with Databricks workspaces
using OAuth authentication with user credentials (U2M - User to Machine).

Supports:
- SQL warehouse queries (Unity Catalog)
- Workspace operations (notebooks, files)
- Job management (create, run, monitor)
- Delta Live Tables pipeline management
- Command execution on clusters
"""

import base64
import json
import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info, emit_warning

# Databricks SDK imports
try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementState
    from databricks.sdk.service.workspace import (
        ExportFormat,
        ImportFormat,
        Language,
        ObjectType,
    )
    from databricks.sdk.service.jobs import (
        RunLifeCycleState,
        RunResultState,
        Task,
        NotebookTask,
        SparkPythonTask,
        Source,
    )
    from databricks.sdk.service.pipelines import (
        PipelineState,
        PipelineStateInfo,
    )
    from databricks.sdk.service.compute import (
        State as ClusterState,
        Language as CommandLanguage,
    )
except ImportError:
    WorkspaceClient = None  # type: ignore
    StatementState = None  # type: ignore
    ExportFormat = None  # type: ignore
    ImportFormat = None  # type: ignore
    Language = None  # type: ignore
    ObjectType = None  # type: ignore
    RunLifeCycleState = None  # type: ignore
    RunResultState = None  # type: ignore
    Task = None  # type: ignore
    NotebookTask = None  # type: ignore
    SparkPythonTask = None  # type: ignore
    Source = None  # type: ignore
    PipelineState = None  # type: ignore
    PipelineStateInfo = None  # type: ignore
    ClusterState = None  # type: ignore
    CommandLanguage = None  # type: ignore

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

    # =========================================================================
    # Workspace / Notebook Operations
    # =========================================================================

    def list_workspace(
        self, path: str = "/", recursive: bool = False
    ) -> list[dict[str, Any]]:
        """List contents of a workspace directory.

        Args:
            path: Workspace path to list (default: root "/")
            recursive: If True, list recursively (flatten all subdirs)

        Returns:
            List of workspace object dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            objects = self._client.workspace.list(path=path)
            results = []

            for obj in objects:
                obj_info = {
                    "path": obj.path,
                    "object_type": str(obj.object_type) if obj.object_type else "",
                    "language": str(obj.language) if obj.language else "",
                    "created_at": obj.created_at,
                    "modified_at": obj.modified_at,
                    "object_id": obj.object_id,
                }
                results.append(obj_info)

                # Recursively list directories if requested
                if recursive and obj.object_type == ObjectType.DIRECTORY:
                    try:
                        sub_results = self.list_workspace(path=obj.path, recursive=True)
                        results.extend(sub_results)
                    except Exception:
                        pass  # Skip inaccessible directories

            return results
        except Exception as e:
            if "not found" in str(e).lower():
                raise DatabricksNotFoundError(
                    f"Workspace path '{path}' not found"
                ) from e
            raise DatabricksAPIError(f"Failed to list workspace: {e}") from e

    def get_notebook(self, path: str, format: str = "SOURCE") -> dict[str, Any]:
        """Export/read a notebook from the workspace.

        Args:
            path: Full workspace path to the notebook
            format: Export format - SOURCE, HTML, JUPYTER, DBC, R_MARKDOWN

        Returns:
            Dictionary containing notebook content and metadata

        Raises:
            DatabricksNotFoundError: If notebook doesn't exist
            DatabricksAPIError: If the API call fails
        """
        try:
            # Map format string to ExportFormat enum
            format_map = {
                "SOURCE": ExportFormat.SOURCE,
                "HTML": ExportFormat.HTML,
                "JUPYTER": ExportFormat.JUPYTER,
                "DBC": ExportFormat.DBC,
                "R_MARKDOWN": ExportFormat.R_MARKDOWN,
            }
            export_format = format_map.get(format.upper(), ExportFormat.SOURCE)

            response = self._client.workspace.export(path=path, format=export_format)

            # Decode base64 content
            content = ""
            if response.content:
                try:
                    content = base64.b64decode(response.content).decode("utf-8")
                except Exception:
                    # For binary formats like DBC, keep as base64
                    content = response.content

            # Get object status for metadata
            status = self._client.workspace.get_status(path=path)

            return {
                "path": path,
                "content": content,
                "format": format.upper(),
                "language": str(status.language) if status.language else "",
                "object_type": str(status.object_type) if status.object_type else "",
                "object_id": status.object_id,
                "created_at": status.created_at,
                "modified_at": status.modified_at,
            }
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                raise DatabricksNotFoundError(
                    f"Notebook '{path}' not found in workspace"
                ) from e
            raise DatabricksAPIError(f"Failed to export notebook: {e}") from e

    def upload_notebook(
        self,
        path: str,
        content: str,
        language: str = "PYTHON",
        format: str = "SOURCE",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Upload/import a notebook to the workspace.

        Args:
            path: Destination workspace path
            content: Notebook content (source code or base64 for binary formats)
            language: Notebook language - PYTHON, SCALA, SQL, R
            format: Import format - SOURCE, HTML, JUPYTER, DBC, R_MARKDOWN
            overwrite: If True, overwrite existing notebook

        Returns:
            Dictionary with upload result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            # Map language string to Language enum
            language_map = {
                "PYTHON": Language.PYTHON,
                "SCALA": Language.SCALA,
                "SQL": Language.SQL,
                "R": Language.R,
            }
            notebook_language = language_map.get(language.upper(), Language.PYTHON)

            # Map format string to ImportFormat enum
            format_map = {
                "SOURCE": ImportFormat.SOURCE,
                "HTML": ImportFormat.HTML,
                "JUPYTER": ImportFormat.JUPYTER,
                "DBC": ImportFormat.DBC,
                "R_MARKDOWN": ImportFormat.R_MARKDOWN,
            }
            import_format = format_map.get(format.upper(), ImportFormat.SOURCE)

            # Encode content to base64
            if format.upper() != "DBC":
                content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
            else:
                content_b64 = content  # Assume already base64 for DBC

            # Ensure parent directory exists
            parent_path = "/".join(path.rsplit("/", 1)[:-1])
            if parent_path:
                try:
                    self._client.workspace.mkdirs(path=parent_path)
                except Exception:
                    pass  # Directory may already exist

            self._client.workspace.import_(
                path=path,
                content=content_b64,
                language=notebook_language,
                format=import_format,
                overwrite=overwrite,
            )

            return {
                "success": True,
                "path": path,
                "language": language.upper(),
                "format": format.upper(),
                "overwrite": overwrite,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to upload notebook: {e}") from e

    def create_workspace_directory(self, path: str) -> dict[str, Any]:
        """Create a directory in the workspace.

        Args:
            path: Workspace path for the new directory

        Returns:
            Dictionary with creation result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            self._client.workspace.mkdirs(path=path)
            return {
                "success": True,
                "path": path,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to create directory: {e}") from e

    def delete_workspace_object(
        self, path: str, recursive: bool = False
    ) -> dict[str, Any]:
        """Delete a workspace object (notebook, file, or directory).

        Args:
            path: Workspace path to delete
            recursive: If True, delete directory contents recursively

        Returns:
            Dictionary with deletion result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            self._client.workspace.delete(path=path, recursive=recursive)
            return {
                "success": True,
                "path": path,
                "recursive": recursive,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to delete workspace object: {e}") from e

    # =========================================================================
    # Job Operations
    # =========================================================================

    def list_jobs(
        self, name_filter: Optional[str] = None, limit: int = 25
    ) -> list[dict[str, Any]]:
        """List all jobs in the workspace.

        Args:
            name_filter: Optional filter by job name (contains)
            limit: Maximum number of jobs to return

        Returns:
            List of job dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            jobs = self._client.jobs.list(name=name_filter, limit=limit)
            return [
                {
                    "job_id": job.job_id,
                    "name": job.settings.name if job.settings else "",
                    "created_time": job.created_time,
                    "creator_user_name": job.creator_user_name,
                }
                for job in jobs
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list jobs: {e}") from e

    def get_job(self, job_id: int) -> dict[str, Any]:
        """Get details of a specific job.

        Args:
            job_id: The job ID

        Returns:
            Job details dictionary

        Raises:
            DatabricksNotFoundError: If job doesn't exist
            DatabricksAPIError: If the API call fails
        """
        try:
            job = self._client.jobs.get(job_id=job_id)
            settings = job.settings

            tasks = []
            if settings and settings.tasks:
                for task in settings.tasks:
                    task_info = {
                        "task_key": task.task_key,
                        "description": task.description or "",
                    }
                    if task.notebook_task:
                        task_info["type"] = "notebook"
                        task_info["notebook_path"] = task.notebook_task.notebook_path
                    elif task.spark_python_task:
                        task_info["type"] = "spark_python"
                        task_info["python_file"] = task.spark_python_task.python_file
                    elif task.spark_jar_task:
                        task_info["type"] = "spark_jar"
                    elif task.sql_task:
                        task_info["type"] = "sql"
                    else:
                        task_info["type"] = "other"
                    tasks.append(task_info)

            return {
                "job_id": job.job_id,
                "name": settings.name if settings else "",
                "created_time": job.created_time,
                "creator_user_name": job.creator_user_name,
                "tasks": tasks,
                "schedule": str(settings.schedule)
                if settings and settings.schedule
                else None,
                "max_concurrent_runs": settings.max_concurrent_runs if settings else 1,
            }
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                raise DatabricksNotFoundError(f"Job {job_id} not found") from e
            raise DatabricksAPIError(f"Failed to get job: {e}") from e

    def create_job(
        self,
        name: str,
        notebook_path: Optional[str] = None,
        python_file: Optional[str] = None,
        cluster_id: Optional[str] = None,
        parameters: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Create a new job.

        Args:
            name: Job name
            notebook_path: Path to notebook (for notebook tasks)
            python_file: Path to Python file (for spark_python tasks)
            cluster_id: Existing cluster ID to use (optional)
            parameters: Base parameters for the job

        Returns:
            Dictionary with created job info

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            # Build the task
            if notebook_path:
                task = Task(
                    task_key="main_task",
                    notebook_task=NotebookTask(
                        notebook_path=notebook_path,
                        source=Source.WORKSPACE,
                        base_parameters=parameters,
                    ),
                    existing_cluster_id=cluster_id,
                )
            elif python_file:
                task = Task(
                    task_key="main_task",
                    spark_python_task=SparkPythonTask(
                        python_file=python_file,
                        parameters=list(parameters.values()) if parameters else [],
                    ),
                    existing_cluster_id=cluster_id,
                )
            else:
                raise DatabricksAPIError(
                    "Either notebook_path or python_file must be specified"
                )

            # Create the job
            response = self._client.jobs.create(
                name=name,
                tasks=[task],
            )

            return {
                "success": True,
                "job_id": response.job_id,
                "name": name,
            }
        except DatabricksAPIError:
            raise
        except Exception as e:
            raise DatabricksAPIError(f"Failed to create job: {e}") from e

    def run_job(
        self,
        job_id: int,
        parameters: Optional[dict[str, str]] = None,
        wait: bool = False,
        timeout_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Run a job immediately.

        Args:
            job_id: The job ID to run
            parameters: Optional notebook or job parameters
            wait: If True, wait for job to complete
            timeout_seconds: Timeout for waiting (default: 1 hour)

        Returns:
            Dictionary with run information

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            if wait:
                run = self._client.jobs.run_now_and_wait(
                    job_id=job_id,
                    notebook_params=parameters,
                    timeout=timedelta(seconds=timeout_seconds),
                )
            else:
                run = self._client.jobs.run_now(
                    job_id=job_id,
                    notebook_params=parameters,
                )

            result = {
                "run_id": run.run_id,
                "job_id": job_id,
                "number_in_job": getattr(run, "number_in_job", None),
            }

            if wait:
                result["state"] = str(run.state.life_cycle_state) if run.state else ""
                result["result_state"] = (
                    str(run.state.result_state)
                    if run.state and run.state.result_state
                    else ""
                )

            return result
        except Exception as e:
            raise DatabricksAPIError(f"Failed to run job: {e}") from e

    def get_run_status(self, run_id: int) -> dict[str, Any]:
        """Get the status of a job run.

        Args:
            run_id: The run ID

        Returns:
            Dictionary with run status

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            run = self._client.jobs.get_run(run_id=run_id)

            return {
                "run_id": run.run_id,
                "job_id": run.job_id,
                "run_name": run.run_name,
                "state": str(run.state.life_cycle_state) if run.state else "",
                "result_state": (
                    str(run.state.result_state)
                    if run.state and run.state.result_state
                    else ""
                ),
                "start_time": run.start_time,
                "end_time": run.end_time,
                "setup_duration": run.setup_duration,
                "execution_duration": run.execution_duration,
                "cleanup_duration": run.cleanup_duration,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to get run status: {e}") from e

    def cancel_run(self, run_id: int) -> dict[str, Any]:
        """Cancel a running job.

        Args:
            run_id: The run ID to cancel

        Returns:
            Dictionary with cancellation result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            self._client.jobs.cancel_run(run_id=run_id)
            return {
                "success": True,
                "run_id": run_id,
                "message": "Run cancellation initiated",
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to cancel run: {e}") from e

    def list_runs(
        self,
        job_id: Optional[int] = None,
        active_only: bool = False,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """List job runs.

        Args:
            job_id: Optional filter by job ID
            active_only: If True, only return active runs
            limit: Maximum number of runs to return

        Returns:
            List of run dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            runs = self._client.jobs.list_runs(
                job_id=job_id,
                active_only=active_only,
                limit=limit,
            )
            return [
                {
                    "run_id": run.run_id,
                    "job_id": run.job_id,
                    "run_name": run.run_name,
                    "state": str(run.state.life_cycle_state) if run.state else "",
                    "result_state": (
                        str(run.state.result_state)
                        if run.state and run.state.result_state
                        else ""
                    ),
                    "start_time": run.start_time,
                }
                for run in runs
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list runs: {e}") from e

    # =========================================================================
    # Pipeline (Delta Live Tables) Operations
    # =========================================================================

    def list_pipelines(
        self, name_filter: Optional[str] = None, max_results: int = 25
    ) -> list[dict[str, Any]]:
        """List Delta Live Tables pipelines.

        Args:
            name_filter: Optional filter by pipeline name
            max_results: Maximum number of results

        Returns:
            List of pipeline dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            pipelines = self._client.pipelines.list_pipelines(
                filter=f"name LIKE '%{name_filter}%'" if name_filter else None,
                max_results=max_results,
            )
            return [
                {
                    "pipeline_id": p.pipeline_id,
                    "name": p.name,
                    "state": str(p.state) if p.state else "",
                    "creator_user_name": p.creator_user_name,
                }
                for p in pipelines
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list pipelines: {e}") from e

    def get_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        """Get details of a specific pipeline.

        Args:
            pipeline_id: The pipeline ID

        Returns:
            Pipeline details dictionary

        Raises:
            DatabricksNotFoundError: If pipeline doesn't exist
            DatabricksAPIError: If the API call fails
        """
        try:
            pipeline = self._client.pipelines.get(pipeline_id=pipeline_id)

            libraries = []
            if pipeline.spec and pipeline.spec.libraries:
                for lib in pipeline.spec.libraries:
                    if lib.notebook:
                        libraries.append(
                            {"type": "notebook", "path": lib.notebook.path}
                        )
                    elif lib.file:
                        libraries.append({"type": "file", "path": lib.file.path})

            return {
                "pipeline_id": pipeline.pipeline_id,
                "name": pipeline.name,
                "state": str(pipeline.state) if pipeline.state else "",
                "creator_user_name": pipeline.creator_user_name,
                "catalog": pipeline.spec.catalog if pipeline.spec else None,
                "target": pipeline.spec.target if pipeline.spec else None,
                "libraries": libraries,
                "continuous": pipeline.spec.continuous if pipeline.spec else False,
                "development": pipeline.spec.development if pipeline.spec else False,
            }
        except Exception as e:
            if "not found" in str(e).lower() or "does not exist" in str(e).lower():
                raise DatabricksNotFoundError(
                    f"Pipeline '{pipeline_id}' not found"
                ) from e
            raise DatabricksAPIError(f"Failed to get pipeline: {e}") from e

    def create_pipeline(
        self,
        name: str,
        notebook_paths: list[str],
        target_schema: Optional[str] = None,
        catalog: Optional[str] = None,
        continuous: bool = False,
        development: bool = True,
        cluster_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Create a Delta Live Tables pipeline.

        Args:
            name: Pipeline name
            notebook_paths: List of notebook paths for the pipeline
            target_schema: Target schema for pipeline tables
            catalog: Unity Catalog name (for UC-enabled pipelines)
            continuous: If True, run in continuous mode
            development: If True, run in development mode
            cluster_id: Optional existing cluster ID

        Returns:
            Dictionary with created pipeline info

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            from databricks.sdk.service.pipelines import (
                PipelineLibrary,
                NotebookLibrary,
            )

            # Build libraries from notebook paths
            libraries = [
                PipelineLibrary(notebook=NotebookLibrary(path=path))
                for path in notebook_paths
            ]

            response = self._client.pipelines.create(
                name=name,
                libraries=libraries,
                target=target_schema,
                catalog=catalog,
                continuous=continuous,
                development=development,
            )

            return {
                "success": True,
                "pipeline_id": response.pipeline_id,
                "name": name,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to create pipeline: {e}") from e

    def start_pipeline(
        self,
        pipeline_id: str,
        full_refresh: bool = False,
        wait: bool = False,
        timeout_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Start a pipeline update.

        Args:
            pipeline_id: The pipeline ID
            full_refresh: If True, refresh all tables
            wait: If True, wait for pipeline to complete
            timeout_seconds: Timeout for waiting

        Returns:
            Dictionary with update information

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            if wait:
                # Start and wait for completion
                update = self._client.pipelines.start_update(
                    pipeline_id=pipeline_id,
                    full_refresh=full_refresh,
                )
                update_id = update.update_id

                # Poll for completion
                start_time = time.time()
                while time.time() - start_time < timeout_seconds:
                    status = self._client.pipelines.get_update(
                        pipeline_id=pipeline_id,
                        update_id=update_id,
                    )
                    state = status.update.state if status.update else None

                    if state in [
                        PipelineState.COMPLETED,
                        PipelineState.FAILED,
                        PipelineState.CANCELED,
                    ]:
                        return {
                            "update_id": update_id,
                            "pipeline_id": pipeline_id,
                            "state": str(state),
                            "full_refresh": full_refresh,
                        }
                    time.sleep(10)

                raise DatabricksAPIError(
                    f"Pipeline update timed out after {timeout_seconds} seconds"
                )
            else:
                update = self._client.pipelines.start_update(
                    pipeline_id=pipeline_id,
                    full_refresh=full_refresh,
                )
                return {
                    "update_id": update.update_id,
                    "pipeline_id": pipeline_id,
                    "full_refresh": full_refresh,
                    "state": "STARTED",
                }
        except DatabricksAPIError:
            raise
        except Exception as e:
            raise DatabricksAPIError(f"Failed to start pipeline: {e}") from e

    def stop_pipeline(self, pipeline_id: str) -> dict[str, Any]:
        """Stop a running pipeline.

        Args:
            pipeline_id: The pipeline ID

        Returns:
            Dictionary with stop result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            self._client.pipelines.stop(pipeline_id=pipeline_id)
            return {
                "success": True,
                "pipeline_id": pipeline_id,
                "message": "Pipeline stop initiated",
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to stop pipeline: {e}") from e

    def get_pipeline_update(self, pipeline_id: str, update_id: str) -> dict[str, Any]:
        """Get status of a pipeline update.

        Args:
            pipeline_id: The pipeline ID
            update_id: The update ID

        Returns:
            Dictionary with update status

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            response = self._client.pipelines.get_update(
                pipeline_id=pipeline_id,
                update_id=update_id,
            )
            update = response.update

            return {
                "update_id": update_id,
                "pipeline_id": pipeline_id,
                "state": str(update.state) if update else "",
                "creation_time": update.creation_time if update else None,
                "full_refresh": update.full_refresh if update else False,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to get pipeline update: {e}") from e

    # =========================================================================
    # Cluster / Command Execution Operations
    # =========================================================================

    def list_clusters(self) -> list[dict[str, Any]]:
        """List all clusters in the workspace.

        Returns:
            List of cluster dictionaries

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            clusters = self._client.clusters.list()
            return [
                {
                    "cluster_id": c.cluster_id,
                    "cluster_name": c.cluster_name,
                    "state": str(c.state) if c.state else "",
                    "spark_version": c.spark_version,
                    "node_type_id": c.node_type_id,
                    "num_workers": c.num_workers,
                    "creator_user_name": c.creator_user_name,
                }
                for c in clusters
            ]
        except Exception as e:
            raise DatabricksAPIError(f"Failed to list clusters: {e}") from e

    def run_notebook(
        self,
        notebook_path: str,
        cluster_id: str,
        parameters: Optional[dict[str, str]] = None,
        timeout_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Run a notebook on a cluster using Jobs API (one-time run).

        This creates a one-time job run to execute the notebook.

        Args:
            notebook_path: Path to the notebook in the workspace
            cluster_id: Cluster ID to run on
            parameters: Optional notebook parameters
            timeout_seconds: Timeout for the run

        Returns:
            Dictionary with run result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            from databricks.sdk.service.jobs import (
                SubmitTask,
                NotebookTask,
                Source,
            )

            # Submit one-time run
            run = self._client.jobs.submit_and_wait(
                run_name=f"notebook_run_{notebook_path.split('/')[-1]}",
                tasks=[
                    SubmitTask(
                        task_key="notebook_task",
                        existing_cluster_id=cluster_id,
                        notebook_task=NotebookTask(
                            notebook_path=notebook_path,
                            source=Source.WORKSPACE,
                            base_parameters=parameters,
                        ),
                    )
                ],
                timeout=timedelta(seconds=timeout_seconds),
            )

            # Get run output
            output = None
            if run.tasks:
                task_run_id = run.tasks[0].run_id
                try:
                    task_output = self._client.jobs.get_run_output(run_id=task_run_id)
                    if task_output.notebook_output:
                        output = task_output.notebook_output.result
                except Exception:
                    pass  # Output retrieval failed

            return {
                "run_id": run.run_id,
                "state": str(run.state.life_cycle_state) if run.state else "",
                "result_state": (
                    str(run.state.result_state)
                    if run.state and run.state.result_state
                    else ""
                ),
                "notebook_path": notebook_path,
                "cluster_id": cluster_id,
                "output": output,
                "execution_duration": run.execution_duration,
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to run notebook: {e}") from e

    def execute_code(
        self,
        cluster_id: str,
        code: str,
        language: str = "python",
        context_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Execute code directly on a cluster using Command Execution API.

        Note: This only works on all-purpose (interactive) clusters.

        Args:
            cluster_id: Cluster ID to execute on
            code: Code to execute
            language: Language - python, scala, sql, r
            context_id: Optional existing execution context ID

        Returns:
            Dictionary with execution result

        Raises:
            DatabricksAPIError: If the API call fails
        """
        try:
            # Map language string
            lang_map = {
                "python": CommandLanguage.PYTHON,
                "scala": CommandLanguage.SCALA,
                "sql": CommandLanguage.SQL,
                "r": CommandLanguage.R,
            }
            cmd_language = lang_map.get(language.lower(), CommandLanguage.PYTHON)

            # Create execution context if not provided
            if not context_id:
                ctx = self._client.command_execution.create_and_wait(
                    cluster_id=cluster_id,
                    language=cmd_language,
                )
                context_id = ctx.id

            # Execute command
            result = self._client.command_execution.execute_and_wait(
                cluster_id=cluster_id,
                context_id=context_id,
                language=cmd_language,
                command=code,
            )

            output = None
            output_type = None
            if result.results:
                output = result.results.data
                output_type = result.results.result_type

            return {
                "context_id": context_id,
                "cluster_id": cluster_id,
                "status": str(result.status) if result.status else "",
                "output": output,
                "output_type": str(output_type) if output_type else "",
            }
        except Exception as e:
            raise DatabricksAPIError(f"Failed to execute code: {e}") from e
