"""GUI-Cub tool registry.

All GUI-Cub related tools (workflows, config, desktop automation, OCR, VQA,
platform-specific tools) are registered here to keep the main tools/__init__.py
clean and minimize diff noise.
"""

import sys

# GUI-Cub workflow and knowledge base tools (always available)
from code_puppy.tools.gui_cub.workflows import (
    register_workflow_tools as register_gui_cub_workflows,
)
from code_puppy.tools.gui_cub.knowledge_base import (
    register_knowledge_base_tool as register_gui_cub_kb,
)
from code_puppy.tools.gui_cub.config_manager import (
    register_config_tools as register_gui_cub_config,
    register_debug_screenshot_tools as register_gui_cub_debug_screenshots,
)

# GUI-Cub desktop automation tools (always available - required dependencies)
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
from code_puppy.tools.gui_cub.vqa_two_stage_tools import register_vqa_two_stage_tools
from code_puppy.tools.gui_cub.os_unified import register_os_unified_tools

# macOS-specific tools
try:
    from code_puppy.tools.gui_cub.accessibility import register_accessibility_tools
    from code_puppy.tools.gui_cub.mac_app_launcher import (
        register_mac_app_launcher_tools,
    )

    ACCESSIBILITY_TOOLS_AVAILABLE = True
    MAC_APP_LAUNCHER_AVAILABLE = True
except ImportError:
    # Accessibility tools only available on macOS (atomacos, PyObjC)
    ACCESSIBILITY_TOOLS_AVAILABLE = False
    MAC_APP_LAUNCHER_AVAILABLE = False
    register_accessibility_tools = None
    register_mac_app_launcher_tools = None

# Windows automation tools - platform-specific (Windows only)
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


# Tool category constant
CATEGORY_DESKTOP = "Desktop Automation"

# Build the GUI-Cub tool registry
GUI_CUB_TOOLS = {}

# GUI-Cub workflow and knowledge base tools (always available)
GUI_CUB_TOOLS.update(
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
        "gui_cub_append_to_knowledge_base": register_gui_cub_kb,
        "gui_cub_get_config": register_gui_cub_config,
        "gui_cub_calibrate": register_gui_cub_config,
        "gui_cub_validate_config": register_gui_cub_config,
        "gui_cub_reset_config": register_gui_cub_config,
        "save_debug_screenshot": register_gui_cub_debug_screenshots,
    }
)

# Desktop automation tools (always available - required dependencies)
GUI_CUB_TOOLS.update(
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
        "desktop_vqa_click_two_stage": register_vqa_two_stage_tools,
    }
)

# Add Accessibility API tools if available (macOS only)
if ACCESSIBILITY_TOOLS_AVAILABLE:
    GUI_CUB_TOOLS.update(
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

# Add macOS app launcher if available (macOS only)
if MAC_APP_LAUNCHER_AVAILABLE:
    GUI_CUB_TOOLS.update(
        {
            "mac_launch_app": register_mac_app_launcher_tools,
        }
    )

# Add Windows automation tools if available (Windows only)
if WINDOWS_TOOLS_AVAILABLE:
    GUI_CUB_TOOLS.update(
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
GUI_CUB_TOOLS.update(
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
