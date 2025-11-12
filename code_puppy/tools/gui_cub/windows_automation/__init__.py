"""Windows UI Automation tools."""

from __future__ import annotations

from .core import (
    WINDOWS_AUTOMATION_AVAILABLE,
    click_element,
    find_element,
    focus_window,
    get_element_value_by_pid,
    get_focused_element_by_pid,
    list_elements_in_window,
    list_windows,
    search_text_in_elements,
)
from .tools import register_windows_tools

__all__ = [
    "WINDOWS_AUTOMATION_AVAILABLE",
    "click_element",
    "find_element",
    "focus_window",
    "get_element_value_by_pid",
    "get_focused_element_by_pid",
    "list_elements_in_window",
    "list_windows",
    "register_windows_tools",
    "search_text_in_elements",
]
