from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from typing import Any, Dict

from code_puppy import __version__ as code_puppy_version
from code_puppy.messaging import emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .detection import detect_displays, detect_platform


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


def detect_winrt_ocr() -> bool:
    """Detect if WinRT OCR is available (Windows 10+).

    This matches the actual provider initialization logic to ensure
    detection accurately reflects runtime availability.
    """
    try:
        if sys.platform != "win32":
            return False

        # Test critical WinRT imports
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401
        from winrt.windows.graphics.imaging import SoftwareBitmap  # noqa: F401
        from winrt.windows.storage.streams import (
            InMemoryRandomAccessStream,  # noqa: F401
        )

        # Try to create OCR engine using the same method as the provider
        # This is more reliable than checking available_languages
        engine = OcrEngine.try_create_from_user_profile_languages()
        return engine is not None
    except Exception:
        return False


def detect_vision_framework() -> bool:
    """Detect if Vision Framework OCR is available (macOS 10.15+)."""
    try:
        if sys.platform != "darwin":
            return False

        # Check macOS version >= 10.15
        import platform

        version = platform.mac_ver()[0]
        if not version:
            return False

        major, minor = map(int, version.split(".")[:2])
        if major < 10 or (major == 10 and minor < 15):
            return False

        # Test Vision Framework imports
        import Vision  # noqa: F401
        import Quartz  # noqa: F401

        return True
    except Exception:
        return False


def detect_tesseract() -> bool:
    """Detect if Tesseract OCR is available."""
    try:
        import pytesseract

        # Try to get version (will fail if tesseract not installed)
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


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

    return capabilities


def detect_ocr_providers() -> Dict[str, Any]:
    """Detect available OCR providers.

    Returns:
        Dictionary with OCR provider availability and primary provider
    """
    providers = {}
    primary_provider = None

    # Check WinRT OCR (Windows 10+ only)
    if sys.platform == "win32":
        try:
            from code_puppy.tools.gui_cub.ocr_providers.winrt_provider import (
                WinRTOCRProvider,
            )

            provider = WinRTOCRProvider()
            providers["winrt_ocr"] = provider.is_available()
            if providers["winrt_ocr"]:
                primary_provider = "winrt"
        except ImportError:
            providers["winrt_ocr"] = False

    # Check Vision Framework (macOS 10.15+ only)
    if sys.platform == "darwin":
        try:
            from code_puppy.tools.gui_cub.ocr_providers.vision_provider import (
                VisionOCRProvider,
            )

            provider = VisionOCRProvider()
            providers["vision_framework"] = provider.is_available()
            if providers["vision_framework"]:
                primary_provider = "vision"
        except ImportError:
            providers["vision_framework"] = False

    return {
        "providers": providers,
        "primary": primary_provider,
    }


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

    # Skip platform-specific capabilities when displaying
    # (atomacos is macOS-only, pywinauto is Windows-only)
    for cap, available in capabilities.items():
        # Skip atomacos on non-macOS platforms
        if cap == "atomacos" and sys.platform != "darwin":
            continue
        # Skip pywinauto on non-Windows platforms
        if cap == "pywinauto" and sys.platform != "win32":
            continue

        status = "✅" if available else "❌"
        emit_info(
            f"  {status} {cap}",
            message_group=group_id,
        )
    emit_info("", message_group=group_id)

    # Detect OCR providers
    emit_info("🔍 Detecting OCR providers...", message_group=group_id)
    ocr_info = detect_ocr_providers()
    ocr_providers = ocr_info["providers"]
    primary_ocr = ocr_info["primary"]

    # Display OCR providers (skip platform-specific ones)
    for provider, available in ocr_providers.items():
        # Skip winrt_ocr on non-Windows platforms
        if provider == "winrt_ocr" and sys.platform != "win32":
            continue
        # Skip vision_framework on non-macOS platforms
        if provider == "vision_framework" and sys.platform != "darwin":
            continue

        status = "✅" if available else "❌"
        emit_info(
            f"  {status} {provider}",
            message_group=group_id,
        )

    # Show primary OCR provider
    if primary_ocr:
        emit_info(
            f"  ⭐ Primary: {primary_ocr}",
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

    # Build config
    config = {
        "version": "1.0",
        "code_puppy_version": code_puppy_version,
        "calibrated_at": datetime.now().isoformat(),
        "platform": platform_info,
        "display": display_info,
        "capabilities": capabilities,
        "ocr_providers": ocr_info,
        "permissions": permissions,
        "missing_capabilities": missing_capabilities,
        # Explicitly set debug defaults (makes config self-documenting)
        "debug": {
            "copy_screenshots_to_cwd": False,
        },
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


async def run_calibration(force: bool = False) -> Dict[str, Any]:
    """Async wrapper for calibrate_platform.

    This function provides an async interface to the synchronous calibration.
    Required for compatibility with async code paths in config_manager.

    Args:
        force: If True, re-calibrate even if config exists

    Returns:
        Dictionary with calibration results
    """
    # calibrate_platform is synchronous, but we need async interface
    # Since calibration is I/O-bound (file operations, subprocess calls),
    # we just call it directly without run_in_executor
    return calibrate_platform(force=force)
