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

# GUI-Cub workflow and knowledge base tools (always available)
from code_puppy.tools.gui_cub.workflows import (
    register_workflow_tools as register_gui_cub_workflows,
)
from code_puppy.tools.gui_cub.executor import (
    register_executor_tool as register_gui_cub_executor,
)
from code_puppy.tools.gui_cub.knowledge_base import (
    register_knowledge_base_tool as register_gui_cub_kb,
)
from code_puppy.tools.gui_cub.config_manager import (
    register_config_tools as register_gui_cub_config,
    register_debug_screenshot_tools as register_gui_cub_debug_screenshots,
)

# GUI-Cub desktop automation tools (always available - required dependencies)
# Dependencies: pyautogui, pillow, opencv-python, openpyxl
from code_puppy.tools.gui_cub.keyboard_control import register_keyboard_control_tools
from code_puppy.tools.gui_cub.keyboard_shortcuts import register_keyboard_shortcut_tools
from code_puppy.tools.gui_cub.mouse_control import register_mouse_control_tools
from code_puppy.tools.gui_cub.screen_capture import register_desktop_screenshot_tools
from code_puppy.tools.gui_cub.window_control import register_window_control_tools
from code_puppy.tools.gui_cub.grid_calibration import register_grid_calibration_tools
from code_puppy.tools.gui_cub.ocr import register_ocr_tools
from code_puppy.tools.gui_cub.click_debugging import register_click_debugging_tools
from code_puppy.tools.gui_cub.multi_strategy_click import (
    register_multi_strategy_click_tools,
)

# OLD VQA removed - replaced with superior two-stage implementation
# from code_puppy.tools.gui_cub.vqa_hover_click import register_vqa_hover_tools
from code_puppy.tools.gui_cub.vqa_two_stage_tools import register_vqa_two_stage_tools

# Desktop Automation Accessibility API tools (macOS only) - platform-specific
# Dependencies: atomacos, pyobjc-framework-Cocoa (installed on macOS via pyproject.toml)
try:
    from code_puppy.tools.gui_cub.accessibility import register_accessibility_tools

    ACCESSIBILITY_TOOLS_AVAILABLE = True
except ImportError:
    # Accessibility tools only available on macOS (atomacos, PyObjC)
    ACCESSIBILITY_TOOLS_AVAILABLE = False
    register_accessibility_tools = None

# Windows automation tools - platform-specific (Windows only)
# Dependencies: pywinauto, pywin32 (installed on Windows via pyproject.toml)
import sys

if sys.platform == "win32":
    try:
        from code_puppy.tools.gui_cub.windows_automation import register_windows_tools

        WINDOWS_TOOLS_AVAILABLE = True
    except ImportError:
        # Windows tools only available on Windows (pywinauto, pywin32)
        WINDOWS_TOOLS_AVAILABLE = False
        register_windows_tools = None
else:
    # Not on Windows - skip import entirely
    WINDOWS_TOOLS_AVAILABLE = False
    register_windows_tools = None

from code_puppy.tools.command_runner import (
    register_agent_run_shell_command,
    register_agent_share_your_reasoning,
)
from code_puppy.tools.confluence_tools import (
    register_confluence_search,
    register_confluence_read_page,
    register_confluence_search_by_space,
)

from code_puppy.tools.gui_cub.os_unified import register_os_unified_tools
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
    CATEGORY_DESKTOP,
    CATEGORY_COMMUNICATION,
)

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

