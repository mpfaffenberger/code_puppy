"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-09-14"
MOTD_MESSAGE = """
# 🛡️ New: Command Safety Validation

Code Puppy now validates shell commands before execution to prevent dangerous operations.

## Risk Levels
Commands are categorized into 4 risk levels:
- **LOW**: Minor risks (file modifications, git operations, etc)
- **MEDIUM**: Moderate risks (package installs, system config changes, update queries which have a where clause, etc)
- **HIGH**: Serious risks (recursive deletes, database updates without a where clause, sudo operations, etc)
- **CRITICAL**: Catastrophic risks (`rm -rf /`, system wipes, fork bombs, drop table/database, etc)

## Permission Levels
Control which commands run automatically:
- `safe` - Only allow safe commands (minimal risk)
- `low` - Allow up to LOW risk (small risk of local data loss or corruption)
- `medium` - Allow up to MEDIUM risk (default)
- `high` - Allow up to HIGH risk (the agent could cause isolated irreversible damage, tread carefully)
- `critical` - Allow all commands (Full YOLO mode)

## Adjust Your Safety Level
```
/set safety_permission_level=high
```
Blocked commands show exit code `-2` and explain why they were stopped.

Your agent will interpret this and adjust accordingly.
"""
MOTD_TRACK_FILE = os.path.join(CONFIG_DIR, "motd.txt")


def has_seen_motd(version: str) -> bool:  # 🐕 Check if puppy has seen this MOTD!
    if not os.path.exists(MOTD_TRACK_FILE):
        return False
    with open(MOTD_TRACK_FILE, "r") as f:
        seen_versions = {line.strip() for line in f if line.strip()}
    return version in seen_versions


def mark_motd_seen(version: str):  # 🐶 Mark MOTD as seen by this good puppy!
    # Create directory if it doesn't exist 🏠🐕
    os.makedirs(os.path.dirname(MOTD_TRACK_FILE), exist_ok=True)

    # Check if the version is already in the file 📋🐶
    seen_versions = set()
    if os.path.exists(MOTD_TRACK_FILE):
        with open(MOTD_TRACK_FILE, "r") as f:
            seen_versions = {line.strip() for line in f if line.strip()}

    # Only add the version if it's not already there 📝🐕‍🦺
    if version not in seen_versions:
        with open(MOTD_TRACK_FILE, "a") as f:
            f.write(f"{version}\n")


def print_motd(
    console=None, force: bool = False
) -> bool:  # 🐶 Print exciting puppy MOTD!
    """
    🐕 Print the message of the day to the user - woof woof! 🐕

    Args:
        console: Optional console object (for backward compatibility) 🖥️🐶
        force: Whether to force printing even if the MOTD has been seen 💪🐕‍🦺

    Returns:
        True if the MOTD was printed, False otherwise 🐾
    """
    if force or not has_seen_motd(MOTD_VERSION):
        # Create a Rich Markdown object for proper rendering 🎨🐶
        from rich.markdown import Markdown

        markdown_content = Markdown(MOTD_MESSAGE)
        emit_info(markdown_content)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
