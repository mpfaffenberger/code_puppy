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
from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_success, emit_warning
from code_puppy.plugins.walmart_specific.bigquery_client import (
    BigQueryAPIError,
    BigQueryAccessDeniedError,
    BigQueryAuthError,
    BigQueryClient,
    BigQueryError,
    BigQueryNotFoundError,
)

RESULTS_DIR_NAME = "bigquery_results"
DEFAULT_PREVIEW_ROWS = 5  # Only show 5 rows to agent to minimize token usage
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


def _extract_table_from_error(error_str: str) -> str | None:
    """Extract a fully-qualified table name from a BQ error message.

    Handles both backtick-quoted (`project.dataset.table`) and plain
    'project:dataset.table' formats found in GCP error strings.
    """
    import re

    m = re.search(r"`([^`]+\.[^`]+\.[^`]+)`", error_str)
    if m:
        return m.group(1)
    m = re.search(r"(\S+:\S+\.\S+)", error_str)
    if m:
        return m.group(1).rstrip(".;,")
    return None


def _handle_bigquery_error(e: Exception) -> dict:
    """Convert BigQuery exceptions to structured error responses.

    Args:
        e: Exception raised by BigQuery client

    Returns:
        Dict with success=False and error details
    """
    if isinstance(e, BigQueryAccessDeniedError):
        table = _extract_table_from_error(str(e))
        table_display = f"`{table}`" if table else "this table"
        emit_warning(f"🔒 Access denied to {table_display}")
        return {
            "success": False,
            "error_type": "access_denied",
            "error": f"You don't have access to {table_display}.",
            "suggestion": (
                "Would you like help requesting access, "
                "or should I find a table you DO have access to?"
            ),
            "table": table,
        }
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
    emit_info(
        Text.from_markup(
            "\n[bold white on blue] BIGQUERY LIST PROJECTS [/bold white on blue] 📊"
        )
    )

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
        Text.from_markup(
            "\n[bold white on blue] BIGQUERY LIST ALL PROJECTS [/bold white on blue] 🌐"
        )
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
        Text.from_markup(
            f"\n[bold white on blue] BIGQUERY LIST DATASETS [/bold white on blue] 📂 [bold cyan]{project_display}[/bold cyan]"
        )
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
        Text.from_markup(
            f"\n[bold white on blue] BIGQUERY LIST TABLES [/bold white on blue] 📋 "
            f"[bold cyan]{project_display}.{dataset_id}[/bold cyan]"
        )
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
    save_to_file: bool = True,
    output_path: str | None = None,
    file_name_hint: str | None = None,
    output_format: str = "csv",
) -> dict:
    """Execute a SQL query in BigQuery.

    SAFETY: Only SELECT queries are allowed. Destructive operations (DELETE, DROP,
    TRUNCATE, INSERT, UPDATE, MERGE, ALTER, CREATE, REPLACE) are blocked.

    Only 5 preview rows are returned inline to minimize token usage. Results are saved
    to a CSV file by default. Set save_to_file=False for exploratory/intermediate queries.

    Args:
        ctx: PydanticAI run context
        query: SQL query string to execute (SELECT only)
        max_results: Maximum number of results to return (default: 100)
        save_to_file: Whether to save full results to a file (default: True)
        output_path: Optional explicit output path (file or directory) for saved results
        file_name_hint: Optional friendly name used when generating filenames
        output_format: File format for saved results ("csv" or "json", default: csv)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - total_rows (int): Total number of rows in result
            - preview_rows (list): First 5 rows as preview for quick context
            - saved_file_path (str | None): Path to saved file (when save_to_file=True)
            - schema (list): List of field definitions
            - job_id (str): BigQuery job ID
            - bytes_processed (int): Bytes processed by the query
            - bytes_billed (int): Bytes billed for the query
            - error (str, optional): Error message if query failed
    """
    # Truncate query for display
    query_preview = query[:100] + "..." if len(query) > 100 else query
    emit_info(
        Text.from_markup(
            f"\n[bold white on blue] BIGQUERY EXECUTE QUERY [/bold white on blue] 🔍\n"
            f"[dim]{query_preview}[/dim]"
        )
    )

    try:
        client = BigQueryClient()
        result = client.execute_query(query=query, max_results=max_results)

        rows = result.get("rows", [])
        total_rows = result["total_rows"]
        preview_rows_data = rows[:DEFAULT_PREVIEW_ROWS]  # Always limit to 5 rows
        saved_file_path: str | None = None

        emit_success(
            f"Query completed: {total_rows} total rows, "
            f"returned {len(rows)} rows\n"
            f"Bytes processed: {result['bytes_processed']:,}\n"
            f"Job ID: {result['job_id']}"
        )

        # Only save results to file when save_to_file=True
        if save_to_file and rows:
            saved_format = _normalize_output_format(output_format)
            try:
                output_file = _resolve_output_path(
                    output_path, result["job_id"], file_name_hint, saved_format
                )
                _write_results_to_file(
                    rows, result["schema"], output_file, saved_format
                )
                saved_file_path = str(output_file)
                emit_success(f"Saved {len(rows)} row(s) to {saved_file_path}")
            except Exception as file_error:
                emit_warning(f"Failed to save query results to file: {file_error}")
                # Return error but include preview rows for context
                return {
                    "success": True,
                    "total_rows": total_rows,
                    "saved_file_path": None,
                    "save_error": str(file_error),
                    "preview_rows": preview_rows_data,
                    "schema": result["schema"],
                    "job_id": result["job_id"],
                    "bytes_processed": result["bytes_processed"],
                    "bytes_billed": result["bytes_billed"],
                }

        return {
            "success": True,
            "total_rows": total_rows,
            "saved_file_path": saved_file_path,
            "preview_rows": preview_rows_data,
            "schema": result["schema"],
            "job_id": result["job_id"],
            "bytes_processed": result["bytes_processed"],
            "bytes_billed": result["bytes_billed"],
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
        Text.from_markup(
            f"\n[bold white on blue] BIGQUERY GET TABLE SCHEMA [/bold white on blue] 📐 "
            f"[bold cyan]{project_display}.{dataset_id}.{table_id}[/bold cyan]"
        )
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
    """Search for tables by name pattern across projects.

    Uses INFORMATION_SCHEMA to find tables matching a pattern. Supports SQL
    LIKE wildcards: % (any characters) and _ (single character).

    When project_id is None, searches ALL accessible projects individually,
    skipping projects with permission errors.

    Args:
        ctx: PydanticAI run context
        search_pattern: Pattern to search for (e.g., "user%", "%orders%", "sales_2024%")
        project_id: Optional GCP project ID. If None, searches ALL accessible projects.
        dataset_filter: Optional dataset ID to limit search to a specific dataset.
        max_results: Maximum number of results to return (default: 100)

    Returns:
        Dict containing:
            - success (bool): Whether the search succeeded
            - tables (list): List of matching tables with full_id, dataset, table_name, type
            - count (int): Number of tables found
            - projects_searched (int): Number of projects successfully searched
            - projects_skipped (int): Number of projects skipped due to errors
            - search_pattern (str): The pattern used
            - error (str, optional): Error message if search failed
    """
    try:
        # Use default project for job execution (where user has bigquery.jobs.create)
        client = BigQueryClient()

        # Determine which projects to search
        if project_id:
            projects_to_search = [project_id]
            emit_info(
                f"\n[bold white on blue] BIGQUERY SEARCH TABLES [/bold white on blue] 🔍 "
                f"[bold cyan]'{search_pattern}'[/bold cyan] in [bold cyan]{project_id}[/bold cyan]"
            )
        else:
            # Global search: get all accessible projects
            emit_info(
                f"\n[bold white on blue] BIGQUERY SEARCH TABLES [/bold white on blue] 🔍 "
                f"[bold cyan]'{search_pattern}'[/bold cyan] in [bold cyan]all projects[/bold cyan]"
            )
            emit_info("🌐 Fetching accessible projects...")
            all_projects = client.list_all_projects()
            projects_to_search = [p["project_id"] for p in all_projects]
            emit_info(f"📋 Searching {len(projects_to_search)} project(s)...")

        from google.cloud import bigquery as bq

        job_config = bq.QueryJobConfig(
            query_parameters=[
                bq.ScalarQueryParameter("pattern", "STRING", search_pattern)
            ]
        )

        all_tables: list[dict] = []
        projects_searched = 0
        projects_skipped = 0

        # Query each project individually to handle permission errors gracefully
        for target_project in projects_to_search:
            if len(all_tables) >= max_results:
                break

            schema = dataset_filter if dataset_filter else "region-us"
            query = f"""
                SELECT
                    table_catalog AS project_id,
                    table_schema AS dataset_id,
                    table_name,
                    table_type,
                    CONCAT(table_catalog, '.', table_schema, '.', table_name) AS full_id
                FROM `{target_project}.{schema}.INFORMATION_SCHEMA.TABLES`
                WHERE LOWER(table_name) LIKE LOWER(@pattern)
                ORDER BY table_schema, table_name
                LIMIT {max_results}
            """

            try:
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

                projects_searched += 1
                if tables:
                    all_tables.extend(tables)
                    for table in tables:
                        emit_info(f"  ✓ {table['full_id']}")

            except Exception:
                # Skip projects with permission errors silently
                projects_skipped += 1

        # Limit total results
        all_tables = all_tables[:max_results]

        if all_tables:
            emit_success(
                f"Found {len(all_tables)} table(s) matching '{search_pattern}' "
                f"({projects_searched} projects searched, {projects_skipped} skipped due to access restrictions)"
            )
        else:
            emit_warning(f"No tables found matching '{search_pattern}'")
            if projects_skipped > 0:
                emit_info(
                    f"💡 {projects_skipped} project(s) were skipped due to access restrictions"
                )
            if not dataset_filter:
                emit_info(
                    "💡 Tip: If your data is in a different region (not US), "
                    "specify dataset_filter to search within a specific dataset."
                )

        return {
            "success": True,
            "tables": all_tables,
            "count": len(all_tables),
            "projects_searched": projects_searched,
            "projects_skipped": projects_skipped,
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
