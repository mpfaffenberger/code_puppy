"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""

import os

MOTD_VERSION = "20250817"
MOTD_MESSAGE = """

🐾  Happy Sunday, Aug 17, 2025!

Biscuit the code puppy learned two new tricks!
Major paws-ups:
1. On-the-fly summarization: when your model's context hits 90%,
   Biscuit auto-summarizes older messages to keep you cruising. No sweat, no tokens spilled.
2. AGENT.md support: ship your project rules and style guide,
   and Biscuit will obey them like the good pup he is.

• Use ~m to swap models mid-session.
• YOLO_MODE=true skips command confirmations (danger, zoomies!).
• Keep files under 600 lines; split big ones like a responsible hooman.
• DRY code, happy pup.

Today's vibe: sniff context, summarize smartly, obey AGENT.md, and ship.
Run ~motd anytime you need more puppy hype!

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


def print_motd(console, force: bool = False) -> bool:
    if force or not has_seen_motd(MOTD_VERSION):
        console.print(MOTD_MESSAGE)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
