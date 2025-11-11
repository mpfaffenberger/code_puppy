"""Click debugging tool registration."""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from ..dependencies import PIL_AVAILABLE, PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if PIL_AVAILABLE:
    from PIL import Image, ImageDraw, ImageFont
else:
    Image = None
    ImageDraw = None
    ImageFont = None

# Import thread-safe screenshot function
from ..screen_capture.capture import _safe_screenshot

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_PILLOW_MISSING, ERROR_PYAUTOGUI_MISSING
from .result_types import (
    ClickDebugResult,
    CoordinateVerifyResult,
    HoverVerifyResult,
    SmartClickResult,
)
from .visualization import draw_pixel_grid


def register_click_debugging_tools(agent):
    """Register click debugging and verification tools.

    This file contains 5 click debugging tools (1,150 lines total):
    1. desktop_hover_and_verify - Hover and verify cursor position (~506 lines)
    2. desktop_highlight_click_target - Highlight click targets (~161 lines)
    3. desktop_verify_coordinates - Verify coordinate accuracy (~89 lines)
    4. desktop_click_with_verification - Click with pre/post verification (~114 lines)
    5. desktop_click_smart - Smart clicking with auto-retry (~234 lines)

    Note: File is long but cohesive - all tools are related to click debugging/verification.
    """

    # ============================================================================
    # TOOL 1: HOVER AND VERIFY (~506 lines)
    # Move mouse and verify position before clicking - critical for debugging!
    # ============================================================================

    @agent.tool
    def desktop_hover_and_verify(
        context: RunContext,
        x: int,
        y: int,
        duration: float = 0.5,
        show_grid: bool = False,
    ) -> HoverVerifyResult:
        """
        Move mouse to coordinates and verify cursor position BEFORE clicking.

        This is a CRITICAL tool for debugging click accuracy issues!
        Instead of clicking blindly, this:
        1. Moves mouse to target coordinates
        2. Waits for cursor to settle
        3. Takes screenshot showing cursor position
        4. Returns actual cursor position for verification

        Use this to verify OCR-based clicks are hovering the right spot!

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Time to wait after moving (seconds) for cursor to settle
            show_grid: If True, overlay a pixel grid for precise coordinate debugging

        Returns:
            HoverVerifyResult with actual cursor position and screenshot

        Example:
            # Before clicking, verify hover position
            result = desktop_hover_and_verify(x=500, y=300)
            print(f"Target: ({result.target_x}, {result.target_y})")
            print(f"Actual: ({result.actual_x}, {result.actual_y})")
            print(f"Offset: ({result.offset_x}, {result.offset_y})")
            # Check screenshot to see if cursor is over the right element
            # Then click if correct:
            desktop_mouse_click(x=result.actual_x, y=result.actual_y)
        """
        if not PYAUTOGUI_AVAILABLE:
            return HoverVerifyResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        group_id = generate_group_id("hover_verify", f"{x}_{y}")
        emit_info(
            f"[bold cyan on black] HOVER & VERIFY [/bold cyan on black] 🎯 Moving to ({x}, {y}) and verifying position",
            message_group=group_id,
        )

        try:
            # Move mouse to target
            pyautogui.moveTo(x, y, duration=duration)

            # Wait for cursor to fully settle
            import time

            time.sleep(0.1)

            # Get actual cursor position
            actual_x, actual_y = pyautogui.position()
            offset_x = actual_x - x
            offset_y = actual_y - y

            # Take screenshot with cursor visible
            screenshot = _safe_screenshot()

            # Detect HiDPI/Retina scale to transform logical coords to screenshot pixel grid
            try:
                from ..platform import get_screen_scale_factor

                scale_factor = get_screen_scale_factor()
            except Exception:
                scale_factor = 1.0

            # Transform logical screen coords to physical screenshot pixel coords
            sx = int(x * scale_factor)
            sy = int(y * scale_factor)
            s_actual_x = int(actual_x * scale_factor)
            s_actual_y = int(actual_y * scale_factor)

            # Draw PRECISE markers for pixel-perfect debugging
            draw = ImageDraw.Draw(screenshot)

            # TARGET POSITION (RED) - Using precise crosshairs instead of huge circles
            crosshair_length = int(
                15 * scale_factor
            )  # Much smaller than old 20px radius
            line_width = max(1, int(1 * scale_factor))

            # Red crosshair at target
            draw.line(
                [(sx - crosshair_length, sy), (sx + crosshair_length, sy)],
                fill=(255, 0, 0),
                width=line_width,
            )
            draw.line(
                [(sx, sy - crosshair_length), (sx, sy + crosshair_length)],
                fill=(255, 0, 0),
                width=line_width,
            )
            # Small red dot at exact target pixel (2px radius)
            dot_radius = max(1, int(2 * scale_factor))
            draw.ellipse(
                [
                    (sx - dot_radius, sy - dot_radius),
                    (sx + dot_radius, sy + dot_radius),
                ],
                fill=(255, 0, 0),
            )

            # ACTUAL CURSOR POSITION (GREEN) - Precise crosshairs
            # Green crosshair at actual cursor position
            draw.line(
                [
                    (s_actual_x - crosshair_length, s_actual_y),
                    (s_actual_x + crosshair_length, s_actual_y),
                ],
                fill=(0, 255, 0),
                width=line_width,
            )
            draw.line(
                [
                    (s_actual_x, s_actual_y - crosshair_length),
                    (s_actual_x, s_actual_y + crosshair_length),
                ],
                fill=(0, 255, 0),
                width=line_width,
            )
            # Small green dot at exact cursor pixel (3px radius, slightly bigger than target)
            cursor_dot_radius = max(2, int(3 * scale_factor))
            draw.ellipse(
                [
                    (s_actual_x - cursor_dot_radius, s_actual_y - cursor_dot_radius),
                    (s_actual_x + cursor_dot_radius, s_actual_y + cursor_dot_radius),
                ],
                fill=(0, 255, 0),
            )

            # Draw line connecting target to actual (if offset)
            if abs(offset_x) > 2 or abs(offset_y) > 2:
                draw.line(
                    [(sx, sy), (s_actual_x, s_actual_y)],
                    fill=(255, 255, 0),
                    width=line_width,
                )

            # Add coordinate labels with legend
            from PIL import ImageFont

            try:
                font = ImageFont.truetype(
                    "/System/Library/Fonts/Helvetica.ttc",
                    max(12, int(16 * scale_factor)),
                )
            except Exception:
                font = ImageFont.load_default()

            label_lines = [
                f"🔴 Target (logical): ({x}, {y})",
                f"🟢 Cursor (logical): ({actual_x}, {actual_y})",
                f"📏 Offset: ({offset_x:+d}, {offset_y:+d}) pixels",
                f"🔍 Scale: {scale_factor}x",
            ]

            # Position labels below the crosshairs
            label_y = s_actual_y + crosshair_length + int(10 * scale_factor)
            for i, line in enumerate(label_lines):
                bbox = draw.textbbox(
                    (
                        s_actual_x - int(100 * scale_factor),
                        label_y + i * int(20 * scale_factor),
                    ),
                    line,
                    font=font,
                )
                draw.rectangle(
                    (
                        bbox[0] - int(3 * scale_factor),
                        bbox[1] - int(3 * scale_factor),
                        bbox[2] + int(3 * scale_factor),
                        bbox[3] + int(3 * scale_factor),
                    ),
                    fill=(255, 255, 255, 230),
                )
                draw.text(
                    (
                        s_actual_x - int(100 * scale_factor),
                        label_y + i * int(20 * scale_factor),
                    ),
                    line,
                    fill=(0, 0, 0),
                    font=font,
                )

            # OPTIONAL: Draw pixel grid overlay for precise debugging
            if show_grid:
                try:
                    draw_pixel_grid(
                        draw,
                        center_x=s_actual_x,
                        center_y=s_actual_y,
                        grid_size=100 * int(scale_factor),
                        spacing=10 * int(scale_factor),
                        scale_factor=scale_factor,
                    )
                except Exception as grid_error:
                    emit_warning(
                        f"[yellow]Grid overlay failed: {grid_error}[/yellow]",
                        message_group=group_id,
                    )

            # ZOOMED INSET VIEW - Show 50x50 pixel area around cursor at 5x magnification
            # This helps see EXACTLY where the cursor is relative to UI elements
            try:
                zoom_factor = 5
                crop_size = 50  # 50x50 pixel area in screenshot coordinates

                # Crop region around actual cursor
                left = max(0, s_actual_x - crop_size // 2)
                top = max(0, s_actual_y - crop_size // 2)
                right = min(screenshot.width, s_actual_x + crop_size // 2)
                bottom = min(screenshot.height, s_actual_y + crop_size // 2)

                zoomed = screenshot.crop((left, top, right, bottom))
                zoomed = zoomed.resize(
                    (
                        int((right - left) * zoom_factor),
                        int((bottom - top) * zoom_factor),
                    ),
                    Image.NEAREST,  # Pixelated zoom for clarity
                )

                # Draw on zoomed inset
                zoom_draw = ImageDraw.Draw(zoomed)

                # Calculate cursor position in zoomed coordinates
                zoom_cursor_x = (s_actual_x - left) * zoom_factor
                zoom_cursor_y = (s_actual_y - top) * zoom_factor

                # Draw crosshair on zoomed view
                zoom_cross_len = 10 * zoom_factor
                zoom_draw.line(
                    [
                        (zoom_cursor_x - zoom_cross_len, zoom_cursor_y),
                        (zoom_cursor_x + zoom_cross_len, zoom_cursor_y),
                    ],
                    fill=(0, 255, 0),
                    width=2,
                )
                zoom_draw.line(
                    [
                        (zoom_cursor_x, zoom_cursor_y - zoom_cross_len),
                        (zoom_cursor_x, zoom_cursor_y + zoom_cross_len),
                    ],
                    fill=(0, 255, 0),
                    width=2,
                )
                # Center dot
                zoom_draw.ellipse(
                    [
                        (zoom_cursor_x - 3, zoom_cursor_y - 3),
                        (zoom_cursor_x + 3, zoom_cursor_y + 3),
                    ],
                    fill=(0, 255, 0),
                )

                # Paste zoomed inset in top-left corner with border
                inset_x = int(20 * scale_factor)
                inset_y = int(20 * scale_factor)

                # Draw border around inset
                screenshot.paste(zoomed, (inset_x, inset_y))
                draw.rectangle(
                    [
                        (inset_x - 2, inset_y - 2),
                        (inset_x + zoomed.width + 2, inset_y + zoomed.height + 2),
                    ],
                    outline=(255, 255, 255),
                    width=3,
                )

                # Label for inset
                inset_label = "5x ZOOM at cursor"
                draw.text(
                    (inset_x, inset_y - int(20 * scale_factor)),
                    inset_label,
                    fill=(255, 255, 255),
                    font=font,
                )
            except Exception as zoom_error:
                # If zoom fails, just continue without it
                emit_warning(
                    f"[yellow]Zoom inset failed: {zoom_error}[/yellow]",
                    message_group=group_id,
                )

            # Save screenshot
            from datetime import datetime
            from pathlib import Path
            from tempfile import gettempdir

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"hover_verify_{x}_{y}_{timestamp}.png"
            save_path = Path(gettempdir()) / "code_puppy_rpa_debug" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(save_path)

            emit_info(
                f"[green]✅ Hover screenshot saved: {save_path}[/green]",
                message_group=group_id,
            )
            emit_info(
                f"[cyan]🎯 Target: ({x}, {y})[/cyan]",
                message_group=group_id,
            )
            emit_info(
                f"[cyan]📍 Actual: ({actual_x}, {actual_y})[/cyan]",
                message_group=group_id,
            )

            if abs(offset_x) > 2 or abs(offset_y) > 2:
                emit_warning(
                    f"[yellow]⚠️  Cursor offset detected: ({offset_x:+d}, {offset_y:+d}) pixels[/yellow]",
                    message_group=group_id,
                )
            else:
                emit_info(
                    "[green]✅ Cursor is within 2px of target[/green]",
                    message_group=group_id,
                )

            return HoverVerifyResult(
                success=True,
                target_x=x,
                target_y=y,
                actual_x=actual_x,
                actual_y=actual_y,
                offset_x=offset_x,
                offset_y=offset_y,
                screenshot_path=str(save_path),
                cursor_visible=True,
                message=f"Cursor at ({actual_x}, {actual_y}), offset from target: ({offset_x:+d}, {offset_y:+d})",
            )

        except Exception as e:
            # On macOS, CGEventCreateMouseEvent errors can occur without Accessibility permissions.
            # Provide a diagnostic screenshot anyway, showing target vs current cursor position.
            try:
                if PYAUTOGUI_AVAILABLE:
                    # Attempt to read current mouse position and draw overlays
                    actual_x, actual_y = pyautogui.position()
                    offset_x = actual_x - x
                    offset_y = actual_y - y
                    screenshot = _safe_screenshot()
                    try:
                        from ..platform import get_screen_scale_factor

                        scale_factor = get_screen_scale_factor()
                    except Exception:
                        scale_factor = 1.0
                    sx = int(x * scale_factor)
                    sy = int(y * scale_factor)
                    s_actual_x = int(actual_x * scale_factor)
                    s_actual_y = int(actual_y * scale_factor)
                    draw = ImageDraw.Draw(screenshot)

                    # Use precise crosshairs (same as main code path)
                    crosshair_length = int(15 * scale_factor)
                    line_width = max(1, int(1 * scale_factor))
                    dot_radius = max(1, int(2 * scale_factor))
                    cursor_dot_radius = max(2, int(3 * scale_factor))

                    # Red crosshair at target
                    draw.line(
                        [(sx - crosshair_length, sy), (sx + crosshair_length, sy)],
                        fill=(255, 0, 0),
                        width=line_width,
                    )
                    draw.line(
                        [(sx, sy - crosshair_length), (sx, sy + crosshair_length)],
                        fill=(255, 0, 0),
                        width=line_width,
                    )
                    draw.ellipse(
                        [
                            (sx - dot_radius, sy - dot_radius),
                            (sx + dot_radius, sy + dot_radius),
                        ],
                        fill=(255, 0, 0),
                    )

                    # Green crosshair at actual cursor
                    draw.line(
                        [
                            (s_actual_x - crosshair_length, s_actual_y),
                            (s_actual_x + crosshair_length, s_actual_y),
                        ],
                        fill=(0, 255, 0),
                        width=line_width,
                    )
                    draw.line(
                        [
                            (s_actual_x, s_actual_y - crosshair_length),
                            (s_actual_x, s_actual_y + crosshair_length),
                        ],
                        fill=(0, 255, 0),
                        width=line_width,
                    )
                    draw.ellipse(
                        [
                            (
                                s_actual_x - cursor_dot_radius,
                                s_actual_y - cursor_dot_radius,
                            ),
                            (
                                s_actual_x + cursor_dot_radius,
                                s_actual_y + cursor_dot_radius,
                            ),
                        ],
                        fill=(0, 255, 0),
                    )

                    # Connecting line
                    if abs(offset_x) > 2 or abs(offset_y) > 2:
                        draw.line(
                            [(sx, sy), (s_actual_x, s_actual_y)],
                            fill=(255, 255, 0),
                            width=line_width,
                        )
                    from PIL import ImageFont

                    try:
                        font = ImageFont.truetype(
                            "/System/Library/Fonts/Helvetica.ttc",
                            max(12, int(16 * scale_factor)),
                        )
                    except Exception:
                        font = ImageFont.load_default()
                    label_lines = [
                        f"🔴 Target (logical): ({x}, {y})",
                        f"🟢 Cursor (logical): ({actual_x}, {actual_y})",
                        f"📏 Offset: ({offset_x:+d}, {offset_y:+d}) pixels",
                        f"🔍 Scale: {scale_factor}x",
                        f"⚠️ Error: {e}",
                    ]
                    label_y = s_actual_y + crosshair_length + int(10 * scale_factor)
                    for i, line in enumerate(label_lines):
                        bbox = draw.textbbox(
                            (
                                s_actual_x - int(80 * scale_factor),
                                label_y + i * int(20 * scale_factor),
                            ),
                            line,
                            font=font,
                        )
                        draw.rectangle(
                            (
                                bbox[0] - int(3 * scale_factor),
                                bbox[1] - int(3 * scale_factor),
                                bbox[2] + int(3 * scale_factor),
                                bbox[3] + int(3 * scale_factor),
                            ),
                            fill=(255, 255, 255, 230),
                        )
                        draw.text(
                            (
                                s_actual_x - int(80 * scale_factor),
                                label_y + i * int(20 * scale_factor),
                            ),
                            line,
                            fill=(0, 0, 0),
                            font=font,
                        )
                    from datetime import datetime
                    from pathlib import Path
                    from tempfile import gettempdir

                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"hover_verify_diag_{x}_{y}_{timestamp}.png"
                    save_path = Path(gettempdir()) / "code_puppy_rpa_debug" / filename
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    screenshot.save(save_path)
                    emit_error(
                        f"[red]Hover verification failed: {e} (diagnostic saved: {save_path})[/red]",
                        message_group=group_id,
                    )
                    return HoverVerifyResult(
                        success=False,
                        error=str(e),
                        target_x=x,
                        target_y=y,
                        actual_x=actual_x,
                        actual_y=actual_y,
                        offset_x=offset_x,
                        offset_y=offset_y,
                        screenshot_path=str(save_path),
                        cursor_visible=True,
                        message=f"Diagnostic hover screenshot saved. Error: {e}",
                    )
            except Exception:
                # If diagnostics fail, return plain error
                emit_error(
                    f"[red]Hover verification failed: {e}[/red]", message_group=group_id
                )
                return HoverVerifyResult(success=False, error=str(e))

    # ============================================================================
    # TOOL 2: HIGHLIGHT CLICK TARGET (~161 lines)
    # Draw visual indicators at click coordinates for debugging
    # ============================================================================

    @agent.tool
    def desktop_highlight_click_target(
        context: RunContext,
        x: int,
        y: int,
        duration: float = 2.0,
        color: Literal["red", "green", "blue", "yellow"] = "red",
    ) -> ClickDebugResult:
        """
        Highlight a coordinate on screen BEFORE clicking to verify it's correct.

        This takes a screenshot, draws a large circle at the target coordinates,
        and saves it for visual verification. USE THIS before clicking to ensure
        the coordinates are correct!

        Args:
            x: X coordinate to highlight
            y: Y coordinate to highlight
            duration: How long to show the highlight (seconds)
            color: Color of the highlight circle

        Returns:
            ClickDebugResult with screenshot path showing the highlight

        Example:
            # Before clicking, verify the coordinates
            result = desktop_highlight_click_target(x=500, y=300, color="red")
            # Check the screenshot at result.screenshot_path
            # If correct, then click:
            desktop_mouse_click(x=500, y=300)
        """
        if not PYAUTOGUI_AVAILABLE:
            return ClickDebugResult(
                success=False,
                error=f"{ERROR_PYAUTOGUI_MISSING} and {ERROR_PILLOW_MISSING}",
            )

        group_id = generate_group_id("highlight_click_target", f"{x}_{y}")
        emit_info(
            f"[bold yellow on black] HIGHLIGHT CLICK TARGET [/bold yellow on black] 🎯 Highlighting ({x}, {y}) in {color}",
            message_group=group_id,
        )

        try:
            # Take screenshot
            screenshot = _safe_screenshot()

            # Draw highlight
            draw = ImageDraw.Draw(screenshot)

            # Color mapping
            colors = {
                "red": (255, 0, 0),
                "green": (0, 255, 0),
                "blue": (0, 0, 255),
                "yellow": (255, 255, 0),
            }
            color_rgb = colors.get(color, (255, 0, 0))

            # Draw large crosshair
            line_length = 50
            line_width = 3

            # Horizontal line
            draw.line(
                [(x - line_length, y), (x + line_length, y)],
                fill=color_rgb,
                width=line_width,
            )
            # Vertical line
            draw.line(
                [(x, y - line_length), (x, y + line_length)],
                fill=color_rgb,
                width=line_width,
            )

            # Draw circle around target
            radius = 30
            draw.ellipse(
                [(x - radius, y - radius), (x + radius, y + radius)],
                outline=color_rgb,
                width=line_width,
            )

            # Draw small center dot
            dot_radius = 5
            draw.ellipse(
                [(x - dot_radius, y - dot_radius), (x + dot_radius, y + dot_radius)],
                fill=color_rgb,
            )

            # Add coordinate label
            from PIL import ImageFont

            try:
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
            except Exception:
                font = ImageFont.load_default()

            label = f"({x}, {y})"
            # Draw label with background
            bbox = draw.textbbox((x + 40, y - 40), label, font=font)
            draw.rectangle(
                (
                    bbox[0] - 5,
                    bbox[1] - 5,
                    bbox[2] + 5,
                    bbox[3] + 5,
                ),
                fill=(255, 255, 255, 200),
            )
            draw.text((x + 40, y - 40), label, fill=color_rgb, font=font)

            # Save screenshot
            from datetime import datetime
            from pathlib import Path
            from tempfile import gettempdir

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"click_highlight_{x}_{y}_{timestamp}.png"
            save_path = Path(gettempdir()) / "code_puppy_rpa_debug" / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot.save(save_path)

            # Get pixel color at target
            pixel = screenshot.getpixel((x, y))

            emit_info(
                f"[green]✅ Highlight saved: {save_path}[/green]",
                message_group=group_id,
            )
            emit_info(
                f"[cyan]📍 Target: ({x}, {y})[/cyan]",
                message_group=group_id,
            )
            emit_info(
                f"[dim]Pixel color at target: RGB{pixel}[/dim]",
                message_group=group_id,
            )
            emit_warning(
                "[yellow]⚠️  VERIFY THE SCREENSHOT BEFORE CLICKING![/yellow]",
                message_group=group_id,
            )

            return ClickDebugResult(
                success=True,
                x=x,
                y=y,
                screen_color=list(pixel[:3]) if len(pixel) >= 3 else None,
                screenshot_path=str(save_path),
                message=f"Highlight saved. Check {save_path} to verify target location.",
            )

        except Exception as e:
            emit_error(
                f"[red]Failed to create highlight: {e}[/red]",
                message_group=group_id,
            )
            return ClickDebugResult(
                success=False,
                error=str(e),
            )

    # ============================================================================
    # TOOL 3: VERIFY COORDINATES (~89 lines)
    # Check if coordinates are within screen bounds and valid
    # ============================================================================

    @agent.tool
    def desktop_verify_coordinates(
        context: RunContext,
        x: int,
        y: int,
    ) -> CoordinateVerifyResult:
        """
        Verify that coordinates are valid and within screen bounds.

        Useful for checking coordinates before clicking to avoid errors.

        Args:
            x: X coordinate to verify
            y: Y coordinate to verify

        Returns:
            CoordinateVerifyResult with validation info

        Example:
            result = desktop_verify_coordinates(x=500, y=300)
            if result.is_valid:
                desktop_mouse_click(x=500, y=300)
            else:
                print(f"Invalid coordinates: {result.message}")
        """
        if not PYAUTOGUI_AVAILABLE:
            return CoordinateVerifyResult(
                success=False,
                error=ERROR_PYAUTOGUI_MISSING,
            )

        group_id = generate_group_id("verify_coordinates", f"{x}_{y}")

        try:
            # Get screen size
            screen_width, screen_height = pyautogui.size()

            # Check if within bounds
            is_valid = 0 <= x < screen_width and 0 <= y < screen_height

            # Calculate distance from edges
            distance_from_edge = {
                "left": x,
                "right": screen_width - x,
                "top": y,
                "bottom": screen_height - y,
            }

            if is_valid:
                emit_info(
                    f"[green]✅ Coordinates ({x}, {y}) are VALID[/green]",
                    message_group=group_id,
                )
                emit_info(
                    f"[dim]Screen: {screen_width}x{screen_height}, Distance from edges: {distance_from_edge}[/dim]",
                    message_group=group_id,
                )
            else:
                emit_error(
                    f"[red]❌ Coordinates ({x}, {y}) are OUT OF BOUNDS![/red]",
                    message_group=group_id,
                )
                emit_error(
                    f"[red]Screen size: {screen_width}x{screen_height}[/red]",
                    message_group=group_id,
                )

            # Warn if too close to edges (might be window title bar issue)
            min_edge_distance = min(distance_from_edge.values())
            if min_edge_distance < 50 and is_valid:
                emit_warning(
                    f"[yellow]⚠️  WARNING: Very close to screen edge ({min_edge_distance}px). Double-check target![/yellow]",
                    message_group=group_id,
                )

            return CoordinateVerifyResult(
                success=True,
                x=x,
                y=y,
                is_valid=is_valid,
                screen_width=screen_width,
                screen_height=screen_height,
                distance_from_edge=distance_from_edge,
            )

        except Exception as e:
            return CoordinateVerifyResult(
                success=False,
                error=str(e),
            )

    # ============================================================================
    # TOOL 4: CLICK WITH VERIFICATION (~114 lines)
    # Click and verify the action was successful with pre/post checks
    # ============================================================================

    @agent.tool
    def desktop_click_with_verification(
        context: RunContext,
        x: int,
        y: int,
        button: str = "left",
        verify_first: bool = True,
    ) -> ClickDebugResult:
        """
        Click at coordinates with automatic verification and highlighting.

        This is a SAFER alternative to desktop_mouse_click that:
        1. Verifies coordinates are in bounds
        2. Optionally highlights the target first
        3. Warns about potential issues
        4. Provides detailed logging

        Args:
            x: X coordinate to click
            y: Y coordinate to click
            button: Mouse button ("left", "right", "middle")
            verify_first: Whether to verify coordinates before clicking

        Returns:
            ClickDebugResult with click details

        Example:
            # Safe click with verification
            desktop_click_with_verification(x=500, y=300)

            # Skip verification for speed (not recommended)
            desktop_click_with_verification(x=500, y=300, verify_first=False)
        """
        if not PYAUTOGUI_AVAILABLE:
            return ClickDebugResult(
                success=False,
                error=ERROR_PYAUTOGUI_MISSING,
            )

        group_id = generate_group_id("click_with_verification", f"{x}_{y}")
        emit_info(
            f"[bold white on blue] VERIFIED CLICK [/bold white on blue] 🖱️  Clicking ({x}, {y}) with {button} button",
            message_group=group_id,
        )

        try:
            if verify_first:
                # Verify coordinates
                verify_result = desktop_verify_coordinates(context, x=x, y=y)
                if not verify_result.is_valid:
                    emit_error(
                        "[red]❌ ABORTING CLICK - Coordinates out of bounds![/red]",
                        message_group=group_id,
                    )
                    return ClickDebugResult(
                        success=False,
                        error="Coordinates out of screen bounds",
                        x=x,
                        y=y,
                    )

                # Warn if close to edges
                min_edge = min(verify_result.distance_from_edge.values())
                if min_edge < 50:
                    emit_warning(
                        f"[yellow]⚠️  WARNING: Clicking very close to screen edge ({min_edge}px)![/yellow]",
                        message_group=group_id,
                    )

            # Take screenshot of target before clicking
            screenshot = _safe_screenshot()

            # Transform logical coords to screenshot pixel grid for color sampling
            try:
                from ..platform import get_screen_scale_factor

                scale_factor = get_screen_scale_factor()
            except Exception:
                scale_factor = 1.0
            sx = int(x * scale_factor)
            sy = int(y * scale_factor)

            pixel_color = screenshot.getpixel((sx, sy))

            # Perform click
            pyautogui.click(x=x, y=y, button=button)

            emit_info(
                f"[green]✅ Clicked at ({x}, {y})[/green]",
                message_group=group_id,
            )
            emit_info(
                f"[dim]Pixel color at click: RGB{pixel_color}[/dim]",
                message_group=group_id,
            )

            return ClickDebugResult(
                success=True,
                x=x,
                y=y,
                screen_color=pixel_color[:3] if len(pixel_color) >= 3 else None,
                message=f"Successfully clicked at ({x}, {y})",
            )

        except Exception as e:
            emit_error(
                f"[red]Click failed: {e}[/red]",
                message_group=group_id,
            )
            return ClickDebugResult(
                success=False,
                error=str(e),
                x=x,
                y=y,
            )

    # ============================================================================
    # TOOL 5: SMART CLICK (~234 lines)
    # Intelligent clicking with automatic retry, offset detection, and fallback
    # ============================================================================

    @agent.tool
    def desktop_click_smart(
        context: RunContext,
        x: int,
        y: int,
        element_type: str = "button",
        max_attempts: int = 5,
        verify_color_change: bool = False,
        expected_color_rgb: list[int] | None = None,
        verify_pixel_x: int | None = None,
        verify_pixel_y: int | None = None,
    ) -> SmartClickResult:
        """
        Smart clicking with automatic offset retry and verification.

        This tool attempts multiple click positions if the first fails:
        1. Try exact center
        2. Try offset variations (up, left, right, down, diagonals)
        3. Verify success after each attempt (optional color change detection)
        4. Return which offset worked

        Perfect for OCR-based clicking where bounding boxes have ±5-10px error!

        Args:
            x: Target X coordinate (e.g., from OCR center_x)
            y: Target Y coordinate (e.g., from OCR center_y)
            element_type: Type of element ("button", "link", "text_field", "checkbox")
                         Adjusts offset strategy accordingly
            max_attempts: Maximum click attempts with different offsets (default: 5)
            verify_color_change: Whether to verify click by checking pixel color change
            expected_color_rgb: Expected color after click [r, g, b] (e.g., [255, 0, 0] for red)
            verify_pixel_x: X coordinate to check color (defaults to click position)
            verify_pixel_y: Y coordinate to check color (defaults to click position)

        Returns:
            SmartClickResult with successful offset and verification details

        Examples:
            # Simple smart click on button
            result = desktop_click_smart(x=500, y=300, element_type="button")
            if result.verification_passed:
                print(f"Clicked successfully with offset: {result.successful_offset}")

            # Paint test: verify red pixel after click
            result = desktop_click_smart(
                x=500, y=300,
                verify_color_change=True,
                expected_color_rgb=[255, 0, 0],  # Red spray paint
            )
        """
        if not PYAUTOGUI_AVAILABLE:
            return SmartClickResult(
                success=False,
                error=ERROR_PYAUTOGUI_MISSING,
            )

        group_id = generate_group_id("smart_click", f"{x}_{y}")
        emit_info(
            f"[bold magenta on black] SMART CLICK [/bold magenta on black] 🎯 Clicking ({x}, {y}) with retry logic",
            message_group=group_id,
        )

        # Define offset strategies based on element type
        offset_strategies = {
            "button": [
                (0, 0),  # Center
                (0, -5),  # Slightly up (avoid bottom padding)
                (-5, 0),  # Slightly left
                (5, 0),  # Slightly right
                (0, 5),  # Slightly down
                (-3, -3),  # Diagonal up-left
                (3, -3),  # Diagonal up-right
            ],
            "link": [
                (0, 0),  # Center
                (-10, 0),  # Left (links often left-aligned)
                (-5, 0),  # Slightly left
                (0, -3),  # Slightly up
                (0, 3),  # Slightly down
            ],
            "checkbox": [
                (-10, 0),  # Far left (where checkbox usually is)
                (-15, 0),  # Even further left
                (-5, 0),  # Slightly left
                (0, 0),  # Center
            ],
            "text_field": [
                (0, 0),  # Center
                (-20, 0),  # Left side of field
                (20, 0),  # Right side of field
            ],
        }

        offsets = offset_strategies.get(element_type, offset_strategies["button"])
        offsets = offsets[:max_attempts]  # Limit to max_attempts

        attempt_log = []

        # Capture before-state for color change verification
        before_screenshot = None
        before_pixel_color = None
        if verify_color_change:
            before_screenshot = _safe_screenshot()
            try:
                from ..platform import get_screen_scale_factor

                scale_factor = get_screen_scale_factor()
            except Exception:
                scale_factor = 1.0
            check_x = verify_pixel_x if verify_pixel_x is not None else x
            check_y = verify_pixel_y if verify_pixel_y is not None else y
            s_check_x = int(check_x * scale_factor)
            s_check_y = int(check_y * scale_factor)
            before_pixel_color = before_screenshot.getpixel((s_check_x, s_check_y))
            emit_info(
                f"[dim]Before-state pixel color at ({check_x}, {check_y}): RGB{before_pixel_color[:3]}[/dim]",
                message_group=group_id,
            )

        try:
            for attempt, (offset_x, offset_y) in enumerate(offsets, 1):
                click_x = x + offset_x
                click_y = y + offset_y

                emit_info(
                    f"[cyan]Attempt {attempt}/{len(offsets)}: Clicking ({click_x}, {click_y}) [offset: ({offset_x:+d}, {offset_y:+d})][/cyan]",
                    message_group=group_id,
                )

                # Perform click
                pyautogui.click(x=click_x, y=click_y)

                # Wait briefly for UI to update
                import time

                time.sleep(0.2)

                # Verify if requested
                verification_passed = False

                if verify_color_change:
                    after_screenshot = _safe_screenshot()
                    check_x = verify_pixel_x if verify_pixel_x is not None else click_x
                    check_y = verify_pixel_y if verify_pixel_y is not None else click_y
                    s_check_x = int(check_x * scale_factor)
                    s_check_y = int(check_y * scale_factor)
                    after_pixel_color = after_screenshot.getpixel(
                        (s_check_x, s_check_y)
                    )

                    # Check if color changed
                    color_changed = before_pixel_color[:3] != after_pixel_color[:3]

                    if expected_color_rgb:
                        # Check for specific color
                        matches_expected = (
                            abs(after_pixel_color[0] - expected_color_rgb[0]) < 30
                            and abs(after_pixel_color[1] - expected_color_rgb[1]) < 30
                            and abs(after_pixel_color[2] - expected_color_rgb[2]) < 30
                        )
                        verification_passed = matches_expected
                        log_msg = f"Attempt {attempt}: Color {'MATCH' if matches_expected else 'MISMATCH'} - Got RGB{after_pixel_color[:3]}, Expected RGB{expected_color_rgb}"
                    else:
                        # Just check for any change
                        verification_passed = color_changed
                        log_msg = f"Attempt {attempt}: Color {'CHANGED' if color_changed else 'UNCHANGED'} - Before RGB{before_pixel_color[:3]}, After RGB{after_pixel_color[:3]}"

                    attempt_log.append(log_msg)
                    emit_info(f"[dim]{log_msg}[/dim]", message_group=group_id)

                    if verification_passed:
                        emit_info(
                            f"[bold green]✅ SUCCESS! Click verified at offset ({offset_x:+d}, {offset_y:+d})[/bold green]",
                            message_group=group_id,
                        )
                        return SmartClickResult(
                            success=True,
                            target_x=x,
                            target_y=y,
                            actual_click_x=click_x,
                            actual_click_y=click_y,
                            attempts=attempt,
                            successful_offset=(offset_x, offset_y),
                            verification_method="color_change",
                            verification_passed=True,
                            attempt_log=attempt_log,
                        )
                else:
                    # No verification requested, assume first click worked
                    log_msg = f"Attempt {attempt}: Clicked (no verification)"
                    attempt_log.append(log_msg)

                    if attempt == 1:  # Return after first attempt if no verification
                        return SmartClickResult(
                            success=True,
                            target_x=x,
                            target_y=y,
                            actual_click_x=click_x,
                            actual_click_y=click_y,
                            attempts=1,
                            successful_offset=(0, 0),
                            verification_method="none",
                            verification_passed=False,
                            attempt_log=attempt_log,
                        )

            # All attempts exhausted without verification success
            emit_warning(
                f"[yellow]⚠️  All {len(offsets)} attempts completed, verification did not pass[/yellow]",
                message_group=group_id,
            )

            return SmartClickResult(
                success=True,  # Tool executed successfully
                target_x=x,
                target_y=y,
                actual_click_x=x,  # Last attempt
                actual_click_y=y,
                attempts=len(offsets),
                successful_offset=None,
                verification_method="color_change" if verify_color_change else "none",
                verification_passed=False,
                attempt_log=attempt_log,
                message="All click attempts completed but verification did not pass",
            )

        except Exception as e:
            emit_error(
                f"[red]Smart click failed: {e}[/red]",
                message_group=group_id,
            )
            return SmartClickResult(
                success=False,
                error=str(e),
                attempt_log=attempt_log,
            )
