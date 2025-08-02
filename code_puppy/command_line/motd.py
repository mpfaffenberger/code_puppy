"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""

import os

MOTD_VERSION = "20250802"
MOTD_MESSAGE = """
/¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯¯\\
|   🐾  Happy Sat-urday, Aug 2, 2025!                       |
|                                                           |
|   Biscuit the code puppy is on full zoomie mode!          |
|   Major paws-up: We now integrate Cerebras Qwen3 Coder    |
|   480b! YES, that’s 480 billion parameters of tail-wagging|
|   code speed. It’s so fast, even my fetch can’t keep up!  |
|                                                           |
|   • Take stretch breaks – you’ll need ‘em!                |
|   • DRY your code, but keep your pup hydrated.            |
|   • If you hit a bug, treat yourself for finding it!      |
|                                                           |
|   Today: sniff, code, roll over, and let Cerebras Qwen3   |
|   Coder 480b do the heavy lifting. Fire up a ~motd anytime|
|   you need some puppy hype!                               |
\___________________________________________________________/
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
