"""Window management for desktop automation automation."""

from __future__ import annotations

import subprocess
import time
from typing import Literal

from pydantic_ai import RunContext

from .constants import (
    DEFAULT_ALERT_TIMEOUT,
    DEFAULT_WINDOW_FOCUS_TIMEOUT,
    ERROR_APPKIT_MISSING,
)
from .platform import IS_MACOS, IS_WINDOWS
from .result_types import (
    AlertResult,
    MonitorInfo,
    MonitorsResult,
    PixelColorResult,
    SleepResult,
    WindowFocusResult,
    WindowBoundsResult,
)
from .tool_wrapper import desktop_tool


def _get_active_window_bounds_impl() -> WindowBoundsResult:
    """
    Internal helper to get active window bounds.

    This is extracted as a module-level function so it can be imported
    for use in other desktop automation tools (e.g., screen_capture).

    Returns:
        WindowBoundsResult with window position, size, and app name
    """
    if IS_WINDOWS:
        # Windows implementation
        try:
            from .windows_automation import WINDOWS_AUTOMATION_AVAILABLE

            if not WINDOWS_AUTOMATION_AVAILABLE:
                return WindowBoundsResult(
                    success=False,
                    error="Windows automation not available. Install: uv pip install pywin32",
                )

            import win32gui

            # Get foreground window
            hwnd = win32gui.GetForegroundWindow()
            if not hwnd:
                return WindowBoundsResult(
                    success=False, error="No foreground window found"
                )

            # Get window rect
            rect = win32gui.GetWindowRect(hwnd)
            x, y, right, bottom = rect
            width = right - x
            height = bottom - y

            # Get window title
            window_title = win32gui.GetWindowText(hwnd)

            return WindowBoundsResult(
                success=True,
                x=x,
                y=y,
                width=width,
                height=height,
                window_title=window_title,
            )

        except Exception as e:
            return WindowBoundsResult(
                success=False, error=f"Failed to get window bounds: {str(e)}"
            )

    elif IS_MACOS:
        # macOS implementation
        try:
            from AppKit import NSWorkspace
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
            )

            # Get frontmost app
            workspace = NSWorkspace.sharedWorkspace()
            app = workspace.frontmostApplication()
            app_name = app.localizedName()
            pid = app.processIdentifier()

            # Get window list and find the frontmost window for this app
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )

            # Find the LARGEST window belonging to this PID
            # This ensures we get the main app window, not mini players or notifications
            candidate_windows = []
            for window in window_list:
                if window.get("kCGWindowOwnerPID") == pid:
                    bounds = window.get("kCGWindowBounds")
                    if bounds:
                        width = int(bounds["Width"])
                        height = int(bounds["Height"])
                        # Filter out tiny windows (< 100x100) - likely helpers/notifications
                        if width >= 100 and height >= 100:
                            candidate_windows.append(
                                {
                                    "bounds": bounds,
                                    "title": window.get("kCGWindowName"),
                                    "area": width * height,
                                    "layer": window.get("kCGWindowLayer", 0),
                                }
                            )

            # Debug logging
            from code_puppy.messaging import emit_info

            if len(candidate_windows) > 1:
                emit_info(
                    f"[dim]🔍 Found {len(candidate_windows)} windows for {app_name}:[/dim]\n"
                    + "\n".join(
                        f"[dim]   • {w['title'] or 'Untitled'}: {int(w['bounds']['Width'])}x{int(w['bounds']['Height'])} "
                        f"at ({int(w['bounds']['X'])}, {int(w['bounds']['Y'])}) - area: {w['area']:,}px²[/dim]"
                        for w in sorted(
                            candidate_windows, key=lambda x: x["area"], reverse=True
                        )
                    )
                )

            if not candidate_windows:
                return WindowBoundsResult(
                    success=False,
                    error=f"No visible windows found for {app_name} (might be minimized or menu bar app)",
                )

            # Sort by area (largest first), then by layer (lower layer = more visible)
            candidate_windows.sort(key=lambda w: (w["area"], -w["layer"]), reverse=True)

            # Return the largest window
            best_window = candidate_windows[0]
            bounds = best_window["bounds"]

            if len(candidate_windows) > 1:
                emit_info(
                    f"[green]✓ Selected largest window: {best_window['title'] or 'Untitled'} "
                    f"({int(bounds['Width'])}x{int(bounds['Height'])})[/green]"
                )

            return WindowBoundsResult(
                success=True,
                x=int(bounds["X"]),
                y=int(bounds["Y"]),
                width=int(bounds["Width"]),
                height=int(bounds["Height"]),
                app_name=app_name,
                window_title=best_window["title"],
            )

        except ImportError:
            return WindowBoundsResult(
                success=False, error="AppKit or Quartz not available (macOS only)"
            )
        except Exception as e:
            return WindowBoundsResult(
                success=False, error=f"Failed to get window bounds: {str(e)}"
            )

    else:
        return WindowBoundsResult(success=False, error="Platform not supported")


