"""BigQuery integration tools.

Provides tools for exploring and querying Google BigQuery databases,
including listing projects, datasets, tables, and executing queries.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.bigquery_client import (
    BigQueryAPIError,
    BigQueryAuthError,
    BigQueryClient,
    BigQueryError,
    BigQueryNotFoundError,
)

RESULTS_DIR_NAME = "bigquery_results"
DEFAULT_PREVIEW_ROWS = 50
AUTO_SAVE_ROW_THRESHOLD = 200
VALID_OUTPUT_FORMATS = {"csv", "json"}


# ============================================================================
# Helper Functions
# ============================================================================


def get_bigquery_client(project_id: str | None = None) -> BigQueryClient:
    """Get a BigQuery client instance.

    Args:
        project_id: Optional GCP project ID

    Returns:
        BigQueryClient: A configured BigQuery client
    """
    return BigQueryClient(project_id=project_id)


def _handle_bigquery_error(e: Exception) -> dict:
    """Convert BigQuery exceptions to structured error responses.

    Args:
        e: Exception raised by BigQuery client

    Returns:
        Dict with success=False and error details
    """
    if isinstance(e, BigQueryAuthError):
        error_msg = f"Authentication failed: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "authentication",
        }
    elif isinstance(e, BigQueryNotFoundError):
        error_msg = f"Resource not found: {str(e)}"
        emit_warning(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "not_found",
        }
    elif isinstance(e, BigQueryAPIError):
        error_msg = f"API error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "api_error",
        }
    elif isinstance(e, BigQueryError):
        error_msg = f"BigQuery error: {str(e)}"
        emit_error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "bigquery",
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
    file_name_hint: str | None, job_id: str, output_format: str
) -> str:
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    slug_source = file_name_hint or f"query-{job_id}"
    slug = _slugify_filename(slug_source)
    return f"{slug}-{timestamp}.{output_format}"


def _resolve_output_path(
    output_path: str | None,
    job_id: str,
    file_name_hint: str | None,
    output_format: str,
) -> Path:
    """Determine where query results should be written."""
    fmt_suffix = f".{output_format}"

    if output_path:
        path = Path(output_path).expanduser()
        if path.is_dir():
            filename = _generate_default_filename(file_name_hint, job_id, output_format)
            path = path / filename
        elif not path.suffix:
            path = path.with_suffix(fmt_suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    results_dir = Path.cwd() / RESULTS_DIR_NAME
    results_dir.mkdir(parents=True, exist_ok=True)
    filename = _generate_default_filename(file_name_hint, job_id, output_format)
    return results_dir / filename


def _write_results_to_file(
    rows: list[dict[str, Any]],
    schema: list[dict[str, Any]],
    output_file: Path,
    output_format: str,
) -> None:
    """Persist query rows to disk in CSV or JSON format."""
    if output_format not in VALID_OUTPUT_FORMATS:
        raise BigQueryAPIError(
            f"Unsupported output format '{output_format}'. "
            f"Supported formats: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
        )

    fieldnames = [field["name"] for field in schema if "name" in field]
    if not fieldnames and rows:
        fieldnames = list(rows[0].keys())

    if output_format == "csv":
        derived_fieldnames = fieldnames or (sorted(rows[0].keys()) if rows else [])
        if not derived_fieldnames:
            raise BigQueryAPIError(
                "Unable to determine field names for CSV export. "
                "Please provide schema information or non-empty rows."
            )
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
        raise BigQueryAPIError(
            f"Invalid output format '{output_format}'. "
            f"Supported formats: {', '.join(sorted(VALID_OUTPUT_FORMATS))}"
        )
    return fmt


# ============================================================================
# BigQuery List Projects Tool
# ============================================================================


def bigquery_get_default_project(ctx: RunContext) -> dict:
    """Get the default GCP project.

    Note: This returns your default/current project. To work with other projects,
    specify the project_id parameter in other commands.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - projects (list): List with default project info
            - count (int): Always 1 (default project)
            - error (str, optional): Error message if operation failed
    """
    emit_info("\n[bold white on blue] BIGQUERY LIST PROJECTS [/bold white on blue] 📊")

    try:
        client = BigQueryClient()
        projects = client.list_projects()

        emit_success(f"Default project: {client.project_id}")
        emit_info(
            "💡 To work with other projects, specify project_id in dataset/table commands."
        )

        return {
            "success": True,
            "projects": projects,
            "count": len(projects),
            "default_project": client.project_id,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_get_default_project(agent: Any) -> Tool:
    """Register the bigquery_get_default_project tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_get_default_project)


