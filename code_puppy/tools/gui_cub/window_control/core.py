"""Window management for desktop automation automation."""

from __future__ import annotations

import subprocess
import time

from code_puppy.messaging import emit_info

from ..constants import (
    DEFAULT_WINDOW_FOCUS_TIMEOUT,
    ERROR_APPKIT_MISSING,
)
from ..platform import IS_MACOS, IS_WINDOWS
from ..result_types import (
    WindowFocusResult,
    WindowBoundsResult,
)


def _get_window_bounds_by_app_name(app_name: str) -> WindowBoundsResult:
    """
    Get window bounds for a specific application by name.

    Args:
        app_name: Name of the application (e.g., "Calculator", "Safari")

    Returns:
        WindowBoundsResult with window position and size
    """
    if IS_WINDOWS:
        # Windows implementation - find window by title/class
        return WindowBoundsResult(
            success=False,
            error="Windows implementation not yet available for app-specific window capture",
        )

    elif IS_MACOS:
        try:
            from AppKit import NSWorkspace
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
            )

            # Find the app by name
            workspace = NSWorkspace.sharedWorkspace()
            running_apps = workspace.runningApplications()

            target_app = None
            for app in running_apps:
                if app.localizedName() == app_name:
                    target_app = app
                    break

            if not target_app:
                return WindowBoundsResult(
                    success=False,
                    error=f"Application '{app_name}' not found or not running",
                )

            pid = target_app.processIdentifier()

            # Get window list and find windows for this PID
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )

            candidate_windows = []
            for window in window_list:
                if window.get("kCGWindowOwnerPID") == pid:
                    bounds = window.get("kCGWindowBounds")
                    if bounds:
                        width = int(bounds["Width"])
                        height = int(bounds["Height"])
                        if width >= 100 and height >= 100:
                            candidate_windows.append(
                                {
                                    "bounds": bounds,
                                    "title": window.get("kCGWindowName"),
                                    "area": width * height,
                                    "layer": window.get("kCGWindowLayer", 0),
                                }
                            )

            if not candidate_windows:
                return WindowBoundsResult(
                    success=False,
                    error=f"No visible windows found for {app_name}",
                )

            # Sort by area (largest first)
            candidate_windows.sort(key=lambda w: (w["area"], -w["layer"]), reverse=True)
            best_window = candidate_windows[0]
            bounds = best_window["bounds"]

            # NOTE: CGWindowListCopyWindowInfo returns coordinates in POINTS (logical coordinates),
            # not physical pixels. On Retina displays, points are the same as logical pixels.
            # To convert to physical pixels for screenshot APIs, multiply by backingScaleFactor.
            # See: https://developer.apple.com/documentation/coregraphics/kcgwindowbounds
            logical_x = int(bounds["X"])
            logical_y = int(bounds["Y"])
            logical_width = int(bounds["Width"])
            logical_height = int(bounds["Height"])

            return WindowBoundsResult(
                success=True,
                x=logical_x,
                y=logical_y,
                width=logical_width,
                height=logical_height,
                app_name=app_name,
                window_title=best_window["title"],
            )

        except Exception as e:
            return WindowBoundsResult(
                success=False,
                error=f"Failed to get window bounds for {app_name}: {str(e)}",
            )

    else:
        return WindowBoundsResult(
            success=False,
            error="Unsupported platform",
        )


# Module-level call counter for tracking
_get_active_window_bounds_call_count = {"count": 0}


def _is_app_window_topmost(app_name: str) -> bool:
    """
    Check if the given app has a window at layer 0 (topmost visible layer).

    This uses the CORRECT method of checking window focus by examining
    kCGWindowLayer values, NOT NSWorkspace.frontmostApplication() which
    returns stale/incorrect data.

    Args:
        app_name: Application name to check (e.g., "TextEdit", "Calculator")

    Returns:
        True if the app has a window at layer 0 (topmost), False otherwise
    """
    if not IS_MACOS:
        return False

    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGNullWindowID,
        )

        # Get ALL on-screen windows
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )

        # Check if ANY window from this app is at layer 0 (topmost)
        for window in window_list:
            owner_name = window.get("kCGWindowOwnerName")
            layer = window.get("kCGWindowLayer", 0)
            bounds = window.get("kCGWindowBounds")

            if owner_name == app_name and layer == 0 and bounds:
                # Also check it's not a tiny window (notification/helper)
                width = int(bounds.get("Width", 0))
                height = int(bounds.get("Height", 0))
                if width >= 100 and height >= 100:
                    return True

        return False

    except Exception:
        return False


