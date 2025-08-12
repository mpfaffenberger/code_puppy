"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.code_puppy/motd.txt.
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-08-12"
MOTD_MESSAGE = """
```
🐶🎉 WOOF WOOF! 0.0.105! 🎉🐶

🚀 BUGS FIXED! 🚀

* GPT-5 no longer causes the `typing.Union` bug
* GPT-5 cooks nicely

 _______  _______  ______   _______    _______  __   __  _______  _______  __   __
|       ||       ||      | |       |  |       ||  | |  ||       ||       ||  | |  |
|       ||   _   ||  _    ||    ___|  |    _  ||  | |  ||    _  ||    _  ||  |_|  |
|       ||  | |  || | |   ||   |___   |   |_| ||  |_|  ||   |_| ||   |_| ||       |
|      _||  |_|  || |_|   ||    ___|  |    ___||       ||    ___||    ___||_     _|
|     |_ |       ||       ||   |___   |   |    |       ||   |    |   |      |   |
|_______||_______||______| |_______|  |___|    |_______||___|    |___|      |___|

🐕 EVERY COMMIT = BETTER GOOD BOY! 🐕

🦴 Go fetch these amazing features and see what your loyal
   code companion can do! 🦴

🎾 This MOTD won't bother you again unless you run `/motd`
   - just like a well-trained pup! 🎾

🐾 Stay pawsome, keep coding, and remember:
   every bug fixed is a treat earned! 🐾🍖
```
"""
MOTD_TRACK_FILE = os.path.join(CONFIG_DIR, "motd.txt")


def has_seen_motd(version: str) -> bool:
    if not os.path.exists(MOTD_TRACK_FILE):
        return False
    with open(MOTD_TRACK_FILE, "r") as f:
        seen_versions = {line.strip() for line in f if line.strip()}
    return version in seen_versions


def mark_motd_seen(version: str):
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(MOTD_TRACK_FILE), exist_ok=True)

    # Check if the version is already in the file
    seen_versions = set()
    if os.path.exists(MOTD_TRACK_FILE):
        with open(MOTD_TRACK_FILE, "r") as f:
            seen_versions = {line.strip() for line in f if line.strip()}

    # Only add the version if it's not already there
    if version not in seen_versions:
        with open(MOTD_TRACK_FILE, "a") as f:
            f.write(f"{version}\n")


def print_motd(console=None, force: bool = False) -> bool:
    """
    Print the message of the day to the user.

    Args:
        console: Optional console object (for backward compatibility)
        force: Whether to force printing even if the MOTD has been seen

    Returns:
        True if the MOTD was printed, False otherwise
    """
    if force or not has_seen_motd(MOTD_VERSION):
        # Create a Rich Markdown object for proper rendering
        from rich.markdown import Markdown

        markdown_content = Markdown(MOTD_MESSAGE)
        emit_info(markdown_content)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
