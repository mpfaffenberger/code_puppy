from code_puppy.messaging import emit_warning
from code_puppy.tools.agent_tools import register_invoke_agent, register_list_agents

# Browser automation tools
from code_puppy.tools.browser.browser_control import (
    register_close_browser,
    register_create_new_page,
    register_get_browser_status,
    register_initialize_browser,
    register_list_pages,
)
from code_puppy.tools.browser.browser_interactions import (
    register_browser_check,
    register_browser_uncheck,
    register_click_element,
    register_double_click_element,
    register_get_element_text,
    register_get_element_value,
    register_hover_element,
    register_select_option,
    register_set_element_text,
)
from code_puppy.tools.browser.browser_locators import (
    register_find_buttons,
    register_find_by_label,
    register_find_by_placeholder,
    register_find_by_role,
    register_find_by_test_id,
    register_find_by_text,
    register_find_links,
    register_run_xpath_query,
)
from code_puppy.tools.browser.browser_navigation import (
    register_browser_go_back,
    register_browser_go_forward,
    register_get_page_info,
    register_navigate_to_url,
    register_reload_page,
    register_wait_for_load_state,
)
from code_puppy.tools.browser.browser_screenshot import (
    register_take_screenshot_and_analyze,
)
from code_puppy.tools.browser.browser_scripts import (
    register_browser_clear_highlights,
    register_browser_highlight_element,
    register_execute_javascript,
    register_scroll_page,
    register_scroll_to_element,
    register_set_viewport_size,
    register_wait_for_element,
)
from code_puppy.tools.browser.browser_workflows import (
    register_list_workflows,
    register_read_workflow,
    register_save_workflow,
)
from code_puppy.tools.browser.terminal_command_tools import (
    register_run_terminal_command,
    register_send_terminal_keys,
    register_wait_terminal_output,
)
from code_puppy.tools.browser.terminal_screenshot_tools import (
    register_load_image,
    register_terminal_compare_mockup,
    register_terminal_read_output,
    register_terminal_screenshot,
)

# Terminal automation tools
from code_puppy.tools.browser.terminal_tools import (
    register_check_terminal_server,
    register_close_terminal,
    register_open_terminal,
    register_start_api_server,
)
from code_puppy.tools.command_runner import (
    register_agent_run_shell_command,
    register_agent_share_your_reasoning,
)
from code_puppy.tools.bigquery_tools import (
    register_bigquery_execute_query,
    register_bigquery_get_table_schema,
    register_bigquery_list_all_projects,
    register_bigquery_list_datasets,
    register_bigquery_get_default_project,
    register_bigquery_list_tables,
    register_bigquery_search_tables,
)
from code_puppy.tools.databricks_tools import (
    register_databricks_list_catalogs,
    register_databricks_list_schemas,
    register_databricks_list_tables,
    register_databricks_get_table_schema,
    register_databricks_list_warehouses,
    register_databricks_execute_query,
)
from code_puppy.tools.confluence_tools import (
    register_confluence_search,
    register_confluence_read_page,
    register_confluence_search_by_space,
    register_confluence_authenticate,
)
# ServiceNow tools - imported from new modular package
from code_puppy.tools.servicenow_tools import ALL_REGISTRATION_FUNCTIONS as SERVICENOW_TOOLS
from code_puppy.tools.jira_tools import (
    register_jira_search,
    register_jira_list_projects,
    register_jira_get_issue,
    register_jira_create_issue,
    register_jira_add_comment,
    register_jira_update_issue,
    register_jira_transition_issue,
    register_jira_get_comments,
    register_jira_authenticate,
)
from code_puppy.tools.marketplace_tools import (
    register_marketplace_search_agents,
    register_marketplace_download_agent,
    register_marketplace_upload_agent,
    register_marketplace_check_update,
    register_marketplace_authenticate,
)

from code_puppy.tools.msgraph import MSGRAPH_TOOLS
from code_puppy.tools.display import (
    display_non_streamed_result as display_non_streamed_result,
)
from code_puppy.tools.file_modifications import register_delete_file, register_edit_file
from code_puppy.tools.file_operations import (
    register_grep,
    register_list_files,
    register_read_file,
)

# Import GUI-Cub tools from separate registry to minimize diff noise
from code_puppy.tools.registry.gui_cub import GUI_CUB_TOOLS