def _get_active_window_bounds_impl() -> WindowBoundsResult:
    """
    Internal helper to get active window bounds.

    This is extracted as a module-level function so it can be imported
    for use in other desktop automation tools (e.g., screen_capture).

    Returns:
        WindowBoundsResult with window position, size, and app name
    """
    # Increment call counter
    _get_active_window_bounds_call_count["count"] += 1
    if IS_WINDOWS:
        # Windows implementation
        try:
            from ..windows_automation import WINDOWS_AUTOMATION_AVAILABLE

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
            from Quartz import (
                CGWindowListCopyWindowInfo,
                kCGWindowListOptionOnScreenOnly,
                kCGNullWindowID,
            )

            # LAYER-FIRST APPROACH: Use CGWindowLayer as GROUND TRUTH, NSWorkspace as fallback hint
            #
            # PROBLEM: NSWorkspace.frontmostApplication() is CACHED and STALE!
            # When we call desktop_focus_window("TextEdit"), AppleScript activates it successfully,
            # but NSWorkspace still returns "Calculator" for several seconds!
            #
            # SOLUTION: Trust the window layer ordering from CGWindowListCopyWindowInfo.
            # The FIRST window at layer 0 (after filtering) IS the active window - no guessing needed!
            #
            # Strategy:
            # 1. Get ALL windows in front-to-back order from CGWindowListCopyWindowInfo
            # 2. Filter out non-normal windows (layer != 0, tiny size, mini-players)
            # 3. Return FIRST valid window = frontmost window (GUARANTEED by macOS window server)
            # 4. No NSWorkspace needed - layer 0 ordering is the ground truth!
            #
            # This fixes:
            # - Focus race condition: Layer updates immediately, NSWorkspace doesn't
            # - Stale menu bar data: We don't trust NSWorkspace at all
            # - Reliable after focus: Works instantly after desktop_focus_window() succeeds

            # Get ALL on-screen windows (front-to-back order)
            window_list = CGWindowListCopyWindowInfo(
                kCGWindowListOptionOnScreenOnly, kCGNullWindowID
            )

            # CRITICAL: CGWindowListCopyWindowInfo returns windows in FRONT-TO-BACK order!
            # The FIRST window at layer 0 is the frontmost window!
            # We must preserve this order and NOT sort by area.
            #
            # Strategy:
            # 1. Iterate in front-to-back order (preserve original list order)
            # 2. Skip windows at layer != 0 (not normal app windows)
            # 3. Skip windows < 100x100 (notifications/helpers)
            # 4. Skip windows < 20,000px² (mini-players/utility windows)
            # 5. Return FIRST window that passes all filters = frontmost main window

            MIN_WIDTH = 100
            MIN_HEIGHT = 100
            MIN_AREA = 20_000  # ~141x141 - filters out tiny notification/helper windows

            # Find the FIRST valid layer-0 window (this is the active window!)
            active_window = None

            for window in window_list:
                bounds = window.get("kCGWindowBounds")
                owner_pid = window.get("kCGWindowOwnerPID")
                owner_name = window.get("kCGWindowOwnerName")
                layer = window.get("kCGWindowLayer", 0)

                # Skip non-normal windows (menus, desktop, etc.)
                if layer != 0:
                    continue

                # Skip windows without required info
                if not (bounds and owner_pid and owner_name):
                    continue

                width = int(bounds["Width"])
                height = int(bounds["Height"])
                area = width * height

                # Filter out tiny windows (notifications, helpers)
                if width < MIN_WIDTH or height < MIN_HEIGHT:
                    continue

                # Filter out mini-players / utility windows
                # But allow small apps like Calculator (69,300px² ~= 263x263)
                # Typical mini-players are < 50,000px² (~224x224)
                if area < MIN_AREA:
                    continue

                # This is the active window! (First valid layer-0 window)
                active_window = {
                    "bounds": bounds,
                    "title": window.get("kCGWindowName"),
                    "area": area,
                    "layer": layer,
                    "pid": owner_pid,
                    "app_name": owner_name,
                }

                emit_info(
                    f"[dim]🔍 DEBUG: Found active window (first layer-0 window): '{owner_name}'[/dim]"
                )
                break  # First valid window IS the active window!

            # Check if we found any valid window
            if not active_window:
                return WindowBoundsResult(
                    success=False,
                    error=f"No visible windows found (all windows < {MIN_WIDTH}x{MIN_HEIGHT} or < {MIN_AREA:,}px²)",
                )

            # Use the active window we found
            best_window = active_window
            # Extract window info
            bounds = best_window["bounds"]
            app_name = best_window["app_name"]
            pid = best_window["pid"]

            # Debug logging
            emit_info(
                f"[dim]🔍 DEBUG: Selected window:[/dim]\n"
                f"[dim]   app_name={app_name!r}, pid={pid}[/dim]\n"
                f"[dim]   window_title={best_window['title']!r}[/dim]\n"
                f"[dim]   layer={best_window['layer']}, area={best_window['area']:,}px²[/dim]"
            )

            # NOTE: macOS CGWindowListCopyWindowInfo returns coordinates in POINTS
            # (logical coordinates), not physical pixels. On Retina displays, points
            # are equivalent to logical pixels. To convert to physical pixels for
            # screenshot APIs, multiply by backingScaleFactor.
            # See: https://developer.apple.com/documentation/coregraphics/kcgwindowbounds
            logical_x = int(bounds["X"])
            logical_y = int(bounds["Y"])
            logical_width = int(bounds["Width"])
            logical_height = int(bounds["Height"])

            # Window bounds are in logical coordinates (points)
            # On Retina displays, multiply by scale_factor to get physical pixels

            # DEBUG: Log the bounds we're about to return
            emit_info(
                f"[dim]🔍 DEBUG [_get_active_window_bounds_impl]: Returning window bounds[/dim]\n"
                f"[dim]   app_name={app_name}[/dim]\n"
                f"[dim]   window_title={best_window['title']}[/dim]\n"
                f"[dim]   LOGICAL coords (points): x={logical_x}, y={logical_y}, w={logical_width}, h={logical_height}[/dim]\n"
                f"[dim]   These are macOS CGWindowBounds in POINTS (will be multiplied by scale_factor for physical pixels)[/dim]"
            )

            return WindowBoundsResult(
                success=True,
                x=logical_x,
                y=logical_y,
                width=logical_width,
                height=logical_height,
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
            from ..windows_automation import WINDOWS_AUTOMATION_AVAILABLE
            from ..windows_automation.core import focus_window

            if not WINDOWS_AUTOMATION_AVAILABLE:
                return WindowFocusResult(
                    success=False,
                    error="Windows automation not available. Install: uv pip install pywin32 pywinauto",
                )

            success, error_msg = focus_window(window_title=app_name)

            if success:
                return WindowFocusResult(success=True, focused_app=app_name)
            else:
                # Provide more specific error message
                if error_msg == "not_found":
                    return WindowFocusResult(
                        success=False,
                        error=f"Window '{app_name}' not found. Window may need to be opened first.",
                    )
                else:
                    return WindowFocusResult(
                        success=False,
                        error=f"Window '{app_name}' found but focus failed: {error_msg}",
                    )

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
                    encoding="utf-8",
                    errors="replace",
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

                # CRITICAL: AppleScript's 'activate' is asynchronous!
                # We need to wait for the window to actually become frontmost
                # before returning, otherwise subsequent OCR/screenshot calls will
                # capture the WRONG window!

                # Verification loop: wait until the app window is actually at layer 0 (topmost)
                # NOTE: We use _is_app_window_topmost() instead of NSWorkspace.frontmostApplication()
                # because NSWorkspace returns stale/incorrect data (it reports menu bar owner,
                # not actual window focus).
                max_wait_time = 3.0  # Maximum 3 seconds to wait
                poll_interval = 0.1  # Check every 100ms
                elapsed = 0.0

                while elapsed < max_wait_time:
                    time.sleep(poll_interval)
                    elapsed += poll_interval

                    # Check if app has a window at layer 0 (topmost)
                    if _is_app_window_topmost(app_name):
                        # Success! The window is now at the topmost layer
                        # Add a tiny buffer to ensure it's fully settled
                        time.sleep(0.2)  # Buffer for stability
                        return WindowFocusResult(success=True, focused_app=app_name)

                # Timeout - the window didn't reach layer 0 in time
                # Try to provide helpful error message
                bounds_result = _get_active_window_bounds_impl()
                actual_topmost = (
                    bounds_result.app_name if bounds_result.success else "unknown"
                )

                return WindowFocusResult(
                    success=False,
                    error=f"Failed to focus {app_name}: Window was activated but {actual_topmost} is still topmost after {max_wait_time}s. Try focusing the window manually or check if it's minimized.",
                )

            else:
                # Re-focus frontmost application
                try:
                    # Get the ACTUAL topmost app using layer detection, not NSWorkspace
                    bounds_result = _get_active_window_bounds_impl()
                    if not bounds_result.success:
                        return WindowFocusResult(
                            success=False,
                            error="Failed to determine current frontmost app",
                        )

                    app_name_current = bounds_result.app_name

                    # Re-activate it via AppleScript
                    script = f'tell application "{app_name_current}" to activate'
                    result = subprocess.run(
                        ["osascript", "-e", script],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=DEFAULT_WINDOW_FOCUS_TIMEOUT,
                    )

                    if result.returncode != 0:
                        return WindowFocusResult(
                            success=False,
                            error=f"Failed to re-focus {app_name_current}",
                        )

                    # Verification loop: ensure it's still at layer 0
                    max_wait_time = 2.0
                    poll_interval = 0.1
                    elapsed = 0.0

                    while elapsed < max_wait_time:
                        time.sleep(poll_interval)
                        elapsed += poll_interval

                        if _is_app_window_topmost(app_name_current):
                            time.sleep(0.2)  # Buffer
                            return WindowFocusResult(
                                success=True, focused_app=app_name_current
                            )

                    # Return failure if verification failed
                    bounds_result = _get_active_window_bounds_impl()
                    actual_topmost = (
                        bounds_result.app_name if bounds_result.success else "unknown"
                    )
                    return WindowFocusResult(
                        success=False,
                        error=f"Failed to re-focus {app_name_current}: {actual_topmost} is frontmost instead",
                    )

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
