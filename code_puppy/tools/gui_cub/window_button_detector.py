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

try:
    import numpy as np
    from PIL import Image
    import pyautogui
    import cv2

    DEPS_AVAILABLE = True
    CV2_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False
    CV2_AVAILABLE = False
    np = None
    Image = None
    pyautogui = None
    cv2 = None


from code_puppy.messaging import emit_info, emit_warning, emit_error
from code_puppy.tools.common import generate_group_id

from .platform import IS_MACOS, IS_WINDOWS
from .screen_capture import capture_screen
from .window_control import _get_active_window_bounds_impl
from .accessibility import find_accessible_element

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


def _detect_button_via_template_matching(
    button: WindowButton,
    group_id: str | None = None,
) -> ButtonLocation | None:
    """
    [removed] template matching logic removed per policy.

    Fast, deterministic method using pre-generated templates.
    Works best for standard OS controls (macOS traffic lights, Windows captions).
    """
    if not IS_MACOS:
        return None  # Currently only macOS templates implemented

    emit_info(
        f"[cyan]🔍 Method 2: Trying Template Matching for '{button.value}' button[/cyan]",
        message_group=group_id,
    )

    if not CV2_AVAILABLE:
        emit_warning(
            "[yellow]⚠️  OpenCV-dependent template matching removed[/yellow]",
            message_group=group_id,
        )
        return None

    try:
        # Get window bounds
        bounds_result = _get_active_window_bounds_impl()
        if not bounds_result.success:
            return None

        # Note: scale_factor removed - was unused after template matching disabled

        # Capture title bar area (similar to color detection)
        title_bar_height = 50
        capture_x = bounds_result.x
        capture_y = bounds_result.y - MacOSTrafficLightOffsets.TITLE_BAR_HEIGHT
        capture_w = min(200, bounds_result.width)  # Only need left 200px
        capture_h = title_bar_height

        # Ensure we're not going off-screen
        if capture_y < 0:
            capture_h += capture_y
            capture_y = 0

        # Capture screenshot
        screenshot_result = capture_screen(
            region=(capture_x, capture_y, capture_w, capture_h),
            save_screenshot=False,
        )

        if not screenshot_result.success or not screenshot_result.screenshot_data:
            return None

        # Convert to OpenCV format
        import io

        img = Image.open(io.BytesIO(screenshot_result.screenshot_data))
        img_bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Try focused state first, then unfocused
        # NOTE: _load_template function was removed - template matching disabled
        emit_warning(
            "[yellow]⚠️  Template matching disabled (templates not available)[/yellow]",
            message_group=group_id,
        )
        return None

        # Dead code below - kept for reference but unreachable
        best_match = None
        best_confidence = 0.0

        for state in ["focused", "focused_light_2x_hover", "unfocused"]:
            # Load template - function doesn't exist
            template = None  # _load_template(button, scale_factor, state.split('_')[0])
            if template is None:
                continue

            # Handle transparency (alpha channel)
            if template.shape[2] == 4:  # RGBA
                # Create mask from alpha channel
                alpha = template[:, :, 3]
                template_bgr = cv2.cvtColor(template, cv2.COLOR_BGRA2BGR)
                mask = alpha
            else:
                template_bgr = template
                mask = None

            # [removed] template matching step removed
            if mask is not None:
                result = cv2.matchTemplate(
                    img_bgr, template_bgr, cv2.TM_CCORR_NORMED, mask=mask
                )
            else:
                result = cv2.matchTemplate(img_bgr, template_bgr, cv2.TM_CCOEFF_NORMED)

            # Get best match location
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val > best_confidence:
                best_confidence = max_val
                # Calculate center of matched region
                template_h, template_w = template_bgr.shape[:2]
                match_center_x = max_loc[0] + template_w // 2
                match_center_y = max_loc[1] + template_h // 2
                best_match = (match_center_x, match_center_y)

                emit_info(
                    f"[dim]   Template '{state}' matched with confidence: {max_val:.2%}[/dim]",
                    message_group=group_id,
                )

        # Check if match is good enough
        CONFIDENCE_THRESHOLD = 0.75  # 75% match required

        if best_match and best_confidence >= CONFIDENCE_THRESHOLD:
            # Convert back to screen coordinates
            screen_x = capture_x + best_match[0]
            screen_y = capture_y + best_match[1]

            emit_info(
                f"[yellow]ℹ️ Template matching removed; using other methods instead[/yellow]\n"
                f"[dim]   Confidence: {best_confidence:.2%}[/dim]",
                message_group=group_id,
            )

            return ButtonLocation(
                x=screen_x,
                y=screen_y,
                confidence=best_confidence,
                method="template_matching",
            )

        emit_info(
            f"[dim]   ❌ No template match above threshold ({CONFIDENCE_THRESHOLD:.0%})[/dim]",
            message_group=group_id,
        )
        return None

    except Exception as e:
        emit_warning(
            f"[yellow]⚠️  Template matching failed: {e}[/yellow]",
            message_group=group_id,
        )
        return None


