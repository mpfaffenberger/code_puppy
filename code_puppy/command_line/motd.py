"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""

import os

from code_puppy.messaging import emit_info

MOTD_VERSION = "20250731"
MOTD_MESSAGE = """
🐕‍🦺 WOOF WOOF! August Update - Code Puppy's Been BUSY! 🐕‍🦺

🎉 NEW TRICKS YOUR PUPPY LEARNED: 🎉

🖱️  **Double-Click Magic**: Double-click history items in the sidebar! No more single-click peasantry!
📋  **Copy-Paste Mastery**: Hit that shiny new "Copy" button in TUI responses! 📋✨
🌈  **Prettier Code**: Syntax highlighting makes your code sparkle like a freshly groomed Golden Retriever! 🌈
⚡  **Smarter Timeouts**: No more hanging around like a patient pup waiting for treats!
🔧  **MCP Server Resilience**: Error handling so robust, even a Chihuahua couldn't break it! 🔧
🎨  **Dev Console Support**: For the fancy developers who like their debugging tools! 🎨
📝  **Multiline Magic**: ESC+ENTER (CLI) and ALT+ENTER (TUI) for multi-line prompts! 📝
🏷️  **Version Checking**: `--version` flag because knowing your puppy's age is important! 🏷️

   🐾 EVERY COMMIT MAKES ME A BETTER BOY! 🐾

   ██████╗  ██████╗  ██████╗ ███████╗    ██████╗ ██╗   ██╗██████╗ ██████╗ ██╗   ██╗
   ██╔════╝ ██╔═══██╗██╔═══██╗██╔════╝    ██╔══██╗██║   ██║██╔══██╗██╔══██╗╚██╗ ██╔╝
   ██║  ███╗██║   ██║██║   ██║█████╗      ██████╔╝██║   ██║██████╔╝██████╔╝ ╚████╔╝
   ██║   ██║██║   ██║██║   ██║██╔══╝      ██╔═══╝ ██║   ██║██╔═══╝ ██╔═══╝   ╚██╔╝
   ╚██████╔╝╚██████╔╝╚██████╔╝███████╗    ██║     ╚██████╔╝██║     ██║        ██║
    ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝    ╚═╝      ╚═════╝ ╚═╝     ╚═╝        ╚═╝

🦴 Fetch all these features with your favorite code companion! 🦴
This MOTD won't bark at you again unless you run `~motd`. Stay pawsome! 🐕💖
"""
MOTD_TRACK_FILE = os.path.expanduser("~/.puppy_cfg/motd.txt")


def has_seen_motd(version: str) -> bool:
    if not os.path.exists(MOTD_TRACK_FILE):
        return False
    with open(MOTD_TRACK_FILE, "r") as f:
        seen_versions = {line.strip() for line in f if line.strip()}
    return version in seen_versions


def mark_motd_seen(version: str):
    os.makedirs(os.path.dirname(MOTD_TRACK_FILE), exist_ok=True)
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
        emit_info(MOTD_MESSAGE)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
