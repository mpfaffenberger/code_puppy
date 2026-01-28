"""Enterprise tools for Walmart-specific integrations.

This module provides registration functions for enterprise tools that are
Walmart-specific and should only be loaded when the Walmart plugin is active.

Tools included:
- BigQuery (7 tools): Data warehouse queries and schema inspection
- Databricks (6 tools): Catalog, schema, and query execution
- Confluence (4 tools): Documentation search and retrieval
- Jira (10 tools): Issue tracking and project management
- Marketplace (5 tools): Agent marketplace operations
"""

from typing import Any, Callable


def get_enterprise_tools() -> list[dict[str, Any]]:
    """Return the list of enterprise tool definitions for dynamic registration.

    Each tool definition contains:
    - name: The tool name used in TOOL_REGISTRY
    - register_func: The function to register the tool with an agent

    Returns:
        List of tool definitions for the callback system.
    """
    # Lazy imports to avoid loading enterprise dependencies when not needed
    from code_puppy.tools.bigquery_tools import (
        register_bigquery_execute_query,
        register_bigquery_get_default_project,
        register_bigquery_get_table_schema,
        register_bigquery_list_all_projects,
        register_bigquery_list_datasets,
        register_bigquery_list_tables,
        register_bigquery_search_tables,
    )
    from code_puppy.tools.confluence_tools import (
        register_confluence_authenticate,
        register_confluence_read_page,
        register_confluence_search,
        register_confluence_search_by_space,
    )
    from code_puppy.tools.databricks_tools import (
        register_databricks_execute_query,
        register_databricks_get_table_schema,
        register_databricks_list_catalogs,
        register_databricks_list_schemas,
        register_databricks_list_tables,
        register_databricks_list_warehouses,
    )
    from code_puppy.tools.jira_tools import (
        register_jira_add_comment,
        register_jira_authenticate,
        register_jira_create_issue,
        register_jira_get_comments,
        register_jira_get_issue,
        register_jira_list_application_services,
        register_jira_list_projects,
        register_jira_search,
        register_jira_transition_issue,
        register_jira_update_issue,
    )
    from code_puppy.tools.marketplace_tools import (
        register_marketplace_authenticate,
        register_marketplace_check_update,
        register_marketplace_download_agent,
        register_marketplace_search_agents,
        register_marketplace_upload_agent,
    )

    return [
        # BigQuery Tools (7)
        {"name": "bigquery_get_default_project", "register_func": register_bigquery_get_default_project},
        {"name": "bigquery_list_all_projects", "register_func": register_bigquery_list_all_projects},
        {"name": "bigquery_list_datasets", "register_func": register_bigquery_list_datasets},
        {"name": "bigquery_list_tables", "register_func": register_bigquery_list_tables},
        {"name": "bigquery_execute_query", "register_func": register_bigquery_execute_query},
        {"name": "bigquery_get_table_schema", "register_func": register_bigquery_get_table_schema},
        {"name": "bigquery_search_tables", "register_func": register_bigquery_search_tables},
        # Databricks Tools (6)
        {"name": "databricks_list_catalogs", "register_func": register_databricks_list_catalogs},
        {"name": "databricks_list_schemas", "register_func": register_databricks_list_schemas},
        {"name": "databricks_list_tables", "register_func": register_databricks_list_tables},
        {"name": "databricks_get_table_schema", "register_func": register_databricks_get_table_schema},
        {"name": "databricks_list_warehouses", "register_func": register_databricks_list_warehouses},
        {"name": "databricks_execute_query", "register_func": register_databricks_execute_query},
        # Confluence Tools (4)
        {"name": "confluence_search", "register_func": register_confluence_search},
        {"name": "confluence_read_page", "register_func": register_confluence_read_page},
        {"name": "confluence_search_by_space", "register_func": register_confluence_search_by_space},
        {"name": "confluence_authenticate", "register_func": register_confluence_authenticate},
        # Jira Tools (10)
        {"name": "jira_search", "register_func": register_jira_search},
        {"name": "jira_list_projects", "register_func": register_jira_list_projects},
        {"name": "jira_list_application_services", "register_func": register_jira_list_application_services},
        {"name": "jira_get_issue", "register_func": register_jira_get_issue},
        {"name": "jira_create_issue", "register_func": register_jira_create_issue},
        {"name": "jira_add_comment", "register_func": register_jira_add_comment},
        {"name": "jira_update_issue", "register_func": register_jira_update_issue},
        {"name": "jira_transition_issue", "register_func": register_jira_transition_issue},
        {"name": "jira_get_comments", "register_func": register_jira_get_comments},
        {"name": "jira_authenticate", "register_func": register_jira_authenticate},
        # Marketplace Tools (5)
        {"name": "marketplace_search_agents", "register_func": register_marketplace_search_agents},
        {"name": "marketplace_download_agent", "register_func": register_marketplace_download_agent},
        {"name": "marketplace_upload_agent", "register_func": register_marketplace_upload_agent},
        {"name": "marketplace_check_update", "register_func": register_marketplace_check_update},
        {"name": "marketplace_authenticate", "register_func": register_marketplace_authenticate},
    ]
