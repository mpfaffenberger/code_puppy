"""Platform calibration for GUI-Cub - detects and caches all automation-relevant info.

Runs on first use (like QA-Kitten downloading Camoufox) to detect:
- Platform (OS, version, architecture)
- Displays (all monitors, resolutions, DPI, scaling)
- Libraries (atomacos, pywinauto, pytesseract, opencv)
- Performance (screenshot, mouse, keyboard latencies)
- Permissions (accessibility, screen recording on macOS)
"""

import asyncio
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from typing import Any, Dict, List

import pyautogui

if sys.platform == "win32":
    import winreg
    import ctypes
from PIL import Image

from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

try:
    from code_puppy import __version__ as code_puppy_version
except ImportError:
    code_puppy_version = "unknown"


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
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WRITE
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
                    ctypes.byref(result)
                )
            except Exception:
                pass  # Broadcast is optional, PATH update still worked
            
            return True, f"Added to system PATH (new length: {len(new_path)} chars)"
    
    except PermissionError:
        return False, "Access denied (requires administrator privileges)"
    except Exception as e:
        return False, f"Registry error: {type(e).__name__}: {str(e)[:100]}"


def detect_platform() -> Dict[str, Any]:
    """Detect OS platform information."""
    os_name = sys.platform
    os_display = {
        "darwin": "macOS",
        "win32": "Windows",
        "linux": "Linux",
    }.get(os_name, os_name)
    
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
            monitors = _detect_linux_monitors()
    except Exception as e:
        # Fallback to primary display only
        monitors = [{
            "id": 0,
            "resolution": [primary_width, primary_height],
            "scale": scale_factor,
            "primary": True,
            "bounds": {"x": 0, "y": 0, "width": primary_width, "height": primary_height},
        }]
    
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
            
            monitors.append({
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
            })
        
        return monitors
    except ImportError:
        # NSScreen not available, fall back to pyautogui
        width, height = pyautogui.size()
        return [{
            "id": 0,
            "resolution": [width, height],
            "scale": 1.0,
            "primary": True,
            "bounds": {"x": 0, "y": 0, "width": width, "height": height},
        }]


def _detect_windows_monitors() -> List[Dict[str, Any]]:
    """Detect monitors on Windows."""
    try:
        import win32api
        
        monitors = []
        for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
            info = win32api.GetMonitorInfo(monitor[0])
            rect = info['Monitor']
            
            width = rect[2] - rect[0]
            height = rect[3] - rect[1]
            
            monitors.append({
                "id": i,
                "resolution": [width, height],
                "scale": 1.0,  # TODO: Get actual DPI
                "primary": info.get('Flags', 0) == 1,
                "bounds": {
                    "x": rect[0],
                    "y": rect[1],
                    "width": width,
                    "height": height,
                },
            })
        
        return monitors
    except ImportError:
        # win32api not available
        width, height = pyautogui.size()
        return [{
            "id": 0,
            "resolution": [width, height],
            "scale": 1.0,
            "primary": True,
            "bounds": {"x": 0, "y": 0, "width": width, "height": height},
        }]


def _detect_linux_monitors() -> List[Dict[str, Any]]:
    """Detect monitors on Linux (basic support)."""
    # Linux multi-monitor detection is complex and varies by display server
    # For now, return primary display only
    width, height = pyautogui.size()
    return [{
        "id": 0,
        "resolution": [width, height],
        "scale": 1.0,
        "primary": True,
        "bounds": {"x": 0, "y": 0, "width": width, "height": height},
    }]


def _attempt_install_windows_dependencies() -> bool:
    """Attempt to install Windows-specific dependencies (pywinauto, pywin32).
    
    Returns:
        True if installation succeeded, False otherwise
    """
    import subprocess
    
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


