"""
🐶 MOTD (Message of the Day) feature for code-puppy! 🐕
Stores seen versions in ~/.code_puppy/motd.txt - woof woof! 🐾
"""

import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

MOTD_VERSION = "2025-08-22"
MOTD_MESSAGE = """🐕‍🦺
🐾```
# 🐶🎉🐕 WOOF WOOF! AUGUST 22ND FLEA COLLAR! 🐕🎉🐶

**Fleas flicked**:

 * 🐶 Message history compaction should now be much more graceful
    * 🐶 The agent can continue its task even if compaction occurs mid-tool-call
    * 🐶 There is now a configurable buffer of token context (the most recent `50,000` by default)
       that is protected from compaction.
    * 🐶 There is now a configurable `compaction threshold` which defaults to `0.85`
        * 🐶 The compaction will trigger once the context length exceeds this threshold

**New features**:
 * 🐶 Save your session with the new command `/dump_context <session_name>`
    * 🐶 Auto-naming and auto-save will come soon
 * 🐶 Load your previous session with `/load_session <session_name>`
 * 🐶 You can now add a custom header block in your MCP JSON, like such:
 ```json
 "jira": {
    "type": "http",
    "url": "https://mcp-jira.stage.walmart.com/mcp/",
    "headers": {
      "Authorization": "Bearer <token>"
    },
    "walmart_internal": true
  }
 ```

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
