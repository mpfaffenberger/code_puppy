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


from code_puppy.tools.command_runner import (
    register_agent_run_shell_command,
    register_agent_share_your_reasoning,
)
from code_puppy.tools.confluence_tools import (
    register_confluence_search,
    register_confluence_read_page,
    register_confluence_search_by_space,
)
from code_puppy.tools.file_modifications import register_delete_file, register_edit_file
from code_puppy.tools.file_operations import (
    register_grep,
    register_list_files,
    register_read_file,
)
from code_puppy.tools.tool_metadata import (
    ToolMetadata,
    CATEGORY_AGENT,
    CATEGORY_FILE_OPS,
    CATEGORY_COMMAND,
    CATEGORY_COMMUNICATION,
)

# Import GUI-Cub tools from separate registry to minimize diff noise
from code_puppy.tools.registry.gui_cub import GUI_CUB_TOOLS

# Map of tool names to their metadata and registration functions
# New format: Each entry can be either:
#   - A bare function (old format, backward compatible)
#   - A ToolMetadata dict with 'register' function + metadata
TOOL_REGISTRY: dict[str, ToolMetadata] = {
    # Agent Tools
    "list_agents": {
        "register": register_list_agents,
        "category": CATEGORY_AGENT,
        "description": "List all available sub-agents that can be invoked",
        "keywords": ["agent", "list", "sub-agent", "available"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["discover available agents", "check agent capabilities"],
    },
    "invoke_agent": {
        "register": register_invoke_agent,
        "category": CATEGORY_AGENT,
        "description": "Invoke a specific sub-agent with a prompt",
        "keywords": ["agent", "invoke", "delegate", "sub-agent"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["delegate tasks to specialized agents", "multi-agent workflows"],
    },
    # File Operations
    "list_files": {
        "register": register_list_files,
        "category": CATEGORY_FILE_OPS,
        "description": "List files and directories with filtering",
        "keywords": ["file", "directory", "list", "browse"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["explore directory structures", "find files"],
    },
    "read_file": {
        "register": register_read_file,
        "category": CATEGORY_FILE_OPS,
        "description": "Read file contents with optional line-range selection",
        "keywords": ["file", "read", "content", "view"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["read code files", "inspect file contents"],
    },
    "grep": {
        "register": register_grep,
        "category": CATEGORY_FILE_OPS,
        "description": "Recursively search for text patterns across files",
        "keywords": ["search", "grep", "find", "pattern", "text"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["search code", "find text in files"],
    },
    # File Modifications
    "edit_file": {
        "register": register_edit_file,
        "category": CATEGORY_FILE_OPS,
        "description": "Comprehensive file editing (create, replace, delete snippets)",
        "keywords": ["edit", "write", "modify", "file", "create"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["modify code", "create files", "update configuration"],
    },
    "delete_file": {
        "register": register_delete_file,
        "category": CATEGORY_FILE_OPS,
        "description": "Safely delete files with diff generation",
        "keywords": ["delete", "remove", "file"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["remove files", "clean up"],
    },
    # Command Runner
    "agent_run_shell_command": {
        "register": register_agent_run_shell_command,
        "category": CATEGORY_COMMAND,
        "description": "Execute shell commands with streaming output",
        "keywords": ["command", "shell", "terminal", "execute", "run"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["run scripts", "execute commands", "build projects"],
    },
    "agent_share_your_reasoning": {
        "register": register_agent_share_your_reasoning,
        "category": CATEGORY_COMMUNICATION,
        "description": "Share reasoning and planned next steps with user",
        "keywords": ["reasoning", "explain", "communicate", "transparency"],
        "platform": "all",
        "requires_typing": False,
        "use_cases": ["explain thought process", "show planning"],
    },
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
    # Browser Screenshots and VQA
    "browser_screenshot_analyze": register_take_screenshot_and_analyze,
    # Browser Workflows
    "browser_save_workflow": register_save_workflow,
    "browser_list_workflows": register_list_workflows,
    "browser_read_workflow": register_read_workflow,
    # Confluence Tools
    "confluence_search": register_confluence_search,
    "confluence_read_page": register_confluence_read_page,
    "confluence_search_by_space": register_confluence_search_by_space,
}

# Merge in GUI-Cub tools from separate registry
TOOL_REGISTRY.update(GUI_CUB_TOOLS)


def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register.
    """
    from code_puppy.tools.tool_metadata import get_tool_register

    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Register the individual tool (supports both old and new format)
        tool_entry = TOOL_REGISTRY[tool_name]
        register_func = get_tool_register(tool_entry)
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


def get_tool_info(query: str | None = None) -> str:
    """Get one-liner information about available tools.

    Single global function for agent-builder to discover tools.
    Returns formatted tool information based on query.

    Args:
        query: Optional search query (keywords, intent, category name).
               If None, returns all tools grouped by category.

    Returns:
        Formatted string with tool information (one-liners).

    Examples:
        >>> get_tool_info()  # All tools by category
        >>> get_tool_info("click")  # Tools matching "click"
        >>> get_tool_info("Desktop Automation")  # Category
    """
    from code_puppy.tools.tool_discovery import (
        suggest_tools,
        get_tools_by_category,
    )
    from code_puppy.tools.tool_metadata import get_tool_metadata

    # If query provided, search for relevant tools
    if query:
        # Check if it's a category name
        category_tools = get_tools_by_category(TOOL_REGISTRY, query)
        if category_tools:
            # It's a category
            lines = [f"### {query}\n"]
            for name in sorted(category_tools):
                metadata = get_tool_metadata(TOOL_REGISTRY[name])
                desc = metadata.get("description", "No description")
                platform = metadata.get("platform", "all")
                platform_tag = f" [{platform.upper()}]" if platform != "all" else ""
                lines.append(f"- {name}: {desc}{platform_tag}")
            return "\n".join(lines)

        # Not a category - use intent-based search
        suggestions = suggest_tools(TOOL_REGISTRY, query)
        if suggestions:
            lines = [f"### Tools matching '{query}'\n"]
            # Show only tools with metadata (representative tools)
            for name in sorted(suggestions):
                metadata = get_tool_metadata(TOOL_REGISTRY[name])
                if "description" in metadata:  # Only show if it has metadata
                    desc = metadata.get("description", "No description")
                    platform = metadata.get("platform", "all")
                    platform_tag = f" [{platform.upper()}]" if platform != "all" else ""
                    lines.append(f"- {name}: {desc}{platform_tag}")
            return "\n".join(lines) if len(lines) > 1 else "No tools found."

        return "No tools found."

    # No query - return all tools grouped by category
    categories = {}
    for name, entry in TOOL_REGISTRY.items():
        metadata = get_tool_metadata(entry)
        category = metadata.get("category")
        if category:  # Only show tools with metadata
            if category not in categories:
                categories[category] = []
            categories[category].append((name, metadata))

    lines = []
    for category in sorted(categories.keys()):
        lines.append(f"\n### {category}\n")
        for name, metadata in sorted(categories[category], key=lambda x: x[0]):
            desc = metadata.get("description", "No description")
            platform = metadata.get("platform", "all")
            platform_tag = f" [{platform.upper()}]" if platform != "all" else ""
            lines.append(f"- {name}: {desc}{platform_tag}")

    return "\n".join(lines)
