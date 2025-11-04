"""Constants and error messages for desktop automation tools."""

from __future__ import annotations

# Error messages for missing dependencies
ERROR_PYAUTOGUI_MISSING = (
    "desktop automation tools require pyautogui. Install with: uv pip install pyautogui"
)
ERROR_PILLOW_MISSING = (
    "Screenshot tools require Pillow. Install with: uv pip install pillow"
)
ERROR_OPENCV_MISSING = (
    "Image recognition requires opencv-python. Install with: uv pip install opencv-python"
)
ERROR_ATOMACOS_MISSING = (
    "Accessibility API requires atomacos. Install with: uv pip install atomacos"
)
ERROR_WINDOWS_AUTOMATION_MISSING = (
    "Windows automation not available. Install: uv pip install pywinauto pywin32"
)
ERROR_APPKIT_MISSING = (
    "AppKit (pyobjc-framework-Cocoa) required for focusing frontmost app"
)

# Platform-specific error messages
ERROR_MACOS_ONLY = "This tool is only available on macOS"
ERROR_WINDOWS_ONLY = "This tool is only available on Windows"
ERROR_LINUX_ONLY = "This tool is only available on Linux"

# Common error messages
ERROR_FAILSAFE_TRIGGERED = "FAILSAFE triggered - mouse moved to screen corner"
ERROR_ELEMENT_NOT_FOUND = "Element not found"
ERROR_WINDOW_NOT_FOUND = "Window not found"
ERROR_NO_FRONTMOST_APP = "Could not get frontmost application"
ERROR_CLICK_FAILED = "Click failed"
ERROR_SCREENSHOT_FAILED = "Screenshot capture failed"
ERROR_VQA_FAILED = "Visual analysis failed"

# Default values
DEFAULT_GRID_SPACING = 100  # pixels between grid lines
DEFAULT_MOUSE_DURATION = 0.25  # seconds for mouse movement
DEFAULT_PYAUTOGUI_PAUSE = 0.1  # seconds between pyautogui actions
DEFAULT_FAILSAFE = True  # Enable failsafe by default

# Timeout values
DEFAULT_WINDOW_FOCUS_TIMEOUT = 5  # seconds
DEFAULT_ALERT_TIMEOUT = 5000  # milliseconds

# Grid overlay defaults
GRID_LINE_COLOR = (255, 0, 0, 128)  # Red, semi-transparent (RGBA)
GRID_TEXT_COLOR = (255, 0, 0)  # Red (RGB)
GRID_LINE_WIDTH = 1  # pixels
