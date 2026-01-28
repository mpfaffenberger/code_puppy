"""Power BI Export tools.

Tools for exporting data from Power BI datasets to various formats
like CSV, JSON, and Excel.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.powerbi.common import get_powerbi_client, handle_powerbi_error


# =============================================================================
# EXPORT TOOLS
# =============================================================================


def powerbi_export_table_to_csv(
    ctx: RunContext,
    dataset_id: str,
    table_name: str,
    output_path: str | None = None,
    workspace_id: str | None = None,
    max_rows: int = 10000,
) -> dict:
    """Export a Power BI table to a CSV file.

    Queries the specified table using DAX and exports the results to CSV.

    Args:
        dataset_id: The ID of the dataset containing the table.
        table_name: Name of the table to export.
        output_path: Optional path for the output CSV. If not specified,
            creates a file in the current directory with the table name.
        workspace_id: Optional workspace ID containing the dataset.
        max_rows: Maximum number of rows to export (default: 10000).

    Returns:
        Dict with success status and path to the created file.

    Example:
        powerbi_export_table_to_csv(
            dataset_id="abc123",
            table_name="Sales",
            output_path="./exports/sales.csv"
        )
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📤 [bold cyan]Exporting '{table_name}' to CSV...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        # Query the table data
        rows = client.get_table_data(dataset_id, table_name, workspace_id, max_rows)
        
        if not rows:
            emit_warning(f"Table '{table_name}' is empty or not accessible")
            return {
                "success": True,
                "row_count": 0,
                "message": "Table is empty",
            }
        
        # Generate output path if not specified
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = table_name.replace(" ", "_").replace("/", "_")
            output_path = f"./{safe_name}_{timestamp}.csv"
        
        # Export to CSV
        output_file = client.export_to_csv(rows, output_path)
        
        emit_success(f"Exported {len(rows)} rows to {output_file}")
        
        return {
            "success": True,
            "row_count": len(rows),
            "output_path": str(output_file.absolute()),
            "table_name": table_name,
            "dataset_id": dataset_id,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_export_table_to_csv(agent: Any) -> Tool:
    """Register the powerbi_export_table_to_csv tool."""
    return agent.tool(powerbi_export_table_to_csv)


def powerbi_export_table_to_json(
    ctx: RunContext,
    dataset_id: str,
    table_name: str,
    output_path: str | None = None,
    workspace_id: str | None = None,
    max_rows: int = 10000,
) -> dict:
    """Export a Power BI table to a JSON file.

    Queries the specified table using DAX and exports the results to JSON.

    Args:
        dataset_id: The ID of the dataset containing the table.
        table_name: Name of the table to export.
        output_path: Optional path for the output JSON. If not specified,
            creates a file in the current directory with the table name.
        workspace_id: Optional workspace ID containing the dataset.
        max_rows: Maximum number of rows to export (default: 10000).

    Returns:
        Dict with success status and path to the created file.

    Example:
        powerbi_export_table_to_json(
            dataset_id="abc123",
            table_name="Products",
            output_path="./exports/products.json"
        )
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📤 [bold cyan]Exporting '{table_name}' to JSON...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        # Query the table data
        rows = client.get_table_data(dataset_id, table_name, workspace_id, max_rows)
        
        if not rows:
            emit_warning(f"Table '{table_name}' is empty or not accessible")
            return {
                "success": True,
                "row_count": 0,
                "message": "Table is empty",
            }
        
        # Generate output path if not specified
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = table_name.replace(" ", "_").replace("/", "_")
            output_path = f"./{safe_name}_{timestamp}.json"
        
        # Export to JSON
        output_file = client.export_to_json(rows, output_path)
        
        emit_success(f"Exported {len(rows)} rows to {output_file}")
        
        return {
            "success": True,
            "row_count": len(rows),
            "output_path": str(output_file.absolute()),
            "table_name": table_name,
            "dataset_id": dataset_id,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_export_table_to_json(agent: Any) -> Tool:
    """Register the powerbi_export_table_to_json tool."""
    return agent.tool(powerbi_export_table_to_json)


def powerbi_export_dax_query_to_csv(
    ctx: RunContext,
    dataset_id: str,
    dax_query: str,
    output_path: str,
    workspace_id: str | None = None,
) -> dict:
    """Execute a DAX query and export results to CSV.

    This allows exporting custom aggregations, joins, and transformations.

    Args:
        dataset_id: The ID of the dataset to query.
        dax_query: The DAX query to execute (must start with EVALUATE).
        output_path: Path for the output CSV file.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with success status and path to the created file.

    Example:
        powerbi_export_dax_query_to_csv(
            dataset_id="abc123",
            dax_query="
                EVALUATE
                SUMMARIZE(
                    'Sales',
                    'Sales'[Region],
                    \"TotalSales\", SUM('Sales'[Amount])
                )
            ",
            output_path="./sales_by_region.csv"
        )
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📤 [bold cyan]Executing DAX and exporting to CSV...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        
        # Execute the DAX query
        result = client.execute_dax_query(dataset_id, dax_query, workspace_id)
        
        # Extract and clean rows
        rows = []
        if "results" in result:
            raw_rows = result["results"][0]["tables"][0].get("rows", [])
            for row in raw_rows:
                clean_row = {}
                for key, value in row.items():
                    # Clean column names
                    clean_key = key.strip("[]").split("[")[-1].strip("]")
                    clean_row[clean_key] = value
                rows.append(clean_row)
        
        if not rows:
            emit_warning("Query returned no results")
            return {
                "success": True,
                "row_count": 0,
                "message": "Query returned no results",
            }
        
        # Export to CSV
        output_file = client.export_to_csv(rows, output_path)
        
        emit_success(f"Exported {len(rows)} rows to {output_file}")
        
        return {
            "success": True,
            "row_count": len(rows),
            "output_path": str(output_file.absolute()),
            "dataset_id": dataset_id,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_export_dax_query_to_csv(agent: Any) -> Tool:
    """Register the powerbi_export_dax_query_to_csv tool."""
    return agent.tool(powerbi_export_dax_query_to_csv)
