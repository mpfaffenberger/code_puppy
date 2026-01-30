"""Centralized debug screenshot temporary storage and management.

This module provides temporary screenshot storage for debug workflows,
allowing users to save debug images on-demand rather than cluttering their
working directory by default.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .dependencies import PIL_AVAILABLE

if PIL_AVAILABLE:
    from PIL import Image
else:
    Image = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from PIL import Image as PILImage

# Global temp directory for debug screenshots (NOT in user's pwd)
_TEMP_SCREENSHOT_DIR: Path | None = None
_LAST_SCREENSHOT_PATH: Path | None = None


def get_temp_screenshot_dir() -> Path:
    """Get or create temporary directory for screenshot storage.

    Uses system temp directory, not user's pwd.

    Returns:
        Path to temp screenshot directory
    """
    global _TEMP_SCREENSHOT_DIR
    if _TEMP_SCREENSHOT_DIR is None:
        _TEMP_SCREENSHOT_DIR = (
            Path(tempfile.gettempdir()) / "code_puppy_debug_screenshots"
        )
        _TEMP_SCREENSHOT_DIR.mkdir(exist_ok=True)
    return _TEMP_SCREENSHOT_DIR


def save_temp_debug_screenshot(
    image: Image.Image,
    name: str,
    group_id: str | None = None,
) -> Path:
    """Save screenshot to temp directory and track as last screenshot.

    This does NOT save to the user's working directory - it saves to system temp.
    Use copy_last_screenshot_to_pwd() to copy to pwd on demand.

    Args:
        image: PIL Image to save
        name: Descriptive name (e.g., "stage1_crop", "ocr_region")
        group_id: Optional message group ID for organized cleanup

    Returns:
        Path to saved temp screenshot
    """
    global _LAST_SCREENSHOT_PATH

    temp_dir = get_temp_screenshot_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    if group_id:
        filename = f"{timestamp}_{group_id}_{name}.png"
    else:
        filename = f"{timestamp}_{name}.png"

    path = temp_dir / filename
    image.save(path)
    _LAST_SCREENSHOT_PATH = path

    return path


def copy_last_screenshot_to_pwd(filename: str | None = None) -> Path | None:
    """Copy the last saved temp screenshot to current working directory.

    This can be called programmatically by agents that need to save debug images
    on request.

    Args:
        filename: Optional custom filename (default: auto-generated with timestamp)

    Returns:
        Path to copied file in pwd, or None if no screenshot available
    """
    global _LAST_SCREENSHOT_PATH

    if _LAST_SCREENSHOT_PATH is None:
        return None

    if filename is None:
        # Auto-generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"debug_screenshot_{timestamp}.png"

    dest_path = Path.cwd() / filename

    # Use try/except instead of exists() check to avoid TOCTOU race
    try:
        shutil.copy2(_LAST_SCREENSHOT_PATH, dest_path)
        return dest_path
    except FileNotFoundError:
        return None


def cleanup_old_temp_screenshots(max_age_hours: int = 24) -> int:
    """Clean up old temporary screenshots.

    Args:
        max_age_hours: Maximum age in hours before deletion (default: 24)

    Returns:
        Number of files deleted
    """
    temp_dir = get_temp_screenshot_dir()

    if not temp_dir.exists():
        return 0

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted = 0

    for file_path in temp_dir.glob("*.png"):
        if current_time - file_path.stat().st_mtime > max_age_seconds:
            file_path.unlink()
            deleted += 1

    return deleted
