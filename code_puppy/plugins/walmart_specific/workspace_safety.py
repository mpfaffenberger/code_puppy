"""Windows workspace safety check for Code Puppy.

Automatic safety measure to move users out of dangerous directories
like System32 or the home directory root on Windows.
"""

import os
from pathlib import Path


def ensure_safe_windows_workspace() -> None:
    """
    On Windows, if the current working directory is System32 or the user's home directory,
    automatically switch to a 'puppy_workspace' in the user's Documents folder.
    """
    # Only applies to Windows
    if os.name != "nt":
        return

    try:
        cwd = Path.cwd()
        home = Path.home()

        # Check if we are in a "dangerous" or "messy" location
        # 1. System32 (or similar system directories)
        # Using simple string check for robustness against variations
        cwd_str = str(cwd).lower()
        is_system_dir = "windows\\system32" in cwd_str

        # 2. Home directory root
        is_home_root = cwd == home

        if is_system_dir or is_home_root:
            # Determine target workspace path
            # Standard location: ~/Documents/puppy_workspace
            documents_dir = home / "Documents"

            # If Documents doesn't exist (rare/custom setup), fall back to creating in Home
            if not documents_dir.exists():
                documents_dir = home

            target_workspace = documents_dir / "puppy_workspace"

            # Create if it doesn't exist
            if not target_workspace.exists():
                target_workspace.mkdir(parents=True, exist_ok=True)
                print(f"🐶 Created new workspace: {target_workspace}")

            # Change directory
            os.chdir(target_workspace)

            # Inform the user
            print(f"🐶 Auto-switched working directory to: {target_workspace}")

            if is_system_dir:
                print("   (Safety measure: Moving out of System32!)")
            elif is_home_root:
                print("   (Housekeeping: Keeping your home directory tidy!)")

    except Exception as e:
        # If anything goes wrong (permissions, etc.), just warn and continue
        # We don't want to crash the whole app just because of this
        print(f"🐶 Warning: Failed to auto-switch workspace: {e}")
