"""Databricks integration tools.

Provides tools for exploring and querying Databricks SQL warehouses,
including listing catalogs, schemas, tables, and executing queries.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any, Optional

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.databricks_client import (
    DatabricksAPIError,
    DatabricksAuthError,
    DatabricksClient,
    DatabricksError,
    DatabricksNotFoundError,
)

RESULTS_DIR_NAME = "databricks_results"
DEFAULT_PREVIEW_ROWS = 5
VALID_OUTPUT_FORMATS = {"csv", "json"}


# ============================================================================
# Helper Functions
# ============================================================================


def get_databricks_client(
    catalog: Optional[str] = None, schema: Optional[str] = None
) -> DatabricksClient:
    """Get a Databricks client instance.

    Args:
        catalog: Optional catalog name
        schema: Optional schema name

    Returns:
        DatabricksClient: A configured Databricks client
    """
    return DatabricksClient(catalog=catalog, schema=schema)


def _handle_databricks_error(e: Exception) -> dict:
    """Convert Databricks exceptions to structured error responses.

    Args:
        e: Exception raised by Databricks client

    Returns:
        Dict with success=False and error details
    """
    if isinstance(e, DatabricksAuthError):
        error_msg = f"Authentication failed: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, DatabricksNotFoundError):
        error_msg = f"Resource not found: {str(e)}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, DatabricksAPIError):
        error_msg = f"API error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
    elif isinstance(e, DatabricksError):
        error_msg = f"Databricks error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "databricks",
        }
    else:
        error_msg = f"Unexpected error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown",
        }


def _slugify_filename(value: str) -> str:
    """Convert an arbitrary string into a filesystem-friendly slug."""
    sanitized = "".join(char if char.isalnum() else "-" for char in value.strip())
    slug = "-".join(filter(None, sanitized.lower().split("-")))
    return slug or "query"


def _generate_default_filename(
    file_name_hint: Optional[str], statement_id: str, output_format: str
) -> str:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    slug_source = file_name_hint or f"query-{statement_id}"
    slug = _slugify_filename(slug_source)
    return f"{slug}-{timestamp}.{output_format}"


def _resolve_output_path(
    output_path: Optional[str],
    statement_id: str,
    file_name_hint: Optional[str],
    output_format: str,
) -> Path:
    """Determine where query results should be written."""
    fmt_suffix = f".{output_format}"

    if output_path:
        path = Path(output_path).expanduser()
        if path.is_dir():
            filename = _generate_default_filename(
                file_name_hint, statement_id, output_format
            )
            path = path / filename
        elif not path.suffix:
            path = path.with_suffix(fmt_suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    results_dir = Path.cwd() / RESULTS_DIR_NAME
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = _generate_default_filename(file_name_hint, statement_id, output_format)
    return results_dir / filename


def _write_results_to_file(
    rows: list[dict[str, Any]],
    schema: list[dict[str, Any]],
    output_file: Path,
    output_format: str,
) -> None:
    """Persist query rows to disk in CSV or JSON format."""
    if output_format not in VALID_OUTPUT_FORMATS:
        raise DatabricksAPIError(
            f"Unsupported output format '{output_format}'. "
            f"Supported formats: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
        )

    fieldnames = [field["name"] for field in schema if "name" in field]
    if not fieldnames and rows:
        fieldnames = list(rows[0].keys())

    if output_format == "csv":
        derived_fieldnames = fieldnames or (sorted(rows[0].keys()) if rows else [])
        if not derived_fieldnames:
            raise DatabricksAPIError("Unable to determine field names for CSV export.")
        with output_file.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=derived_fieldnames,
                extrasaction="ignore",
            )
            if derived_fieldnames:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)
    else:
        with output_file.open("w", encoding="utf-8") as json_file:
            json.dump(rows, json_file, indent=2, ensure_ascii=False)


def _normalize_output_format(output_format: str) -> str:
    fmt = (output_format or "csv").lower().strip()
    if fmt not in VALID_OUTPUT_FORMATS:
        raise DatabricksAPIError(
            f"Invalid output format '{output_format}'. "
            f"Supported formats: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
        )
    return fmt


# ============================================================================
# Databricks List Catalogs Tool
# ============================================================================


def databricks_list_catalogs(ctx: RunContext) -> dict:
    """List all accessible catalogs in Databricks.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - catalogs (list): List of catalog dictionaries
            - count (int): Number of catalogs found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST CATALOGS [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        catalogs = client.list_catalogs()

        emit_success(f"Found {len(catalogs)} catalog(s)")

        return {
            "success": True,
            "catalogs": catalogs,
            "count": len(catalogs),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_catalogs(agent: Any) -> Tool:
    """Register the databricks_list_catalogs tool."""
    return agent.tool(databricks_list_catalogs)


# ============================================================================
# Databricks List Schemas Tool
# ============================================================================


def databricks_list_schemas(
    ctx: RunContext, catalog_name: Optional[str] = None
) -> dict:
    """List all schemas in a Databricks catalog.

    Args:
        ctx: PydanticAI run context
        catalog_name: Catalog name. If None, uses default catalog.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - schemas (list): List of schema dictionaries
            - count (int): Number of schemas found
            - catalog_name (str): The catalog searched
            - error (str, optional): Error message if operation failed
    """
    catalog_display = catalog_name or "default"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS LIST SCHEMAS [/bold white on blue] "
            f"[bold cyan]{catalog_display}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        schemas = client.list_schemas(catalog_name=catalog_name)

        emit_success(f"Found {len(schemas)} schema(s)")

        return {
            "success": True,
            "schemas": schemas,
            "count": len(schemas),
            "catalog_name": catalog_name or client.catalog,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_schemas(agent: Any) -> Tool:
    """Register the databricks_list_schemas tool."""
    return agent.tool(databricks_list_schemas)


# ============================================================================
# Databricks List Tables Tool
# ============================================================================


def databricks_list_tables(
    ctx: RunContext,
    catalog_name: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> dict:
    """List all tables in a Databricks schema.

    Args:
        ctx: PydanticAI run context
        catalog_name: Catalog name. If None, uses default catalog.
        schema_name: Schema name. If None, uses default schema.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - tables (list): List of table dictionaries
            - count (int): Number of tables found
            - catalog_name (str): The catalog searched
            - schema_name (str): The schema searched
            - error (str, optional): Error message if operation failed
    """
    catalog_display = catalog_name or "default"
    schema_display = schema_name or "default"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS LIST TABLES [/bold white on blue] "
            f"[bold cyan]{catalog_display}.{schema_display}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        tables = client.list_tables(catalog_name=catalog_name, schema_name=schema_name)

        emit_success(f"Found {len(tables)} table(s)")

        return {
            "success": True,
            "tables": tables,
            "count": len(tables),
            "catalog_name": catalog_name or client.catalog,
            "schema_name": schema_name or client.schema,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_tables(agent: Any) -> Tool:
    """Register the databricks_list_tables tool."""
    return agent.tool(databricks_list_tables)


# ============================================================================
# Databricks Get Table Schema Tool
# ============================================================================


def databricks_get_table_schema(
    ctx: RunContext,
    table_name: str,
    catalog_name: Optional[str] = None,
    schema_name: Optional[str] = None,
) -> dict:
    """Get the schema for a specific Databricks table.

    Args:
        ctx: PydanticAI run context
        table_name: Table name
        catalog_name: Catalog name. If None, uses default catalog.
        schema_name: Schema name. If None, uses default schema.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - schema (list): List of column dictionaries
            - table_name (str): The table name
            - full_name (str): Full table name (catalog.schema.table)
            - error (str, optional): Error message if operation failed
    """
    catalog_display = catalog_name or "default"
    schema_display = schema_name or "default"
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS GET TABLE SCHEMA [/bold white on blue] "
            f"[bold cyan]{catalog_display}.{schema_display}.{table_name}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        columns = client.get_table_schema(
            table_name=table_name,
            catalog_name=catalog_name,
            schema_name=schema_name,
        )

        emit_success(f"Retrieved schema with {len(columns)} column(s)")

        cat = catalog_name or client.catalog
        sch = schema_name or client.schema
        full_name = f"{cat}.{sch}.{table_name}"

        return {
            "success": True,
            "schema": columns,
            "table_name": table_name,
            "full_name": full_name,
            "catalog_name": cat,
            "schema_name": sch,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_get_table_schema(agent: Any) -> Tool:
    """Register the databricks_get_table_schema tool."""
    return agent.tool(databricks_get_table_schema)


# ============================================================================
# Databricks List Warehouses Tool
# ============================================================================


def databricks_list_warehouses(ctx: RunContext) -> dict:
    """List all SQL warehouses in Databricks.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - warehouses (list): List of warehouse dictionaries
            - count (int): Number of warehouses found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST WAREHOUSES [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        warehouses = client.list_warehouses()

        emit_success(f"Found {len(warehouses)} warehouse(s)")

        return {
            "success": True,
            "warehouses": warehouses,
            "count": len(warehouses),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_warehouses(agent: Any) -> Tool:
    """Register the databricks_list_warehouses tool."""
    return agent.tool(databricks_list_warehouses)


# ============================================================================
# Databricks Execute Query Tool
# ============================================================================


def databricks_execute_query(
    ctx: RunContext,
    query: str,
    max_results: int = 100,
    save_to_file: bool = True,
    output_path: Optional[str] = None,
    file_name_hint: Optional[str] = None,
    output_format: str = "csv",
) -> dict:
    """Execute a SQL query in Databricks.

    SAFETY: Only SELECT queries are allowed. Destructive operations (DELETE, DROP,
    TRUNCATE, INSERT, UPDATE, MERGE, ALTER, CREATE, REPLACE) are blocked.

    Only 5 preview rows are returned inline to minimize token usage. Results are saved
    to a CSV file by default.

    Args:
        ctx: PydanticAI run context
        query: SQL query string to execute (SELECT only)
        max_results: Maximum number of results to return (default: 100)
        save_to_file: Whether to save full results to a file (default: True)
        output_path: Optional explicit output path for saved results
        file_name_hint: Optional friendly name used when generating filenames
        output_format: File format for saved results ("csv" or "json", default: csv)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - total_rows (int): Total number of rows in result
            - preview_rows (list): First 5 rows as preview
            - saved_file_path (str | None): Path to saved file
            - schema (list): List of field definitions
            - statement_id (str): Databricks statement ID
            - error (str, optional): Error message if query failed
    """
    query_preview = query[:100] + "..." if len(query) > 100 else query
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS EXECUTE QUERY [/bold white on blue]\n"
            f"[dim]{query_preview}[/dim]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.execute_query(query=query, max_results=max_results)

        rows = result.get("rows", [])
        total_rows = result["total_rows"]
        preview_rows_data = rows[:DEFAULT_PREVIEW_ROWS]
        saved_file_path: Optional[str] = None

        emit_success(
            f"Query completed: {total_rows} total rows, "
            f"returned {len(rows)} rows\n"
            f"Statement ID: {result['statement_id']}"
        )

        if save_to_file and rows:
            saved_format = _normalize_output_format(output_format)
            try:
                output_file = _resolve_output_path(
                    output_path, result["statement_id"], file_name_hint, saved_format
                )
                _write_results_to_file(
                    rows, result["schema"], output_file, saved_format
                )
                saved_file_path = str(output_file)
                emit_success(f"Saved {len(rows)} row(s) to {saved_file_path}")
            except Exception as file_error:
                emit_warning(f"Failed to save query results to file: {file_error}")
                return {
                    "success": True,
                    "total_rows": total_rows,
                    "saved_file_path": None,
                    "save_error": str(file_error),
                    "preview_rows": preview_rows_data,
                    "schema": result["schema"],
                    "statement_id": result["statement_id"],
                }

        return {
            "success": True,
            "total_rows": total_rows,
            "saved_file_path": saved_file_path,
            "preview_rows": preview_rows_data,
            "schema": result["schema"],
            "statement_id": result["statement_id"],
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_execute_query(agent: Any) -> Tool:
    """Register the databricks_execute_query tool."""
    return agent.tool(databricks_execute_query)


# ============================================================================
# Databricks Workspace / Notebook Tools
# ============================================================================


def databricks_list_workspace(
    ctx: RunContext,
    path: str = "/",
    recursive: bool = False,
) -> dict:
    """List contents of a Databricks workspace directory.

    Args:
        ctx: PydanticAI run context
        path: Workspace path to list (default: root "/")
        recursive: If True, list recursively (flatten all subdirectories)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - objects (list): List of workspace object dictionaries
            - count (int): Number of objects found
            - path (str): The path listed
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS LIST WORKSPACE [/bold white on blue] "
            f"[bold cyan]{path}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        objects = client.list_workspace(path=path, recursive=recursive)

        emit_success(f"Found {len(objects)} object(s)")

        return {
            "success": True,
            "objects": objects,
            "count": len(objects),
            "path": path,
            "recursive": recursive,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_workspace(agent: Any) -> Tool:
    """Register the databricks_list_workspace tool."""
    return agent.tool(databricks_list_workspace)


def databricks_get_notebook(
    ctx: RunContext,
    path: str,
    format: str = "SOURCE",
) -> dict:
    """Read/export a notebook from the Databricks workspace.

    Args:
        ctx: PydanticAI run context
        path: Full workspace path to the notebook
        format: Export format - SOURCE (default), HTML, JUPYTER, DBC, R_MARKDOWN

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - content (str): Notebook content
            - path (str): Notebook path
            - language (str): Notebook language (PYTHON, SCALA, SQL, R)
            - format (str): Export format used
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS GET NOTEBOOK [/bold white on blue] "
            f"[bold cyan]{path}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.get_notebook(path=path, format=format)

        emit_success(f"Retrieved notebook: {path}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_get_notebook(agent: Any) -> Tool:
    """Register the databricks_get_notebook tool."""
    return agent.tool(databricks_get_notebook)


def databricks_upload_notebook(
    ctx: RunContext,
    path: str,
    content: str,
    language: str = "PYTHON",
    format: str = "SOURCE",
    overwrite: bool = False,
) -> dict:
    """Upload/import a notebook to the Databricks workspace.

    Args:
        ctx: PydanticAI run context
        path: Destination workspace path (e.g., /Users/user@example.com/my_notebook)
        content: Notebook content (source code)
        language: Notebook language - PYTHON (default), SCALA, SQL, R
        format: Import format - SOURCE (default), HTML, JUPYTER, DBC, R_MARKDOWN
        overwrite: If True, overwrite existing notebook

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - path (str): Notebook path
            - language (str): Notebook language
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS UPLOAD NOTEBOOK [/bold white on blue] "
            f"[bold cyan]{path}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.upload_notebook(
            path=path,
            content=content,
            language=language,
            format=format,
            overwrite=overwrite,
        )

        emit_success(f"Uploaded notebook to: {path}")

        return result

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_upload_notebook(agent: Any) -> Tool:
    """Register the databricks_upload_notebook tool."""
    return agent.tool(databricks_upload_notebook)


# ============================================================================
# Databricks Job Tools
# ============================================================================


def databricks_list_jobs(
    ctx: RunContext,
    name_filter: Optional[str] = None,
    limit: int = 25,
) -> dict:
    """List all jobs in the Databricks workspace.

    Args:
        ctx: PydanticAI run context
        name_filter: Optional filter by job name (contains)
        limit: Maximum number of jobs to return (default: 25)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - jobs (list): List of job dictionaries
            - count (int): Number of jobs found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST JOBS [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        jobs = client.list_jobs(name_filter=name_filter, limit=limit)

        emit_success(f"Found {len(jobs)} job(s)")

        return {
            "success": True,
            "jobs": jobs,
            "count": len(jobs),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_jobs(agent: Any) -> Tool:
    """Register the databricks_list_jobs tool."""
    return agent.tool(databricks_list_jobs)


def databricks_get_job(ctx: RunContext, job_id: int) -> dict:
    """Get details of a specific Databricks job.

    Args:
        ctx: PydanticAI run context
        job_id: The job ID

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - job details (various fields)
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS GET JOB [/bold white on blue] "
            f"[bold cyan]Job ID: {job_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        job = client.get_job(job_id=job_id)

        emit_success(f"Retrieved job: {job.get('name', job_id)}")

        return {
            "success": True,
            **job,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_get_job(agent: Any) -> Tool:
    """Register the databricks_get_job tool."""
    return agent.tool(databricks_get_job)


def databricks_create_job(
    ctx: RunContext,
    name: str,
    notebook_path: Optional[str] = None,
    python_file: Optional[str] = None,
    cluster_id: Optional[str] = None,
    parameters: Optional[dict] = None,
) -> dict:
    """Create a new Databricks job.

    Args:
        ctx: PydanticAI run context
        name: Job name
        notebook_path: Path to notebook (for notebook tasks)
        python_file: Path to Python file (for spark_python tasks)
        cluster_id: Existing cluster ID to use (optional)
        parameters: Base parameters for the job

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - job_id (int): Created job ID
            - name (str): Job name
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS CREATE JOB [/bold white on blue] "
            f"[bold cyan]{name}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.create_job(
            name=name,
            notebook_path=notebook_path,
            python_file=python_file,
            cluster_id=cluster_id,
            parameters=parameters,
        )

        emit_success(f"Created job '{name}' with ID: {result['job_id']}")

        return result

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_create_job(agent: Any) -> Tool:
    """Register the databricks_create_job tool."""
    return agent.tool(databricks_create_job)


def databricks_run_job(
    ctx: RunContext,
    job_id: int,
    parameters: Optional[dict] = None,
    wait: bool = False,
    timeout_seconds: int = 3600,
) -> dict:
    """Run a Databricks job immediately.

    Args:
        ctx: PydanticAI run context
        job_id: The job ID to run
        parameters: Optional notebook or job parameters
        wait: If True, wait for job to complete (default: False)
        timeout_seconds: Timeout for waiting (default: 3600 = 1 hour)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - run_id (int): The run ID
            - state (str): Run state (if wait=True)
            - result_state (str): Result state (if wait=True)
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS RUN JOB [/bold white on blue] "
            f"[bold cyan]Job ID: {job_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.run_job(
            job_id=job_id,
            parameters=parameters,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )

        if wait:
            emit_success(f"Job run completed: {result.get('result_state', 'UNKNOWN')}")
        else:
            emit_success(f"Job run started: Run ID {result['run_id']}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_run_job(agent: Any) -> Tool:
    """Register the databricks_run_job tool."""
    return agent.tool(databricks_run_job)


def databricks_get_run_status(ctx: RunContext, run_id: int) -> dict:
    """Get the status of a Databricks job run.

    Args:
        ctx: PydanticAI run context
        run_id: The run ID

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - run status details (various fields)
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS GET RUN STATUS [/bold white on blue] "
            f"[bold cyan]Run ID: {run_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.get_run_status(run_id=run_id)

        emit_success(f"Run state: {result.get('state', 'UNKNOWN')}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_get_run_status(agent: Any) -> Tool:
    """Register the databricks_get_run_status tool."""
    return agent.tool(databricks_get_run_status)


def databricks_list_runs(
    ctx: RunContext,
    job_id: Optional[int] = None,
    active_only: bool = False,
    limit: int = 25,
) -> dict:
    """List Databricks job runs.

    Args:
        ctx: PydanticAI run context
        job_id: Optional filter by job ID
        active_only: If True, only return active runs
        limit: Maximum number of runs to return (default: 25)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - runs (list): List of run dictionaries
            - count (int): Number of runs found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST RUNS [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        runs = client.list_runs(job_id=job_id, active_only=active_only, limit=limit)

        emit_success(f"Found {len(runs)} run(s)")

        return {
            "success": True,
            "runs": runs,
            "count": len(runs),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_runs(agent: Any) -> Tool:
    """Register the databricks_list_runs tool."""
    return agent.tool(databricks_list_runs)


# ============================================================================
# Databricks Pipeline (Delta Live Tables) Tools
# ============================================================================


def databricks_list_pipelines(
    ctx: RunContext,
    name_filter: Optional[str] = None,
    max_results: int = 25,
) -> dict:
    """List Delta Live Tables pipelines.

    Args:
        ctx: PydanticAI run context
        name_filter: Optional filter by pipeline name
        max_results: Maximum number of results (default: 25)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - pipelines (list): List of pipeline dictionaries
            - count (int): Number of pipelines found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST PIPELINES [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        pipelines = client.list_pipelines(
            name_filter=name_filter, max_results=max_results
        )

        emit_success(f"Found {len(pipelines)} pipeline(s)")

        return {
            "success": True,
            "pipelines": pipelines,
            "count": len(pipelines),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_pipelines(agent: Any) -> Tool:
    """Register the databricks_list_pipelines tool."""
    return agent.tool(databricks_list_pipelines)


def databricks_get_pipeline(ctx: RunContext, pipeline_id: str) -> dict:
    """Get details of a specific Delta Live Tables pipeline.

    Args:
        ctx: PydanticAI run context
        pipeline_id: The pipeline ID

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - pipeline details (various fields)
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS GET PIPELINE [/bold white on blue] "
            f"[bold cyan]{pipeline_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        pipeline = client.get_pipeline(pipeline_id=pipeline_id)

        emit_success(f"Retrieved pipeline: {pipeline.get('name', pipeline_id)}")

        return {
            "success": True,
            **pipeline,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_get_pipeline(agent: Any) -> Tool:
    """Register the databricks_get_pipeline tool."""
    return agent.tool(databricks_get_pipeline)


def databricks_create_pipeline(
    ctx: RunContext,
    name: str,
    notebook_paths: list,
    target_schema: Optional[str] = None,
    catalog: Optional[str] = None,
    continuous: bool = False,
    development: bool = True,
) -> dict:
    """Create a Delta Live Tables pipeline.

    Args:
        ctx: PydanticAI run context
        name: Pipeline name
        notebook_paths: List of notebook paths for the pipeline
        target_schema: Target schema for pipeline tables
        catalog: Unity Catalog name (for UC-enabled pipelines)
        continuous: If True, run in continuous mode (default: False)
        development: If True, run in development mode (default: True)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - pipeline_id (str): Created pipeline ID
            - name (str): Pipeline name
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS CREATE PIPELINE [/bold white on blue] "
            f"[bold cyan]{name}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.create_pipeline(
            name=name,
            notebook_paths=notebook_paths,
            target_schema=target_schema,
            catalog=catalog,
            continuous=continuous,
            development=development,
        )

        emit_success(f"Created pipeline '{name}' with ID: {result['pipeline_id']}")

        return result

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_create_pipeline(agent: Any) -> Tool:
    """Register the databricks_create_pipeline tool."""
    return agent.tool(databricks_create_pipeline)


def databricks_start_pipeline(
    ctx: RunContext,
    pipeline_id: str,
    full_refresh: bool = False,
    wait: bool = False,
    timeout_seconds: int = 3600,
) -> dict:
    """Start a Delta Live Tables pipeline update.

    Args:
        ctx: PydanticAI run context
        pipeline_id: The pipeline ID
        full_refresh: If True, refresh all tables (default: False)
        wait: If True, wait for pipeline to complete (default: False)
        timeout_seconds: Timeout for waiting (default: 3600 = 1 hour)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - update_id (str): The update ID
            - state (str): Pipeline state
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS START PIPELINE [/bold white on blue] "
            f"[bold cyan]{pipeline_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.start_pipeline(
            pipeline_id=pipeline_id,
            full_refresh=full_refresh,
            wait=wait,
            timeout_seconds=timeout_seconds,
        )

        if wait:
            emit_success(f"Pipeline update completed: {result.get('state', 'UNKNOWN')}")
        else:
            emit_success(f"Pipeline update started: Update ID {result['update_id']}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_start_pipeline(agent: Any) -> Tool:
    """Register the databricks_start_pipeline tool."""
    return agent.tool(databricks_start_pipeline)


def databricks_stop_pipeline(ctx: RunContext, pipeline_id: str) -> dict:
    """Stop a running Delta Live Tables pipeline.

    Args:
        ctx: PydanticAI run context
        pipeline_id: The pipeline ID

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - pipeline_id (str): The pipeline ID
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS STOP PIPELINE [/bold white on blue] "
            f"[bold cyan]{pipeline_id}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.stop_pipeline(pipeline_id=pipeline_id)

        emit_success(f"Pipeline stop initiated: {pipeline_id}")

        return result

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_stop_pipeline(agent: Any) -> Tool:
    """Register the databricks_stop_pipeline tool."""
    return agent.tool(databricks_stop_pipeline)


# ============================================================================
# Databricks Cluster / Execution Tools
# ============================================================================


def databricks_list_clusters(ctx: RunContext) -> dict:
    """List all clusters in the Databricks workspace.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - clusters (list): List of cluster dictionaries
            - count (int): Number of clusters found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] DATABRICKS LIST CLUSTERS [/bold white on blue]"
        )
    )

    try:
        client = DatabricksClient()
        clusters = client.list_clusters()

        emit_success(f"Found {len(clusters)} cluster(s)")

        return {
            "success": True,
            "clusters": clusters,
            "count": len(clusters),
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_list_clusters(agent: Any) -> Tool:
    """Register the databricks_list_clusters tool."""
    return agent.tool(databricks_list_clusters)


def databricks_run_notebook(
    ctx: RunContext,
    notebook_path: str,
    cluster_id: str,
    parameters: Optional[dict] = None,
    timeout_seconds: int = 3600,
) -> dict:
    """Run a notebook on a Databricks cluster.

    This creates a one-time job run to execute the notebook and waits for completion.
    Use this for running PySpark code in notebooks.

    Args:
        ctx: PydanticAI run context
        notebook_path: Path to the notebook in the workspace
        cluster_id: Cluster ID to run on (must be running)
        parameters: Optional notebook parameters (dict of key-value pairs)
        timeout_seconds: Timeout for the run (default: 3600 = 1 hour)

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - run_id (int): The run ID
            - state (str): Run state
            - result_state (str): Result state
            - output (str): Notebook output if available
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS RUN NOTEBOOK [/bold white on blue] "
            f"[bold cyan]{notebook_path}[/bold cyan]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.run_notebook(
            notebook_path=notebook_path,
            cluster_id=cluster_id,
            parameters=parameters,
            timeout_seconds=timeout_seconds,
        )

        emit_success(f"Notebook run completed: {result.get('result_state', 'UNKNOWN')}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_run_notebook(agent: Any) -> Tool:
    """Register the databricks_run_notebook tool."""
    return agent.tool(databricks_run_notebook)


def databricks_execute_code(
    ctx: RunContext,
    cluster_id: str,
    code: str,
    language: str = "python",
) -> dict:
    """Execute code directly on a Databricks cluster.

    Note: This only works on all-purpose (interactive) clusters, not job clusters.
    Use this for running quick PySpark code snippets.

    Args:
        ctx: PydanticAI run context
        cluster_id: Cluster ID to execute on (must be running all-purpose cluster)
        code: Code to execute (PySpark, SQL, Scala, or R)
        language: Language - python (default), scala, sql, r

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - output: Command output
            - status (str): Execution status
            - error (str, optional): Error message if operation failed
    """
    code_preview = code[:100] + "..." if len(code) > 100 else code
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] DATABRICKS EXECUTE CODE [/bold white on blue]\n"
            f"[dim]{code_preview}[/dim]"
        )
    )

    try:
        client = DatabricksClient()
        result = client.execute_code(
            cluster_id=cluster_id,
            code=code,
            language=language,
        )

        emit_success(f"Code execution completed: {result.get('status', 'UNKNOWN')}")

        return {
            "success": True,
            **result,
        }

    except Exception as e:
        return _handle_databricks_error(e)


def register_databricks_execute_code(agent: Any) -> Tool:
    """Register the databricks_execute_code tool."""
    return agent.tool(databricks_execute_code)