# Public module-level functions that can be imported
# These are used by other desktop automation modules (e.g., screen_capture)


def get_active_window_bounds() -> WindowBoundsResult:
    """Get the bounds of the active/frontmost window.

    Public API for getting window bounds. Can be imported and used
    directly without needing agent tool registration.

    Returns:
        WindowBoundsResult with window position, size, and app name
    """
    return _get_active_window_bounds_impl()


def focus_window(app_name: str | None = None) -> WindowFocusResult:
    """Focus (activate) a window by app name.

    Public API for focusing windows. Can be imported and used
    directly without needing agent tool registration.

    Args:
        app_name: Name of application to focus (None to refocus frontmost)

    Returns:
        WindowFocusResult with success status and focused app name
    """
    return _focus_window_impl(app_name)


# Backwards compatibility aliases
desktop_get_active_window = get_active_window_bounds
desktop_focus_window = focus_window


def _focus_window_impl(app_name: str | None = None) -> WindowFocusResult:
    """
    Internal helper to focus a window by app name.

    This is extracted as a module-level function so it can be imported
    for use in other desktop automation tools (e.g., screen_capture).

    Args:
        app_name: Name of the application to focus (None to refocus frontmost)

    Returns:
        WindowFocusResult with success status and focused app name
    """
    if IS_WINDOWS:
        # Windows implementation
        try:
            from .windows_automation import (
                WINDOWS_AUTOMATION_AVAILABLE,
                focus_window,
            )

            if not WINDOWS_AUTOMATION_AVAILABLE:
                return WindowFocusResult(
                    success=False,
                    error="Windows automation not available. Install: uv pip install pywin32 pywinauto",
                )

            success = focus_window(window_title=app_name)

            if success:
                return WindowFocusResult(success=True, focused_app=app_name)
            else:
                return WindowFocusResult(success=False, error="Window not found")

        except Exception as e:
            return WindowFocusResult(
                success=False, error=f"Failed to focus window: {str(e)}"
            )

    elif IS_MACOS:
        # macOS implementation
        try:
            if app_name:
                # Focus specific application using AppleScript
                script = f'tell application "{app_name}" to activate'
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=DEFAULT_WINDOW_FOCUS_TIMEOUT,
                )

                if result.returncode != 0:
                    error_msg = (
                        result.stderr.strip() if result.stderr else "Unknown error"
                    )
                    return WindowFocusResult(
                        success=False,
                        error=f"Failed to focus {app_name}: {error_msg}",
                    )

                return WindowFocusResult(success=True, focused_app=app_name)

            else:
                # Re-focus frontmost application
                try:
                    from AppKit import NSWorkspace

                    workspace = NSWorkspace.sharedWorkspace()
                    app = workspace.frontmostApplication()
                    app_name_current = app.localizedName()

                    # Re-activate it
                    app.activateWithOptions_(0)

                    return WindowFocusResult(success=True, focused_app=app_name_current)

                except ImportError:
                    return WindowFocusResult(success=False, error=ERROR_APPKIT_MISSING)

        except subprocess.TimeoutExpired:
            return WindowFocusResult(
                success=False,
                error=f"Timeout while trying to focus {app_name or 'app'}",
            )
        except Exception as e:
            return WindowFocusResult(
                success=False, error=f"Failed to focus window: {str(e)}"
            )

    else:
        return WindowFocusResult(success=False, error="Platform not supported")


