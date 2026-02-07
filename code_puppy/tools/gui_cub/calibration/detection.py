"""Platform calibration for GUI-Cub - detects and caches all automation-relevant info.

Runs on first use (like QA-Kitten downloading Camoufox) to detect:
- Platform (OS, version, architecture)
- Displays (all monitors, resolutions, DPI, scaling)
- Libraries (atomacos, pywinauto)
- Performance (screenshot, mouse, keyboard latencies)
- Permissions (accessibility, screen recording on macOS)
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Any

from ..dependencies import PYAUTOGUI_AVAILABLE
from ..rich_emit import emit_rich

try:
    from code_puppy import __version__ as code_puppy_version
except ImportError:
    code_puppy_version = "unknown"

if PYAUTOGUI_AVAILABLE:
    import pyautogui
else:
    pyautogui = None

if sys.platform == "win32":
    import winreg
    import ctypes

    # Windows constants for SendMessageTimeoutW
    HWND_BROADCAST = 0xFFFF
    WM_SETTINGCHANGE = 0x001A
    SMTO_ABORTIFHUNG = 0x0002


def download_with_walmart_fallback(
    url: str,
    destination_path: "os.PathLike[str]",
    group_id: str | None = None,
    chunk_size: int = 8192,
) -> bool:
    """Download a file with Walmart-friendly settings (proxy + cert bundle).

    Uses Walmart proxy and cert bundle by default, which works both inside
    and outside the corporate network. Falls back to direct download if needed.

    Args:
        url: URL to download from
        destination_path: Where to save the downloaded file
        group_id: Optional message group ID for emit_info calls
        chunk_size: Download chunk size in bytes

    Returns:
        True if download succeeded, False otherwise
    """
    import os
    from pathlib import Path

    import requests

    dest = Path(destination_path)

    # First try: Walmart settings (proxy + cert bundle)
    try:
        # Get Walmart cert bundle path if available
        cert_bundle = os.environ.get("_SSL_CERT_FILE")
        if cert_bundle and not os.path.exists(cert_bundle):
            cert_bundle = None

        # Create session with Walmart settings
        session = requests.Session()
        if cert_bundle:
            session.verify = cert_bundle

        # Add Walmart proxy settings
        session.proxies.update(
            {
                "http": "http://sysproxy.wal-mart.com:8080",
                "https": "http://sysproxy.wal-mart.com:8080",
            }
        )

        response = session.get(url, stream=True, timeout=60.0)
        response.raise_for_status()

        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

        return True

    except Exception as e:
        emit_rich(
            f"  • Download with Walmart settings failed: {e}",
            message_group=group_id,
        )
        emit_rich(
            "  • Retrying without proxy/cert...",
            message_group=group_id,
        )

    # Second try: direct download without Walmart settings
    try:
        session = requests.Session()
        session.verify = True  # Use default system certs

        response = session.get(url, stream=True, timeout=60.0)
        response.raise_for_status()

        with open(dest, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)

        emit_rich(
            "  • Download succeeded without proxy",
            message_group=group_id,
        )
        return True

    except Exception as e:
        emit_rich(
            f"  • Direct download also failed: {e}",
            message_group=group_id,
        )
        return False


def _update_system_path_registry(path_to_add: str) -> tuple[bool, str]:
    """Update system PATH via Windows registry (no 1024 char limit).

    Args:
        path_to_add: Path to add to system PATH

    Returns:
        Tuple of (success: bool, message: str)
    """
    if sys.platform != "win32":
        return False, "Not Windows"

    try:
        # Open registry key for system environment variables
        key_path = r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE
        ) as key:
            # Read current PATH
            try:
                current_path, reg_type = winreg.QueryValueEx(key, "Path")
            except FileNotFoundError:
                current_path = ""
                reg_type = winreg.REG_EXPAND_SZ

            # Check if already in PATH (case-insensitive)
            path_entries = [p.strip() for p in current_path.split(";") if p.strip()]
            path_to_add_lower = path_to_add.lower()

            if any(entry.lower() == path_to_add_lower for entry in path_entries):
                return True, "Already in system PATH"

            # Add to PATH
            if current_path and not current_path.endswith(";"):
                new_path = f"{current_path};{path_to_add}"
            else:
                new_path = f"{current_path}{path_to_add}"

            # Write back to registry
            winreg.SetValueEx(key, "Path", 0, reg_type, new_path)

            # Broadcast WM_SETTINGCHANGE to notify system of environment change
            try:
                result = ctypes.c_long()

                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST,
                    WM_SETTINGCHANGE,
                    0,
                    "Environment",
                    SMTO_ABORTIFHUNG,
                    5000,
                    ctypes.byref(result),
                )
            except Exception:
                pass  # Broadcast is optional, PATH update still worked

            return True, f"Added to system PATH (new length: {len(new_path)} chars)"

    except PermissionError:
        return False, "Access denied (requires administrator privileges)"
    except Exception as e:
        return False, f"Registry error: {type(e).__name__}: {str(e)[:100]}"


def detect_platform() -> dict[str, Any]:
    """Detect OS platform information (Windows/macOS only)."""
    os_name = sys.platform
    os_display = {
        "darwin": "macOS",
        "win32": "Windows",
    }.get(os_name, "Unsupported")

    return {
        "os": os_name,
        "os_display": os_display,
        "version": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor() or "unknown",
    }


def detect_displays() -> dict[str, Any]:
    """Detect all displays, resolutions, and scaling."""
    # Get primary display
    try:
        from code_puppy.tools.gui_cub.platform import get_screen_scale_factor

        scale_factor = get_screen_scale_factor()
    except Exception:
        scale_factor = 1.0

    primary_width, primary_height = pyautogui.size()

    # Try to get all monitors
    monitors = []
    try:
        # pyautogui doesn't have built-in multi-monitor support
        # We'll use the platform-specific code if available
        if sys.platform == "darwin":
            monitors = _detect_macos_monitors()
        elif sys.platform == "win32":
            monitors = _detect_windows_monitors()
        else:
            # Unsupported platform - use primary display fallback
            monitors = []
    except Exception:
        # Fallback to primary display only
        monitors = [
            {
                "id": 0,
                "resolution": [primary_width, primary_height],
                "scale": scale_factor,
                "primary": True,
                "bounds": {
                    "x": 0,
                    "y": 0,
                    "width": primary_width,
                    "height": primary_height,
                },
            }
        ]

    return {
        "primary_resolution": [primary_width, primary_height],
        "scale_factor": scale_factor,
        "dpi": int(96 * scale_factor),  # Approximate DPI
        "monitors": monitors,
        "monitor_count": len(monitors),
    }


def _detect_macos_monitors() -> list[dict[str, Any]]:
    """Detect monitors on macOS using NSScreen."""
    try:
        from AppKit import NSScreen

        monitors = []
        screens = NSScreen.screens()

        for i, screen in enumerate(screens):
            frame = screen.frame()
            scale = screen.backingScaleFactor()

            monitors.append(
                {
                    "id": i,
                    "resolution": [int(frame.size.width), int(frame.size.height)],
                    "scale": float(scale),
                    "primary": i == 0,
                    "bounds": {
                        "x": int(frame.origin.x),
                        "y": int(frame.origin.y),
                        "width": int(frame.size.width),
                        "height": int(frame.size.height),
                    },
                }
            )

        return monitors
    except ImportError:
        # NSScreen not available, fall back to pyautogui
        width, height = pyautogui.size()
        return [
            {
                "id": 0,
                "resolution": [width, height],
                "scale": 1.0,
                "primary": True,
                "bounds": {"x": 0, "y": 0, "width": width, "height": height},
            }
        ]


def _detect_windows_monitors() -> list[dict[str, Any]]:
    """Detect monitors on Windows."""
    try:
        import win32api

        monitors = []
        for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
            info = win32api.GetMonitorInfo(monitor[0])
            rect = info["Monitor"]

            width = rect[2] - rect[0]
            height = rect[3] - rect[1]

            monitors.append(
                {
                    "id": i,
                    "resolution": [width, height],
                    "scale": 1.0,  # DPI detection not implemented for Windows
                    "primary": info.get("Flags", 0) == 1,
                    "bounds": {
                        "x": rect[0],
                        "y": rect[1],
                        "width": width,
                        "height": height,
                    },
                }
            )

        return monitors
    except ImportError:
        # win32api not available
        width, height = pyautogui.size()
        return [
            {
                "id": 0,
                "resolution": [width, height],
                "scale": 1.0,
                "primary": True,
                "bounds": {"x": 0, "y": 0, "width": width, "height": height},
            }
        ]