# Map of tool names to their individual registration functions
TOOL_REGISTRY = {
    # Agent Tools
    "list_agents": register_list_agents,
    "invoke_agent": register_invoke_agent,
    # File Operations
    "list_files": register_list_files,
    "read_file": register_read_file,
    "grep": register_grep,
    # File Modifications
    "edit_file": register_edit_file,
    "delete_file": register_delete_file,
    # Command Runner
    "agent_run_shell_command": register_agent_run_shell_command,
    "agent_share_your_reasoning": register_agent_share_your_reasoning,
    # Browser Control
    "browser_initialize": register_initialize_browser,
    "browser_close": register_close_browser,
    "browser_status": register_get_browser_status,
    "browser_new_page": register_create_new_page,
    "browser_list_pages": register_list_pages,
    # Browser Navigation
    "browser_navigate": register_navigate_to_url,
    "browser_get_page_info": register_get_page_info,
    "browser_go_back": register_browser_go_back,
    "browser_go_forward": register_browser_go_forward,
    "browser_reload": register_reload_page,
    "browser_wait_for_load": register_wait_for_load_state,
    # Browser Element Discovery
    "browser_find_by_role": register_find_by_role,
    "browser_find_by_text": register_find_by_text,
    "browser_find_by_label": register_find_by_label,
    "browser_find_by_placeholder": register_find_by_placeholder,
    "browser_find_by_test_id": register_find_by_test_id,
    "browser_xpath_query": register_run_xpath_query,
    "browser_find_buttons": register_find_buttons,
    "browser_find_links": register_find_links,
    # Browser Element Interactions
    "browser_click": register_click_element,
    "browser_double_click": register_double_click_element,
    "browser_hover": register_hover_element,
    "browser_set_text": register_set_element_text,
    "browser_get_text": register_get_element_text,
    "browser_get_value": register_get_element_value,
    "browser_select_option": register_select_option,
    "browser_check": register_browser_check,
    "browser_uncheck": register_browser_uncheck,
    # Browser Scripts and Advanced Features
    "browser_execute_js": register_execute_javascript,
    "browser_scroll": register_scroll_page,
    "browser_scroll_to_element": register_scroll_to_element,
    "browser_set_viewport": register_set_viewport_size,
    "browser_wait_for_element": register_wait_for_element,
    "browser_highlight_element": register_browser_highlight_element,
    "browser_clear_highlights": register_browser_clear_highlights,
    # Browser Screenshots
    "browser_screenshot_analyze": register_take_screenshot_and_analyze,
    # Browser Workflows
    "browser_save_workflow": register_save_workflow,
    "browser_list_workflows": register_list_workflows,
    "browser_read_workflow": register_read_workflow,
    # Confluence Tools
    "confluence_search": register_confluence_search,
    "confluence_read_page": register_confluence_read_page,
    "confluence_search_by_space": register_confluence_search_by_space,
    "confluence_authenticate": register_confluence_authenticate,
    # ServiceNow Tools - merged from SERVICENOW_TOOLS dict below
    # Jira Tools
    "jira_search": register_jira_search,
    "jira_list_projects": register_jira_list_projects,
    "jira_get_issue": register_jira_get_issue,
    "jira_create_issue": register_jira_create_issue,
    "jira_add_comment": register_jira_add_comment,
    "jira_update_issue": register_jira_update_issue,
    "jira_transition_issue": register_jira_transition_issue,
    "jira_get_comments": register_jira_get_comments,
    "jira_authenticate": register_jira_authenticate,
    # BigQuery Tools
    "bigquery_get_default_project": register_bigquery_get_default_project,
    "bigquery_list_all_projects": register_bigquery_list_all_projects,
    "bigquery_list_datasets": register_bigquery_list_datasets,
    "bigquery_list_tables": register_bigquery_list_tables,
    "bigquery_execute_query": register_bigquery_execute_query,
    "bigquery_get_table_schema": register_bigquery_get_table_schema,
    "bigquery_search_tables": register_bigquery_search_tables,
    # Databricks Tools
    "databricks_list_catalogs": register_databricks_list_catalogs,
    "databricks_list_schemas": register_databricks_list_schemas,
    "databricks_list_tables": register_databricks_list_tables,
    "databricks_get_table_schema": register_databricks_get_table_schema,
    "databricks_list_warehouses": register_databricks_list_warehouses,
    "databricks_execute_query": register_databricks_execute_query,
    # Marketplace Tools
    "marketplace_search_agents": register_marketplace_search_agents,
    "marketplace_download_agent": register_marketplace_download_agent,
    "marketplace_upload_agent": register_marketplace_upload_agent,
    "marketplace_check_update": register_marketplace_check_update,
    "marketplace_authenticate": register_marketplace_authenticate,
    # Terminal Connection Tools
    "terminal_check_server": register_check_terminal_server,
    "terminal_open": register_open_terminal,
    "terminal_close": register_close_terminal,
    "start_api_server": register_start_api_server,
    # Terminal Command Execution Tools
    "terminal_run_command": register_run_terminal_command,
    "terminal_send_keys": register_send_terminal_keys,
    "terminal_wait_output": register_wait_terminal_output,
    # Terminal Screenshot Tools
    "terminal_screenshot_analyze": register_terminal_screenshot,
    "terminal_read_output": register_terminal_read_output,
    "terminal_compare_mockup": register_terminal_compare_mockup,
    "load_image_for_analysis": register_load_image,
}

# Merge in GUI-Cub tools from separate registry
TOOL_REGISTRY.update(GUI_CUB_TOOLS)

# Merge in ServiceNow tools from modular package
TOOL_REGISTRY.update(SERVICENOW_TOOLS)

# Merge in MS Graph tools
TOOL_REGISTRY.update(MSGRAPH_TOOLS)


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register.
    """
    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Get the registry entry (can be function or dict with metadata)
        registry_entry = TOOL_REGISTRY[tool_name]

        # Handle both formats: dict with metadata or direct function reference
        if isinstance(registry_entry, dict):
            # New format: {"register": func, "category": ..., "description": ...}
            register_func = registry_entry["register"]
        else:
            # Old format: direct function reference (backward compatibility)
            register_func = registry_entry

        # Register the tool
        register_func(agent)


def register_all_tools(agent):
    """Register all available tools to the provided agent.

    Args:
        agent: The agent to register tools to.
    """
    all_tools = list(TOOL_REGISTRY.keys())
    register_tools_for_agent(agent, all_tools)


def get_available_tool_names() -> list[str]:
    """Get list of all available tool names.

    Returns:
        List of all tool names that can be registered.
    """
    return list(TOOL_REGISTRY.keys())
