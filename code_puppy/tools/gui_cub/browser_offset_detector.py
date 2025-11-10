"""Browser and canvas offset detection for accurate web automation.

This module detects when OCR is being performed on browser windows and
calculates the necessary coordinate offsets to account for:
1. Browser chrome (title bar, address bar, tabs, bookmarks bar)
2. Canvas/iframe elements within web pages
3. Window title bar on different platforms

These offsets are critical for accurate clicking in web automation scenarios.
"""

from __future__ import annotations

import re
from typing import Tuple

from .core.browser_offsets import (
    get_title_bar_height,
    apply_chrome_offset,
)

try:
    from AppKit import NSWorkspace
    from Quartz import (
        CGWindowListCopyWindowInfo,
        kCGWindowListOptionOnScreenOnly,
        kCGNullWindowID,
    )

    MACOS_AVAILABLE = True
except ImportError:
    MACOS_AVAILABLE = False
    NSWorkspace = None
    CGWindowListCopyWindowInfo = None
    kCGWindowListOptionOnScreenOnly = None
    kCGNullWindowID = None

try:
    import win32gui
    import win32con

    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    win32gui = None
    win32con = None

from .platform import IS_MACOS, IS_WINDOWS


# Known browser chrome heights (approximate, in pixels)
# These are estimates for typical browser configurations
BROWSER_CHROME_HEIGHTS = {
    "chrome": {
        "macos": 85,  # Title bar (22) + Tab bar (38) + Address bar (40) - 15 overlap
        "windows": 95,  # Similar but slightly taller
    },
    "firefox": {
        "macos": 80,
        "windows": 90,
    },
    "safari": {
        "macos": 82,  # Title bar + unified tab/address bar
        "windows": 0,  # Not applicable on Windows
    },
    "edge": {
        "macos": 85,
        "windows": 95,
    },
    "brave": {
        "macos": 85,
        "windows": 95,
    },
    "arc": {
        "macos": 40,  # Arc has minimal chrome with sidebar instead
        "windows": 0,
    },
}

# Browser detection patterns (case-insensitive)
BROWSER_PATTERNS = {
    "chrome": [r"google chrome", r"chrome"],
    "firefox": [r"firefox", r"mozilla"],
    "safari": [r"safari"],
    "edge": [r"microsoft edge", r"edge"],
    "brave": [r"brave"],
    "arc": [r"arc"],
}

# Title bar heights imported from logic module (see imports above)


class BrowserOffsetInfo:
    """Information about detected browser and required coordinate offsets."""

    def __init__(
        self,
        is_browser: bool = False,
        browser_name: str | None = None,
        chrome_height: int = 0,
        window_title: str | None = None,
        confidence: float = 0.0,
    ):
        self.is_browser = is_browser
        self.browser_name = browser_name
        self.chrome_height = chrome_height
        self.window_title = window_title
        self.confidence = confidence

    def __repr__(self) -> str:
        if self.is_browser:
            return (
                f"BrowserOffsetInfo(browser={self.browser_name}, "
                f"chrome_height={self.chrome_height}px, confidence={self.confidence:.2f})"
            )
        return "BrowserOffsetInfo(is_browser=False)"


def detect_browser_from_window_title(window_title: str) -> Tuple[str | None, float]:
    """
    Detect browser type from window title.

    Args:
        window_title: The window title string

    Returns:
        Tuple of (browser_name, confidence) where confidence is 0.0-1.0

    Examples:
        >>> detect_browser_from_window_title("Application Window")
        ('chrome', 0.95)
        >>> detect_browser_from_window_title("My Document - Application")
        ('firefox', 0.90)
    """
    if not window_title:
        return None, 0.0

    window_title_lower = window_title.lower()

    # Check each browser pattern
    for browser, patterns in BROWSER_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, window_title_lower):
                # High confidence for exact browser name match
                confidence = 0.95 if browser.lower() in window_title_lower else 0.85
                return browser, confidence

    return None, 0.0


def get_active_window_info_macos() -> Tuple[str | None, str | None]:
    """
    Get active window information on macOS.

    Returns:
        Tuple of (app_name, window_title)
    """
    if not MACOS_AVAILABLE:
        return None, None

    try:
        workspace = NSWorkspace.sharedWorkspace()
        app = workspace.frontmostApplication()
        app_name = app.localizedName()
        pid = app.processIdentifier()

        # Get window title from window list
        window_list = CGWindowListCopyWindowInfo(
            kCGWindowListOptionOnScreenOnly, kCGNullWindowID
        )

        for window in window_list:
            if window.get("kCGWindowOwnerPID") == pid:
                window_title = window.get("kCGWindowName", "")
                if window_title:  # Return first non-empty window title
                    return app_name, window_title

        return app_name, None

    except Exception:
        return None, None


