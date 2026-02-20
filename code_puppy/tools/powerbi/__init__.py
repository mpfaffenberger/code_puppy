"""Power BI API tools for Code Puppy.

Organized by API category:
- workspaces.py: Workspace management and user access
- reports.py: Report listing, details, and cloning
- datasets.py: Dataset management and DAX queries
- dashboards.py: Dashboard and tile management
- exports.py: Data export to CSV/JSON
- common.py: Generic API request and authentication

"""

# Workspaces
from code_puppy.tools.powerbi.workspaces import (
    register_powerbi_list_workspaces,
    register_powerbi_get_workspace,
    register_powerbi_list_workspace_users,
)

# Reports
from code_puppy.tools.powerbi.reports import (
    register_powerbi_list_reports,
    register_powerbi_get_report,
    register_powerbi_list_report_pages,
    register_powerbi_clone_report,
)

# Datasets
from code_puppy.tools.powerbi.datasets import (
    register_powerbi_get_calculation_group_items,
    register_powerbi_list_datasets,
    register_powerbi_get_dataset,
    register_powerbi_get_dataset_tables,
    register_powerbi_get_table_columns,
    register_powerbi_get_measures,
    register_powerbi_execute_dax_query,
    register_powerbi_get_table_data,
    register_powerbi_refresh_dataset,
    register_powerbi_get_refresh_history,
    register_powerbi_get_datasources,
    register_powerbi_get_dataset_parameters,
)

# Dashboards
from code_puppy.tools.powerbi.dashboards import (
    register_powerbi_list_dashboards,
    register_powerbi_get_dashboard,
    register_powerbi_list_dashboard_tiles,
)

# Exports
from code_puppy.tools.powerbi.exports import (
    register_powerbi_export_table_to_csv,
    register_powerbi_export_table_to_json,
    register_powerbi_export_dax_query_to_csv,
)

# Common (generic API request and authentication)
from code_puppy.tools.powerbi.common import (
    register_powerbi_api_request,
    register_powerbi_authenticate,
)

# Convenience dict for bulk registration
POWERBI_TOOLS = {
    # Workspaces
    "powerbi_list_workspaces": register_powerbi_list_workspaces,
    "powerbi_get_workspace": register_powerbi_get_workspace,
    "powerbi_list_workspace_users": register_powerbi_list_workspace_users,
    # Reports
    "powerbi_list_reports": register_powerbi_list_reports,
    "powerbi_get_report": register_powerbi_get_report,
    "powerbi_list_report_pages": register_powerbi_list_report_pages,
    "powerbi_clone_report": register_powerbi_clone_report,
    # Datasets
    "powerbi_list_datasets": register_powerbi_list_datasets,
    "powerbi_get_dataset": register_powerbi_get_dataset,
    "powerbi_get_dataset_tables": register_powerbi_get_dataset_tables,
    "powerbi_get_table_columns": register_powerbi_get_table_columns,
    "powerbi_get_measures": register_powerbi_get_measures,
    "powerbi_get_calculation_group_items": register_powerbi_get_calculation_group_items,
    "powerbi_execute_dax_query": register_powerbi_execute_dax_query,
    "powerbi_get_table_data": register_powerbi_get_table_data,
    "powerbi_refresh_dataset": register_powerbi_refresh_dataset,
    "powerbi_get_refresh_history": register_powerbi_get_refresh_history,
    "powerbi_get_datasources": register_powerbi_get_datasources,
    "powerbi_get_dataset_parameters": register_powerbi_get_dataset_parameters,
    # Dashboards
    "powerbi_list_dashboards": register_powerbi_list_dashboards,
    "powerbi_get_dashboard": register_powerbi_get_dashboard,
    "powerbi_list_dashboard_tiles": register_powerbi_list_dashboard_tiles,
    # Exports
    "powerbi_export_table_to_csv": register_powerbi_export_table_to_csv,
    "powerbi_export_table_to_json": register_powerbi_export_table_to_json,
    "powerbi_export_dax_query_to_csv": register_powerbi_export_dax_query_to_csv,
    # Generic API request (fallback for any endpoint)
    "powerbi_api_request": register_powerbi_api_request,
    # Authentication tool (use when you get a 401 error)
    "powerbi_authenticate": register_powerbi_authenticate,
}