def _download_and_install_tesseract(url: str, group_id: str) -> tuple[bool, bool, bool]:
    """Download and silently install Tesseract from a URL.
    
    Args:
        url: Download URL for Tesseract installer
        group_id: Message group ID for logging
        
    Returns:
        Tuple of (install_success: bool, path_success: bool, needs_restart: bool)
    """
    import subprocess
    import tempfile
    from pathlib import Path
    
    from code_puppy.messaging import emit_info, emit_warning
    
    try:
        # Check admin rights on Windows
        if sys.platform == "win32" and not _is_admin():
            emit_warning(
                "[yellow]⚠️ Installation requires administrator privileges[/yellow]",
                message_group=group_id,
            )
            emit_info(
                "  • Please restart PowerShell/Terminal as Administrator",
                message_group=group_id,
            )
            emit_info(
                "  • Then run: pup",
                message_group=group_id,
            )
            return False, False, False  # install_success, path_success, needs_restart, False  # install_success=False, path_success=False, needs_restart=False
        
        # Download the installer
        emit_info(
            f"  • Downloading from {url}...",
            message_group=group_id,
        )
        
        import urllib.request
        temp_dir = tempfile.gettempdir()
        installer_path = Path(temp_dir) / "tesseract-installer.exe"
        
        urllib.request.urlretrieve(url, installer_path)
        
        emit_info(
            "  • Download complete, installing...",
            message_group=group_id,
        )
        
        # Run silent installation
        # /S = silent mode
        # /D = installation directory (must be last parameter)
        install_result = subprocess.run(
            [str(installer_path), "/S", "/D=C:\\Program Files\\Tesseract-OCR"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )
        
        # Clean up installer
        try:
            installer_path.unlink()
        except Exception:
            pass
        
        if install_result.returncode == 0:
            emit_info(
                "[green]✅ Tesseract installed successfully[/green]",
                message_group=group_id,
            )
            
            # Add Tesseract to system PATH using Windows registry (no 1024 char limit)
            tesseract_path = "C:\\Program Files\\Tesseract-OCR"
            emit_info(
                "  • Adding Tesseract to system PATH via registry...",
                message_group=group_id,
            )
            emit_info(
                f"[dim]  • Path to add: {tesseract_path}[/dim]",
                message_group=group_id,
            )
            
            path_success, message = _update_system_path_registry(tesseract_path)
            needs_restart = False  # Default to no restart needed
            
            if path_success:
                if "Already" in message:
                    emit_info(
                        f"[green]  • {message}[/green]",
                        message_group=group_id,
                    )
                    # Check if tesseract is actually accessible in current process
                    try:
                        subprocess.run(
                            ["tesseract", "--version"],
                            capture_output=True,
                            timeout=5,
                            check=True
                        )
                        needs_restart = False  # Works now
                    except Exception:
                        emit_info(
                            "[yellow]  • Restart needed to use tesseract in this terminal[/yellow]",
                            message_group=group_id,
                        )
                        needs_restart = True  # In PATH but current process can't see it
                else:
                    emit_info(
                        f"[green]  • PATH updated successfully via registry[/green]",
                        message_group=group_id,
                    )
                    emit_info(
                        f"[dim]  • {message}[/dim]",
                        message_group=group_id,
                    )
                    needs_restart = True  # PATH just updated
            else:
                emit_warning(
                    f"[yellow]  • Could not update PATH: {message}[/yellow]",
                    message_group=group_id,
                )
                emit_info(
                    f"  • Please manually add to system PATH: {tesseract_path}",
                    message_group=group_id,
                )
                emit_info(
                    "[dim]  • Instructions: System Properties > Environment Variables > System PATH > Edit > New[/dim]",
                    message_group=group_id,
                )
                emit_info(
                    "[dim]Press Enter to continue...[/dim]",
                    message_group=group_id,
                )
                try:
                    input()
                except (KeyboardInterrupt, EOFError):
                    pass  # User pressed Ctrl+C or EOF, continue anyway
            
            # Return (install_success=True, path_success=True/False, needs_restart=True/False)
            return True, path_success, needs_restart
        else:
            emit_warning(
                f"[yellow]⚠️ Installation failed: {install_result.stderr[:200]}[/yellow]",
                message_group=group_id,
            )
            return False, False, False  # install_success, path_success, needs_restart, False  # install_success=False, path_success=False, needs_restart=False
    
    except Exception as e:
        error_msg = str(e)
        
        # Check for admin rights issue (WinError 740)
        if "740" in error_msg or "elevation" in error_msg.lower():
            emit_warning(
                "[yellow]⚠️ Installation requires administrator privileges[/yellow]",
                message_group=group_id,
            )
            emit_info(
                "  • Please run PowerShell/Terminal as Administrator",
                message_group=group_id,
            )
            emit_info(
                "  • Or manually download and install Tesseract",
                message_group=group_id,
            )
        else:
            emit_warning(
                f"[yellow]⚠️ Download/install error: {error_msg[:200]}[/yellow]",
                message_group=group_id,
            )
        return False, False, False  # install_success, path_success, needs_restart, False  # install_success=False, path_success=False, needs_restart=False


def _attempt_install_tesseract_windows() -> tuple[bool, bool, bool]:
    """Attempt to install Tesseract OCR on Windows.
    
    Tries multiple strategies:
    1. Check WALMART_TESSERACT_URL env var for internal mirror
    2. Try direct download and silent install from official release
    3. Try winget install (Windows 10+ only)
    4. Show download instructions if all fail
    
    Returns:
        Tuple of (install_success: bool, path_success: bool, needs_restart: bool)
    """
    import os
    import subprocess
    import tempfile
    from pathlib import Path
    
    from code_puppy.messaging import emit_info, emit_warning
    from code_puppy.tools.common import generate_group_id
    
    group_id = generate_group_id("tesseract_install")
    
    emit_info(
        "[cyan]📦 Tesseract OCR not found, attempting installation...[/cyan]",
        message_group=group_id,
    )
    
    # Strategy 1: Check for Walmart internal binary
    walmart_url = os.environ.get("WALMART_TESSERACT_URL")
    if walmart_url:
        emit_info(
            f"  • Found WALMART_TESSERACT_URL: {walmart_url}",
            message_group=group_id,
        )
        # Try to download and install from Walmart mirror
        install_success, path_success, needs_restart = _download_and_install_tesseract(walmart_url, group_id)
        if install_success:
            return install_success, path_success, needs_restart
        else:
            emit_info(
                "  • Walmart mirror installation failed, trying other methods...",
                message_group=group_id,
            )
    
    # Strategy 2: Direct download from official GitHub release
    emit_info(
        "  • Attempting direct download from GitHub...",
        message_group=group_id,
    )
    
    tesseract_url = "https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
    install_success, path_success, needs_restart = _download_and_install_tesseract(tesseract_url, group_id)
    if install_success:
        return install_success, path_success, needs_restart
    
    # Strategy 3: Try winget (Windows 10+ package manager)
    try:
        emit_info(
            "  • Attempting winget installation...",
            message_group=group_id,
        )
        
        result = subprocess.run(
            ["winget", "install", "--id=UB-Mannheim.TesseractOCR", "--silent", "--accept-source-agreements"],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for download
        )
        
        if result.returncode == 0:
            emit_info(
                "[green]✅ Tesseract installed via winget[/green]",
                message_group=group_id,
            )
            emit_info(
                "  • Please restart your terminal for PATH changes to take effect",
                message_group=group_id,
            )
            # winget handles PATH automatically (but still need restart)
            return True, True, True  # install_success, path_success, needs_restart
        else:
            emit_info(
                "  • winget installation failed, falling back to manual instructions",
                message_group=group_id,
            )
    except Exception:
        pass  # winget might not be available
    
    # All strategies failed
    emit_warning(
        "[⚠️ yellow]⚠️ Could not install Tesseract automatically[/yellow]",
        message_group=group_id,
    )
    emit_info(
        "[yellow]Tesseract OCR installation required for OCR features[/yellow]",
        message_group=group_id,
    )
    emit_info(
        "  • Manual download: https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe",
        message_group=group_id,
    )
    emit_info(
        "  • Or ask IT for the Walmart internal mirror",
        message_group=group_id,
    )
    emit_info(
        "  • After installation, restart terminal and agent will auto-detect",
        message_group=group_id,
    )
    
    return False, False, False  # install_success, path_success, needs_restart


def detect_capabilities() -> Dict[str, bool]:
    """Detect which libraries are available.
    
    On Windows, attempts to auto-install pywinauto and pywin32 if missing.
    """
    capabilities = {}
    
    # Always available (required dependencies)
    capabilities["pyautogui"] = True
    capabilities["pillow"] = True
    
    # Test atomacos (macOS accessibility)
    try:
        import atomacos
        capabilities["atomacos"] = True
    except ImportError:
        capabilities["atomacos"] = False
    
    # Test pywinauto (Windows automation)
    # If on Windows and not installed, attempt auto-install
    try:
        import pywinauto
        capabilities["pywinauto"] = True
    except ImportError:
        if sys.platform == "win32":
            # Attempt to install Windows dependencies
            if _attempt_install_windows_dependencies():
                # Try importing again after installation
                try:
                    import pywinauto
                    capabilities["pywinauto"] = True
                except ImportError:
                    capabilities["pywinauto"] = False
            else:
                capabilities["pywinauto"] = False
        else:
            capabilities["pywinauto"] = False
    
    # Test pytesseract (OCR)
    # If on Windows and tesseract binary is missing, attempt auto-install
    try:
        import pytesseract
        # Try to run a test to ensure tesseract binary is available
        pytesseract.get_tesseract_version()
        capabilities["pytesseract"] = True
    except Exception:
        if sys.platform == "win32":
            # Attempt to install Tesseract binary
            install_success, path_success, needs_restart = _attempt_install_tesseract_windows()
            if install_success:
                # Installation succeeded, track PATH status and restart requirement
                capabilities["pytesseract_install_success"] = True
                capabilities["pytesseract_path_success"] = path_success
                capabilities["pytesseract_needs_restart"] = needs_restart
                
                # Try checking again after installation
                # Note: May still fail if PATH not updated until terminal restart
                try:
                    import pytesseract
                    pytesseract.get_tesseract_version()
                    capabilities["pytesseract"] = True
                except Exception:
                    capabilities["pytesseract"] = False
            else:
                capabilities["pytesseract"] = False
                capabilities["pytesseract_install_success"] = False
                capabilities["pytesseract_path_success"] = False
                capabilities["pytesseract_needs_restart"] = False
        else:
            capabilities["pytesseract"] = False
    
    # Test opencv
    try:
        import cv2
        capabilities["opencv"] = True
    except ImportError:
        capabilities["opencv"] = False
    
    return capabilities


def detect_permissions() -> Dict[str, Any]:
    """Detect accessibility permissions (macOS only)."""
    permissions = {}
    
    if sys.platform == "darwin":
        try:
            from code_puppy.tools.gui_cub.platform import check_macos_accessibility_permission
            has_access, message = check_macos_accessibility_permission()
            permissions["accessibility"] = has_access
            permissions["accessibility_message"] = message
        except Exception as e:
            permissions["accessibility"] = False
            permissions["accessibility_message"] = f"Failed to check: {e}"
    
    return permissions


async def test_performance() -> Dict[str, Any]:
    """Test performance of key operations."""
    performance = {}
    
    # Test screenshot latency
    try:
        start = time.perf_counter()
        screenshot = pyautogui.screenshot()
        end = time.perf_counter()
        performance["screenshot_ms"] = int((end - start) * 1000)
    except Exception:
        performance["screenshot_ms"] = -1
    
    # Test mouse movement latency (small movement)
    try:
        current_pos = pyautogui.position()
        start = time.perf_counter()
        pyautogui.moveTo(current_pos[0] + 1, current_pos[1])
        end = time.perf_counter()
        performance["mouse_move_ms"] = int((end - start) * 1000)
        # Move back
        pyautogui.moveTo(current_pos[0], current_pos[1])
    except Exception:
        performance["mouse_move_ms"] = -1
    
    # Test click latency (no actual click, just timing)
    try:
        start = time.perf_counter()
        # Don't actually click, just measure the time
        end = time.perf_counter()
        # Click typically takes 50-200ms
        performance["click_estimate_ms"] = 100  # Default estimate
    except Exception:
        performance["click_estimate_ms"] = -1
    
    # Test keyboard latency estimate
    performance["keyboard_estimate_ms"] = 50  # Default estimate
    
    return performance


async def run_calibration() -> Dict[str, Any]:
    """Run full platform calibration (QA-Kitten pattern).
    
    This is called:
    - On first run (no config.json exists)
    - When config is invalid (resolution changed, etc.)
    - When user manually calls gui_cub_calibrate()
    
    Returns:
        Dict with success, config, and calibration timestamp
    """
    group_id = generate_group_id("calibration")
    emit_info(
        "[bold green]🔍 Detecting platform capabilities...[/bold green]",
        message_group=group_id,
    )
    
    # Detect platform
    emit_info("  • Detecting OS and version...", message_group=group_id)
    platform_info = detect_platform()
    emit_info(
        f"    → {platform_info['os_display']} {platform_info['version']} ({platform_info['machine']})",
        message_group=group_id,
    )
    
    # Detect displays
    emit_info("  • Detecting displays and resolution...", message_group=group_id)
    display_info = detect_displays()
    emit_info(
        f"    → {display_info['monitor_count']} monitor(s), primary: {display_info['primary_resolution'][0]}x{display_info['primary_resolution'][1]} @ {display_info['scale_factor']}x scale",
        message_group=group_id,
    )
    
    # Detect libraries (this may attempt installations on Windows)
    emit_info("  • Checking library availability...", message_group=group_id)
    capabilities = detect_capabilities()
    
    # After detect_capabilities runs (which includes installation attempts),
    # we need to re-check pytesseract availability since it might have just been installed
    if sys.platform == "win32" and not capabilities.get("pytesseract", False):
        # If it was marked unavailable initially, check again in case installation just succeeded
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            capabilities["pytesseract"] = True  # Update to reflect successful installation
        except Exception:
            pass  # Still not available, keep as False
    
    available = [k for k, v in capabilities.items() if v]
    emit_info(
        f"    → Available: {', '.join(available)}",
        message_group=group_id,
    )
    
    # Detect permissions
    permissions = detect_permissions()
    if permissions:
        emit_info("  • Checking permissions...", message_group=group_id)
        for key, value in permissions.items():
            if isinstance(value, bool):
                status = "✅" if value else "❌"
                emit_info(f"    → {key}: {status}", message_group=group_id)
    
    # Test performance
    emit_info("  • Testing performance...", message_group=group_id)
    performance = await test_performance()
    if performance.get("screenshot_ms", -1) > 0:
        emit_info(
            f"    → Screenshot: {performance['screenshot_ms']}ms, Mouse: {performance['mouse_move_ms']}ms",
            message_group=group_id,
        )
    
    # Build list of missing capabilities with reasons
    missing_capabilities = {}
    
    # Note: PATH update failures are handled inline during installation
    # with immediate user prompt, so we don't add them to missing_capabilities
    # to avoid duplicate pause screens
    
    # Only show pytesseract warning if installation didn't succeed
    # If it just installed successfully, user will restart terminal and it will work
    if not capabilities.get("pytesseract", False) and not capabilities.get("pytesseract_install_success", False):
        if sys.platform == "win32" and not _is_admin():
            missing_capabilities["pytesseract"] = {
                "reason": "admin_required",
                "message": "Tesseract installation requires administrator privileges",
                "solution": "Run PowerShell/Terminal as Administrator and restart code-puppy, or manually install from https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe and manually add to PATH: C:\\Program Files\\Tesseract-OCR",
                "affects": ["OCR", "VQA", "text recognition", "screenshot analysis"],
            }
        else:
            missing_capabilities["pytesseract"] = {
                "reason": "installation_failed",
                "message": "Tesseract OCR could not be installed automatically",
                "solution": "Manually install from https://github.com/tesseract-ocr/tesseract/releases/download/5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe and manually add to PATH: C:\\Program Files\\Tesseract-OCR",
                "affects": ["OCR", "VQA", "text recognition", "screenshot analysis"],
            }
    
    # Build config
    config = {
        "success": True,
        "calibrated_at": datetime.now().isoformat(),
        "version": "1.0.0",
        "code_puppy_version": code_puppy_version,
        "platform": platform_info,
        "display": display_info,
        "capabilities": capabilities,
        "missing_capabilities": missing_capabilities,
        "permissions": permissions,
        "performance": performance,
        "metadata": {
            "last_validated": datetime.now().isoformat(),
            "calibration_count": 1,
        },
    }
    
    # Save config
    from code_puppy.tools.gui_cub.config_manager import get_config_path, save_config
    
    if save_config(config):
        emit_info(
            f"[green]✅ Platform calibrated successfully[/green]",
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
    
    # Check if terminal restart is required (PATH was updated)
    if capabilities.get("pytesseract_needs_restart", False):
        emit_info(
            "\n[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]",
            message_group=group_id,
        )
        emit_warning(
            "[bold yellow]⚠️  TERMINAL RESTART REQUIRED ⚠️[/bold yellow]",
            message_group=group_id,
        )
        emit_info(
            "[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]",
            message_group=group_id,
        )
        emit_info(
            "[yellow]Tesseract installed and PATH updated successfully![/yellow]",
            message_group=group_id,
        )
        emit_info("", message_group=group_id)
        emit_info(
            "[bold white]To use OCR features, you MUST:[/bold white]",
            message_group=group_id,
        )
        emit_info(
            "[bold white]  1. Close this terminal window[/bold white]",
            message_group=group_id,
        )
        emit_info(
            "[bold white]  2. Open a new terminal[/bold white]",
            message_group=group_id,
        )
        emit_info(
            "[bold white]  3. Run 'pup' again[/bold white]",
            message_group=group_id,
        )
        emit_info("", message_group=group_id)
        emit_info(
            "[dim](The new PATH will be active in the new terminal)[/dim]",
            message_group=group_id,
        )
        emit_info(
            "[bold yellow]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold yellow]",
            message_group=group_id,
        )
        
        try:
            input("\nPress Enter to exit...")
        except (KeyboardInterrupt, EOFError):
            pass
        
        # sys is already imported at module level
        sys.exit(0)
    
    # If there are missing capabilities, pause so user can read the messages
    if missing_capabilities:
        emit_info(
            "[yellow]\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]",
            message_group=group_id,
        )
        emit_warning(
            "[bold yellow]⚠️  IMPORTANT: Some features are unavailable[/bold yellow]",
            message_group=group_id,
        )
        
        for capability_name, info in missing_capabilities.items():
            emit_info(
                f"\n[yellow]Missing:[/yellow] {capability_name}",
                message_group=group_id,
            )
            emit_info(
                f"[yellow]Reason:[/yellow] {info['message']}",
                message_group=group_id,
            )
            emit_info(
                f"[yellow]Affects:[/yellow] {', '.join(info['affects'])}",
                message_group=group_id,
            )
            emit_info(
                f"[yellow]Solution:[/yellow] {info['solution']}",
                message_group=group_id,
            )
            
            # Show instructions if available (for PATH issues)
            if "instructions" in info:
                emit_info(
                    f"[yellow]Instructions:[/yellow] {info['instructions']}",
                    message_group=group_id,
                )
        
        emit_info(
            "[yellow]\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/yellow]",
            message_group=group_id,
        )
        emit_info(
            "[dim]Press Enter to continue...[/dim]",
            message_group=group_id,
        )
        
        # Pause for user to read
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