# ============================================================================
# BigQuery List All Projects Tool
# ============================================================================


def bigquery_list_all_projects(ctx: RunContext) -> dict:
    """List all accessible GCP projects using gcloud CLI.

    Uses `gcloud projects list` command - reliable and works without API setup.

    Args:
        ctx: PydanticAI run context

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - projects (list): List of all accessible projects
            - count (int): Number of projects found
            - error (str, optional): Error message if operation failed
    """
    emit_info(
        "\n[bold white on blue] BIGQUERY LIST ALL PROJECTS [/bold white on blue] 🌐"
    )

    try:
        client = BigQueryClient()
        projects = client.list_all_projects()

        emit_success(f"Found {len(projects)} accessible project(s)")

        return {
            "success": True,
            "projects": projects,
            "count": len(projects),
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_list_all_projects(agent: Any) -> Tool:
    """Register the bigquery_list_all_projects tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_list_all_projects)


# ============================================================================
# BigQuery List Datasets Tool
# ============================================================================


def bigquery_list_datasets(ctx: RunContext, project_id: str | None = None) -> dict:
    """List all datasets in a GCP project.

    Args:
        ctx: PydanticAI run context
        project_id: Optional GCP project ID. If None, uses default project.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - datasets (list): List of dataset dictionaries
            - count (int): Number of datasets found
            - project_id (str): The project ID used
            - error (str, optional): Error message if operation failed
    """
    project_display = project_id or "default"
    emit_info(
        f"\n[bold white on blue] BIGQUERY LIST DATASETS [/bold white on blue] 📂 [bold cyan]{project_display}[/bold cyan]"
    )

    try:
        client = BigQueryClient(project_id=project_id)
        datasets = client.list_datasets(project_id=project_id)

        emit_success(
            f"Found {len(datasets)} dataset(s) in project '{client.project_id}'"
        )

        return {
            "success": True,
            "datasets": datasets,
            "count": len(datasets),
            "project_id": client.project_id,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_list_datasets(agent: Any) -> Tool:
    """Register the bigquery_list_datasets tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_list_datasets)


# ============================================================================
# BigQuery List Tables Tool
# ============================================================================


