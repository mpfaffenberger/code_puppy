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
