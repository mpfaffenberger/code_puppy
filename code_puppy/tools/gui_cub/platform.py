"""Platform detection and helpers for cross-platform desktop automation tools."""

from __future__ import annotations

import sys
from enum import Enum
from typing import Callable


class Platform(Enum):
    """Supported platforms for desktop automation automation."""

    MACOS = "darwin"
    WINDOWS = "win32"
    LINUX = "linux"


# Platform detection constants
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform == "linux"
CURRENT_PLATFORM = sys.platform


def get_platform() -> Platform | None:
    """Get current platform as enum.

    Returns:
        Platform enum or None if unsupported
    """
    for platform in Platform:
        if sys.platform == platform.value:
            return platform
    return None


def require_platform(*platforms: Platform) -> Callable:
    """Decorator to require specific platform(s).

    Args:
        platforms: One or more Platform enums required

    Returns:
        Decorator that validates platform before execution

    Example:
        @require_platform(Platform.MACOS)
        def macos_only_function():
            pass
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            current = get_platform()
            if current not in platforms:
                platform_names = ", ".join(p.name for p in platforms)
                return {
                    "success": False,
                    "error": f"This tool requires {platform_names}, but you're on {current.name if current else 'unknown platform'}",
                }
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def get_platform_display_name() -> str:
    """Get human-readable platform name.

    Returns:
        Platform display name (e.g., 'macOS', 'Windows', 'Linux')
    """
    if IS_MACOS:
        return "macOS"
    elif IS_WINDOWS:
        return "Windows"
    elif IS_LINUX:
        return "Linux"
    else:
        return "Unknown"


def get_screen_scale_factor() -> float:
    """Detect HiDPI/Retina screen scaling factor reliably.

    We compare full-screen screenshot pixel size to the logical screen size.
    This is more robust than tiny-region tricks and avoids oddities.

    Returns:
        Scale factor (commonly 1.0 or 2.0). Falls back to 1.0 on failure.
    """
    try:
        import pyautogui

        # Logical size from OS APIs
        logical_width, logical_height = pyautogui.size()

        # Physical size from full screenshot
        shot = pyautogui.screenshot()
        physical_width, physical_height = shot.size

        # Compute scale by width ratio (height should match)
        if logical_width == 0 or logical_height == 0:
            return 1.0
        scale_x = physical_width / logical_width
        scale_y = physical_height / logical_height

        # If mismatch beyond small epsilon, choose width ratio as authoritative
        if abs(scale_x - scale_y) > 0.1:
            scale = scale_x
        else:
            scale = (scale_x + scale_y) / 2

        # Round to nearest 0.25 to handle non-integer scales, but clamp reasonable bounds
        scale_rounded = max(1.0, min(4.0, round(scale * 4) / 4))
        return scale_rounded
    except Exception:
        return 1.0


def convert_screenshot_to_screen_coords(screenshot_x: int, screenshot_y: int, scale_factor: float | None = None) -> tuple[int, int]:
    """Convert screenshot (physical) coordinates to screen (logical) coordinates.

    On HiDPI/Retina displays, screenshots are captured at higher resolution
    than the logical screen size. This function converts coordinates from
    the screenshot space to the screen space that the mouse uses.

    Args:
        screenshot_x: X coordinate from screenshot (physical pixels)
        screenshot_y: Y coordinate from screenshot (physical pixels)
        scale_factor: Optional pre-calculated scale factor
                     If None, will auto-detect using get_screen_scale_factor()

    Returns:
        Tuple of (screen_x, screen_y) in logical screen coordinates

    Example:
        >>> # On 2x Retina display
        >>> # OCR found text at (940, 250) in screenshot
        >>> screen_x, screen_y = convert_screenshot_to_screen_coords(940, 250)
        >>> print(screen_x, screen_y)  # (470, 125)
        >>> # Now you can click at (470, 125) with the mouse
    """
    if scale_factor is None:
        scale_factor = get_screen_scale_factor()

    screen_x = int(screenshot_x / scale_factor)
    screen_y = int(screenshot_y / scale_factor)

    return screen_x, screen_y


def check_macos_accessibility_permission() -> tuple[bool, str | None]:
    """Check if macOS Accessibility permissions are granted.

    On macOS, mouse/keyboard automation requires Accessibility permissions.
    Without these permissions, pyautogui operations may silently fail or
    throw errors.

    Returns:
        Tuple of (has_permission, error_message_if_not)

    Note:
        This function attempts to verify permissions by trying a benign
        operation. It's not 100% reliable but catches most cases.
    """
    if not IS_MACOS:
        return True, None  # Not applicable on other platforms

    try:
        import pyautogui

        # Try to get current mouse position - requires Accessibility permission
        # If this succeeds, we likely have permission
        current_x, current_y = pyautogui.position()

        # Try a tiny mouse movement (1px) and verify it worked
        # This is a more robust check than just getting position
        original_pos = pyautogui.position()
        test_x = min(current_x + 1, pyautogui.size()[0] - 1)
        test_y = current_y

        pyautogui.moveTo(test_x, test_y, duration=0)
        new_pos = pyautogui.position()

        # Move back to original position
        pyautogui.moveTo(original_pos[0], original_pos[1], duration=0)

        # If the position actually changed, we have permission
        if new_pos[0] != original_pos[0] or abs(new_pos[0] - test_x) <= 1:
            return True, None
        else:
            # Mouse didn't move - likely permission issue
            error_msg = (
                "macOS Accessibility permission required! "
                "Go to System Preferences → Security & Privacy → Privacy → Accessibility, "
                "and grant permission to Terminal (or your Python IDE/app)."
            )
            return False, error_msg

    except Exception as e:
        # If we get an exception, assume it's a permission issue
        error_msg = (
            f"macOS Accessibility permission check failed: {e}. "
            "Please grant Accessibility permission to Terminal/Python in System Preferences."
        )
        return False, error_msg


def get_display_info() -> dict[str, any]:
    """Get comprehensive display information for debugging.

    Returns:
        Dictionary with display metrics including logical size,
        physical size (if available), and scale factor.

    Example:
        >>> info = get_display_info()
        >>> print(f"Platform: {info['platform']}")
        >>> print(f"Logical resolution: {info['logical_width']}x{info['logical_height']}")
        >>> print(f"Scale factor: {info['scale_factor']}x")
    """
    info = {
        "platform": get_platform_display_name(),
    }

    try:
        import pyautogui

        # Get logical screen size
        logical_width, logical_height = pyautogui.size()
        info["logical_width"] = logical_width
        info["logical_height"] = logical_height

        # Get scale factor
        scale_factor = get_screen_scale_factor()
        info["scale_factor"] = scale_factor

        # Calculate physical size
        info["physical_width"] = int(logical_width * scale_factor)
        info["physical_height"] = int(logical_height * scale_factor)

        # Display type
        if scale_factor >= 2.0:
            info["display_type"] = "HiDPI/Retina"
        elif scale_factor > 1.0:
            info["display_type"] = "Scaled"
        else:
            info["display_type"] = "Standard"

    except Exception as e:
        info["error"] = str(e)

    # Check macOS accessibility permissions if on macOS
    if IS_MACOS:
        has_permission, permission_error = check_macos_accessibility_permission()
        info["macos_accessibility_permission"] = has_permission
        if not has_permission:
            info["permission_error"] = permission_error

    return info
