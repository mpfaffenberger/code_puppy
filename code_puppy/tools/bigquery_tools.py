"""BigQuery integration tools.

Provides tools for exploring and querying Google BigQuery databases,
including listing projects, datasets, tables, and executing queries.
"""

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


def bigquery_execute_query(ctx: RunContext, query: str, max_results: int = 100) -> dict:
    """Execute a SQL query in BigQuery.

    SAFETY: Only SELECT queries are allowed. Destructive operations (DELETE, DROP,
    TRUNCATE, INSERT, UPDATE, MERGE, ALTER, CREATE, REPLACE) are blocked.

    Args:
        ctx: PydanticAI run context
        query: SQL query string to execute (SELECT only)
        max_results: Maximum number of results to return (default: 100)

    Returns:
        Dict containing:
            - success (bool): Whether the query succeeded
            - rows (list): List of result row dictionaries
            - schema (list): List of field definitions
            - total_rows (int): Total number of rows in result
            - job_id (str): BigQuery job ID
            - bytes_processed (int): Bytes processed by the query
            - bytes_billed (int): Bytes billed for the query
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

        emit_success(
            f"Query completed: {result['total_rows']} total rows, "
            f"returned {len(result['rows'])} rows\n"
            f"Bytes processed: {result['bytes_processed']:,}\n"
            f"Job ID: {result['job_id']}"
        )

        return {
            "success": True,
            **result,
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
