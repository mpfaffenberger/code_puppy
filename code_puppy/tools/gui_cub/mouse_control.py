"""Mouse control for desktop automation automation."""

from __future__ import annotations

from typing import Literal

from pydantic_ai import RunContext

from .dependencies import PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui

    # Safety settings for pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1  # Small pause between actions
else:
    pyautogui = None

from rich.text import Text

from code_puppy.messaging import emit_warning

from .constants import DEFAULT_MOUSE_DURATION
from .platform import (
    IS_MACOS,
    IS_WINDOWS,
    check_macos_accessibility_permission,
    click_mouse_native,
    get_mouse_position_native,
    move_mouse_native,
)
from .result_types import (
    MouseActionResult,
    MouseDragResult,
    MousePositionResult,
    MouseScrollResult,
)
from .tool_wrapper import desktop_tool

# Platform-specific scroll distance calibration (pixels per scroll click)
# These are approximate values based on default OS settings
SCROLL_PIXELS_PER_CLICK = 20  # macOS: ~15-25, Windows: ~15-25
if IS_MACOS:
    SCROLL_PIXELS_PER_CLICK = 22  # macOS tends to scroll slightly more
elif IS_WINDOWS:
    SCROLL_PIXELS_PER_CLICK = 18  # Windows tends to scroll slightly less

# Delay for content rendering after scroll (macOS needs more due to animations)
SCROLL_DELAY = 0.08 if IS_MACOS else 0.05


# Module-level function (importable by workflow executor)
def desktop_mouse_click(
    context: RunContext,
    x: int | None = None,
    y: int | None = None,
    button: Literal["left", "right", "middle"] = "left",
    clicks: int = 1,
    interval: float = 0.0,
) -> MouseActionResult:
    """Click the mouse at the current position or specific coordinates.

    Uses native Quartz APIs on macOS for multi-monitor support.
    pyautogui.click() is clamped to primary monitor bounds on macOS.

    Args:
        x: Optional X coordinate (if None, clicks current position)
        y: Optional Y coordinate (if None, clicks current position)
        button: Which mouse button to click (left, right, middle)
        clicks: Number of clicks (2 for double-click)
        interval: Time between clicks in seconds

    Returns:
        MouseActionResult with success status and click details
    """
    # Get current position if coordinates not specified
    if x is None or y is None:
        current_x, current_y = get_mouse_position_native()
        if x is None:
            x = current_x
        if y is None:
            y = current_y

    # Use native API for clicking on macOS (multi-monitor safe)
    if IS_MACOS:
        success, error = click_mouse_native(
            x=x, y=y, button=button, clicks=clicks, interval=interval
        )
        if not success:
            return MouseActionResult(
                success=False,
                error=error or "Native mouse click failed",
                x=x,
                y=y,
                button=button,
                clicks=clicks,
            )
    else:
        # Windows: pyautogui works correctly for multi-monitor
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)

    final_x, final_y = get_mouse_position_native()
    return MouseActionResult(
        success=True, x=final_x, y=final_y, button=button, clicks=clicks
    )