def bigquery_list_tables(
    ctx: RunContext, dataset_id: str, project_id: str | None = None
) -> dict:
    """List all tables in a BigQuery dataset.

    Args:
        ctx: PydanticAI run context
        dataset_id: Dataset ID to list tables from
        project_id: Optional GCP project ID. If None, uses default project.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - tables (list): List of table dictionaries
            - count (int): Number of tables found
            - dataset_id (str): The dataset ID used
            - project_id (str): The project ID used
            - error (str, optional): Error message if operation failed
    """
    project_display = project_id or "default"
    emit_info(
        f"\n[bold white on blue] BIGQUERY LIST TABLES [/bold white on blue] 📋 "
        f"[bold cyan]{project_display}.{dataset_id}[/bold cyan]"
    )

    try:
        client = BigQueryClient(project_id=project_id)
        tables = client.list_tables(dataset_id=dataset_id, project_id=project_id)

        emit_success(
            f"Found {len(tables)} table(s) in '{client.project_id}.{dataset_id}'"
        )

        return {
            "success": True,
            "tables": tables,
            "count": len(tables),
            "dataset_id": dataset_id,
            "project_id": client.project_id,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_list_tables(agent: Any) -> Tool:
    """Register the bigquery_list_tables tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_list_tables)


# ============================================================================
# BigQuery Execute Query Tool
# ============================================================================


def bigquery_execute_query(
    ctx: RunContext,
    query: str,
    max_results: int = 100,
    save_results: bool | None = None,
    output_path: str | None = None,
    file_name_hint: str | None = None,
    output_format: str = "csv",
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
) -> dict:
    """Execute a SQL query in BigQuery.

    SAFETY: Only SELECT queries are allowed. Destructive operations (DELETE, DROP,
    TRUNCATE, INSERT, UPDATE, MERGE, ALTER, CREATE, REPLACE) are blocked.

    Args:
        ctx: PydanticAI run context
        query: SQL query string to execute (SELECT only)
        max_results: Maximum number of results to return (default: 100)
        save_results: Force saving the full result set to disk (default: automatic)
        output_path: Explicit output path (file or directory) for saved results
        file_name_hint: Friendly name used when generating filenames
        output_format: File format for saved results ("csv" or "json")
        preview_rows: Number of rows returned inline for reasoning (default: 50)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - rows (list): Inline preview rows (capped by preview_rows)
            - schema (list): List of field definitions
            - total_rows (int): Total number of rows in result
            - job_id (str): BigQuery job ID
            - bytes_processed (int): Bytes processed by the query
            - bytes_billed (int): Bytes billed for the query
            - rows_truncated (bool): True if inline rows were truncated
            - saved_file_path (str | None): Path to saved results when available
            - rows_saved_to_file (int): Number of rows persisted to disk
            - error (str, optional): Error message if query failed
    """
    # Truncate query for display
    query_preview = query[:100] + "..." if len(query) > 100 else query
    emit_info(
        f"\n[bold white on blue] BIGQUERY EXECUTE QUERY [/bold white on blue] 🔍\n"
        f"[dim]{query_preview}[/dim]"
    )

    try:
        client = BigQueryClient()
        result = client.execute_query(query=query, max_results=max_results)

        rows = result.get("rows", [])
        preview_limit = max(1, preview_rows or DEFAULT_PREVIEW_ROWS)
        inline_rows = rows[:preview_limit]
        rows_were_truncated = len(rows) > preview_limit
        saved_file_path: str | None = None
        rows_saved = 0
        auto_saved = False
        saved_format: str | None = None

        emit_success(
            f"Query completed: {result['total_rows']} total rows, "
            f"returned {len(rows)} rows\n"
            f"Bytes processed: {result['bytes_processed']:,}\n"
            f"Job ID: {result['job_id']}"
        )

        explicit_save_requested = bool(
            save_results or output_path is not None or file_name_hint is not None
        )
        should_save = explicit_save_requested or len(rows) > AUTO_SAVE_ROW_THRESHOLD

        if should_save:
            saved_format = _normalize_output_format(output_format)
            try:
                output_file = _resolve_output_path(
                    output_path, result["job_id"], file_name_hint, saved_format
                )
                _write_results_to_file(
                    rows, result["schema"], output_file, saved_format
                )
                saved_file_path = str(output_file)
                rows_saved = len(rows)
                auto_saved = (
                    not explicit_save_requested and len(rows) > AUTO_SAVE_ROW_THRESHOLD
                )
                emit_success(
                    f"Saved {rows_saved} row(s) to {saved_file_path}"
                    + (" (auto-saved due to large result set)" if auto_saved else "")
                )
            except Exception as file_error:
                emit_warning(f"Failed to save query results to file: {file_error}")
                inline_rows = rows
                rows_were_truncated = False

        if rows_were_truncated and saved_file_path:
            emit_info(
                "Inline results truncated to manage token usage. "
                f"Full results are available at: {saved_file_path}"
            )
        elif rows_were_truncated:
            emit_warning(
                "Inline results truncated but no file was saved. "
                "Re-run with save_results=True or provide output_path to persist data."
            )

        return {
            "success": True,
            "rows": inline_rows,
            "schema": result["schema"],
            "total_rows": result["total_rows"],
            "job_id": result["job_id"],
            "bytes_processed": result["bytes_processed"],
            "bytes_billed": result["bytes_billed"],
            "rows_returned": len(inline_rows),
            "rows_truncated": rows_were_truncated,
            "rows_saved_to_file": rows_saved,
            "saved_file_path": saved_file_path,
            "saved_file_format": saved_format,
            "auto_saved_result_file": auto_saved,
            "preview_row_limit": preview_limit,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_execute_query(agent: Any) -> Tool:
    """Register the bigquery_execute_query tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_execute_query)


# ============================================================================
# BigQuery Get Table Schema Tool
# ============================================================================


