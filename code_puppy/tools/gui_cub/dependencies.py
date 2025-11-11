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

# OpenCV - Computer vision
try:
    import cv2  # noqa: F401

    CV2_AVAILABLE = True
    OPENCV_AVAILABLE = True  # Alias for compatibility
except ImportError:
    CV2_AVAILABLE = False
    OPENCV_AVAILABLE = False

# NumPy - Numerical computing (often used with PIL/CV2)
try:
    import numpy  # noqa: F401

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

# atomacos - macOS accessibility API
try:
    import atomacos  # noqa: F401

    ATOMACOS_AVAILABLE = True
except ImportError:
    ATOMACOS_AVAILABLE = False

# Windows automation libraries (pywinauto, win32gui)
try:
    import win32gui  # noqa: F401
    from pywinauto import Application  # noqa: F401

    WINDOWS_AUTOMATION_AVAILABLE = True
except ImportError:
    WINDOWS_AUTOMATION_AVAILABLE = False

# Combined dependency checks for common combinations
DEPS_AVAILABLE = PIL_AVAILABLE and NUMPY_AVAILABLE
VISION_AVAILABLE = CV2_AVAILABLE and NUMPY_AVAILABLE

# Export all availability flags
__all__ = [
    "PYAUTOGUI_AVAILABLE",
    "PIL_AVAILABLE",
    "CV2_AVAILABLE",
    "OPENCV_AVAILABLE",
    "NUMPY_AVAILABLE",
    "ATOMACOS_AVAILABLE",
    "WINDOWS_AUTOMATION_AVAILABLE",
    "DEPS_AVAILABLE",
    "VISION_AVAILABLE",
]
