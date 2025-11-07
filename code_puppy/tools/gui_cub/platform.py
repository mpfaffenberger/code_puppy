"""Platform detection and helpers for cross-platform desktop automation tools."""

from __future__ import annotations

import sys
from enum import Enum
from typing import Callable


class Platform(Enum):
    """Supported platforms for desktop automation (Windows/macOS only)."""

    MACOS = "darwin"
    WINDOWS = "win32"


# Platform detection constants (Windows/macOS only)
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"
CURRENT_PLATFORM = sys.platform

# Windows DPI awareness initialization
if IS_WINDOWS:
    import ctypes

    # Set DPI awareness at module import time (before any GUI operations)
    # This ensures GetWindowRect and pyautogui.screenshot() use the same coordinate system.
    try:
        user32 = ctypes.windll.user32
        shcore = ctypes.windll.shcore

        # Try Per-Monitor-V2 (Windows 10 1703+)
        # This makes GetWindowRect return physical pixels
        try:
            # -4 == DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            _WINDOWS_DPI_MODE = "Per-Monitor-V2"
        except Exception:
            try:
                # 2 == PROCESS_PER_MONITOR_DPI_AWARE
                shcore.SetProcessDpiAwareness(2)
                _WINDOWS_DPI_MODE = "Per-Monitor"
            except Exception:
                try:
                    # Legacy fallback: system DPI aware
                    user32.SetProcessDPIAware()
                    _WINDOWS_DPI_MODE = "System-Aware"
                except Exception:
                    _WINDOWS_DPI_MODE = "Unaware"
    except Exception:
        _WINDOWS_DPI_MODE = "Failed"
else:
    _WINDOWS_DPI_MODE = None


def get_platform() -> Platform | None:
    """Get current platform as enum.

    Returns:
        Platform enum or None if unsupported
    """
    for platform in Platform:
        if sys.platform == platform.value:
            return platform
    return None


def get_windows_dpi_mode() -> str | None:
    """Get Windows DPI awareness mode.

    Returns:
        DPI mode string or None if not Windows:
        - "Per-Monitor-V2": Best mode, GetWindowRect returns physical pixels
        - "Per-Monitor": Good mode, per-monitor aware
        - "System-Aware": Legacy mode, may have issues on multi-monitor
        - "Unaware": DPI virtualization active, coordinate mismatches likely
        - "Failed": Could not set DPI awareness
    """
    return _WINDOWS_DPI_MODE if IS_WINDOWS else None


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
        Platform display name (e.g., 'macOS', 'Windows')
    """
    if IS_MACOS:
        return "macOS"
    elif IS_WINDOWS:
        return "Windows"
    else:
        return "Unsupported"


# Cache for scale factor (avoids repeated screenshot calculations)
_cached_scale_factor: float | None = None


def get_screen_scale_factor(use_cache: bool = True) -> float:
    """Detect HiDPI/Retina screen scaling factor reliably.

    Checks cached config first (fast), falls back to screenshot comparison (slow).

    Priority:
    1. Check in-memory cache (from current session)
    2. Check config file (from calibration)
    3. Calculate manually via screenshot (slow, ~100-200ms)

    Args:
        use_cache: Whether to use cached value (default: True)
                  Set to False to force recalculation

    Returns:
        Scale factor (commonly 1.0 or 2.0). Falls back to 1.0 on failure.
    """
    global _cached_scale_factor

    # Return in-memory cache if available
    if use_cache and _cached_scale_factor is not None:
        return _cached_scale_factor

    # Try to load from config file
    if use_cache:
        try:
            from code_puppy.tools.gui_cub.config_manager import load_config

            config = load_config()
            if config:
                scale = config.get("display", {}).get("scale_factor")
                if scale is not None and isinstance(scale, (int, float)) and scale > 0:
                    _cached_scale_factor = float(scale)
                    return _cached_scale_factor
        except Exception:
            # Config not available, fall through to manual calculation
            pass

    # Fall back to manual calculation via screenshot
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

        # Cache the calculated value
        _cached_scale_factor = scale_rounded
        return scale_rounded
    except Exception:
        return 1.0


def convert_screenshot_to_screen_coords(
    screenshot_x: int, screenshot_y: int, scale_factor: float | None = None
) -> tuple[int, int]:
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


def get_screen_resolution(use_cache: bool = True) -> tuple[int, int]:
    """Get current screen resolution (logical points).

    Checks config first (fast), falls back to pyautogui (slow).

    Args:
        use_cache: Whether to use cached config value (default: True)
                  Set to False to force live query

    Returns:
        Tuple of (width, height) in logical points
    """
    # Try to load from config file
    if use_cache:
        try:
            from code_puppy.tools.gui_cub.config_manager import load_config

            config = load_config()
            if config:
                resolution = config.get("display", {}).get("primary_resolution")
                if resolution and isinstance(resolution, list) and len(resolution) == 2:
                    return (int(resolution[0]), int(resolution[1]))
        except Exception:
            # Config not available, fall through to live query
            pass

    # Fall back to live query
    try:
        import pyautogui

        return pyautogui.size()
    except Exception:
        # Ultimate fallback
        return (1920, 1080)


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
