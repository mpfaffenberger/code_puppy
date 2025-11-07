"""Type stubs for mouse control operations.

Provides mouse movement, clicking, dragging, and scrolling.
"""

from typing import Literal
from pydantic_ai import RunContext
from ..result_types import (
    MouseActionResult,
    MouseDragResult,
    MousePositionResult,
    MouseScrollResult,
)

def desktop_mouse_move(
    context: RunContext,
    x: int,
    y: int,
    duration: float = ...,
) -> MouseActionResult:
    """Move mouse to coordinates.

    Args:
        context: Agent context
        x: Target X coordinate
        y: Target Y coordinate
        duration: Movement duration in seconds

    Returns:
        MouseActionResult with success status
    """
    ...

def desktop_mouse_click(
    context: RunContext,
    x: int | None = ...,
    y: int | None = ...,
    button: Literal["left", "right", "middle"] = ...,
    clicks: int = ...,
    interval: float = ...,
) -> MouseActionResult:
    """Click mouse at coordinates.

    Args:
        context: Agent context
        x: Click X coordinate (None = current position)
        y: Click Y coordinate (None = current position)
        button: Mouse button to click
        clicks: Number of clicks (1=single, 2=double)
        interval: Interval between clicks

    Returns:
        MouseActionResult with success status
    """
    ...

def desktop_mouse_drag(
    context: RunContext,
    x: int,
    y: int,
    duration: float = ...,
    button: Literal["left", "right", "middle"] = ...,
) -> MouseDragResult:
    """Drag mouse from current position to target.

    Args:
        context: Agent context
        x: Target X coordinate
        y: Target Y coordinate
        duration: Drag duration in seconds
        button: Mouse button to hold

    Returns:
        MouseDragResult with drag info
    """
    ...

def desktop_mouse_scroll(
    context: RunContext,
    clicks: int,
    x: int | None = ...,
    y: int | None = ...,
) -> MouseScrollResult:
    """Scroll mouse wheel.

    Args:
        context: Agent context
        clicks: Scroll amount (positive=up, negative=down)
        x: Optional X position to scroll at
        y: Optional Y position to scroll at

    Returns:
        MouseScrollResult with scroll info
    """
    ...

def desktop_mouse_get_position(
    context: RunContext,
) -> MousePositionResult:
    """Get current mouse position.

    Args:
        context: Agent context

    Returns:
        MousePositionResult with x, y coordinates
    """
    ...

def desktop_scroll_page(
    context: RunContext,
    direction: Literal["up", "down", "page_up", "page_down"],
    pages: int = ...,
) -> MouseScrollResult:
    """Scroll by pages.

    Args:
        context: Agent context
        direction: Scroll direction
        pages: Number of pages to scroll

    Returns:
        MouseScrollResult with scroll info
    """
    ...
