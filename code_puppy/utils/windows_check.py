"""Windows-specific checks and utilities.

Provides runtime checks for Windows configuration issues that could
cause problems during installation or execution.
"""

import platform
import sys
from typing import Optional


def is_windows() -> bool:
    """Check if running on Windows.
    
    Returns:
        True if on Windows, False otherwise.
    """
    return platform.system() == "Windows"


def check_long_paths_enabled() -> bool:
    """Check if Windows long path support is enabled.
    
    Returns:
        True if enabled or not on Windows, False if disabled on Windows.
    """
    if not is_windows():
        return True
    
    try:
        import winreg
        
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
            0,
            winreg.KEY_READ,
        )
        value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
        winreg.CloseKey(key)
        return value == 1
    except (ImportError, FileNotFoundError, OSError):
        # If we can't read the registry, assume it's not enabled
        return False


def get_long_paths_warning() -> Optional[str]:
    """Get a warning message if long paths are disabled on Windows.
    
    Returns:
        Warning message string if long paths are disabled, None otherwise.
    """
    if not is_windows():
        return None
    
    if check_long_paths_enabled():
        return None
    
    return (
        "\n"
        "⚠️  WARNING: Windows Long Path Support is DISABLED\n"
        "\n"
        "This may cause installation failures for certain dependencies (like winsdk).\n"
        "\n"
        "To fix this (recommended):\n"
        "  1. Run PowerShell as Administrator\n"
        "  2. Run: .\\scripts\\windows_setup.ps1\n"
        "  3. Restart your computer\n"
        "\n"
        "Or manually enable it:\n"
        "  New-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem' `\n"
        "    -Name 'LongPathsEnabled' -Value 1 -PropertyType DWORD -Force\n"
        "\n"
        "For more details, see: WINDOWS_INSTALLATION.md\n"
    )


def warn_if_long_paths_disabled(force: bool = False) -> None:
    """Print a warning if long paths are disabled on Windows.
    
    Args:
        force: If True, always print the message even if it was shown before.
               If False, only show once per session (not implemented yet).
    """
    warning = get_long_paths_warning()
    if warning:
        try:
            print(warning, file=sys.stderr)
        except UnicodeEncodeError:
            # Fallback for consoles that can't handle emojis
            import re
            ascii_warning = re.sub(r'[^\x00-\x7F]+', '', warning)
            print(ascii_warning, file=sys.stderr)


def is_path_too_long(path: str, max_length: int = 260) -> bool:
    """Check if a path exceeds Windows path length limits.
    
    Args:
        path: The path to check.
        max_length: Maximum allowed length (default 260 for Windows).
    
    Returns:
        True if path is too long, False otherwise.
    """
    if not is_windows():
        return False
    
    # If long paths are enabled, this isn't an issue
    if check_long_paths_enabled():
        return False
    
    return len(str(path)) >= max_length
