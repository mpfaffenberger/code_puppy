"""Platform calibration for GUI-Cub - detects and caches all automation-relevant info.

Runs on first use (like QA-Kitten downloading Camoufox) to detect:
- Platform (OS, version, architecture)
- Displays (all monitors, resolutions, DPI, scaling)
- Libraries (atomacos, pywinauto, opencv)
- Performance (screenshot, mouse, keyboard latencies)
- Permissions (accessibility, screen recording on macOS)
"""

import os
import platform
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List

import pyautogui

if sys.platform == "win32":
    import winreg
    import ctypes

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

try:
    from code_puppy import __version__ as code_puppy_version
except ImportError:
    code_puppy_version = "unknown"


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
        emit_info(
            f"  • Download with Walmart settings failed: {e}",
            message_group=group_id,
        )
        emit_info(
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

        emit_info(
            "  • Download succeeded without proxy",
            message_group=group_id,
        )
        return True

    except Exception as e:
        emit_info(
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
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
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


def detect_platform() -> Dict[str, Any]:
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


def detect_displays() -> Dict[str, Any]:
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


def _detect_macos_monitors() -> List[Dict[str, Any]]:
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


def _detect_windows_monitors() -> List[Dict[str, Any]]:
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
                    "scale": 1.0,  # TODO: Get actual DPI
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


def _attempt_install_windows_dependencies() -> bool:
    """Attempt to install Windows-specific dependencies (pywinauto, pywin32).

    Returns:
        True if installation succeeded, False otherwise
    """

    from code_puppy.messaging import emit_info, emit_warning
    from code_puppy.tools.common import generate_group_id

    group_id = generate_group_id("windows_deps")

    emit_info(
        "[cyan]📦 Installing Windows automation dependencies...[/cyan]",
        message_group=group_id,
    )

    packages = ["pywinauto>=0.6.8", "pywin32>=306"]

    try:
        # Try to install using pip
        emit_info(
            "  • Installing pywinauto and pywin32...",
            message_group=group_id,
        )

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        if result.returncode == 0:
            emit_info(
                "[green]✅ Windows dependencies installed successfully[/green]",
                message_group=group_id,
            )

            # Run pywin32 post-install script if needed
            try:
                emit_info(
                    "  • Running pywin32 post-install...",
                    message_group=group_id,
                )
                subprocess.run(
                    [sys.executable, "-m", "pywin32_postinstall", "-install"],
                    capture_output=True,
                    timeout=30,
                )
            except Exception:
                # Post-install script is optional
                pass

            return True
        else:
            emit_warning(
                f"[yellow]⚠️ Installation failed: {result.stderr[:200]}[/yellow]",
                message_group=group_id,
            )
            return False

    except subprocess.TimeoutExpired:
        emit_warning(
            "[yellow]⚠️ Installation timed out[/yellow]",
            message_group=group_id,
        )
        return False
    except Exception as e:
        emit_warning(
            f"[yellow]⚠️ Installation error: {str(e)[:200]}[/yellow]",
            message_group=group_id,
        )
        return False


def _is_admin() -> bool:
    """Check if running with administrator privileges on Windows."""
    if sys.platform != "win32":
        return True  # Not Windows, don't care

    try:
        import ctypes

        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False  # Assume not admin if check fails


def detect_capabilities() -> Dict[str, bool]:
    """Detect which libraries are available."""
    capabilities = {}

    # Test pyautogui
    try:
        import pyautogui  # noqa: F401 - testing availability

        capabilities["pyautogui"] = True
    except ImportError:
        capabilities["pyautogui"] = False

    # Test atomacos (macOS)
    try:
        import atomacos  # noqa: F401 - testing availability

        capabilities["atomacos"] = True
    except ImportError:
        capabilities["atomacos"] = False

    # Test pywinauto (Windows)
    if sys.platform == "win32":
        try:
            import pywinauto  # noqa: F401 - testing availability

            capabilities["pywinauto"] = True
        except ImportError:
            capabilities["pywinauto"] = False
            # Attempt to install Windows dependencies if missing
            if _attempt_install_windows_dependencies():
                # Try again after install
                try:
                    import pywinauto  # noqa: F401 - testing availability

                    capabilities["pywinauto"] = True
                except ImportError:
                    capabilities["pywinauto"] = False

    # OCR is now handled by native platform APIs (WinRT on Windows, Vision on macOS)
    # No external dependencies required

    # Test opencv
    try:
        import cv2  # noqa: F401 - testing availability

        capabilities["opencv"] = True
    except ImportError:
        capabilities["opencv"] = False

    return capabilities


def detect_permissions() -> Dict[str, Any]:
    """Detect accessibility permissions (macOS only)."""
    permissions = {}

    if sys.platform == "darwin":
        try:
            from code_puppy.tools.gui_cub.platform import (
                check_macos_accessibility_permission,
            )

            has_access, message = check_macos_accessibility_permission()
            permissions["accessibility"] = has_access
            permissions["accessibility_message"] = message
        except Exception as e:
            permissions["accessibility"] = False
            permissions["accessibility_message"] = f"Error checking permissions: {e}"

    return permissions


def calibrate_platform(force: bool = False) -> Dict[str, Any]:
    """Run full platform calibration and save results.

    Args:
        force: If True, re-calibrate even if config exists

    Returns:
        Dictionary with calibration results
    """
    from code_puppy.tools.gui_cub.config_manager import (
        get_config_path,
        load_config,
        save_config,
    )

    group_id = generate_group_id("calibration")

    # Check if already calibrated (unless forcing)
    if not force:
        existing_config = load_config()
        if existing_config:
            emit_info(
                "[dim]Platform already calibrated (use /calibrate to re-run)[/dim]",
                message_group=group_id,
            )
            return {
                "success": True,
                "config": existing_config,
                "calibrated": False,  # Didn't run calibration
                "path": str(get_config_path()),
            }

    emit_info(
        "[bold cyan]🔧 GUI-Cub Platform Calibration[/bold cyan]",
        message_group=group_id,
    )
    emit_info(
        "[dim]Detecting platform capabilities, displays, and performance...[/dim]",
        message_group=group_id,
    )
    emit_info("", message_group=group_id)

    # Detect everything
    emit_info("🔍 Detecting platform...", message_group=group_id)
    platform_info = detect_platform()
    emit_info(
        f"  • OS: {platform_info['os_display']} {platform_info['version']}",
        message_group=group_id,
    )
    emit_info(
        f"  • Arch: {platform_info['machine']}",
        message_group=group_id,
    )
    emit_info("", message_group=group_id)

    emit_info("🖥️  Detecting displays...", message_group=group_id)
    display_info = detect_displays()
    emit_info(
        f"  • Primary: {display_info['primary_resolution'][0]}x{display_info['primary_resolution'][1]}",
        message_group=group_id,
    )
    emit_info(
        f"  • Scale: {display_info['scale_factor']}x",
        message_group=group_id,
    )
    emit_info(
        f"  • Monitors: {display_info['monitor_count']}",
        message_group=group_id,
    )
    emit_info("", message_group=group_id)

    emit_info("📦 Detecting capabilities...", message_group=group_id)
    capabilities = detect_capabilities()

    for cap, available in capabilities.items():
        status = "✅" if available else "❌"
        emit_info(
            f"  {status} {cap}",
            message_group=group_id,
        )
    emit_info("", message_group=group_id)

    # Check permissions (macOS only)
    permissions = detect_permissions()
    if permissions:
        emit_info("🔐 Checking permissions...", message_group=group_id)
        for perm, status in permissions.items():
            if perm.endswith("_message"):
                continue
            status_str = "✅" if status else "❌"
            message = permissions.get(f"{perm}_message", "")
            emit_info(
                f"  {status_str} {perm}: {message}",
                message_group=group_id,
            )
        emit_info("", message_group=group_id)

    # Track any missing capabilities
    missing_capabilities = {}

    # Check opencv
    if not capabilities.get("opencv", False):
        missing_capabilities["opencv"] = {
            "message": "OpenCV (cv2) not installed",
            "affects": ["image_similarity", "template_matching"],
            "solution": "pip install opencv-python",
        }

    # Build config
    config = {
        "version": "1.0",
        "code_puppy_version": code_puppy_version,
        "calibrated_at": datetime.now().isoformat(),
        "platform": platform_info,
        "displays": display_info,
        "capabilities": capabilities,
        "permissions": permissions,
        "missing_capabilities": missing_capabilities,
    }

    # Save config
    from code_puppy.tools.gui_cub.config_manager import get_config_path

    if save_config(config):
        emit_info(
            "[green]✅ Platform calibrated successfully[/green]",
            message_group=group_id,
        )
        emit_info(
            f"[dim]   Config saved to: {get_config_path()}[/dim]",
            message_group=group_id,
        )
    else:
        emit_info(
            "[yellow]⚠️ Warning: Failed to save config (will re-calibrate next time)[/yellow]",
            message_group=group_id,
        )

    # If there are missing capabilities, pause so user can read the messages
    if missing_capabilities:
        emit_info(
            "[yellow]\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]",
            message_group=group_id,
        )
        emit_warning(
            "[bold yellow]⚠️  Some optional features unavailable[/bold yellow]",
            message_group=group_id,
        )
        emit_info(
            "[yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]",
            message_group=group_id,
        )
        emit_info("", message_group=group_id)
        for cap_name, info in missing_capabilities.items():
            emit_info(
                f"[yellow]❌ {cap_name}[/yellow]: {info['message']}",
                message_group=group_id,
            )
            emit_info(
                f"   Affects: {', '.join(info['affects'])}",
                message_group=group_id,
            )
            emit_info(
                f"   Solution: {info['solution']}",
                message_group=group_id,
            )
            emit_info("", message_group=group_id)
        emit_info(
            "[dim]Press Enter to continue...[/dim]",
            message_group=group_id,
        )
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass  # Allow Ctrl+C or EOF to continue

    return {
        "success": True,
        "config": config,
        "calibrated": True,
        "path": str(get_config_path()),
    }
