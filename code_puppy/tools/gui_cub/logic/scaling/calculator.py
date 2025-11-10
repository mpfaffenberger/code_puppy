"""Pure coordinate scaling calculations for HiDPI/Retina displays.

This module contains pure mathematical functions for converting between
screenshot coordinates (physical pixels) and screen coordinates (logical pixels),
separated from I/O operations for easy testing.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class DisplayMetrics:
    """Display metrics for scaling calculations."""
    logical_width: int
    logical_height: int
    physical_width: int
    physical_height: int


def calculate_scale_factor(metrics: DisplayMetrics) -> float:
    """Calculate screen scale factor from display metrics.
    
    Scale factor is the ratio of physical pixels to logical pixels.
    Common values: 1.0 (normal), 1.5 (150%), 2.0 (Retina/200%)
    
    Args:
        metrics: Display metrics with logical and physical dimensions
        
    Returns:
        Scale factor, rounded to nearest 0.25
        Returns 1.0 if metrics are invalid
    """
    # Validate metrics
    if metrics.logical_width <= 0 or metrics.logical_height <= 0:
        return 1.0
    
    if metrics.physical_width <= 0 or metrics.physical_height <= 0:
        return 1.0
    
    # Calculate scale from both dimensions
    scale_x = metrics.physical_width / metrics.logical_width
    scale_y = metrics.physical_height / metrics.logical_height
    
    # If x and y scales differ significantly, use x (width) as authoritative
    if abs(scale_x - scale_y) > 0.1:
        scale = scale_x
    else:
        # Average if they're close
        scale = (scale_x + scale_y) / 2.0
    
    # Round to nearest 0.25 (handles 1.25x, 1.5x, 1.75x, 2.0x, etc.)
    scale_rounded = round(scale * 4) / 4
    
    # Clamp to reasonable bounds [1.0, 4.0]
    scale_clamped = max(1.0, min(4.0, scale_rounded))
    
    return scale_clamped


def convert_physical_to_logical(
    physical_x: int,
    physical_y: int,
    scale_factor: float,
) -> Tuple[int, int]:
    """Convert physical screenshot coordinates to logical screen coordinates.
    
    On HiDPI/Retina displays, screenshots are captured at higher resolution
    (physical pixels) than the logical screen size (what the mouse uses).
    
    Args:
        physical_x: X coordinate from screenshot (physical pixels)
        physical_y: Y coordinate from screenshot (physical pixels)  
        scale_factor: Display scale factor (e.g., 2.0 for Retina)
        
    Returns:
        Tuple of (logical_x, logical_y) for mouse operations
        
    Example:
        >>> # On 2x Retina display
        >>> # OCR found text at (940, 250) in screenshot
        >>> logical_x, logical_y = convert_physical_to_logical(940, 250, 2.0)
        >>> print(logical_x, logical_y)  # (470, 125)
        >>> # Now click at (470, 125) with the mouse
    """
    if scale_factor <= 0:
        scale_factor = 1.0
    
    logical_x = int(physical_x / scale_factor)
    logical_y = int(physical_y / scale_factor)
    
    return logical_x, logical_y


def convert_logical_to_physical(
    logical_x: int,
    logical_y: int,
    scale_factor: float,
) -> Tuple[int, int]:
    """Convert logical screen coordinates to physical screenshot coordinates.
    
    Inverse of convert_physical_to_logical(). Useful when you have a mouse
    position and need to find it in a screenshot.
    
    Args:
        logical_x: X coordinate in logical screen space (mouse position)
        logical_y: Y coordinate in logical screen space (mouse position)
        scale_factor: Display scale factor (e.g., 2.0 for Retina)
        
    Returns:
        Tuple of (physical_x, physical_y) in screenshot space
        
    Example:
        >>> # Mouse at (100, 50) on 2x display
        >>> physical_x, physical_y = convert_logical_to_physical(100, 50, 2.0)
        >>> print(physical_x, physical_y)  # (200, 100)
    """
    if scale_factor <= 0:
        scale_factor = 1.0
    
    physical_x = int(logical_x * scale_factor)
    physical_y = int(logical_y * scale_factor)
    
    return physical_x, physical_y


def is_valid_scale_factor(scale_factor: float) -> bool:
    """Check if a scale factor is valid.
    
    Valid scale factors are positive numbers, typically in range [1.0, 4.0].
    Common values: 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0
    
    Args:
        scale_factor: Scale factor to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(scale_factor, (int, float)):
        return False
    
    if scale_factor <= 0:
        return False
    
    # Allow up to 4x scaling (uncommon but possible)
    if scale_factor > 4.0:
        return False
    
    return True


def calculate_aspect_ratio(width: int, height: int) -> float:
    """Calculate aspect ratio from dimensions.
    
    Args:
        width: Width in pixels
        height: Height in pixels
        
    Returns:
        Aspect ratio (width / height)
        Returns 0.0 if dimensions are invalid
    """
    if width <= 0 or height <= 0:
        return 0.0
    
    return width / height


def scales_match(scale_x: float, scale_y: float, tolerance: float = 0.1) -> bool:
    """Check if two scale factors match within tolerance.
    
    Used to verify that x and y scaling are consistent.
    
    Args:
        scale_x: Scale factor in X dimension
        scale_y: Scale factor in Y dimension
        tolerance: Maximum allowed difference (default: 0.1)
        
    Returns:
        True if scales match within tolerance, False otherwise
    """
    return abs(scale_x - scale_y) <= tolerance
