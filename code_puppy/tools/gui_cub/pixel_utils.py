"""DPI-safe pixel sampling utilities with neighborhood strategies."""

from __future__ import annotations

from typing import Literal, Tuple

try:
    import pyautogui
    from PIL import Image
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None
    Image = None

from .platform import get_screen_scale_factor


def _to_rgb(val) -> Tuple[int, int, int]:
    if isinstance(val, (tuple, list)):
        return (int(val[0]), int(val[1]), int(val[2]))
    return (int(val), int(val), int(val))


def sample_neighborhood_rgb(
    x: int,
    y: int,
    neighborhood: int = 1,
) -> tuple[list[tuple[int, int, int]], tuple[int, int, int]]:
    """
    Sample an NxN neighborhood around (x, y) logical coordinates and return RGB values.

    **HiDPI/Retina Fix:** This function now calculates the scale factor directly from
    the screenshot dimensions rather than trusting get_screen_scale_factor(), which
    can incorrectly report 1.0x on Retina displays.

    Args:
        x: X coordinate in logical screen space (what the mouse uses)
        y: Y coordinate in logical screen space (what the mouse uses)
        neighborhood: Half-size of sampling window (0=single pixel, 1=3x3, 2=5x5)

    Returns:
        Tuple of (samples, center_rgb) where:
        - samples: List of RGB tuples from the neighborhood
        - center_rgb: RGB tuple of the center pixel

    Note:
        On a 2x Retina display, logical (500, 500) becomes physical (1000, 1000)
        in the screenshot. This function handles the conversion automatically.
    """
    if not PYAUTOGUI_AVAILABLE:
        raise ImportError("pyautogui/Pillow not available")

    # Take screenshot first
    screenshot = pyautogui.screenshot()
    
    # Calculate scale factor from screenshot dimensions (source of truth!)
    # This is more reliable than get_screen_scale_factor() which can report wrong values
    logical_width, logical_height = pyautogui.size()
    physical_width, physical_height = screenshot.size
    
    # Calculate scale (typically 1.0, 2.0, or other HiDPI factors)
    scale_x = physical_width / logical_width if logical_width > 0 else 1.0
    scale_y = physical_height / logical_height if logical_height > 0 else 1.0
    
    # Use the average scale (they should be the same on most displays)
    scale = (scale_x + scale_y) / 2
    
    # Convert logical coordinates to physical screenshot coordinates
    sx = int(x * scale)
    sy = int(y * scale)
    
    # Calculate neighborhood radius in both spaces
    radius = max(0, int(neighborhood))
    phys_radius = max(0, int(radius * scale))

    # Build list of physical coordinates to sample
    coords = [
        (sx + dx, sy + dy)
        for dy in range(-phys_radius, phys_radius + 1)
        for dx in range(-phys_radius, phys_radius + 1)
    ]
    
    # Clamp coordinates to screenshot bounds
    max_x = screenshot.size[0] - 1
    max_y = screenshot.size[1] - 1
    coords = [
        (max(0, min(cx, max_x)), max(0, min(cy, max_y)))
        for cx, cy in coords
    ]
    
    # Sample RGB values from screenshot
    samples = [_to_rgb(screenshot.getpixel(c)) for c in coords]
    center_idx = len(samples) // 2
    center_rgb = samples[center_idx] if samples else _to_rgb(screenshot.getpixel((sx, sy)))
    
    return samples, center_rgb


def match_rgb(
    samples: list[tuple[int, int, int]],
    expected: tuple[int, int, int],
    tolerance: int = 10,
    strategy: Literal["any", "all", "majority", "mean"] = "any",
) -> bool:
    """
    Determine if the sampled neighborhood matches expected RGB per strategy.
    """
    tol = int(tolerance)

    def within(rgb: tuple[int, int, int]) -> bool:
        return all(abs(a - e) <= tol for a, e in zip(rgb, expected))

    if not samples:
        return False

    if strategy == "all":
        return all(within(rgb) for rgb in samples)
    if strategy == "majority":
        hits = sum(1 for rgb in samples if within(rgb))
        return hits > (len(samples) // 2)
    if strategy == "mean":
        mean_rgb = tuple(int(sum(channel) / len(samples)) for channel in zip(*samples))
        return within(mean_rgb)
    return any(within(rgb) for rgb in samples)
