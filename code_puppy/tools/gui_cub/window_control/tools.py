from __future__ import annotations

import time
from typing import Literal

from pydantic_ai import RunContext

from ..dependencies import PYAUTOGUI_AVAILABLE

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None


from ..constants import DEFAULT_ALERT_TIMEOUT
from ..result_types import (
    AlertResult,
    MonitorInfo,
    MonitorsResult,
    PixelColorResult,
    SleepResult,
    WindowBoundsResult,
    WindowFocusResult,
)
from ..tool_wrapper import desktop_tool
from .core import _focus_window_impl, _get_active_window_bounds_impl


def register_window_control_tools(agent):
    """Register window control tools for desktop automation."""

    # Global counters to track tool invocations
    _focus_window_call_count = {"count": 0}
    _get_active_window_call_count = {"count": 0}

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
        # Use thread-safe native dialogs instead of pyautogui (which uses tkinter)
        from ..native_dialogs import native_alert

        try:
            response = native_alert(text=text, title=title, timeout=timeout)
            return AlertResult(success=True, response=response)
        except Exception as e:
            return AlertResult(success=False, error=str(e))

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
        # Use thread-safe native dialogs instead of pyautogui (which uses tkinter)
        from ..native_dialogs import native_confirm

        try:
            response = native_confirm(text=text, title=title, buttons=buttons)
            cancelled = response is None
            return AlertResult(success=True, response=response, cancelled=cancelled)
        except Exception as e:
            return AlertResult(success=False, error=str(e))

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
        # Use thread-safe native dialogs instead of pyautogui (which uses tkinter)
        from ..native_dialogs import native_prompt

        try:
            response = native_prompt(text=text, title=title, default=default)
            cancelled = response is None
            return AlertResult(success=True, response=response, cancelled=cancelled)
        except Exception as e:
            return AlertResult(success=False, error=str(e))

    @agent.tool
    def desktop_focus_window(
        context: RunContext,
        app_name: str | None = None,
    ) -> WindowFocusResult:
        # Increment call counter
        _focus_window_call_count["count"] += 1
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
        # Increment call counter
        _get_active_window_call_count["count"] += 1
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

        Uses native APIs for accurate multi-monitor detection:
        - macOS: Quartz/CoreGraphics for all displays
        - Windows: win32api for all monitors
        - Fallback: pyautogui (may only detect primary)

        Returns:
            MonitorsResult with list of monitors and their properties
            Coordinates are absolute virtual desktop (negative X = left of primary)

        Example:
            - desktop_get_monitors() -> Information about all displays

        Note: Useful for multi-monitor setups to target specific screens.
        """
        import sys

        try:
            monitors: list[MonitorInfo] = []
            primary_index: int | None = None

            if sys.platform == "darwin":
                # macOS: Use NSScreen for accurate multi-monitor detection
                try:
                    from AppKit import NSScreen

                    screens = NSScreen.screens()
                    main_screen = NSScreen.mainScreen()

                    for i, screen in enumerate(screens):
                        frame = screen.frame()
                        is_main = screen == main_screen
                        scale = screen.backingScaleFactor()  # HiDPI scale factor

                        monitor = MonitorInfo(
                            index=i,
                            x=int(frame.origin.x),
                            y=int(frame.origin.y),
                            width=int(frame.size.width),
                            height=int(frame.size.height),
                            is_primary=is_main,
                            scale_factor=float(scale),
                            scale_factor_detected=True,
                        )
                        monitors.append(monitor)

                        if is_main:
                            primary_index = i
                except ImportError:
                    pass  # Fall through to pyautogui fallback

            elif sys.platform == "win32":
                # Windows: Use ctypes for accurate multi-monitor detection
                try:
                    import ctypes
                    from ctypes import wintypes

                    user32 = ctypes.windll.user32

                    # MONITORINFOEXW structure (defined once, outside loop)
                    class MONITORINFOEXW(ctypes.Structure):
                        _fields_ = [
                            ("cbSize", wintypes.DWORD),
                            ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD),
                            ("szDevice", wintypes.WCHAR * 32),
                        ]

                    # Callback type for EnumDisplayMonitors
                    # Signature: BOOL CALLBACK MonitorEnumProc(HMONITOR, HDC, LPRECT, LPARAM)
                    MONITORENUMPROC = ctypes.WINFUNCTYPE(
                        wintypes.BOOL,
                        wintypes.HMONITOR,
                        wintypes.HDC,
                        ctypes.POINTER(wintypes.RECT),
                        wintypes.LPARAM,
                    )

                    # Collect monitor handles via callback
                    monitor_handles: list = []

                    def monitor_enum_callback(
                        hMonitor, hdcMonitor, lprcMonitor, dwData
                    ):
                        monitor_handles.append(hMonitor)
                        return True

                    # Enumerate all monitors
                    user32.EnumDisplayMonitors(
                        None, None, MONITORENUMPROC(monitor_enum_callback), 0
                    )

                    # Get detailed info for each monitor
                    for idx, hMonitor in enumerate(monitor_handles):
                        try:
                            mi = MONITORINFOEXW()
                            mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
                            user32.GetMonitorInfoW(hMonitor, ctypes.byref(mi))

                            rect = mi.rcMonitor
                            is_primary = bool(mi.dwFlags & 0x1)  # MONITORINFOF_PRIMARY

                            # Get per-monitor DPI (Windows 8.1+)
                            scale = 1.0
                            try:
                                shcore = ctypes.windll.shcore
                                dpi_x = ctypes.c_uint()
                                dpi_y = ctypes.c_uint()
                                # GetDpiForMonitor(hMonitor, MDT_EFFECTIVE_DPI=0, &dpiX, &dpiY)
                                if (
                                    shcore.GetDpiForMonitor(
                                        hMonitor,
                                        0,
                                        ctypes.byref(dpi_x),
                                        ctypes.byref(dpi_y),
                                    )
                                    == 0
                                ):  # S_OK
                                    scale = dpi_x.value / 96.0  # 96 DPI = 100% = 1.0x
                            except Exception:
                                pass  # Older Windows or DPI-unaware, assume 1.0

                            monitor = MonitorInfo(
                                index=idx,
                                x=rect.left,
                                y=rect.top,
                                width=rect.right - rect.left,
                                height=rect.bottom - rect.top,
                                is_primary=is_primary,
                                scale_factor=scale,
                                scale_factor_detected=True,
                            )
                            monitors.append(monitor)

                            if is_primary:
                                primary_index = idx
                        except Exception:
                            continue
                except Exception:
                    pass  # Fall through to pyautogui fallback

            # Fallback to pyautogui if native APIs didn't work
            if not monitors:
                try:
                    monitors_data = pyautogui.getAllMonitors()
                    monitors = [
                        MonitorInfo(
                            index=i,
                            x=m.x,
                            y=m.y,
                            width=m.width,
                            height=m.height,
                            is_primary=(i == 0),
                        )
                        for i, m in enumerate(monitors_data)
                    ]
                    primary_index = 0 if monitors else None
                except AttributeError:
                    # Oldest fallback - just primary screen
                    width, height = pyautogui.size()
                    monitors = [
                        MonitorInfo(
                            index=0,
                            x=0,
                            y=0,
                            width=width,
                            height=height,
                            is_primary=True,
                        )
                    ]
                    primary_index = 0

            return MonitorsResult(
                success=True,
                count=len(monitors),
                monitors=monitors,
                primary_index=primary_index,
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
            # pixel_utils is in parent directory (gui_cub), not window_control
            from ..pixel_utils import sample_neighborhood_rgb, match_rgb

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
