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
from code_puppy.tools.display import (
    display_non_streamed_result as display_non_streamed_result,
)
from code_puppy.tools.file_modifications import register_delete_file, register_edit_file
from code_puppy.tools.file_operations import (
    register_grep,
    register_list_files,
    register_read_file,
)
from code_puppy.tools.universal_constructor import register_universal_constructor

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
    # Universal Constructor
    "universal_constructor": register_universal_constructor,
}


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register. UC tools are prefixed with "uc:".
    """
    from code_puppy.config import get_universal_constructor_enabled

    for tool_name in tool_names:
        # Handle UC tools (prefixed with "uc:")
        if tool_name.startswith("uc:"):
            uc_tool_name = tool_name[3:]  # Remove "uc:" prefix
            _register_uc_tool_wrapper(agent, uc_tool_name)
            continue

        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Check if Universal Constructor is disabled
        if (
            tool_name == "universal_constructor"
            and not get_universal_constructor_enabled()
        ):
            continue  # Skip UC if disabled in config

        # Register the individual tool
        register_func = TOOL_REGISTRY[tool_name]
        register_func(agent)


def _register_uc_tool_wrapper(agent, uc_tool_name: str):
    """Register a wrapper for a UC tool that calls it via the UC registry.

    This creates a dynamic tool that wraps the UC tool, allowing it to be
    called directly by the agent without going through universal_constructor.

    Args:
        agent: The agent to register the tool wrapper to.
        uc_tool_name: The full name of the UC tool (e.g., "api.weather").
    """
    from typing import Any

    from pydantic_ai import RunContext

    # Get tool info for description and signature
    try:
        from code_puppy.plugins.universal_constructor.registry import get_registry

        registry = get_registry()
        tool_info = registry.get_tool(uc_tool_name)
        if not tool_info:
            emit_warning(f"Warning: UC tool '{uc_tool_name}' not found, skipping...")
            return

        description = tool_info.meta.description
        docstring = tool_info.docstring or description
    except Exception as e:
        emit_warning(f"Warning: Failed to get UC tool '{uc_tool_name}' info: {e}")
        return

    # Create the wrapper function dynamically
    # We use a closure to capture the tool name
    def make_uc_wrapper(tool_name: str, tool_desc: str):
        async def uc_tool_wrapper(
            context: RunContext,
            **kwargs: Any,
        ) -> Any:
            """Dynamically generated wrapper for a UC tool."""
            from code_puppy.plugins.universal_constructor.registry import get_registry

            registry = get_registry()
            func = registry.get_tool_function(tool_name)
            if not func:
                return {"error": f"UC tool '{tool_name}' function not found"}

            try:
                result = func(**kwargs)
                return result
            except Exception as e:
                return {"error": f"UC tool '{tool_name}' failed: {e}"}

        # Set metadata for the tool
        uc_tool_wrapper.__name__ = tool_name.replace(".", "_")
        uc_tool_wrapper.__doc__ = (
            f"{tool_desc}\n\nThis is a Universal Constructor tool."
        )
        return uc_tool_wrapper

    wrapper = make_uc_wrapper(uc_tool_name, docstring)

    # Register the wrapper as a tool
    try:
        agent.tool(wrapper)
    except Exception as e:
        emit_warning(f"Warning: Failed to register UC tool '{uc_tool_name}': {e}")


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
