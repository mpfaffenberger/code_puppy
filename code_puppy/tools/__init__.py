from code_puppy.callbacks import on_register_tools
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
from code_puppy.tools.ask_user_question import register_ask_user_question
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

# Scheduler tools
from code_puppy.tools.scheduler_tools import (
    register_scheduler_create_task,
    register_scheduler_daemon_status,
    register_scheduler_delete_task,
    register_scheduler_list_tasks,
    register_scheduler_run_task,
    register_scheduler_start_daemon,
    register_scheduler_stop_daemon,
    register_scheduler_toggle_task,
    register_scheduler_view_log,
)
from code_puppy.tools.skills_tools import (
    register_activate_skill,
    register_list_or_search_skills,
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
    # User Interaction
    "ask_user_question": register_ask_user_question,
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
    # Skills Tools
    "activate_skill": register_activate_skill,
    "list_or_search_skills": register_list_or_search_skills,
    # Universal Constructor
    "universal_constructor": register_universal_constructor,
    # Scheduler Tools
    "scheduler_list_tasks": register_scheduler_list_tasks,
    "scheduler_create_task": register_scheduler_create_task,
    "scheduler_delete_task": register_scheduler_delete_task,
    "scheduler_toggle_task": register_scheduler_toggle_task,
    "scheduler_daemon_status": register_scheduler_daemon_status,
    "scheduler_start_daemon": register_scheduler_start_daemon,
    "scheduler_stop_daemon": register_scheduler_stop_daemon,
    "scheduler_run_task": register_scheduler_run_task,
    "scheduler_view_log": register_scheduler_view_log,
}


def _load_plugin_tools() -> None:
    """Load tools registered by plugins via the register_tools callback.

    This merges plugin-provided tools into the TOOL_REGISTRY.
    Called lazily when tools are first accessed.
    """
    try:
        results = on_register_tools()
        for result in results:
            if result is None:
                continue
            # Each result should be a list of tool definitions
            tools_list = result if isinstance(result, list) else [result]
            for tool_def in tools_list:
                if (
                    isinstance(tool_def, dict)
                    and "name" in tool_def
                    and "register_func" in tool_def
                ):
                    tool_name = tool_def["name"]
                    register_func = tool_def["register_func"]
                    if callable(register_func):
                        TOOL_REGISTRY[tool_name] = register_func
    except Exception:
        # Don't let plugin failures break core functionality
        pass


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register. UC tools are prefixed with "uc:".
    """
    from code_puppy.config import get_universal_constructor_enabled

    _load_plugin_tools()
    for tool_name in tool_names:
        # Handle UC tools (prefixed with "uc:")
        if tool_name.startswith("uc:"):
            # Skip UC tools if UC is disabled
            if not get_universal_constructor_enabled():
                continue
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

    This creates a dynamic tool that wraps the UC tool, preserving its
    parameter signature so pydantic-ai can generate proper JSON schema.

    Args:
        agent: The agent to register the tool wrapper to.
        uc_tool_name: The full name of the UC tool (e.g., "api.weather").
    """
    import inspect
    from typing import Any

    from pydantic_ai import RunContext

    # Get tool info and function from registry
    try:
        from code_puppy.plugins.universal_constructor.registry import get_registry

        registry = get_registry()
        tool_info = registry.get_tool(uc_tool_name)
        if not tool_info:
            emit_warning(f"Warning: UC tool '{uc_tool_name}' not found, skipping...")
            return

        func = registry.get_tool_function(uc_tool_name)
        if not func:
            emit_warning(
                f"Warning: UC tool '{uc_tool_name}' function not found, skipping..."
            )
            return

        description = tool_info.meta.description
        docstring = tool_info.docstring or description
    except Exception as e:
        emit_warning(f"Warning: Failed to get UC tool '{uc_tool_name}' info: {e}")
        return

    # Get the original function's signature
    try:
        sig = inspect.signature(func)
        # Get annotations from the original function
        annotations = getattr(func, "__annotations__", {}).copy()
    except (ValueError, TypeError):
        sig = None
        annotations = {}

    # Create wrapper that preserves the signature
    def make_uc_wrapper(
        tool_name: str, original_func, original_sig, original_annotations
    ):
        # Build the wrapper function
        async def uc_tool_wrapper(context: RunContext, **kwargs: Any) -> Any:
            """Dynamically generated wrapper for a UC tool."""
            try:
                result = original_func(**kwargs)
                # Await async tool implementations
                if inspect.isawaitable(result):
                    result = await result
                return result
            except Exception as e:
                return {"error": f"UC tool '{tool_name}' failed: {e}"}

        # Copy signature info from original function
        uc_tool_wrapper.__name__ = tool_name.replace(".", "_")
        uc_tool_wrapper.__doc__ = (
            f"{docstring}\n\nThis is a Universal Constructor tool."
        )

        # Preserve annotations for pydantic-ai schema generation
        if original_annotations:
            # Add 'context' param and copy original params (excluding 'return')
            new_annotations = {"context": RunContext}
            for param_name, param_type in original_annotations.items():
                if param_name != "return":
                    new_annotations[param_name] = param_type
            if "return" in original_annotations:
                new_annotations["return"] = original_annotations["return"]
            else:
                new_annotations["return"] = Any
            uc_tool_wrapper.__annotations__ = new_annotations

        # Try to set __signature__ for better introspection
        if original_sig:
            try:
                # Build new parameters list: context first, then original params
                new_params = [
                    inspect.Parameter(
                        "context",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=RunContext,
                    )
                ]
                for param in original_sig.parameters.values():
                    new_params.append(param)

                # Create new signature with return annotation
                return_annotation = original_annotations.get("return", Any)
                new_sig = original_sig.replace(
                    parameters=new_params, return_annotation=return_annotation
                )
                uc_tool_wrapper.__signature__ = new_sig
            except (ValueError, TypeError):
                pass  # Signature manipulation failed, continue without it

        return uc_tool_wrapper

    wrapper = make_uc_wrapper(uc_tool_name, func, sig, annotations)

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
    _load_plugin_tools()
    return list(TOOL_REGISTRY.keys())
