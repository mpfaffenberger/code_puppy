"""macOS Accessibility API tools for UI automation."""

from __future__ import annotations

from .element_finder import (
    ACCESSIBILITY_AVAILABLE,
    find_accessible_element,
    get_frontmost_app,
)
from .element_list import _list_macos_windows, list_accessible_elements
from .tools import register_accessibility_tools

__all__ = [
    "ACCESSIBILITY_AVAILABLE",
    "_list_macos_windows",
    "find_accessible_element",
    "get_frontmost_app",
    "list_accessible_elements",
    "register_accessibility_tools",
]