def bigquery_get_table_schema(
    ctx: RunContext,
    table_id: str,
    dataset_id: str,
    project_id: str | None = None,
) -> dict:
    """Get the schema for a specific BigQuery table.

    Args:
        ctx: PydanticAI run context
        table_id: Table ID
        dataset_id: Dataset ID
        project_id: Optional GCP project ID. If None, uses default project.

    Returns:
        Dict containing:
            - success (bool): Whether the operation succeeded
            - schema (list): List of field dictionaries
            - table_id (str): The table ID
            - dataset_id (str): The dataset ID
            - project_id (str): The project ID
            - error (str, optional): Error message if operation failed
    """
    project_display = project_id or "default"
    emit_info(
        f"\n[bold white on blue] BIGQUERY GET TABLE SCHEMA [/bold white on blue] 📐 "
        f"[bold cyan]{project_display}.{dataset_id}.{table_id}[/bold cyan]"
    )

    try:
        client = BigQueryClient(project_id=project_id)
        schema = client.get_table_schema(
            table_id=table_id, dataset_id=dataset_id, project_id=project_id
        )

        emit_success(f"Retrieved schema with {len(schema)} field(s)")

        return {
            "success": True,
            "schema": schema,
            "table_id": table_id,
            "dataset_id": dataset_id,
            "project_id": client.project_id,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_get_table_schema(agent: Any) -> Tool:
    """Register the bigquery_get_table_schema tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_get_table_schema)


# ============================================================================
# BigQuery Search Tables Tool
# ============================================================================


def bigquery_search_tables(
    ctx: RunContext,
    search_pattern: str,
    project_id: str | None = None,
    dataset_filter: str | None = None,
    max_results: int = 100,
) -> dict:
    """Search for tables by name pattern across datasets in a project.

    Uses INFORMATION_SCHEMA to find tables matching a pattern. Supports SQL
    LIKE wildcards: % (any characters) and _ (single character).

    Args:
        ctx: PydanticAI run context
        search_pattern: Pattern to search for (e.g., "user%", "%orders%", "sales_2024%")
        project_id: Optional GCP project ID. If None, uses default project.
        dataset_filter: Optional dataset ID to limit search to a specific dataset.
        max_results: Maximum number of results to return (default: 100)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - tables (list): List of matching tables with full_id, dataset, table_name, type
            - count (int): Number of tables found
            - project_id (str): The project ID searched
            - search_pattern (str): The pattern used
            - error (str, optional): Error message if search failed
    """
    project_display = project_id or "default"
    emit_info(
        f"\n[bold white on blue] BIGQUERY SEARCH TABLES [/bold white on blue] 🔍 "
        f"[bold cyan]'{search_pattern}'[/bold cyan] in [bold cyan]{project_display}[/bold cyan]"
    )

    try:
        # Use default project for job execution (where user has bigquery.jobs.create)
        client = BigQueryClient()
        # Target project for INFORMATION_SCHEMA query (can differ from job project)
        target_project = project_id or client.project_id

        # Build query using INFORMATION_SCHEMA
        # Query across all datasets using region-scoped INFORMATION_SCHEMA
        if dataset_filter:
            # Search within a specific dataset
            query = f"""
                SELECT
                    table_catalog AS project_id,
                    table_schema AS dataset_id,
                    table_name,
                    table_type,
                    CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_id
                FROM `{target_project}.{dataset_filter}.INFORMATION_SCHEMA.TABLES`
                WHERE LOWER(table_name) LIKE LOWER(@pattern)
                ORDER BY table_schema, table_name
                LIMIT {max_results}
            """
        else:
            # Search across all datasets using region-US INFORMATION_SCHEMA
            # Note: This works for US region. For multi-region, users can specify dataset.
            query = f"""
                SELECT
                    table_catalog AS project_id,
                    table_schema AS dataset_id,
                    table_name,
                    table_type,
                    CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_id
                FROM `{target_project}.region-us.INFORMATION_SCHEMA.TABLES`
                WHERE LOWER(table_name) LIKE LOWER(@pattern)
                ORDER BY table_schema, table_name
                LIMIT {max_results}
            """

        # Execute with parameterized query for safety
        from google.cloud import bigquery as bq

        job_config = bq.QueryJobConfig(
            query_parameters=[
                bq.ScalarQueryParameter("pattern", "STRING", search_pattern)
            ]
        )

        query_job = client._client.query(query, job_config=job_config)
        results = query_job.result()

        tables = [
            {
                "full_id": row.full_id,
                "project_id": row.project_id,
                "dataset_id": row.dataset_id,
                "table_name": row.table_name,
                "table_type": row.table_type,
            }
            for row in results
        ]

        if tables:
            emit_success(f"Found {len(tables)} table(s) matching '{search_pattern}'")
        else:
            emit_warning(f"No tables found matching '{search_pattern}'")
            if not dataset_filter:
                emit_info(
                    "💡 Tip: If your data is in a different region (not US), "
                    "specify dataset_filter to search within a specific dataset."
                )

        return {
            "success": True,
            "tables": tables,
            "count": len(tables),
            "project_id": target_project,
            "search_pattern": search_pattern,
            "dataset_filter": dataset_filter,
        }

    except Exception as e:
        return _handle_bigquery_error(e)


def register_bigquery_search_tables(agent: Any) -> Tool:
    """Register the bigquery_search_tables tool with a PydanticAI agent.

    Args:
        agent: PydanticAI agent instance

    Returns:
        The registered Tool instance
    """
    return agent.tool(bigquery_search_tables)
