"""Coordinate conversion utilities for window-relative RPA operations.

This module provides utilities for converting between window-relative and
screen-absolute coordinates, enabling more portable and focused RPA workflows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .result_types import WindowBoundsResult


def window_to_screen_coords(
    window_x: int,
    window_y: int,
    window_bounds: WindowBoundsResult | None = None,
) -> tuple[int, int]:
    """
    Convert window-relative coordinates to screen-absolute coordinates.

    This is useful for converting VQA results (which are window-relative)
    to screen coordinates for mouse operations.

    Args:
        window_x: X coordinate relative to window top-left
        window_y: Y coordinate relative to window top-left
        window_bounds: Window bounds result. If None, gets active window.

    Returns:
        Tuple of (screen_x, screen_y) in absolute screen coordinates

    Raises:
        ValueError: If window bounds cannot be obtained

    Examples:
        >>> # Window at (100, 50), button at (200, 150) within window
        >>> from .window_control import desktop_get_active_window
        >>> bounds = desktop_get_active_window(None)
        >>> screen_x, screen_y = window_to_screen_coords(200, 150, bounds)
        >>> print(screen_x, screen_y)  # (300, 200)
    """
    if window_bounds is None:
        # Lazy import to avoid circular dependency
        from .window_control import _get_active_window_bounds_impl

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            raise ValueError(
                f"Could not get active window bounds: {bounds.error or 'Unknown error'}"
            )
        window_bounds = bounds

    if window_bounds.x is None or window_bounds.y is None:
        raise ValueError("Window bounds missing x/y coordinates")

    screen_x = window_bounds.x + window_x
    screen_y = window_bounds.y + window_y

    return screen_x, screen_y


def screen_to_window_coords(
    screen_x: int,
    screen_y: int,
    window_bounds: WindowBoundsResult | None = None,
) -> tuple[int, int]:
    """
    Convert screen-absolute coordinates to window-relative coordinates.

    This is useful for converting screen coordinates to window-relative
    coordinates for VQA analysis or element location.

    Args:
        screen_x: X coordinate in absolute screen space
        screen_y: Y coordinate in absolute screen space
        window_bounds: Window bounds result. If None, gets active window.

    Returns:
        Tuple of (window_x, window_y) relative to window top-left

    Raises:
        ValueError: If window bounds cannot be obtained

    Examples:
        >>> # Window at (100, 50), click at screen (300, 200)
        >>> from .window_control import desktop_get_active_window
        >>> bounds = desktop_get_active_window(None)
        >>> win_x, win_y = screen_to_window_coords(300, 200, bounds)
        >>> print(win_x, win_y)  # (200, 150)
    """
    if window_bounds is None:
        # Lazy import to avoid circular dependency
        from .window_control import _get_active_window_bounds_impl

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            raise ValueError(
                f"Could not get active window bounds: {bounds.error or 'Unknown error'}"
            )
        window_bounds = bounds

    if window_bounds.x is None or window_bounds.y is None:
        raise ValueError("Window bounds missing x/y coordinates")

    window_x = screen_x - window_bounds.x
    window_y = screen_y - window_bounds.y

    return window_x, window_y


# TODO: Future optimization - Cache window bounds for repeated operations
# This could significantly speed up workflows that do multiple operations
# on the same window without refocusing.
#
# class WindowBoundsCache:
#     """Cache window bounds to avoid repeated system calls."""
#
#     def __init__(self, ttl: float = 5.0):
#         """Initialize cache with time-to-live in seconds."""
#         self._cache: dict[str, tuple[WindowBoundsResult, float]] = {}
#         self._ttl = ttl
#
#     def get_bounds(self, window_title: str | None = None) -> WindowBoundsResult:
#         """Get cached bounds or fetch fresh if stale."""
#         import time
#         cache_key = window_title or "__active__"
#         now = time.time()
#
#         # Check cache
#         if cache_key in self._cache:
#             bounds, cached_at = self._cache[cache_key]
#             if now - cached_at < self._ttl:
#                 return bounds
#
#         # Fetch fresh
#         from .window_control import desktop_get_active_window
#         bounds = desktop_get_active_window(None)
#         self._cache[cache_key] = (bounds, now)
#         return bounds
#
#     def invalidate(self, window_title: str | None = None):
#         """Clear cache for specific window or all windows."""
#         if window_title is None:
#             self._cache.clear()
#         else:
#             self._cache.pop(window_title, None)
