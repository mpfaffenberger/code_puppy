"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""
import os
from typing import Optional

MOTD_VERSION = "20240601"
MOTD_MESSAGE = """
June 14th, 2025 - Wow... code_puppy has been downloaded 10s of thousands of times. 

This new update has a bug fix where message truncation would sometimes cause tool-calls and tool-replies
to become isolated, and an exception would be raied creating a situation only recoverable by restarting
code-puppy or using the `clear` command to get rid of all message history. 

Thankfully that is fixed. Message truncation max-length is configurable with the following command:
`~set message_history_length 25` if you want to truncate to 25 messages. The default is 40. 

This message-of-the-day will not appear again unless you run ~motd.

Please open issues on GitHub if you find any bugs! Cheers!
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
