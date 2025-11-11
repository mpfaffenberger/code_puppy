"""Window management for desktop automation automation."""

from __future__ import annotations

import subprocess


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
            from ..config_manager import get_debug_screenshots_enabled

            # Always log when debug mode is on, or when there are multiple windows
            if get_debug_screenshots_enabled() or len(candidate_windows) > 1:
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

            # NOTE: macOS CGWindowListCopyWindowInfo returns coordinates in POINTS
            # (logical coordinates), not physical pixels. On Retina displays, points
            # are equivalent to logical pixels. To convert to physical pixels for
            # screenshot APIs, multiply by backingScaleFactor.
            # See: https://developer.apple.com/documentation/coregraphics/kcgwindowbounds
            logical_x = int(bounds["X"])
            logical_y = int(bounds["Y"])
            logical_width = int(bounds["Width"])
            logical_height = int(bounds["Height"])

            # Debug: show final bounds
            if get_debug_screenshots_enabled():
                from ..platform import get_screen_scale_factor

                scale_factor = get_screen_scale_factor()
                emit_info(
                    f"[yellow]🐛 DEBUG: Window bounds (in points/logical):[/yellow]\n"
                    f"[yellow]   Points: ({int(bounds['X'])}, {int(bounds['Y'])}) {int(bounds['Width'])}x{int(bounds['Height'])}[/yellow]\n"
                    f"[yellow]   Physical would be: ({int(bounds['X'] * scale_factor)}, {int(bounds['Y'] * scale_factor)}) {int(bounds['Width'] * scale_factor)}x{int(bounds['Height'] * scale_factor)}[/yellow]\n"
                    f"[yellow]   Scale: {scale_factor}x[/yellow]"
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
