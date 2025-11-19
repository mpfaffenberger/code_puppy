"""Centralized dependency availability checking for GUI automation tools.

This module provides a single source of truth for checking which optional
dependencies are available. Instead of duplicating try/except import logic
across 20+ files, all availability flags are defined here.

Usage:
    from code_puppy.tools.gui_cub.dependencies import PYAUTOGUI_AVAILABLE, PIL_AVAILABLE

    if PYAUTOGUI_AVAILABLE:
        import pyautogui
        pyautogui.moveTo(100, 100)
"""

from __future__ import annotations

import sys

# Platform detection (same as platform.py to avoid circular import)
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

# PyAutoGUI - Core desktop automation library
try:
    import pyautogui  # noqa: F401

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# PIL/Pillow - Image processing
try:
    from PIL import Image  # noqa: F401

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


# NumPy - Numerical computing (often used with PIL)
try:
    import numpy  # noqa: F401

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# atomacos - macOS accessibility API (macOS-only)
if IS_MACOS:
    try:
        import atomacos  # noqa: F401

        ATOMACOS_AVAILABLE = True
    except ImportError:
        ATOMACOS_AVAILABLE = False
else:
    ATOMACOS_AVAILABLE = False  # Not available on non-macOS platforms

# Windows automation libraries - pywinauto, win32gui (Windows-only)
if IS_WINDOWS:
    try:
        import win32gui  # noqa: F401
        from pywinauto import Application  # noqa: F401

        WINDOWS_AUTOMATION_AVAILABLE = True
    except ImportError:
        WINDOWS_AUTOMATION_AVAILABLE = False
else:
    WINDOWS_AUTOMATION_AVAILABLE = False  # Not available on non-Windows platforms

# Combined dependency checks for common combinations
DEPS_AVAILABLE = PIL_AVAILABLE and NUMPY_AVAILABLE

# Export all availability flags
__all__ = [
    "PYAUTOGUI_AVAILABLE",
    "PIL_AVAILABLE",
    "NUMPY_AVAILABLE",
    "ATOMACOS_AVAILABLE",
    "WINDOWS_AUTOMATION_AVAILABLE",
    "DEPS_AVAILABLE",
]
