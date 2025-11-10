"""Pure browser offset calculation logic."""

from __future__ import annotations

# Platform-specific title bar heights (pixels)
OS_TITLE_BAR_HEIGHTS: dict[str, int] = {
    "macos": 22,
    "windows": 30,
    "linux": 25,
}

DEFAULT_TITLE_BAR_HEIGHT = 25


def get_title_bar_height(platform: str) -> int:
    """
    Get OS title bar height for platform.
    
    Args:
        platform: Platform name ("macos", "windows", "linux")
        
    Returns:
        Title bar height in pixels
        
    Examples:
        >>> get_title_bar_height("macos")
        22
        >>> get_title_bar_height("windows")
        30
        >>> get_title_bar_height("unknown")
        25
    """
    return OS_TITLE_BAR_HEIGHTS.get(platform, DEFAULT_TITLE_BAR_HEIGHT)


def apply_chrome_offset(
    x: int,
    y: int,
    chrome_height: int,
    confidence: float = 1.0,
    confidence_threshold: float = 0.7,
) -> tuple[int, int]:
    """
    Apply browser chrome offset to coordinates.
    
    Args:
        x: X coordinate
        y: Y coordinate  
        chrome_height: Browser chrome height in pixels
        confidence: Detection confidence (0.0-1.0)
        confidence_threshold: Minimum confidence to apply offset
        
    Returns:
        Tuple of (adjusted_x, adjusted_y)
        
    Examples:
        >>> apply_chrome_offset(100, 50, 85)
        (100, 135)
        >>> apply_chrome_offset(100, 50, 85, confidence=0.5)
        (100, 50)
    """
    if confidence >= confidence_threshold:
        return (x, y + chrome_height)
    return (x, y)
