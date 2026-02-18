"""Power BI Dataset tools.

Datasets are the data models that power reports. They can be queried
using DAX (Data Analysis Expressions) to extract data.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool
from rich.text import Text

from code_puppy.messaging import emit_info, emit_success, emit_warning
from code_puppy.tools.powerbi.common import get_powerbi_client, handle_powerbi_error


# =============================================================================
# DATASET LIST/GET TOOLS
# =============================================================================


def powerbi_list_datasets(
    ctx: RunContext,
    workspace_id: str | None = None,
    top: int = 100,
    skip: int = 0,
) -> dict:
    """List Power BI datasets.

    Supports pagination via top/skip parameters. Check 'has_more' in the response
    to determine if additional pages exist, and use 'next_skip' for the next request.

    Args:
        workspace_id: Optional workspace ID. If not specified, lists datasets
            from "My Workspace".
        top: Maximum number of datasets to return (default: 100).
        skip: Number of datasets to skip for pagination (default: 0).

    Returns:
        Dict with success=True and list of datasets, plus pagination metadata:
        - count: Number of datasets returned in this page
        - datasets: List of dataset objects
        - has_more: True if there may be more results (returned count == top)
        - next_skip: The skip value to use for the next page (if has_more is True)
        - top_used: The top value used for this request
        - skip_used: The skip value used for this request

    Example:
        # List first page of datasets in My Workspace
        powerbi_list_datasets()

        # Get next page
        powerbi_list_datasets(skip=100)

        # List datasets in a specific workspace
        powerbi_list_datasets(workspace_id="abc-123-def")
    """
    workspace_label = (
        f"workspace {workspace_id[:8]}..." if workspace_id else "My Workspace"
    )

    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"🗃️ [bold cyan]Listing datasets in {workspace_label}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets"
        else:
            endpoint = "/datasets"

        response = client.get(endpoint, params={"$top": top, "$skip": skip})
        datasets = response.get("value", [])

        # Determine if there are more results
        has_more = len(datasets) == top
        next_skip = skip + len(datasets) if has_more else None

        emit_success(
            f"Found {len(datasets)} datasets (skip={skip}, has_more={has_more})"
        )

        formatted = []
        for ds in datasets:
            formatted.append(
                {
                    "id": ds.get("id"),
                    "name": ds.get("name"),
                    "configured_by": ds.get("configuredBy"),
                    "is_refreshable": ds.get("isRefreshable", False),
                    "web_url": ds.get("webUrl"),
                    "created_date": ds.get("createdDate"),
                }
            )

        return {
            "success": True,
            "count": len(formatted),
            "workspace_id": workspace_id,
            "datasets": formatted,
            # Pagination metadata
            "has_more": has_more,
            "next_skip": next_skip,
            "top_used": top,
            "skip_used": skip,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_list_datasets(agent: Any) -> Tool:
    """Register the powerbi_list_datasets tool."""
    return agent.tool(powerbi_list_datasets)


def powerbi_get_dataset(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get details of a specific Power BI dataset.

    Args:
        dataset_id: The ID of the dataset to retrieve.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with dataset details or error.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"🗃️ [bold cyan]Getting dataset: {dataset_id[:8]}...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}"
        else:
            endpoint = f"/datasets/{dataset_id}"

        response = client.get(endpoint)

        emit_success(f"Got dataset: {response.get('name', 'Unknown')}")

        return {
            "success": True,
            "dataset": {
                "id": response.get("id"),
                "name": response.get("name"),
                "configured_by": response.get("configuredBy"),
                "is_refreshable": response.get("isRefreshable", False),
                "web_url": response.get("webUrl"),
                "created_date": response.get("createdDate"),
                "content_provider_type": response.get("contentProviderType"),
                "is_on_prem_gateway_required": response.get("isOnPremGatewayRequired"),
                "target_storage_mode": response.get("targetStorageMode"),
            },
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_dataset(agent: Any) -> Tool:
    """Register the powerbi_get_dataset tool."""
    return agent.tool(powerbi_get_dataset)


# =============================================================================
# DATASET SCHEMA/TABLES TOOLS
# =============================================================================


def powerbi_get_dataset_tables(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get the tables in a Power BI dataset using DAX.

    Uses DAX INFO.TABLES() to retrieve table metadata from the dataset.

    Args:
        dataset_id: The ID of the dataset.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with list of tables and their properties.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "📝 [bold cyan]Getting dataset tables...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        # Use DAX INFO.TABLES() to get table metadata
        dax_query = "EVALUATE INFO.TABLES()"
        result = client.execute_dax_query(dataset_id, dax_query, workspace_id)

        tables = []
        if "results" in result:
            raw_rows = result["results"][0]["tables"][0].get("rows", [])
            for row in raw_rows:
                # Extract table info - skip internal tables
                table_id = row.get("[ID]")
                name = row.get("[Name]", "")
                is_hidden = row.get("[IsHidden]", False)

                # Skip system tables (usually negative IDs or $ prefix)
                if table_id and table_id >= 0 and not name.startswith("$"):
                    tables.append(
                        {
                            "id": table_id,
                            "name": name,
                            "is_hidden": is_hidden,
                            "description": row.get("[Description]", ""),
                        }
                    )

        emit_success(f"Found {len(tables)} tables")

        return {
            "success": True,
            "count": len(tables),
            "dataset_id": dataset_id,
            "tables": tables,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_dataset_tables(agent: Any) -> Tool:
    """Register the powerbi_get_dataset_tables tool."""
    return agent.tool(powerbi_get_dataset_tables)


def powerbi_get_table_columns(
    ctx: RunContext,
    dataset_id: str,
    table_name: str,
    workspace_id: str | None = None,
) -> dict:
    """Get columns in a specific table using DAX INFO.COLUMNS().

    Args:
        dataset_id: The ID of the dataset.
        table_name: Name of the table to get columns for.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with list of columns and their properties.
    """
    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📊 [bold cyan]Getting columns for table '{table_name}'...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        # Get columns and filter by table
        dax_query = """
        EVALUATE 
        FILTER(
            INFO.COLUMNS(),
            [ExplicitName] <> BLANK()
        )
        """
        result = client.execute_dax_query(dataset_id, dax_query, workspace_id)

        columns = []
        if "results" in result:
            raw_rows = result["results"][0]["tables"][0].get("rows", [])
            for row in raw_rows:
                # Get column info
                col_name = row.get("[ExplicitName]") or row.get("[InferredName]")
                if col_name:
                    columns.append(
                        {
                            "name": col_name,
                            "table_id": row.get("[TableID]"),
                            "data_type": row.get("[ExplicitDataType]"),
                            "is_hidden": row.get("[IsHidden]", False),
                        }
                    )

        emit_success(f"Found {len(columns)} columns")

        return {
            "success": True,
            "count": len(columns),
            "table_name": table_name,
            "columns": columns,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_table_columns(agent: Any) -> Tool:
    """Register the powerbi_get_table_columns tool."""
    return agent.tool(powerbi_get_table_columns)


# =============================================================================
# DAX QUERY TOOLS
# =============================================================================


def powerbi_execute_dax_query(
    ctx: RunContext,
    dataset_id: str,
    dax_query: str,
    workspace_id: str | None = None,
) -> dict:
    """Execute a DAX query against a Power BI dataset.

    DAX (Data Analysis Expressions) is a formula language used in Power BI
    to query and analyze data.

    Args:
        dataset_id: The ID of the dataset to query.
        dax_query: The DAX query to execute. Must start with EVALUATE.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with query results (tables and rows) or error.

    Examples:
        # Get top 10 rows from a table
        powerbi_execute_dax_query(
            dataset_id="abc123",
            dax_query="EVALUATE TOPN(10, 'Sales')"
        )

        # Aggregate data
        powerbi_execute_dax_query(
            dataset_id="abc123",
            dax_query="
                EVALUATE
                SUMMARIZE(
                    'Sales',
                    'Sales'[Category],
                    \"Total\", SUM('Sales'[Amount])
                )
            "
        )
    """
    # Validate query starts with EVALUATE
    query_upper = dax_query.strip().upper()
    if not query_upper.startswith("EVALUATE"):
        emit_warning("DAX query should start with EVALUATE")

    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "⚡ [bold cyan]Executing DAX query...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()
        result = client.execute_dax_query(dataset_id, dax_query, workspace_id)

        # Parse and clean up the results
        tables = []
        total_rows = 0

        if "results" in result:
            for query_result in result["results"]:
                for table in query_result.get("tables", []):
                    rows = table.get("rows", [])
                    total_rows += len(rows)

                    # Clean up column names in each row
                    clean_rows = []
                    for row in rows:
                        clean_row = {}
                        for key, value in row.items():
                            # Remove brackets from column names
                            clean_key = key.strip("[]")
                            # Also remove table prefix like "Table[Column]"
                            if "[" in clean_key:
                                clean_key = clean_key.split("[")[-1].strip("]")
                            clean_row[clean_key] = value
                        clean_rows.append(clean_row)

                    tables.append({"rows": clean_rows})

        emit_success(f"Query returned {total_rows} rows")

        return {
            "success": True,
            "dataset_id": dataset_id,
            "row_count": total_rows,
            "tables": tables,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_execute_dax_query(agent: Any) -> Tool:
    """Register the powerbi_execute_dax_query tool."""
    return agent.tool(powerbi_execute_dax_query)


def powerbi_get_table_data(
    ctx: RunContext,
    dataset_id: str,
    table_name: str,
    workspace_id: str | None = None,
    top_n: int = 100,
    columns: list[str] | None = None,
) -> dict:
    """Get data from a Power BI dataset table.

    A simplified way to query table data without writing DAX manually.

    Args:
        dataset_id: The ID of the dataset.
        table_name: Name of the table to query.
        workspace_id: Optional workspace ID containing the dataset.
        top_n: Maximum number of rows to return (default: 100, max: 10000).
        columns: Optional list of column names to select.

    Returns:
        Dict with table rows or error.

    Example:
        # Get first 50 rows from Sales table
        powerbi_get_table_data(
            dataset_id="abc123",
            table_name="Sales",
            top_n=50
        )

        # Get specific columns
        powerbi_get_table_data(
            dataset_id="abc123",
            table_name="Products",
            columns=["Name", "Category", "Price"]
        )
    """
    # Limit top_n to reasonable max
    top_n = min(top_n, 10000)

    emit_info(
        Text.from_markup(
            f"\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            f"📃 [bold cyan]Getting data from '{table_name}' (top {top_n})...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        # Build DAX query
        if columns:
            ", ".join(f"'{table_name}'[{col}]" for col in columns)
        else:
            pass

        rows = client.get_table_data(dataset_id, table_name, workspace_id, top_n)

        emit_success(f"Got {len(rows)} rows from '{table_name}'")

        return {
            "success": True,
            "dataset_id": dataset_id,
            "table_name": table_name,
            "row_count": len(rows),
            "rows": rows,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_table_data(agent: Any) -> Tool:
    """Register the powerbi_get_table_data tool."""
    return agent.tool(powerbi_get_table_data)


# =============================================================================
# DATASET REFRESH TOOLS
# =============================================================================


def powerbi_refresh_dataset(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
    notify_option: str = "NoNotification",
) -> dict:
    """Trigger a refresh of a Power BI dataset.

    Args:
        dataset_id: The ID of the dataset to refresh.
        workspace_id: Optional workspace ID containing the dataset.
        notify_option: Notification option - "NoNotification", "MailOnFailure",
            or "MailOnComplete".

    Returns:
        Dict with success status or error.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "🔄 [bold cyan]Triggering dataset refresh...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        else:
            endpoint = f"/datasets/{dataset_id}/refreshes"

        body = {"notifyOption": notify_option}
        client.post(endpoint, json=body)

        emit_success("Dataset refresh triggered successfully!")

        return {
            "success": True,
            "message": "Dataset refresh triggered. Use powerbi_get_refresh_history to check status.",
            "dataset_id": dataset_id,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_refresh_dataset(agent: Any) -> Tool:
    """Register the powerbi_refresh_dataset tool."""
    return agent.tool(powerbi_refresh_dataset)


def powerbi_get_refresh_history(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
    top: int = 10,
    skip: int = 0,
) -> dict:
    """Get the refresh history for a Power BI dataset.

    Supports pagination via top/skip parameters. Check 'has_more' in the response
    to determine if additional pages exist, and use 'next_skip' for the next request.

    Args:
        dataset_id: The ID of the dataset.
        workspace_id: Optional workspace ID containing the dataset.
        top: Maximum number of refresh entries to return (default: 10).
        skip: Number of refresh entries to skip for pagination (default: 0).

    Returns:
        Dict with refresh history entries, plus pagination metadata:
        - count: Number of refresh entries returned in this page
        - refreshes: List of refresh history objects
        - has_more: True if there may be more results (returned count == top)
     skip: The skip value to use for the next page (if has_more is True)
        - top_used: The top value used for this request
        - skip_used: The skip value used for this request
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "📊 [bold cyan]Getting refresh history...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
        else:
            endpoint = f"/datasets/{dataset_id}/refreshes"

        response = client.get(endpoint, params={"$top": top, "$skip": skip})
        refreshes = response.get("value", [])

        # Determine if there are more results
        has_more = len(refreshes) == top
        next_skip = skip + len(refreshes) if has_more else None

        emit_success(
            f"Found {len(refreshes)} refresh entries (skip={skip}, has_more={has_more})"
        )

        formatted = []
        for ref in refreshes:
            formatted.append(
                {
                    "request_id": ref.get("requestId"),
                    "status": ref.get("status"),
                    "refresh_type": ref.get("refreshType"),
                    "start_time": ref.get("startTime"),
                    "end_time": ref.get("endTime"),
                    "service_exception_json": ref.get("serviceExceptionJson"),
                }
            )

        return {
            "success": True,
            "dataset_id": dataset_id,
            "count": len(formatted),
            "refreshes": formatted,
            # Pagination metadata
            "has_more": has_more,
            "next_skip": next_skip,
            "top_used": top,
            "skip_used": skip,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_refresh_history(agent: Any) -> Tool:
    """Register the powerbi_get_refresh_history tool."""
    return agent.tool(powerbi_get_refresh_history)


# =============================================================================
# DATASOURCE TOOLS
# =============================================================================


def powerbi_get_datasources(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get the datasources for a Power BI dataset.

    Shows all data connections used by the dataset, including:
    - Connection type (SQL Server, Azure SQL, SharePoint, etc.)
    - Server/host names
    - Database names
    - Connection details

    Args:
        dataset_id: The ID of the dataset.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with list of datasources and their connection details.

    Example:
        # Get datasources for a dataset
        powerbi_get_datasources(dataset_id="abc123")
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "🔌 [bold cyan]Getting datasources for dataset...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}/datasources"
        else:
            endpoint = f"/datasets/{dataset_id}/datasources"

        response = client.get(endpoint)
        datasources = response.get("value", [])

        emit_success(f"Found {len(datasources)} datasources")

        formatted = []
        for ds in datasources:
            # Extract connection details
            conn_details = ds.get("connectionDetails", {})
            gateway_id = ds.get("gatewayId")

            formatted.append(
                {
                    "datasource_id": ds.get("datasourceId"),
                    "datasource_type": ds.get("datasourceType"),
                    "gateway_id": gateway_id,
                    "connection_details": {
                        "server": conn_details.get("server"),
                        "database": conn_details.get("database"),
                        "url": conn_details.get("url"),
                        "path": conn_details.get("path"),
                        "kind": conn_details.get("kind"),
                    },
                }
            )

        return {
            "success": True,
            "dataset_id": dataset_id,
            "count": len(formatted),
            "datasources": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_datasources(agent: Any) -> Tool:
    """Register the powerbi_get_datasources tool."""
    return agent.tool(powerbi_get_datasources)


def powerbi_get_dataset_parameters(
    ctx: RunContext,
    dataset_id: str,
    workspace_id: str | None = None,
) -> dict:
    """Get parameters defined in a Power BI dataset.

    Parameters are variables that can be used to customize queries,
    filter data, or change connection strings dynamically.

    Args:
        dataset_id: The ID of the dataset.
        workspace_id: Optional workspace ID containing the dataset.

    Returns:
        Dict with list of parameters and their current values.
    """
    emit_info(
        Text.from_markup(
            "\n[bold white on #0053e2] POWER BI [/bold white on #0053e2] "
            "⚙️ [bold cyan]Getting dataset parameters...[/bold cyan]"
        )
    )

    try:
        client = get_powerbi_client()

        if workspace_id:
            endpoint = f"/groups/{workspace_id}/datasets/{dataset_id}/parameters"
        else:
            endpoint = f"/datasets/{dataset_id}/parameters"

        response = client.get(endpoint)
        parameters = response.get("value", [])

        emit_success(f"Found {len(parameters)} parameters")

        formatted = []
        for param in parameters:
            formatted.append(
                {
                    "name": param.get("name"),
                    "type": param.get("type"),
                    "current_value": param.get("currentValue"),
                    "is_required": param.get("isRequired", False),
                    "suggested_values": param.get("suggestedValues", []),
                }
            )

        return {
            "success": True,
            "dataset_id": dataset_id,
            "count": len(formatted),
            "parameters": formatted,
        }

    except Exception as e:
        return handle_powerbi_error(e)


def register_powerbi_get_dataset_parameters(agent: Any) -> Tool:
    """Register the powerbi_get_dataset_parameters tool."""
    return agent.tool(powerbi_get_dataset_parameters)
