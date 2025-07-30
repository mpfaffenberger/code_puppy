"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""

import os

from code_puppy.messaging import emit_info

MOTD_VERSION = "20250730"
MOTD_MESSAGE = """
July 30th, 2025 - 🚀🐶🐶🐶🐶🐶🚀

Thanks to major contributions from Luc Masalar, we now have the ability to use multiline input in both the TUI
and also --interactive mode!! Use either alt+enter or esc+enter to make a new line without submitting your prompt!

🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶 EXTREME PUPPY POWER!!!!.

KEEP COOKIN!

  1 ██╗    ██╗ █████╗ ██╗     ███╗   ███╗ █████╗ ██████╗ ████████╗
  2 ██║    ██║██╔══██╗██║     ████╗ ████║██╔══██╗██╔══██╗╚══██╔══╝
  3 ██║ █╗ ██║███████║██║     ██╔████╔██║███████║██████╔╝   ██║
  4 ██║███╗██║██╔══██║██║     ██║╚██╔╝██║██╔══██║██╔══██╗   ██║
  5 ╚███╔███╔╝██║  ██║███████╗██║ ╚═╝ ██║██║  ██║██║  ██║   ██║
  6  ╚══╝╚══╝ ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝

This message-of-the-day won’t bug you again unless you run ~motd. Stay fluffy!
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
