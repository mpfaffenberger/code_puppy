"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-10-13"
MOTD_MESSAGE = """
# 🎉 Quality of life features

## 📎 Image Support drag and drop!
You can now **drag-and-drop image files**!

- **Supported formats**: Images (PNG, JPG, GIF, WebP)
- **Local files**: Just drag them from your file explorer into the terminal

Try it: Drag an image and ask "What's in this image?"

## 💾 Autosave Session Management
Never lose your work! Sessions are now auto-saved with full management:

- **Auto-restore on startup**: Pick up where you left off
- **Interactive auto-save restore picker**: Browse sessions with metadata (message counts, timestamps)
- **Pagination**: Navigate through sessions 5 at a time
- **Session commands**:
  - `/session` - View current session ID
  - `/session new` - Start a fresh session
- **Auto-rotation**: Switching agents or clearing history creates a new session

Sessions live in `~/.code_puppy/autosaves/`

## ⌨️ Better Multiline Input
New keyboard shortcuts for multiline prompts:

- **CLI**: `Alt+M` or `F2` to toggle multiline mode (persistent!)
- **TUI**: `Shift+Enter` for newlines (more intuitive!)
- **Universal**: `Ctrl+J` also inserts newlines
- **Visual feedback**: See when multiline mode is active

---

*Woof! Your faithful code puppy is getting smarter every day! 🐶*
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
