"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-08-18"
MOTD_MESSAGE = """🐕‍🦺
🐾```
🐶🎉🐕 WOOF WOOF! 0.0.108! 🐕🎉🐶

🚀🐶 AWESOME NEW STUFF THAT'LL BLOW YOUR MIND! 🐶🚀

* Your puppy is now SMART about memory! It keeps track of how much brain space it's using 🐕‍🦺
    * No more brain explosions! Built-in protection so I don't try to remember too much at once 🛡️🐶
    * If you ask me to read a MASSIVE file, I'll politely say "nope, too big for my puppy brain!" 📁🐕
        * I can only handle 10,000 tokens at once (that's like 1/20th of Claude's mega-brain) 🧠🐶
        * But don't worry! I'm clever enough to read stuff in bite-sized chunks if needed 🧩🐕
    * When searching with grep, I won't spam you with walls of text anymore (max 4096 chars per line) 🔍🐶
    * At 90% brain capacity, I'll do some smart compression magic to make room for more awesomeness 📝🐕‍🦺
    * Hard stop at 95% - I'll never let myself get overwhelmed and crash on you! 🚨🐶

* CTRL+C on shell commands works now! No more waiting forever for runaway processes to die 🛑🐕
    * I'll know when you hit cancel and ask "what went wrong?" like a good helpful puppy 💬🐶

* I got WAY more efficient! No more chatty tools hogging precious brain space ⚡🐕‍🦺
    * Tools now shut up when they don't need to be verbose, saving room for the important stuff 💎🐶


🚀🐕 SPRING CLEANING TIME! 🐕🚀

* Threw out the broken session memory - it was causing more problems than my chewed up shoes! 🧹🐶
* Said goodbye to the Codemap tool - turns out nobody really used it anyway 🗑️🐕
* Ditched web search - who needs Google when you have a smart puppy? 🌐🐶


🚀🐕‍🦺 SQUASHED THOSE PESKY BUGS! 🐕‍🦺🚀

* Remember when I used to crash and burn trying to list massive directories? NOT ANYMORE! Now I'm tough as nails 💪🐶

 _______  _______  ______   _______    _______  __   __  _______  _______  __   __
|       ||       ||      | |       |  |       ||  | |  ||       ||       ||  | |  |
|       ||   _   ||  _    ||    ___|  |    _  ||  | |  ||    _  ||    _  ||  |_|  |
|       ||  | |  || | |   ||   |___   |   |_| ||  |_|  ||   |_| ||   |_| ||       |
|      _||  |_|  || |_|   ||    ___|  |    ___||       ||    ___||    ___||_     _|
|     |_ |       ||       ||   |___   |   |    |       ||   |    |   |      |   |
|_______||_______||______| |_______|  |___|    |_______||___|    |___|      |___|

🐾```
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
