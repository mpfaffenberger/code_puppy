"""Screen capture and visual analysis for desktop automation.

This package provides screenshot capture, image manipulation, and VQA analysis
functionality split into focused modules under 600 lines each.
"""

from __future__ import annotations

from .capture import build_screenshot_path, capture_screen, screenshot
from .image_utils import (
    VQA_MAX_IMAGE_SIZE_BYTES,
    VQA_MAX_RESOLUTION,
    add_coordinate_grid,
    resize_image_if_needed,
)
from .tools import register_desktop_screenshot_tools
from .screenshot_analyze import screenshot_analyze
from .take_screenshot import take_desktop_screenshot_and_analyze

__all__ = [
    # Capture functions
    "build_screenshot_path",
    "capture_screen",
    "screenshot",
    # Image utils
    "add_coordinate_grid",
    "resize_image_if_needed",
    "VQA_MAX_IMAGE_SIZE_BYTES",
    "VQA_MAX_RESOLUTION",
    # VQA analysis
    "screenshot_analyze",
    "take_desktop_screenshot_and_analyze",
    # Tool registration
    "register_desktop_screenshot_tools",
]