# GUI-Cub workflow and knowledge base tools (always available)
TOOL_REGISTRY.update(
    {
        # Representative names (NEW - preferred) with metadata
        "gui_cub_workflows": {
            "register": register_gui_cub_workflows,
            "category": CATEGORY_DESKTOP,
            "description": "Workflow management (save, list, read workflows)",
            "keywords": ["workflow", "automation", "yaml", "save", "reuse"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["save automation workflows", "reuse automation patterns"],
        },
        "gui_cub_config": {
            "register": register_gui_cub_config,
            "category": CATEGORY_DESKTOP,
            "description": "GUI-CUB configuration (calibrate, validate, reset)",
            "keywords": ["config", "calibrate", "settings", "setup"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["configure GUI-CUB", "calibrate screen"],
        },
        "gui_cub_debug": {
            "register": register_gui_cub_debug_screenshots,
            "category": CATEGORY_DESKTOP,
            "description": "Debug screenshot tools",
            "keywords": ["debug", "screenshot", "troubleshoot"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["debug automation", "save debug screenshots"],
        },
        # Individual tool names (backward compatibility)
        "gui_cub_save_workflow": register_gui_cub_workflows,
        "gui_cub_list_workflows": register_gui_cub_workflows,
        "gui_cub_read_workflow": register_gui_cub_workflows,
        "gui_cub_execute_workflow": register_gui_cub_executor,
        "gui_cub_append_to_knowledge_base": register_gui_cub_kb,
        "gui_cub_get_config": register_gui_cub_config,
        "gui_cub_calibrate": register_gui_cub_config,
        "gui_cub_validate_config": register_gui_cub_config,
        "gui_cub_reset_config": register_gui_cub_config,
        "save_debug_screenshot": register_gui_cub_debug_screenshots,
    }
)

# Desktop automation tools (always available - required dependencies)
TOOL_REGISTRY.update(
    {
        # Representative names (NEW - preferred) with metadata
        "desktop_screenshot": {
            "register": register_desktop_screenshot_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Screenshot capture and analysis (OCR/VQA)",
            "keywords": ["screenshot", "capture", "screen", "image", "visual"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["capture screenshots", "visual analysis", "debugging"],
        },
        "desktop_mouse": {
            "register": register_mouse_control_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Mouse operations (move, click, drag, scroll)",
            "keywords": ["mouse", "click", "drag", "scroll", "pointer"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["clicking elements", "drag and drop", "scrolling pages"],
        },
        "desktop_shortcuts": {
            "register": register_keyboard_shortcut_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Common keyboard shortcuts (copy, paste, save, etc.)",
            "keywords": ["shortcut", "hotkey", "keyboard", "copy", "paste"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["copy/paste", "save files", "keyboard shortcuts"],
        },
        "desktop_keyboard": {
            "register": register_keyboard_control_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Keyboard operations (type, press, hotkey)",
            "keywords": ["keyboard", "type", "text", "input", "hotkey"],
            "platform": "all",
            "requires_typing": True,
            "use_cases": ["typing text", "form input", "keyboard automation"],
        },
        "desktop_window_control": {
            "register": register_window_control_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Window management (focus, sleep, alerts)",
            "keywords": ["window", "focus", "alert", "dialog"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["focus windows", "show alerts", "window management"],
        },
        "desktop_grid_calibration": {
            "register": register_grid_calibration_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Grid overlay calibration for coordinate debugging",
            "keywords": ["calibration", "grid", "coordinates", "debug"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["calibrate screen coordinates", "debug clicking"],
        },
        "desktop_ocr": {
            "register": register_ocr_tools,
            "category": CATEGORY_DESKTOP,
            "description": "OCR text extraction and search",
            "keywords": ["ocr", "text", "extract", "read", "recognize"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["extract text from screen", "find text", "OCR"],
        },
        "desktop_click_debugging": {
            "register": register_click_debugging_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Click debugging tools (highlight, verify coordinates)",
            "keywords": ["click", "debug", "highlight", "verify", "coordinates"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["debug clicking", "verify coordinates", "highlight targets"],
        },
        "desktop_vqa": {
            "register": register_vqa_two_stage_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Visual Question Answering for element location",
            "keywords": ["vqa", "visual", "ai", "vision", "locate"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": ["find elements visually", "AI-powered clicking"],
        },
        "desktop_vqa_two_stage": register_vqa_two_stage_tools,  # Alias
        # Individual tool names (backward compatibility)
        "desktop_screenshot_analyze": register_desktop_screenshot_tools,
        "desktop_get_screen_size": register_desktop_screenshot_tools,
        "desktop_mouse_move": register_mouse_control_tools,
        "desktop_mouse_click": register_mouse_control_tools,
        "desktop_mouse_drag": register_mouse_control_tools,
        "desktop_mouse_scroll": register_mouse_control_tools,
        "desktop_mouse_get_position": register_mouse_control_tools,
        "desktop_copy": register_keyboard_shortcut_tools,
        "desktop_paste": register_keyboard_shortcut_tools,
        "desktop_cut": register_keyboard_shortcut_tools,
        "desktop_select_all": register_keyboard_shortcut_tools,
        "desktop_save": register_keyboard_shortcut_tools,
        "desktop_undo": register_keyboard_shortcut_tools,
        "desktop_redo": register_keyboard_shortcut_tools,
        "desktop_find": register_keyboard_shortcut_tools,
        "desktop_new": register_keyboard_shortcut_tools,
        "desktop_open": register_keyboard_shortcut_tools,
        "desktop_close": register_keyboard_shortcut_tools,
        "desktop_quit": register_keyboard_shortcut_tools,
        "desktop_keyboard_type": register_keyboard_control_tools,
        "desktop_keyboard_press": register_keyboard_control_tools,
        "desktop_keyboard_hotkey": register_keyboard_control_tools,
        "desktop_keyboard_hold": register_keyboard_control_tools,
        "desktop_keyboard_release": register_keyboard_control_tools,
        "desktop_sleep": register_window_control_tools,
        "desktop_alert": register_window_control_tools,
        "desktop_confirm": register_window_control_tools,
        "desktop_prompt": register_window_control_tools,
        "desktop_focus_window": register_window_control_tools,
        "desktop_get_monitors": register_window_control_tools,
        "desktop_check_pixel_color": register_window_control_tools,
        "desktop_set_grid_density": register_grid_calibration_tools,
        "desktop_show_grid_test_pattern": register_grid_calibration_tools,
        "desktop_screenshot_with_confidence": register_grid_calibration_tools,
        "desktop_extract_text": register_ocr_tools,
        "desktop_find_text": register_ocr_tools,
        "desktop_verify_text": register_ocr_tools,
        "desktop_find_text_reliable": register_ocr_tools,
        "desktop_show_all_ocr_boxes": register_ocr_tools,
        "desktop_highlight_click_target": register_click_debugging_tools,
        "desktop_verify_coordinates": register_click_debugging_tools,
        "desktop_click_with_verification": register_click_debugging_tools,
        "desktop_hover_and_verify": register_click_debugging_tools,
        "desktop_click_smart": register_click_debugging_tools,
        "desktop_click_element_smart": register_multi_strategy_click_tools,
        "desktop_vqa_click_two_stage": register_vqa_two_stage_tools,  # Primary two-stage VQA tool
    }
)

# Add Accessibility API tools if available (macOS only)
if ACCESSIBILITY_TOOLS_AVAILABLE:
    TOOL_REGISTRY.update(
        {
            # Representative name (NEW - preferred) with metadata
            "macos_automation": {
                "register": register_accessibility_tools,
                "category": CATEGORY_DESKTOP,
                "description": "macOS Accessibility API (native UI automation)",
                "keywords": ["macos", "accessibility", "native", "ui", "automation"],
                "platform": "macos",
                "requires_typing": False,
                "use_cases": [
                    "macOS UI automation",
                    "native element clicking",
                    "macOS-specific automation",
                ],
            },
            # Individual tool names (backward compatibility)
            "desktop_find_accessible_element": register_accessibility_tools,
            "desktop_list_accessible_elements": register_accessibility_tools,
            "desktop_click_accessible_element": register_accessibility_tools,
            "desktop_get_accessible_element_value": register_accessibility_tools,
            "desktop_list_accessible_tree": register_accessibility_tools,
            "desktop_list_windows": register_accessibility_tools,
        }
    )

# Add Windows automation tools if available (Windows only)
if WINDOWS_TOOLS_AVAILABLE:
    TOOL_REGISTRY.update(
        {
            # Representative name (NEW - preferred) with metadata
            "windows_automation": {
                "register": register_windows_tools,
                "category": CATEGORY_DESKTOP,
                "description": "Windows UIA (native UI automation)",
                "keywords": ["windows", "uia", "native", "ui", "automation"],
                "platform": "windows",
                "requires_typing": False,
                "use_cases": [
                    "Windows UI automation",
                    "native element clicking",
                    "Windows-specific automation",
                ],
            },
            # Individual tool names (backward compatibility)
            "windows_focus_window": register_windows_tools,
            "windows_find_element": register_windows_tools,
            "windows_click_element": register_windows_tools,
            "windows_list_elements": register_windows_tools,
            "windows_list_windows": register_windows_tools,
            "windows_get_focused_element": register_windows_tools,
            "windows_get_element_value": register_windows_tools,
        }
    )


# Unified OS-aware tool names
TOOL_REGISTRY.update(
    {
        # Representative name (NEW - preferred) with metadata
        "ui_automation": {
            "register": register_os_unified_tools,
            "category": CATEGORY_DESKTOP,
            "description": "Cross-platform UI automation (auto-selects macOS/Windows API)",
            "keywords": ["ui", "automation", "cross-platform", "unified", "element"],
            "platform": "all",
            "requires_typing": False,
            "use_cases": [
                "cross-platform UI automation",
                "element clicking without platform-specific code",
            ],
        },
        # Individual tool names (backward compatibility)
        "ui_list_windows": register_os_unified_tools,
        "ui_list_elements": register_os_unified_tools,
        "ui_find_element": register_os_unified_tools,
        "ui_click_element": register_os_unified_tools,
    }
)


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
