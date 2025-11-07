"""Type stubs for GUI-CUB desktop automation tools.

Main entry point for all GUI-CUB functionality.
"""

import sys

# Re-export from submodules
from .screen_capture import screenshot, screenshot_analyze, get_screen_size
from .ocr import extract_text, find_text, verify_text
from .workflows import save_workflow, list_workflows, read_workflow
from .mouse_control import (
    desktop_mouse_move,
    desktop_mouse_click,
    desktop_mouse_drag,
    desktop_mouse_scroll,
    desktop_mouse_get_position,
    desktop_scroll_page,
)
from .keyboard_control import (
    desktop_keyboard_type,
    desktop_keyboard_press,
    desktop_keyboard_hotkey,
    desktop_keyboard_hold,
    desktop_keyboard_release,
)
from .window_control import (
    focus_window,
    get_active_window_bounds,
    desktop_focus_window,
    desktop_get_active_window,
)

# Platform-specific exports
if sys.platform == "darwin":
    from .accessibility import (
        find_accessible_element,
        list_accessible_elements,
        click_accessible_element,
    )

if sys.platform == "win32":
    from .windows_automation import (
        list_windows,
        # focus_window conflicts with window_control.focus_window
        find_element,
        click_element,
        list_elements_in_window,
    )

__all__ = [
    # Screenshot
    "screenshot",
    "screenshot_analyze",
    "get_screen_size",
    # OCR
    "extract_text",
    "find_text",
    "verify_text",
    # Workflows
    "save_workflow",
    "list_workflows",
    "read_workflow",
    # Mouse
    "desktop_mouse_move",
    "desktop_mouse_click",
    "desktop_mouse_drag",
    "desktop_mouse_scroll",
    "desktop_mouse_get_position",
    "desktop_scroll_page",
    # Keyboard
    "desktop_keyboard_type",
    "desktop_keyboard_press",
    "desktop_keyboard_hotkey",
    "desktop_keyboard_hold",
    "desktop_keyboard_release",
    # Window
    "focus_window",
    "get_active_window_bounds",
    "desktop_focus_window",
    "desktop_get_active_window",
    # Platform-specific (conditionally available)
    "find_accessible_element",
    "list_accessible_elements",
    "click_accessible_element",
    "list_windows",
    "find_element",
    "click_element",
    "list_elements_in_window",
]
