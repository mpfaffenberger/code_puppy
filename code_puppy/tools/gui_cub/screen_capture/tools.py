"""Tool registration for screen capture functionality."""

from __future__ import annotations

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

from pydantic_ai import RunContext

from ..constants import ERROR_PYAUTOGUI_MISSING
from ..result_types import VQAResult
from .screenshot_analyze import screenshot_analyze


def register_desktop_screenshot_tools(agent):
    """Register desktop screenshot and analysis tools."""

    @agent.tool
    def desktop_convert_screenshot_to_screen_coords(
        context: RunContext,
        screenshot_x: int,
        screenshot_y: int,
    ) -> dict[str, int | float]:
        """
        Convert screenshot (physical pixel) coordinates to screen (logical) coordinates.

        **CRITICAL for HiDPI/Retina displays!** On 2x displays, screenshots are 2x larger
        than the screen coordinates that mouse operations use.

        Use this when:
        - You used OCR to find text in a screenshot
        - You used VQA to locate an element in a screenshot
        - You need to click at a position found in a screenshot

        Args:
            screenshot_x: X coordinate from screenshot analysis (physical pixels)
            screenshot_y: Y coordinate from screenshot analysis (physical pixels)

        Returns:
            Dictionary with screen_x, screen_y (logical coordinates for mouse),
            and the scale_factor used

        Example:
            >>> # On 2x Retina display
            >>> # OCR found "Submit" at (940, 250) in screenshot
            >>> coords = desktop_convert_screenshot_to_screen_coords(940, 250)
            >>> # coords = {"screen_x": 470, "screen_y": 125, "scale_factor": 2.0}
            >>> # Now click at the converted coordinates:
            >>> desktop_mouse_click(x=coords["screen_x"], y=coords["screen_y"])
        """
        from ..platform import (
            convert_screenshot_to_screen_coords,
            get_screen_scale_factor,
        )

        scale_factor = get_screen_scale_factor()
        screen_x, screen_y = convert_screenshot_to_screen_coords(
            screenshot_x, screenshot_y, scale_factor
        )

        return {
            "screenshot_x": screenshot_x,
            "screenshot_y": screenshot_y,
            "screen_x": screen_x,
            "screen_y": screen_y,
            "scale_factor": scale_factor,
            "note": (
                f"Converted from screenshot space to screen space using scale factor {scale_factor}x. "
                "Use screen_x/screen_y for mouse operations."
            ),
        }

    @agent.tool
    def desktop_get_screen_size(context: RunContext) -> dict[str, int | float | str]:
        """
        Get the current screen resolution (logical points) and scale metadata.

        Returns:
            Dict with width, height (logical), scale_x/y, physical_width/height, and coordinate_space

        Example:
            - desktop_get_screen_size() -> {"width": 1728, "height": 1117, "scale_x": 2.0, "physical_width": 3456, ...}
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"error": ERROR_PYAUTOGUI_MISSING}

        width, height = pyautogui.size()
        try:
            from ..platform import get_screen_scale_factor

            scale = get_screen_scale_factor()
        except Exception:
            scale = 1.0
        physical_width = int(width * scale)
        physical_height = int(height * scale)
        return {
            "width": width,
            "height": height,
            "logical_width": width,
            "logical_height": height,
            "scale_x": scale,
            "scale_y": scale,
            "physical_width": physical_width,
            "physical_height": physical_height,
            "coordinate_space": "logical_points",
        }

    @agent.tool
    def desktop_get_screen_scale(context: RunContext) -> dict[str, int | float | str]:
        """
        Get screen DPI scale and coordinate space metadata (computed via screenshot).

        Returns:
            Dict with scale_x/y, logical (OS) size, physical (screenshot) size, and notes.
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"error": ERROR_PYAUTOGUI_MISSING}
        logical_w, logical_h = pyautogui.size()
        shot = pyautogui.screenshot()
        physical_w, physical_h = shot.size
        scale = round((physical_w / logical_w) * 4) / 4 if logical_w else 1.0
        return {
            "logical_width": logical_w,
            "logical_height": logical_h,
            "physical_width": physical_w,
            "physical_height": physical_h,
            "scale_x": scale,
            "scale_y": scale,
            "coordinate_space": "logical_points",
            "note": "Mouse APIs expect logical points; screenshots are physical pixels. Convert using scale computed from screenshot.",
        }

    @agent.tool
    async def desktop_vqa_window(
        context: RunContext,
        question: str,
        window_title: str | None = None,
        use_grid: bool = False,
    ) -> VQAResult:
        """
        Convenience wrapper for VQA on active window.

        This is the recommended way to use VQA for desktop automation workflows.
        Always captures window-only (never full screen).

        Args:
            question: Question to ask about the window
            window_title: Optional app/window to focus first
            use_grid: Add coordinate grid overlay

        Returns:
            VQAResult with window-relative coordinates

        Examples:
            # Find element in current window
            - desktop_vqa_window(question="Where is the Submit button?")

            # Find element in specific app
            - desktop_vqa_window(
                question="Locate the address bar",
                window_title="TextEdit"
              )
        """
        # Use new unified screenshot_analyze()
        result = await screenshot_analyze(
            question=question,
            window_title=window_title,
            mode="active_window",
            add_grid=use_grid,
        )

        # Convert dict result to VQAResult for backwards compatibility
        from ..result_types import VQAResult

        return VQAResult(
            success=result.get("success", False),
            question=result.get("question"),
            answer=result.get("answer", ""),
            confidence=result.get("confidence", 0.0),
            observations=result.get("observations"),
            screenshot_path=result.get("screenshot_path"),
        )

    @agent.tool
    def desktop_window_to_screen_coords(
        context: RunContext,
        window_x: int,
        window_y: int,
        window_title: str | None = None,
    ) -> dict[str, int | str]:
        """
        Convert window-relative coordinates to screen-absolute coordinates.

        Use this when you have coordinates from VQA (which are window-relative by default)
        and need to convert them to screen coordinates for mouse operations.

        Args:
            window_x: X coordinate relative to window top-left
            window_y: Y coordinate relative to window top-left
            window_title: Optional window to get bounds for (default: active window)

        Returns:
            Dict with screen_x, screen_y, and metadata

        Examples:
            # VQA found button at (200, 150) in window
            - coords = desktop_window_to_screen_coords(window_x=200, window_y=150)
            - desktop_mouse_click(x=coords["screen_x"], y=coords["screen_y"])
        """
        from ..coordinates import window_to_screen_coords
        from ..window_control import _focus_window_impl, _get_active_window_bounds_impl

        # Get window bounds
        if window_title:
            _focus_window_impl(window_title)

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            return {
                "error": f"Could not get window bounds: {bounds.error or 'Unknown error'}"
            }

        try:
            screen_x, screen_y = window_to_screen_coords(window_x, window_y, bounds)
            return {
                "screen_x": screen_x,
                "screen_y": screen_y,
                "window_x": window_x,
                "window_y": window_y,
                "window_title": bounds.window_title or bounds.app_name,
                "window_bounds": {
                    "x": bounds.x,
                    "y": bounds.y,
                    "width": bounds.width,
                    "height": bounds.height,
                },
            }
        except ValueError as e:
            return {"error": str(e)}

    @agent.tool
    def desktop_screen_to_window_coords(
        context: RunContext,
        screen_x: int,
        screen_y: int,
        window_title: str | None = None,
    ) -> dict[str, int | str]:
        """
        Convert screen-absolute coordinates to window-relative coordinates.

        Use this when you have screen coordinates and need to convert them to
        window-relative coordinates.

        Args:
            screen_x: X coordinate in screen space
            screen_y: Y coordinate in screen space
            window_title: Optional window to get bounds for (default: active window)

        Returns:
            Dict with window_x, window_y, and metadata

        Examples:
            # Convert screen click to window coords
            - coords = desktop_screen_to_window_coords(screen_x=1000, screen_y=500)
            - print(f"Window position: ({coords['window_x']}, {coords['window_y']})")
        """
        from ..coordinates import screen_to_window_coords
        from ..window_control import _focus_window_impl, _get_active_window_bounds_impl

        # Get window bounds
        if window_title:
            _focus_window_impl(window_title)

        bounds = _get_active_window_bounds_impl()
        if not bounds.success:
            return {
                "error": f"Could not get window bounds: {bounds.error or 'Unknown error'}"
            }

        try:
            window_x, window_y = screen_to_window_coords(screen_x, screen_y, bounds)
            return {
                "window_x": window_x,
                "window_y": window_y,
                "screen_x": screen_x,
                "screen_y": screen_y,
                "window_title": bounds.window_title or bounds.app_name,
                "window_bounds": {
                    "x": bounds.x,
                    "y": bounds.y,
                    "width": bounds.width,
                    "height": bounds.height,
                },
            }
        except ValueError as e:
            return {"error": str(e)}
