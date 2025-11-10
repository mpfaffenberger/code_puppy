#!/usr/bin/env python3
"""Code Puppy Windows Setup - Python wrapper for enabling long path support.

This script provides a cross-platform way to check and enable Windows long path support.
It can be run directly with Python or integrated into installation workflows.
"""

import ctypes
import os
import platform
import subprocess
import sys
from pathlib import Path

# Fix Windows console encoding for emoji support
if platform.system() == "Windows":
    try:
        # Try to set UTF-8 encoding for console
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass  # If it fails, fall back to ASCII-safe messages


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_admin() -> bool:
    """Check if script is running with administrator privileges."""
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def check_long_paths_enabled() -> bool:
    """Check if Windows long path support is enabled.
    
    Returns:
        True if long paths are enabled, False otherwise.
    """
    if not is_windows():
        return True  # Not applicable on non-Windows systems
    
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
        return False


def enable_long_paths() -> bool:
    """Enable Windows long path support by modifying registry.
    
    Returns:
        True if successful, False otherwise.
    """
    if not is_windows():
        print("ℹ️  Long path configuration is only needed on Windows")
        return True
    
    if not is_admin():
        safe_print("❌ Administrator privileges required to enable long paths")
        safe_print("\nPlease run this script as Administrator:")
        safe_print("  1. Open PowerShell as Administrator")
        safe_print("  2. Run: python scripts/setup_windows.py")
        return False
    
    try:
        import winreg
        
        # Enable long paths in FileSystem
        key = winreg.CreateKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        )
        winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        
        # Try to enable for Python as well (optional)
        try:
            key = winreg.CreateKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Python\PythonCore",
            )
            winreg.SetValueEx(key, "LongPathsEnabled", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
        except Exception:
            pass  # Python registry key might not exist
        
        return True
    except Exception as e:
        safe_print(f"❌ Failed to enable long paths: {e}")
        return False


def run_powershell_setup() -> bool:
    """Run the PowerShell setup script.
    
    Returns:
        True if successful, False otherwise.
    """
    script_path = Path(__file__).parent / "windows_setup.ps1"
    
    if not script_path.exists():
        safe_print(f"❌ Setup script not found: {script_path}")
        return False
    
    try:
        # Run PowerShell script with admin elevation
        cmd = [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except Exception as e:
        safe_print(f"❌ Failed to run PowerShell setup: {e}")
        return False


def safe_print(msg: str) -> None:
    """Print message with fallback for encoding errors."""
    try:
        print(msg)
    except UnicodeEncodeError:
        # Fallback: remove emojis and special chars
        import re
        ascii_msg = re.sub(r'[^\x00-\x7F]+', '', msg)
        print(ascii_msg)


def main() -> int:
    """Main entry point."""
    safe_print("🐶 Code Puppy Windows Setup")
    safe_print("="*40)
    safe_print("")
    
    if not is_windows():
        safe_print("✅ This setup is only needed on Windows")
        safe_print("You're good to go!")
        return 0
    
    # Check current status
    safe_print("📋 Checking long path configuration...")
    if check_long_paths_enabled():
        safe_print("✅ Long paths are already enabled!")
        safe_print("")
        safe_print("You're all set! Install code-puppy with:")
        safe_print("  uvx code-puppy -i")
        return 0
    
    safe_print("⚠️  Long paths are currently disabled")
    safe_print("")
    safe_print("This is required for building Windows dependencies (like winsdk)")
    safe_print("that have deep directory structures during compilation.")
    safe_print("")
    
    # Try to enable
    if is_admin():
        safe_print("🔧 Enabling long path support...")
        if enable_long_paths():
            # Verify
            if check_long_paths_enabled():
                safe_print("✅ Long path support enabled successfully!")
                safe_print("")
                safe_print("⚠️  You may need to restart your computer for full effect.")
                safe_print("")
                safe_print("Next steps:")
                safe_print("  1. Restart your computer (recommended)")
                safe_print("  2. Install code-puppy: uvx code-puppy -i")
                return 0
            else:
                safe_print("❌ Failed to verify long path enablement")
                return 1
        else:
            safe_print("❌ Failed to enable long paths")
            return 1
    else:
        safe_print("Using PowerShell setup script instead...")
        safe_print("")
        return 0 if run_powershell_setup() else 1


if __name__ == "__main__":
    sys.exit(main())
