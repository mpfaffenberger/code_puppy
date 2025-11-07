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
from code_puppy.tools.gui_cub.ocr_tools import register_ocr_tools
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
        # Representative names (NEW - preferred)
        "gui_cub_workflows": register_gui_cub_workflows,  # Registers: save, list, read
        "gui_cub_config": register_gui_cub_config,  # Registers: get, calibrate, validate, reset
        "gui_cub_debug": register_gui_cub_debug_screenshots,  # Registers: save_debug_screenshot
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
        # Representative names (NEW - preferred)
        "desktop_screenshot": register_desktop_screenshot_tools,  # Registers: screenshot, analyze, get_screen_size
        "desktop_mouse": register_mouse_control_tools,  # Registers: move, click, drag, scroll, get_position
        "desktop_shortcuts": register_keyboard_shortcut_tools,  # Registers: copy, paste, cut, select_all, save, undo, redo, find, new, open, close, quit
        "desktop_keyboard": register_keyboard_control_tools,  # Registers: type, press, hotkey, hold, release
        "desktop_window_control": register_window_control_tools,  # Registers: sleep, alert, confirm, prompt, focus_window, get_monitors, check_pixel_color
        "desktop_grid_calibration": register_grid_calibration_tools,  # Registers: set_density, show_test_pattern, screenshot_with_confidence
        "desktop_ocr": register_ocr_tools,  # Registers: extract_text, find_text, verify_text, find_text_reliable, show_all_ocr_boxes
        "desktop_click_debugging": register_click_debugging_tools,  # Registers: highlight, verify_coordinates, click_with_verification, hover_and_verify, click_smart
        "desktop_vqa": register_vqa_two_stage_tools,  # Two-stage VQA (93% success, 2.1px error)
        "desktop_vqa_two_stage": register_vqa_two_stage_tools,  # Alias for desktop_vqa
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
            # Representative name (NEW - preferred)
            "macos_automation": register_accessibility_tools,  # Registers: find, list, click, get_value, list_tree, list_windows
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
            # Representative name (NEW - preferred)
            "windows_automation": register_windows_tools,  # Registers: focus_window, find, click, list_elements, list_windows, get_focused, get_value
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
        # Representative name (NEW - preferred)
        "ui_automation": register_os_unified_tools,  # Registers: ui_list_windows, ui_list_elements, ui_find_element, ui_click_element
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
    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Register the individual tool
        register_func = TOOL_REGISTRY[tool_name]
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
