"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in XDG_CONFIG_HOME/code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-01-01"
MOTD_MESSAGE = """🐕‍🦺
🐾```
# 🐶 Welcome to Code Puppy! 🐕
Your friendly open-source AI code agent.
Ready to help you write, refactor, and ship code faster! 🚀

Type /help to see available commands.
```
"""
MOTD_TRACK_FILE = os.path.join(CONFIG_DIR, "motd.txt")


def get_motd_content() -> tuple[str, str]:
    """Get MOTD content, checking plugins first.

    Returns:
        Tuple of (message, version) - either from plugin or built-in.
    """
    # Check if plugins want to override MOTD
    try:
        from code_puppy.callbacks import on_get_motd

        results = on_get_motd()
        # Use the last non-None result
        for result in reversed(results):
            if result is not None and isinstance(result, tuple) and len(result) == 2:
                return result
    except Exception:
        pass

    # Fall back to built-in MOTD
    return (MOTD_MESSAGE, MOTD_VERSION)


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
    message, version = get_motd_content()
    if force or not has_seen_motd(version):
        # Create a Rich Markdown object for proper rendering 🎨🐶
        from rich.markdown import Markdown

        markdown_content = Markdown(message)
        emit_info(markdown_content)
        mark_motd_seen(version)
        return True
    return False
