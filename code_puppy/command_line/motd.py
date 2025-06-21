"""
MOTD (Message of the Day) feature for code-puppy.
Stores seen versions in ~/.puppy_cfg/motd.txt.
"""
import os
from typing import Optional

MOTD_VERSION = "20240621"
MOTD_MESSAGE = """
June 21th, 2025 - 🚀 Woof-tastic news! Code Puppy now supports **MCP (Model Context Protocol) servers** for EXTREME PUPPY POWER!!!!.

You can now connect plugins like doc search, Context7 integration, and more by simply dropping their info in your `~/.code_puppy/mcp_servers.json`. I’ll bark at remote docs or wrangle code tools for you—no extra fetches needed.

Setup is easy:
1. Add your MCP config to `~/.code_puppy/mcp_servers.json`.
2. Fire up something like Context7, or any MCP server you want.
3. Ask me to search docs, analyze, and more.

The following example will let code_puppy use Context7! 
Example config (+ more details in the README): 

{
  "mcp_servers": {
     "context7": { 
        "url": "https://mcp.context7.com/sse"
     }
  }
}

I fetch docs and power-ups via those servers. If you break stuff, please file an issue—bonus treat for reproducible bugs! 🦴

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


def print_motd(console, force: bool = False) -> bool:
    if force or not has_seen_motd(MOTD_VERSION):
        console.print(MOTD_MESSAGE)
        mark_motd_seen(MOTD_VERSION)
        return True
    return False