async def _try_color_detection(
    window_title: str | None,
    button: WindowButton,
    group_id: str,
) -> ButtonLocation | None:
    """
    Use color detection to find macOS traffic light buttons.

    Red (close), Yellow (minimize), Green (maximize).
    This is fast and works even with custom themes.
    """
    if not IS_MACOS:
        return None  # Only works on macOS

    emit_info(
        f"[cyan]🔍 Method 4: Trying Color Detection for '{button.value}' button[/cyan]",
        message_group=group_id,
    )

    if not DEPS_AVAILABLE:
        emit_warning(
            "[yellow]⚠️  PIL/numpy not available for color detection[/yellow]",
            message_group=group_id,
        )
        return None

    try:
        # Get window bounds
        bounds_result = _get_active_window_bounds_impl()
        if not bounds_result.success:
            return None

        # Capture title bar area only (top 50px of window)
        title_bar_height = 50
        capture_x = bounds_result.x
        capture_y = bounds_result.y - MacOSTrafficLightOffsets.TITLE_BAR_HEIGHT
        capture_w = min(200, bounds_result.width)  # Only need left 200px
        capture_h = title_bar_height

        # Ensure we're not going off-screen
        if capture_y < 0:
            capture_h += capture_y  # Reduce height
            capture_y = 0

        screenshot_result = capture_screen(
            region=(capture_x, capture_y, capture_w, capture_h),
            save_screenshot=False,
        )

        if not screenshot_result.success or not screenshot_result.screenshot_data:
            return None

        # Convert to PIL Image
        import io

        img = Image.open(io.BytesIO(screenshot_result.screenshot_data))
        img_array = np.array(img)

        # Define color ranges for each button (RGB, allowing for some variation)
        color_ranges = {
            WindowButton.CLOSE: {
                "lower": np.array([220, 50, 50]),  # Red
                "upper": np.array([255, 100, 100]),
            },
            WindowButton.MINIMIZE: {
                "lower": np.array([220, 180, 0]),  # Yellow
                "upper": np.array([255, 220, 50]),
            },
            WindowButton.MAXIMIZE: {
                "lower": np.array([50, 200, 50]),  # Green
                "upper": np.array([100, 255, 100]),
            },
        }

        color_range = color_ranges[button]

        # Find pixels matching the color
        mask = np.all(
            (img_array[:, :, :3] >= color_range["lower"])
            & (img_array[:, :, :3] <= color_range["upper"]),
            axis=2,
        )

        # Find contours/clusters
        if np.any(mask):
            # Get centroid of matching pixels
            y_coords, x_coords = np.where(mask)

            if len(x_coords) > 5:  # Need enough pixels
                center_x = int(np.median(x_coords))
                center_y = int(np.median(y_coords))

                # Convert back to screen coordinates
                screen_x = capture_x + center_x
                screen_y = capture_y + center_y

                emit_info(
                    f"[green]✅ Found via color detection at ({screen_x}, {screen_y})[/green]\n"
                    f"[dim]   Matching pixels: {len(x_coords)}[/dim]",
                    message_group=group_id,
                )

                return ButtonLocation(
                    x=screen_x,
                    y=screen_y,
                    confidence=0.9,
                    method="color_detection",
                )

        emit_info(
            "[dim]   ❌ No matching color found[/dim]",
            message_group=group_id,
        )
        return None

    except Exception as e:
        emit_warning(
            f"[yellow]⚠️  Color detection failed: {e}[/yellow]",
            message_group=group_id,
        )
        return None


async def find_window_button(
    button: WindowButton,
    window_title: str | None = None,
    methods: list[str] | None = None,
) -> ButtonLocation | None:
    """
    Find a window control button using multiple fallback strategies.

    Tries methods in order:
    1. Accessibility API (fastest, most reliable)
    2. Template matching (fast, deterministic, 95%+ accuracy)
    3. Geometry heuristics (fast, works for standard UI)
    4. Color detection (fast, works for macOS traffic lights)
    5. VQA (slowest; use only as last resort via gui-cub VQA tools)

    Args:
        button: Which button to find (close, minimize, maximize)
        window_title: Optional window to focus first
        methods: Optional list of methods to try (default: all)

    Returns:
        ButtonLocation with coordinates and confidence, or None if not found
    """
    group_id = generate_group_id(
        "window_button_detector",
        f"{button.value}_{window_title or 'active'}",
    )

    emit_info(
        f"[bold white on blue] 🎯 WINDOW BUTTON DETECTOR [/bold white on blue] Finding '{button.value}' button",
        message_group=group_id,
    )

    if window_title:
        emit_info(
            f"[dim]   Target window: {window_title}[/dim]",
            message_group=group_id,
        )

    # Default methods (no template matching)
    if methods is None:
        methods = ["accessibility", "heuristic", "color"]

    # Try each method in order
    for method in methods:
        try:
            if method == "accessibility":
                result = await _try_accessibility_api(window_title, button, group_id)

            elif method == "heuristic":
                result = await _try_geometry_heuristics(window_title, button, group_id)
            elif method == "color":
                result = await _try_color_detection(window_title, button, group_id)
            else:
                emit_warning(
                    f"[yellow]⚠️  Unknown method '{method}', skipping[/yellow]",
                    message_group=group_id,
                )
                continue

            if result:
                emit_info(
                    f"[bold green]✅ SUCCESS: Found '{button.value}' button at ({result.x}, {result.y})[/bold green]\n"
                    f"[dim]   Method: {result.method}[/dim]\n"
                    f"[dim]   Confidence: {result.confidence:.0%}[/dim]",
                    message_group=group_id,
                )
                return result

        except Exception as e:
            emit_error(
                f"[red]💥 Method '{method}' threw exception: {e}[/red]",
                message_group=group_id,
            )
            continue

    emit_error(
        f"[red]❌ FAILED: Could not find '{button.value}' button with any method[/red]",
        message_group=group_id,
    )
    return None
