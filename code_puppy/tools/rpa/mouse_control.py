"""Mouse control for desktop RPA automation."""

from __future__ import annotations

from typing import Literal

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
    # Safety settings for pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1  # Small pause between actions
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

from pydantic_ai import RunContext

from code_puppy.messaging import emit_warning

from .constants import DEFAULT_MOUSE_DURATION
from .platform import IS_MACOS, check_macos_accessibility_permission
from .result_types import (
    MouseActionResult,
    MouseDragResult,
    MousePositionResult,
    MouseScrollResult,
)
from .tool_wrapper import rpa_tool


def register_mouse_control_tools(agent):
    """Register mouse control tools for RPA."""

    @agent.tool
    @rpa_tool("MOUSE MOVE", requires="pyautogui")
    def desktop_mouse_move(
        context: RunContext,
        x: int,
        y: int,
        duration: float = DEFAULT_MOUSE_DURATION,
    ) -> MouseActionResult:
        """
        Move the mouse cursor to specific screen coordinates.

        **IMPORTANT - macOS Users:**
        Requires Accessibility permission! If the mouse doesn't move:
        → System Preferences → Security & Privacy → Privacy → Accessibility
        → Grant permission to Terminal (or your Python IDE)

        **HiDPI/Retina Displays:**
        Coordinates are in LOGICAL screen space (not screenshot pixels).
        Use convert_screenshot_to_screen_coords() if working with OCR results.

        Args:
            x: X coordinate (pixels from left edge of screen, logical points)
            y: Y coordinate (pixels from top edge of screen, logical points)
            duration: Time in seconds to move (0 for instant)

        Returns:
            MouseActionResult with success status and final position

        Examples:
            - desktop_mouse_move(x=500, y=300) - Move to center-ish area
            - desktop_mouse_move(x=100, y=100, duration=0.5) - Slow movement
        """
        # Check macOS permissions before attempting movement
        if IS_MACOS:
            has_permission, error_msg = check_macos_accessibility_permission()
            if not has_permission:
                emit_warning(f"[yellow]{error_msg}[/yellow]")
                return MouseActionResult(
                    success=False,
                    error=error_msg,
                    x=x,
                    y=y,
                )

        # Attempt to move mouse
        pyautogui.moveTo(x, y, duration=duration)
        final_x, final_y = pyautogui.position()

        # Verify movement succeeded (within tolerance for rounding)
        tolerance = 2  # pixels
        moved_successfully = (
            abs(final_x - x) <= tolerance and abs(final_y - y) <= tolerance
        )

        if not moved_successfully:
            error_msg = (
                f"Mouse movement failed! Target: ({x}, {y}), Actual: ({final_x}, {final_y}). "
            )
            if IS_MACOS:
                error_msg += (
                    "This is usually a macOS Accessibility permission issue. "
                    "Grant permission in System Preferences → Security & Privacy → Accessibility."
                )
            emit_warning(f"[yellow]{error_msg}[/yellow]")
            return MouseActionResult(
                success=False,
                error=error_msg,
                x=final_x,
                y=final_y,
            )

        return MouseActionResult(success=True, x=final_x, y=final_y)

    @agent.tool
    @rpa_tool("MOUSE CLICK", requires="pyautogui")
    def desktop_mouse_click(
        context: RunContext,
        x: int | None = None,
        y: int | None = None,
        button: Literal["left", "right", "middle"] = "left",
        clicks: int = 1,
        interval: float = 0.0,
    ) -> MouseActionResult:
        """
        Click the mouse at the current position or specific coordinates.

        Args:
            x: Optional X coordinate (if None, clicks current position)
            y: Optional Y coordinate (if None, clicks current position)
            button: Which mouse button to click (left, right, middle)
            clicks: Number of clicks (2 for double-click)
            interval: Time between clicks in seconds

        Returns:
            MouseActionResult with success status and click details

        Examples:
            - desktop_mouse_click() - Left click at current position
            - desktop_mouse_click(x=500, y=300) - Click at specific location
            - desktop_mouse_click(button="right") - Right-click at current position
            - desktop_mouse_click(clicks=2, interval=0.1) - Double-click
        """
        if x is not None and y is not None:
            pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
        else:
            pyautogui.click(button=button, clicks=clicks, interval=interval)

        final_x, final_y = pyautogui.position()
        return MouseActionResult(
            success=True, x=final_x, y=final_y, button=button, clicks=clicks
        )

    @agent.tool
    @rpa_tool("MOUSE DRAG", requires="pyautogui")
    def desktop_mouse_drag(
        context: RunContext,
        x: int,
        y: int,
        duration: float = DEFAULT_MOUSE_DURATION,
        button: Literal["left", "right", "middle"] = "left",
    ) -> MouseDragResult:
        """
        Drag the mouse from current position to target coordinates.

        Args:
            x: Target X coordinate
            y: Target Y coordinate
            duration: Time in seconds to complete the drag
            button: Which mouse button to hold during drag

        Returns:
            MouseDragResult with success status and drag details

        Examples:
            - desktop_mouse_drag(x=800, y=600) - Drag to new position
            - desktop_mouse_drag(x=500, y=500, duration=1.0) - Slow drag
        """
        start_x, start_y = pyautogui.position()
        pyautogui.drag(x - start_x, y - start_y, duration=duration, button=button)
        final_x, final_y = pyautogui.position()
        return MouseDragResult(
            success=True,
            start_x=start_x,
            start_y=start_y,
            end_x=final_x,
            end_y=final_y,
            button=button,
        )

    @agent.tool
    @rpa_tool("MOUSE SCROLL", requires="pyautogui")
    def desktop_mouse_scroll(
        context: RunContext,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> MouseScrollResult:
        """
        Scroll the mouse wheel.

        Args:
            clicks: Number of "clicks" to scroll (positive=up, negative=down)
            x: Optional X coordinate to scroll at (if None, uses current position)
            y: Optional Y coordinate to scroll at (if None, uses current position)

        Returns:
            MouseScrollResult with success status and scroll details

        Examples:
            - desktop_mouse_scroll(clicks=5) - Scroll up 5 clicks
            - desktop_mouse_scroll(clicks=-10) - Scroll down 10 clicks
            - desktop_mouse_scroll(clicks=3, x=500, y=500) - Scroll at specific location
        """
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)

        direction = "up" if clicks > 0 else "down"
        return MouseScrollResult(success=True, clicks=clicks, direction=direction)

    @agent.tool
    def desktop_mouse_get_position(context: RunContext) -> MousePositionResult:
        """
        Get the current mouse cursor position.

        Returns:
            MousePositionResult with x and y coordinates

        Example:
            - desktop_mouse_get_position() -> {"x": 542, "y": 319}
        """
        if not PYAUTOGUI_AVAILABLE:
            # Can't use decorator here since this returns a different type
            return {"error": "pyautogui not available"}

        x, y = pyautogui.position()
        return MousePositionResult(x=x, y=y)

    @agent.tool
    def desktop_check_automation_permissions(context: RunContext) -> dict[str, any]:
        """
        Check if the system has necessary permissions for desktop automation.

        On macOS, this checks Accessibility permissions required for mouse/keyboard control.
        On other platforms, performs basic sanity checks.

        Returns:
            Dictionary with permission status, platform info, and troubleshooting guidance

        Example:
            - desktop_check_automation_permissions() -> {
                "platform": "macOS",
                "has_permission": False,
                "error": "Accessibility permission required...",
                "instructions": "Go to System Preferences..."
              }
        """
        from .platform import get_display_info

        result = {
            "pyautogui_available": PYAUTOGUI_AVAILABLE,
        }

        if not PYAUTOGUI_AVAILABLE:
            result["error"] = "pyautogui not installed. Install with: uv pip install pyautogui"
            return result

        # Get display info (includes permission check on macOS)
        display_info = get_display_info()
        result.update(display_info)

        # Add specific instructions based on platform
        if IS_MACOS:
            has_permission = display_info.get("macos_accessibility_permission", False)
            result["has_permission"] = has_permission

            if not has_permission:
                result["instructions"] = (
                    "1. Open System Preferences (or System Settings on newer macOS)\n"
                    "2. Go to Security & Privacy → Privacy → Accessibility\n"
                    "3. Click the lock icon to make changes\n"
                    "4. Check the box next to Terminal (or your Python IDE/app)\n"
                    "5. Restart your terminal/IDE if the permission was just granted"
                )
            else:
                result["status"] = "All permissions granted! ✅"
        else:
            # For Windows/Linux, just check if basic operations work
            try:
                pos = pyautogui.position()
                result["has_permission"] = True
                result["status"] = "Basic automation appears to be working ✅"
            except Exception as e:
                result["has_permission"] = False
                result["error"] = f"Automation test failed: {e}"

        return result
