"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-08-29"
MOTD_MESSAGE = """```
# 🐶🎉🚀 WOOF WOOF BARK BARK! AUGUST 29th! 🚀🎉🐶
# 🐕‍🦺 PUPPY POWER RELEASE 0.0.128 TO THE MOON! 🚀🌙🐕

🎉🎊🚀 MEGA ULTRA SUPER DUPER PUPPY FEATURE ALERT! 🚀🎊🎉
🐶🤖🐕‍🦺 CREATE YOUR OWN AGENT!! By the legendary Andrew Tilson!!! 🏆🐶🚀

🐾 Type `/agents` to list all your puppy friends! 🐕‍🦺🐶
🚀 Use `/agents agent-creator` to birth a new digital puppy! 🐣🤖🐶
🎨 Use the agent creator to craft your own coding companion:
    🏗️ Create a puppy_architect that plans features and saves them in `.md` files! 📋🐕
    🎯 Make a test_puppy that writes unit tests like a good boy! 🧪🐶
    🎭 Build a refactor_pup that cleans up messy code! 🧹🐕‍🦺
🔄 Use `/agents puppy_architect` to switch to your new digital friend! 🐶💝
🏠 Use `/agents code-puppy` to come back home to default mode! 🏡🐕


🎾 ADDITIONAL NEW PUPPY TRICKS (Features):
🐶🚀 Adds plugin hooks for `edit_file`, `delete_file`, `run_shell_command` (SO FETCH!) 🦴
🐕 Adds a new config option for truncation strategy (Smart puppy!) 🧠🐶
🎾 Renamed summarization_threshold to truncation threshold (Fancy words!) 📚🐕‍🦺
🚀 Added emergency filtration to compaction where enormous messages (>50000 tokens) are clipped (Big bites!) 🍖🐕
⚖️ Enforced compaction threshold cannot be less than 0.8 (Good puppy boundaries!) 🐶🚧
🛡️ `protected_tokens` cannot be greater than 75% of model context (Safety first, puppy!) 🦺🐕‍🦺

🐛🔧 Flea Extermination Squad:
🚀 Fixed flea that caused stack trace in non-interactive mode (Squished that bug!) 🐾💥
🐛 Fixed a flea where sometimes summarization failed due to tool_call isolates (No more itchy bugs!) 🚿🐶

🚀🐶 WOOF WOOF! Happy coding, human! 🐕‍🦺🎾🦴
🐾 Remember: Good code is like a well-trained puppy - clean, reliable, and brings joy! 🐶💖
``
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
