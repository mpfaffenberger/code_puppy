"""Smart window control button detection with fallback hierarchy.

This module implements a robust strategy for finding and clicking window control
buttons (minimize, maximize, close) on macOS and Windows:

1. Accessibility API (fastest, most reliable)
2. Geometry heuristics (known offsets for standard UI)
3. Geometry heuristics (fast, robust for standard UI) (no template matching)
4. VQA (slowest, most flexible)

Key insight: Don't jump to VQA first - use knowledge about OS UI conventions!
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

from ..dependencies import (
    CV2_AVAILABLE,
    DEPS_AVAILABLE,
    PIL_AVAILABLE,
    PYAUTOGUI_AVAILABLE,
)

if DEPS_AVAILABLE:
    import numpy as np
else:
    np = None

if PIL_AVAILABLE:
    from PIL import Image
else:
    Image = None

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if CV2_AVAILABLE:
    import cv2
else:
    cv2 = None


from code_puppy.messaging import emit_info, emit_warning

from ..platform import IS_MACOS, IS_WINDOWS
from ..window_control import _get_active_window_bounds_impl
from ..accessibility import find_accessible_element

# Template cache for faster loading


class WindowButton(str, Enum):
    """Standard window control buttons."""

    CLOSE = "close"
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"  # Zoom on macOS


@dataclass
class ButtonLocation:
    """Detected button location with confidence."""

    x: int
    y: int
    confidence: float
    method: str  # "accessibility", "heuristic", "cv", "vqa"


class MacOSTrafficLightOffsets:
    """Known offsets for macOS traffic light buttons.

    Based on Apple Human Interface Guidelines and empirical testing.
    All coordinates are relative to window's top-left corner (including title bar).
    """

    # Standard offsets for macOS (logical pixels)
    # Title bar is typically 40px tall on modern macOS
    TITLE_BAR_HEIGHT = 40

    # Button positions from top-left of window (including title bar)
    # These are centers of the buttons
    CLOSE_X = 20
    CLOSE_Y = 20

    MINIMIZE_X = 40
    MINIMIZE_Y = 20

    MAXIMIZE_X = 60  # "Zoom" on macOS
    MAXIMIZE_Y = 20

    # Button radius (for hit testing)
    BUTTON_RADIUS = 8

    # Tolerance for position variations (some apps customize slightly)
    POSITION_TOLERANCE = 5


class WindowsControlOffsets:
    """Known offsets for Windows window control buttons."""

    # Windows buttons are typically in top-right
    # These vary more by theme/DPI
    BUTTON_WIDTH = 45
    BUTTON_HEIGHT = 30

    # From top-right corner
    CLOSE_OFFSET_X = -45
    MAXIMIZE_OFFSET_X = -90
    MINIMIZE_OFFSET_X = -135

    # Y is typically titlebar height / 2
    TITLE_BAR_HEIGHT = 30


async def _try_accessibility_api(
    window_title: str | None,
    button: WindowButton,
    group_id: str,
) -> ButtonLocation | None:
    """
    Try to find button using Accessibility API.

    This is the fastest and most reliable method when it works.
    """
    emit_info(
        f"[cyan]🔍 Method 1: Trying Accessibility API for '{button.value}' button[/cyan]",
        message_group=group_id,
    )

    try:
        if IS_MACOS:
            # Map button names to accessibility roles
            role_map = {
                WindowButton.CLOSE: "AXCloseButton",
                WindowButton.MINIMIZE: "AXMinimizeButton",
                WindowButton.MAXIMIZE: "AXZoomButton",  # macOS calls it "zoom"
            }

            role = role_map.get(button)
            if not role:
                return None

            # Try to find the button
            result = await asyncio.to_thread(
                find_accessible_element,
                role=role,
                title=None,  # These buttons typically don't have titles
                fuzzy=False,
            )

            if result.success and result.element_info:
                x = result.element_info.get("x")
                y = result.element_info.get("y")

                if x is not None and y is not None:
                    emit_info(
                        f"[green]✅ Found via Accessibility API at ({x}, {y})[/green]",
                        message_group=group_id,
                    )
                    return ButtonLocation(
                        x=int(x),
                        y=int(y),
                        confidence=1.0,
                        method="accessibility",
                    )

            emit_info(
                "[dim]   ❌ Not found via Accessibility API[/dim]",
                message_group=group_id,
            )
            return None
        elif IS_WINDOWS:
            # Try pywinauto if available to retrieve standard caption buttons
            try:
                from pywinauto import Desktop

                d = Desktop(backend="uia")
                app_win = (
                    d.window(title_re=window_title) if window_title else d.active()
                )
                if app_win.exists():
                    # Windows convention: control type Button with names 'Minimize', 'Maximize', 'Close'
                    name_map = {
                        WindowButton.MINIMIZE: "Minimize",
                        WindowButton.MAXIMIZE: "Maximize",
                        WindowButton.CLOSE: "Close",
                    }
                    target_name = name_map[button]
                    try:
                        btn = app_win.child_window(
                            title=target_name, control_type="Button"
                        )
                        rect = btn.rectangle()
                        x = int((rect.left + rect.right) / 2)
                        y = int((rect.top + rect.bottom) / 2)
                        emit_info(
                            f"[green]✅ Found via Windows UIA at ({x}, {y})[/green]",
                            message_group=group_id,
                        )
                        return ButtonLocation(x=x, y=y, confidence=0.95, method="uia")
                    except Exception:
                        emit_info(
                            "[dim]   ❌ Not found via Windows UIA[/dim]",
                            message_group=group_id,
                        )
                        return None
                else:
                    emit_info(
                        "[dim]   ❌ Active window not found via Windows UIA[/dim]",
                        message_group=group_id,
                    )
                    return None
            except Exception as e:
                emit_warning(
                    f"[yellow]⚠️  Windows UIA failed: {e}[/yellow]",
                    message_group=group_id,
                )
                return None
        else:
            emit_info(
                "[dim]   ⏭️  Accessibility path not implemented on this platform[/dim]",
                message_group=group_id,
            )
            return None

    except Exception as e:
        emit_warning(
            f"[yellow]⚠️  Accessibility API failed: {e}[/yellow]",
            message_group=group_id,
        )
        return None


async def _try_geometry_heuristics(
    window_title: str | None,
    button: WindowButton,
    group_id: str,
) -> ButtonLocation | None:
    """
    Use known geometry offsets for standard OS window controls.

    This is fast (<1ms) and works for apps that follow OS conventions.
    """
    emit_info(
        f"[cyan]🔍 Method 3: Trying Geometry Heuristics for '{button.value}' button[/cyan]",
        message_group=group_id,
    )

    # Get active window bounds
    bounds_result = _get_active_window_bounds_impl()

    if not bounds_result.success:
        emit_warning(
            f"[yellow]⚠️  Could not get window bounds: {bounds_result.error}[/yellow]",
            message_group=group_id,
        )
        return None

    emit_info(
        f"[dim]   Window bounds: ({bounds_result.x}, {bounds_result.y}) "
        f"{bounds_result.width}x{bounds_result.height}[/dim]",
        message_group=group_id,
    )

    if IS_MACOS:
        # macOS: Traffic lights in top-left
        # CRITICAL: CGWindowListCopyWindowInfo returns bounds WITHOUT title bar!
        # So we need to adjust Y coordinate upward

        button_offset_map = {
            WindowButton.CLOSE: (
                MacOSTrafficLightOffsets.CLOSE_X,
                MacOSTrafficLightOffsets.CLOSE_Y,
            ),
            WindowButton.MINIMIZE: (
                MacOSTrafficLightOffsets.MINIMIZE_X,
                MacOSTrafficLightOffsets.MINIMIZE_Y,
            ),
            WindowButton.MAXIMIZE: (
                MacOSTrafficLightOffsets.MAXIMIZE_X,
                MacOSTrafficLightOffsets.MAXIMIZE_Y,
            ),
        }

        offset_x, offset_y = button_offset_map[button]

        # Calculate button position
        # Window bounds Y is at TOP of content area (below title bar)
        # Need to go UP by (title_bar_height - button_y_offset)
        button_x = bounds_result.x + offset_x
        button_y = bounds_result.y - (
            MacOSTrafficLightOffsets.TITLE_BAR_HEIGHT - offset_y
        )

        emit_info(
            f"[green]✅ Calculated position via heuristics:[/green]\n"
            f"[dim]   Window top-left: ({bounds_result.x}, {bounds_result.y})[/dim]\n"
            f"[dim]   Title bar offset: -{MacOSTrafficLightOffsets.TITLE_BAR_HEIGHT}px[/dim]\n"
            f"[dim]   Button offset from window origin: (+{offset_x}, +{offset_y})[/dim]\n"
            f"[dim]   Final position: ({button_x}, {button_y})[/dim]",
            message_group=group_id,
        )

        return ButtonLocation(
            x=button_x,
            y=button_y,
            confidence=0.85,  # High confidence for standard macOS
            method="heuristic",
        )

    elif IS_WINDOWS:
        # Windows: Controls in top-right
        button_offset_map = {
            WindowButton.CLOSE: WindowsControlOffsets.CLOSE_OFFSET_X,
            WindowButton.MAXIMIZE: WindowsControlOffsets.MAXIMIZE_OFFSET_X,
            WindowButton.MINIMIZE: WindowsControlOffsets.MINIMIZE_OFFSET_X,
        }

        offset_x = button_offset_map[button]

        button_x = (
            bounds_result.x
            + bounds_result.width
            + offset_x
            + (WindowsControlOffsets.BUTTON_WIDTH // 2)
        )
        button_y = bounds_result.y + (WindowsControlOffsets.TITLE_BAR_HEIGHT // 2)

        emit_info(
            f"[green]✅ Calculated position via heuristics at ({button_x}, {button_y})[/green]",
            message_group=group_id,
        )

        return ButtonLocation(
            x=button_x,
            y=button_y,
            confidence=0.75,  # Medium confidence (varies by theme)
            method="heuristic",
        )

    emit_warning(
        "[yellow]⚠️  Platform not supported for heuristics[/yellow]",
        message_group=group_id,
    )
    return None


# Template matching removed - was dead code with orphaned docstrings
# The _load_template function referenced below doesn't exist