def register_window_control_tools(agent):
    """Register window control tools for desktop automation."""

    @agent.tool
    @desktop_tool("SLEEP", requires="pyautogui")
    def desktop_sleep(
        context: RunContext,
        seconds: float,
    ) -> SleepResult:
        """
        Pause execution for a specified number of seconds.

        Args:
            seconds: Time to sleep in seconds (can be fractional)

        Returns:
            SleepResult with success status

        Examples:
            - desktop_sleep(seconds=1.0) - Wait 1 second
            - desktop_sleep(seconds=0.5) - Wait half a second
            - desktop_sleep(seconds=2.5) - Wait 2.5 seconds
        """
        time.sleep(seconds)
        return SleepResult(success=True, seconds=seconds)

    @agent.tool
    @desktop_tool("ALERT", requires="pyautogui")
    def desktop_alert(
        context: RunContext,
        text: str,
        title: str = "Desktop Automation Alert",
        timeout: int = DEFAULT_ALERT_TIMEOUT,
    ) -> AlertResult:
        """
        Display an alert dialog box (useful for debugging or getting user attention).

        Args:
            text: The message to display
            title: The title of the alert box
            timeout: Milliseconds before auto-close (0 for no timeout)

        Returns:
            AlertResult with success status and button clicked

        Examples:
            - desktop_alert(text="Task completed!") - Show simple alert
            - desktop_alert(text="Please review", title="Manual Check Required") - Custom title
        """
        import pyautogui

        response = pyautogui.alert(text=text, title=title, timeout=timeout)
        return AlertResult(success=True, response=response)

    @agent.tool
    @desktop_tool("CONFIRM", requires="pyautogui")
    def desktop_confirm(
        context: RunContext,
        text: str,
        title: str = "Confirm",
        buttons: list[str] | None = None,
    ) -> AlertResult:
        """
        Display a confirmation dialog with buttons.

        Args:
            text: The message to display
            title: The title of the confirmation box
            buttons: List of button labels (default: ["OK", "Cancel"])

        Returns:
            AlertResult with success status and which button was clicked

        Examples:
            - desktop_confirm(text="Continue with this action?") - OK/Cancel
            - desktop_confirm(text="Choose option:", buttons=["Yes", "No", "Cancel"]) - Custom buttons
        """
        import pyautogui

        if buttons:
            response = pyautogui.confirm(text=text, title=title, buttons=buttons)
        else:
            response = pyautogui.confirm(text=text, title=title)

        return AlertResult(success=True, response=response)

    @agent.tool
    @desktop_tool("PROMPT", requires="pyautogui")
    def desktop_prompt(
        context: RunContext,
        text: str,
        title: str = "Input",
        default: str = "",
    ) -> AlertResult:
        """
        Display a text input prompt dialog.

        Args:
            text: The prompt message
            title: The title of the prompt box
            default: Default text in the input field

        Returns:
            AlertResult with success status and user input

        Examples:
            - desktop_prompt(text="Enter your name:") - Simple text input
            - desktop_prompt(text="Enter amount:", default="100") - Input with default value
        """
        import pyautogui

        response = pyautogui.prompt(text=text, title=title, default=default)
        cancelled = response is None
        return AlertResult(success=True, response=response, cancelled=cancelled)

    @agent.tool
    def desktop_focus_window(
        context: RunContext,
        app_name: str | None = None,
    ) -> WindowFocusResult:
        """
        Focus (activate/bring to front) a window or application.

        This ensures the target window is active before performing actions like:
        - Accessibility API element searches
        - Screenshot capture
        - Mouse clicks and keyboard input

        Args:
            app_name: Name of application to focus (e.g., "Finder", "TextEdit", "Terminal")
                      If None, re-focuses the current frontmost application

        Returns:
            WindowFocusResult with success status and focused app name

        Examples:
            - desktop_focus_window(app_name="Finder") - Bring Finder to front
            - desktop_focus_window(app_name="TextEdit") - Activate TextEdit
            - desktop_focus_window() - Re-focus current app (useful to ensure focus)

        Best Practice:
            ALWAYS focus the window before clicking or searching for elements!

        Workflow:
            1. desktop_focus_window(app_name="Finder")
            2. desktop_sleep(seconds=0.5)  # Let focus settle
            3. desktop_click_accessible_element(title="Documents")

        Note: Cross-platform! Uses AppleScript on macOS, Win32 API on Windows.

        Platform-specific args:
            macOS: Use app_name ("Finder", "TextEdit")
            Windows: Use app_name as window title ("Notepad", "Calculator")
        """
        # Use the platform-independent helper function
        return _focus_window_impl(app_name)

    @agent.tool
    def desktop_get_active_window(context: RunContext) -> WindowBoundsResult:
        """
        Get the bounds (position and size) of the active/frontmost window.

        This is useful for targeting specific windows for screenshots, OCR, or clicks
        instead of capturing the entire screen.

        Returns:
            WindowBoundsResult with window position, size, and app name

        Examples:
            - desktop_get_active_window() -> Get frontmost window bounds

        Best Practice:
            Use this to get window bounds before OCR/screenshots to avoid
            capturing unrelated windows and improve performance.

        Workflow:
            1. desktop_focus_window(app_name="Finder")
            2. desktop_sleep(seconds=0.5)  # Let focus settle
            3. bounds = desktop_get_active_window()
            4. desktop_extract_text(x=bounds.x, y=bounds.y, width=bounds.width, height=bounds.height)

        Note: Cross-platform! Uses AppKit on macOS, Win32 API on Windows.
        """
        return _get_active_window_bounds_impl()

    @agent.tool
    def desktop_get_monitors(context: RunContext) -> MonitorsResult:
        """
        Get information about all connected monitors/displays.

        Returns:
            MonitorsResult with list of monitors and their properties

        Example:
            - desktop_get_monitors() -> Information about all displays

        Note: Useful for multi-monitor setups to target specific screens.
        """
        try:
            import pyautogui

            # Get all monitors (pyautogui 0.9.54+)
            try:
                monitors_data = pyautogui.getAllMonitors()
                monitors = [
                    MonitorInfo(
                        index=i,
                        x=m.x,
                        y=m.y,
                        width=m.width,
                        height=m.height,
                        is_primary=(i == 0),  # First monitor is typically primary
                    )
                    for i, m in enumerate(monitors_data)
                ]

                return MonitorsResult(
                    success=True,
                    count=len(monitors),
                    monitors=monitors,
                    primary_index=0 if monitors else None,
                )
            except AttributeError:
                # Fallback for older pyautogui versions
                # Just return single screen info
                width, height = pyautogui.size()
                monitors = [
                    MonitorInfo(
                        index=0, x=0, y=0, width=width, height=height, is_primary=True
                    )
                ]
                return MonitorsResult(
                    success=True, count=1, monitors=monitors, primary_index=0
                )

        except Exception as e:
            return MonitorsResult(success=False, error=str(e))

    @agent.tool
    @desktop_tool("CHECK PIXEL COLOR", requires="pyautogui")
    def desktop_check_pixel_color(
        context: RunContext,
        x: int,
        y: int,
        red: int,
        green: int,
        blue: int,
        tolerance: int = 10,
        neighborhood: int = 1,
        strategy: Literal["any", "all", "majority", "mean"] = "any",
    ) -> PixelColorResult:
        """
        Check if pixel at coordinates matches expected RGB color.

        Useful for verifying UI state changes, color-based detection.

        HiDPI-safe and anti-aliasing aware: supports neighborhood sampling and
        flexible match strategies.

        Args:
            x: X coordinate (logical points)
            y: Y coordinate (logical points)
            red: Expected red value (0-255)
            green: Expected green value (0-255)
            blue: Expected blue value (0-255)
            tolerance: Allowed difference per channel (0-255)
            neighborhood: Half-size of sampling window in pixels (logical). 0 = exact pixel,
                          1 = 3x3, 2 = 5x5, etc.
            strategy: Matching strategy across neighborhood:
                - "any": any sampled pixel within tolerance (good for thin outlines)
                - "all": all sampled pixels within tolerance (strict)
                - "majority": more than half sampled pixels within tolerance
                - "mean": mean RGB within tolerance of expected

        Returns:
            PixelColorResult with match status and actual color (center pixel)

        Examples:
            - desktop_check_pixel_color(x=100, y=100, red=255, green=0, blue=0) - Check for red
            - desktop_check_pixel_color(x=500, y=300, red=0, green=255, blue=0, tolerance=20) - Check for green

        Note: Useful for verifying button states, progress indicators, etc.
        """
        expected_color = (int(red), int(green), int(blue))
        import pyautogui

        try:
            # Use DPI-safe neighborhood sampling utilities
            from .pixel_utils import sample_neighborhood_rgb, match_rgb

            samples, center_rgb = sample_neighborhood_rgb(
                x=x, y=y, neighborhood=neighborhood
            )
            matches = match_rgb(
                samples,
                expected=expected_color,
                tolerance=int(tolerance),
                strategy=strategy,
            )

            return PixelColorResult(
                success=True,
                matches=matches,
                expected=list(expected_color),
                actual=list(center_rgb),
                position={"x": x, "y": y},
                tolerance=int(tolerance),
            )
        except Exception as e:
            # Fallback: try pyautogui.pixel (may be DPI-unsafe on some platforms)
            try:
                actual = pyautogui.pixel(x, y)
                # actual may be a RGB or RGBA tuple
                actual_rgb = (
                    list(actual[:3]) if hasattr(actual, "__len__") else [int(actual)]
                )
                matches = all(
                    abs(a - e) <= int(tolerance)
                    for a, e in zip(actual_rgb, list(expected_color))
                )
                return PixelColorResult(
                    success=True,
                    matches=matches,
                    expected=list(expected_color),
                    actual=actual_rgb,
                    position={"x": x, "y": y},
                    tolerance=int(tolerance),
                    error=str(e),
                )
            except Exception as e2:
                return PixelColorResult(
                    success=False,
                    error=f"Pixel color check failed: {e2}",
                    position={"x": x, "y": y},
                    tolerance=int(tolerance),
                )