def get_active_window_info_windows() -> Tuple[str | None, str | None]:
    """
    Get active window information on Windows.

    Returns:
        Tuple of (app_name, window_title)
    """
    if not WINDOWS_AVAILABLE:
        return None, None

    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None, None

        window_title = win32gui.GetWindowText(hwnd)

        # Get process name
        import psutil
        import win32process

        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        try:
            process = psutil.Process(pid)
            app_name = process.name()
        except Exception:
            app_name = None

        return app_name, window_title

    except Exception:
        return None, None


def detect_browser_offset() -> BrowserOffsetInfo:
    """
    Detect if the active window is a browser and calculate chrome offset.

    This function:
    1. Gets the active window information
    2. Detects if it's a browser window
    3. Calculates the browser chrome height offset

    Returns:
        BrowserOffsetInfo with detected browser and offset information

    Examples:
        >>> info = detect_browser_offset()
        >>> if info.is_browser:
        ...     print(f"Browser: {info.browser_name}, Offset: {info.chrome_height}px")
    """
    # Get active window info based on platform
    if IS_MACOS:
        app_name, window_title = get_active_window_info_macos()
    elif IS_WINDOWS:
        app_name, window_title = get_active_window_info_windows()
    else:
        return BrowserOffsetInfo()

    if not app_name and not window_title:
        return BrowserOffsetInfo()

    # First try: detect from window title
    browser_name, confidence = detect_browser_from_window_title(window_title or "")

    # Second try: detect from app name
    if not browser_name and app_name:
        browser_name, app_confidence = detect_browser_from_window_title(app_name)
        confidence = app_confidence * 0.8  # Lower confidence from app name alone

    if not browser_name:
        return BrowserOffsetInfo(
            window_title=window_title,
            confidence=0.0,
        )

    # Get platform-specific chrome height
    platform_key = "macos" if IS_MACOS else "windows"
    chrome_height = BROWSER_CHROME_HEIGHTS.get(browser_name, {}).get(platform_key, 80)

    return BrowserOffsetInfo(
        is_browser=True,
        browser_name=browser_name,
        chrome_height=chrome_height,
        window_title=window_title,
        confidence=confidence,
    )


def calculate_window_chrome_offset() -> int:
    """
    Calculate the window chrome offset for the active window.

    Uses extracted pure logic for platform-specific title bar heights.

    Returns:
        Window chrome offset in pixels
    """
    platform_key = "macos" if IS_MACOS else "windows"
    return get_title_bar_height(platform_key)


def apply_browser_offset_to_coordinates(
    x: int,
    y: int,
    browser_info: BrowserOffsetInfo | None = None,
) -> Tuple[int, int]:
    """
    Apply browser chrome offset to screen coordinates.

    This adjusts OCR-detected coordinates to account for browser chrome.
    The coordinates from OCR are relative to the screenshot (which includes
    the browser chrome), but we need to convert them to screen coordinates.

    Args:
        x: X coordinate from OCR
        y: Y coordinate from OCR
        browser_info: Optional BrowserOffsetInfo (will detect if None)

    Returns:
        Tuple of (adjusted_x, adjusted_y)

    Examples:
        >>> # Element found at (100, 50) in screenshot
        >>> # Browser has 85px chrome
        >>> apply_browser_offset_to_coordinates(100, 50)
        (100, 135)  # Y adjusted by +85px
    """
    if browser_info is None:
        browser_info = detect_browser_offset()

    # Use extracted pure logic to apply chrome offset
    is_browser = browser_info.is_browser
    confidence = browser_info.confidence if is_browser else 0.0
    chrome_height = browser_info.chrome_height if is_browser else 0

    return apply_chrome_offset(x, y, chrome_height, confidence)


def get_browser_offset_summary() -> str:
    """
    Get a human-readable summary of browser offset detection.

    Returns:
        String description of detected browser and offset
    """
    info = detect_browser_offset()

    if info.is_browser:
        return (
            f"Browser detected: {info.browser_name} "
            f"(chrome offset: {info.chrome_height}px, confidence: {info.confidence:.0%})"
        )
    else:
        return "No browser detected (using default window offsets)"
