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

# RPA (Robotic Process Automation) tools - required dependencies
# Dependencies: pyautogui, pillow, opencv-python, pytesseract, openpyxl (installed via pyproject.toml)
from code_puppy.tools.rpa.keyboard_control import register_keyboard_control_tools
from code_puppy.tools.rpa.keyboard_shortcuts import register_keyboard_shortcut_tools
from code_puppy.tools.rpa.mouse_control import register_mouse_control_tools
from code_puppy.tools.rpa.screen_capture import register_desktop_screenshot_tools
from code_puppy.tools.rpa.window_control import register_window_control_tools
from code_puppy.tools.rpa.grid_calibration import register_grid_calibration_tools
from code_puppy.tools.rpa.ocr_tools import register_ocr_tools
from code_puppy.tools.rpa.click_debugging import register_click_debugging_tools
from code_puppy.tools.rpa.multi_strategy_click import register_multi_strategy_click_tools
from code_puppy.tools.rpa.vqa_hover_click import register_vqa_hover_tools

RPA_TOOLS_AVAILABLE = True  # Always available - required dependencies

# RPA Accessibility API tools (macOS only) - platform-specific
# Dependencies: atomacos, pyobjc-framework-Cocoa (installed on macOS via pyproject.toml)
try:
    from code_puppy.tools.rpa.accessibility import register_accessibility_tools

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
        from code_puppy.tools.rpa.windows_automation import register_windows_tools

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
from code_puppy.tools.rpa.os_unified import register_os_unified_tools
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
}

# Add RPA tools if available
if RPA_TOOLS_AVAILABLE:
    TOOL_REGISTRY.update(
        {
            # RPA - Screen Capture
            "desktop_screenshot": register_desktop_screenshot_tools,
            "desktop_screenshot_analyze": register_desktop_screenshot_tools,
            "desktop_get_screen_size": register_desktop_screenshot_tools,
            # RPA - Mouse Control
            "desktop_mouse_move": register_mouse_control_tools,
            "desktop_mouse_click": register_mouse_control_tools,
            "desktop_mouse_drag": register_mouse_control_tools,
            "desktop_mouse_scroll": register_mouse_control_tools,
            "desktop_mouse_get_position": register_mouse_control_tools,
            # RPA - Keyboard Shortcuts (platform-aware)
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
            # RPA - Keyboard Control (low-level)
            "desktop_keyboard_type": register_keyboard_control_tools,
            "desktop_keyboard_press": register_keyboard_control_tools,
            "desktop_keyboard_hotkey": register_keyboard_control_tools,
            "desktop_keyboard_hold": register_keyboard_control_tools,
            "desktop_keyboard_release": register_keyboard_control_tools,
            # RPA - Window and Utility Control
            "desktop_sleep": register_window_control_tools,
            "desktop_alert": register_window_control_tools,
            "desktop_confirm": register_window_control_tools,
            "desktop_prompt": register_window_control_tools,


            "desktop_focus_window": register_window_control_tools,
            "desktop_get_monitors": register_window_control_tools,
            "desktop_check_pixel_color": register_window_control_tools,
            # RPA - Grid Calibration (NEW!)
            "desktop_set_grid_density": register_grid_calibration_tools,
            "desktop_show_grid_test_pattern": register_grid_calibration_tools,
            "desktop_screenshot_with_confidence": register_grid_calibration_tools,
            # RPA - OCR Tools (NEW!)
            "desktop_extract_text": register_ocr_tools,
            "desktop_find_text": register_ocr_tools,
            "desktop_verify_text": register_ocr_tools,
            "desktop_find_text_reliable": register_ocr_tools,
            "desktop_show_all_ocr_boxes": register_ocr_tools,
            # RPA - Click Debugging Tools (NEW!)
            "desktop_highlight_click_target": register_click_debugging_tools,
            "desktop_verify_coordinates": register_click_debugging_tools,
            "desktop_click_with_verification": register_click_debugging_tools,
            "desktop_hover_and_verify": register_click_debugging_tools,
            "desktop_click_smart": register_click_debugging_tools,
            # RPA - Multi-Strategy Click (NEW!)
            "desktop_click_element_smart": register_multi_strategy_click_tools,

            # RPA - Simplified VQA Hover & Click (RECOMMENDED! - Single-shot VQA + hover verification)
            "desktop_find_and_hover": register_vqa_hover_tools,
            "desktop_find_and_click": register_vqa_hover_tools,
        }
    )

# Add Accessibility API tools if available (macOS only)
if ACCESSIBILITY_TOOLS_AVAILABLE:
    TOOL_REGISTRY.update(
        {
            # RPA - Accessibility API (macOS)
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
            # RPA - Windows UI Automation
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
TOOL_REGISTRY.update({
    "ui_list_windows": register_os_unified_tools,
    "ui_list_elements": register_os_unified_tools,
    "ui_find_element": register_os_unified_tools,
    "ui_click_element": register_os_unified_tools,
})

def register_tools_for_agent(agent, tool_names: list[str]):
    """Register specific tools for an agent based on tool names.

    Args:
        agent: The agent to register tools to.
        tool_names: List of tool names to register.
    """
    # Track which registration functions we've already called to avoid duplicates
    registered_funcs = set()

    for tool_name in tool_names:
        if tool_name not in TOOL_REGISTRY:
            # Skip unknown tools with a warning instead of failing
            emit_warning(f"Warning: Unknown tool '{tool_name}' requested, skipping...")
            continue

        # Register the individual tool
        register_func = TOOL_REGISTRY[tool_name]

        # Only call each registration function once (some functions register multiple tools)
        if register_func not in registered_funcs:
            register_func(agent)
            registered_funcs.add(register_func)


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