def register_mouse_control_tools(agent):
    """Register mouse control tools for desktop automation."""

    @agent.tool
    @desktop_tool("MOUSE MOVE", requires="pyautogui")
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
                emit_warning(Text.from_markup(f"[yellow]{error_msg}[/yellow]"))
                return MouseActionResult(
                    success=False,
                    error=error_msg,
                    x=x,
                    y=y,
                )

        # Use native API for mouse movement on macOS (multi-monitor safe)
        # pyautogui.moveTo() is clamped to primary monitor bounds on macOS
        if IS_MACOS:
            success, error = move_mouse_native(x, y, duration=duration)
            if not success:
                emit_warning(Text.from_markup(f"[yellow]Native mouse move failed: {error}[/yellow]"))
                return MouseActionResult(
                    success=False,
                    error=error or "Native mouse move failed",
                    x=x,
                    y=y,
                )
            # Brief pause for CGEvent to propagate before verification
            import time

            time.sleep(0.02)
        else:
            # Windows: pyautogui works correctly for multi-monitor
            pyautogui.moveTo(x, y, duration=duration)

        # Use native API for position verification
        final_x, final_y = get_mouse_position_native()

        # Verify movement succeeded (within tolerance for rounding)
        tolerance = 5  # pixels - increased for multi-monitor edge cases
        moved_successfully = (
            abs(final_x - x) <= tolerance and abs(final_y - y) <= tolerance
        )

        if not moved_successfully:
            error_msg = f"Mouse movement failed! Target: ({x}, {y}), Actual: ({final_x}, {final_y}). "
            if IS_MACOS:
                error_msg += (
                    "This is usually a macOS Accessibility permission issue. "
                    "Grant permission in System Preferences → Security & Privacy → Accessibility."
                )
            emit_warning(Text.from_markup(f"[yellow]{error_msg}[/yellow]"))
            return MouseActionResult(
                success=False,
                error=error_msg,
                x=final_x,
                y=final_y,
            )

        return MouseActionResult(success=True, x=final_x, y=final_y)

    @agent.tool
    @desktop_tool("MOUSE CLICK", requires="pyautogui")
    def _wrapped_mouse_click(
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
        return desktop_mouse_click(context, x, y, button, clicks, interval)

    @agent.tool
    @desktop_tool("MOUSE DRAG", requires="pyautogui")
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
    @desktop_tool("MOUSE SCROLL", requires="pyautogui")
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
    @desktop_tool("SCROLL INTO VIEW", requires="pyautogui")
    def desktop_scroll_to_position(
        context: RunContext,
        target_y: int,
        x: int | None = None,
        scroll_amount: int = 3,
        max_scrolls: int = 50,
    ) -> MouseScrollResult:
        """
        Scroll the page/window until a target Y position is visible on screen.

        This is useful for scrolling to elements in long forms or pages.
        Similar to scrollIntoView() in browsers.

        Args:
            target_y: Target Y coordinate to bring into view
            x: X coordinate to scroll at (if None, uses center of screen)
            scroll_amount: Clicks per scroll action (default: 3)
            max_scrolls: Maximum scroll attempts to prevent infinite loops (default: 50)

        Returns:
            MouseScrollResult with success status

        Examples:
            - desktop_scroll_to_position(target_y=1500) - Scroll down to y=1500
            - desktop_scroll_to_position(target_y=100, scroll_amount=5) - Scroll up with larger steps

        Note: Cross-platform (macOS & Windows). Scroll distance auto-calibrated per platform.
        """
        import time

        # Get screen dimensions
        screen_width, screen_height = pyautogui.size()

        # Use center X if not specified
        if x is None:
            x = screen_width // 2

        # Determine if we need to scroll up or down
        if target_y < 0:
            # Target is above screen, scroll up
            direction = 1  # Positive = up
        elif target_y > screen_height:
            # Target is below screen, scroll down
            direction = -1  # Negative = down
        else:
            # Target already visible
            return MouseScrollResult(
                success=True,
                clicks=0,
                direction="none",
            )

        # Scroll until target is visible or max_scrolls reached
        total_clicks = 0
        for i in range(max_scrolls):
            # Scroll
            pyautogui.scroll(direction * scroll_amount, x=x, y=screen_height // 2)
            total_clicks += scroll_amount
            time.sleep(SCROLL_DELAY)  # Small delay for content to render

            # Check if we've scrolled enough
            # (This is approximate - actual scroll distance varies by application)
            estimated_scroll = total_clicks * SCROLL_PIXELS_PER_CLICK

            if direction == -1:  # Scrolling down
                if estimated_scroll >= (target_y - screen_height):
                    break
            else:  # Scrolling up
                if estimated_scroll >= abs(target_y):
                    break

        direction_str = "up" if direction > 0 else "down"
        return MouseScrollResult(
            success=True,
            clicks=total_clicks,
            direction=direction_str,
        )

    @agent.tool
    @desktop_tool("SCROLL TO ELEMENT", requires="pyautogui")
    def desktop_scroll_element_into_view(
        context: RunContext,
        element_y: int,
        element_height: int = 0,
        padding: int = 100,
        x: int | None = None,
        scroll_amount: int = 3,
    ) -> MouseScrollResult:
        """
        Scroll an element into view (like scrollIntoView in browsers).

        This scrolls the page so the element is visible with some padding.

        Args:
            element_y: Y coordinate of the element's top edge
            element_height: Height of the element (default: 0)
            padding: Pixels of padding to keep above/below element (default: 100)
            x: X coordinate to scroll at (if None, uses center)
            scroll_amount: Clicks per scroll action (default: 3)

        Returns:
            MouseScrollResult with success status

        Examples:
            - desktop_scroll_element_into_view(element_y=1500)
            - desktop_scroll_element_into_view(element_y=2000, element_height=50, padding=150)

        Use case: After finding an element with desktop_find_accessible_element,
        scroll it into view before clicking.

        Note: Cross-platform (macOS & Windows). Works with any scrollable window.
        """
        # Get screen dimensions
        screen_width, screen_height = pyautogui.size()

        # Use center X if not specified
        if x is None:
            x = screen_width // 2

        # Check if element is already visible
        visible_top = padding
        visible_bottom = screen_height - padding

        if visible_top <= element_y <= visible_bottom:
            # Element already visible
            return MouseScrollResult(
                success=True,
                clicks=0,
                direction="none",
            )

        # Determine scroll direction and amount
        if element_y < visible_top:
            # Element is above visible area - scroll up
            direction = 1  # Positive = up
            clicks_needed = (visible_top - element_y) // SCROLL_PIXELS_PER_CLICK
        else:
            # Element is below visible area - scroll down
            direction = -1  # Negative = down
            clicks_needed = (element_y - visible_bottom) // SCROLL_PIXELS_PER_CLICK

        # Clamp to reasonable values
        clicks_needed = min(max(clicks_needed, 1), 100)

        # Perform scroll
        total_clicks = 0
        for i in range(0, clicks_needed, scroll_amount):
            pyautogui.scroll(direction * scroll_amount, x=x, y=screen_height // 2)
            total_clicks += scroll_amount
            import time

            time.sleep(SCROLL_DELAY)  # Small delay for rendering

        direction_str = "up" if direction > 0 else "down"
        return MouseScrollResult(
            success=True,
            clicks=total_clicks,
            direction=direction_str,
        )

    @agent.tool
    @desktop_tool("SCROLL PAGE", requires="pyautogui")
    def desktop_scroll_page(
        context: RunContext,
        direction: Literal["up", "down", "page_up", "page_down"] = "down",
        pages: int = 1,
    ) -> MouseScrollResult:
        """
        Scroll by pages (like Page Up/Page Down keys).

        This performs large scrolls suitable for navigating long documents.

        Args:
            direction: Scroll direction - "up", "down", "page_up", "page_down"
            pages: Number of pages to scroll (default: 1)

        Returns:
            MouseScrollResult with success status

        Examples:
            - desktop_scroll_page(direction="down", pages=1) - Scroll down one page
            - desktop_scroll_page(direction="page_up", pages=2) - Scroll up two pages
            - desktop_scroll_page(direction="down", pages=5) - Scroll down 5 pages quickly

        Note: One "page" is approximately 10 scroll clicks
        """
        # Map direction to clicks
        clicks_per_page = 10

        if direction in ["down", "page_down"]:
            total_clicks = -clicks_per_page * pages  # Negative = down
        else:  # up or page_up
            total_clicks = clicks_per_page * pages  # Positive = up

        # Perform scroll
        pyautogui.scroll(total_clicks)

        direction_str = "up" if total_clicks > 0 else "down"
        return MouseScrollResult(
            success=True,
            clicks=abs(total_clicks),
            direction=direction_str,
        )

    @agent.tool
    def desktop_mouse_get_position(context: RunContext) -> MousePositionResult:
        """
        Get the current mouse cursor position.

        Uses native macOS APIs for accurate multi-monitor coordinate reporting.
        On Windows, uses pyautogui which handles multi-monitor correctly.

        Returns:
            MousePositionResult with x and y coordinates

        Example:
            - desktop_mouse_get_position() -> {"x": 542, "y": 319}
        """
        if not PYAUTOGUI_AVAILABLE:
            # Can't use decorator here since this returns a different type
            return {"error": "pyautogui not available"}

        # Use native API for accurate multi-monitor coordinates
        x, y = get_mouse_position_native()
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
            result["error"] = (
                "pyautogui not installed. Install with: uv pip install pyautogui"
            )
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
            # For Windows, just check if basic operations work
            try:
                pyautogui.position()
                result["has_permission"] = True
                result["status"] = "Basic automation appears to be working ✅"
            except Exception as e:
                result["has_permission"] = False
                result["error"] = f"Automation test failed: {e}"

        return result
