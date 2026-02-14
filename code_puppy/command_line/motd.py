"""
🐶 MOTD (Message of the Day) feature for code-puppy!
Stores seen versions in XDG_CONFIG_HOME/code_puppy/motd.txt
"""

import logging
import os

from code_puppy.config import CONFIG_DIR
from code_puppy.messaging import emit_info

logger = logging.getLogger(__name__)

MOTD_VERSION = "2026-02-14"
MOTD_MESSAGE = """🐕‍🦺
🐾```
# 🐶 Welcome to Code Puppy! 🐕
Your friendly open-source AI code agent.
Ready to help you write, refactor, and ship code faster! 🚀

Type /help to see available commands.
```
"""
MOTD_TRACK_FILE = os.path.join(CONFIG_DIR, "motd.txt")


def _read_seen_versions() -> set[str]:
    """Read the set of previously seen MOTD versions from the track file."""
    if not os.path.exists(MOTD_TRACK_FILE):
        return set()
    with open(MOTD_TRACK_FILE, "r") as f:
        return {line.strip() for line in f if line.strip()}


def get_motd_content() -> tuple[str, str]:
    """Get MOTD content, checking plugins first.

    Returns:
        Tuple of (message, version) - either from plugin or built-in.
    """
    try:
        from code_puppy.callbacks import on_get_motd

        results = on_get_motd()
        for result in reversed(results):
            if result is not None and isinstance(result, tuple) and len(result) == 2:
                return result
    except Exception:
        logger.debug("Failed to load MOTD from plugins, using built-in", exc_info=True)

    return (MOTD_MESSAGE, MOTD_VERSION)


def has_seen_motd(version: str) -> bool:
    """Check whether the given MOTD version has already been seen."""
    return version in _read_seen_versions()


def mark_motd_seen(version: str) -> None:
    """Mark an MOTD version as seen, appending it to the track file."""
    os.makedirs(os.path.dirname(MOTD_TRACK_FILE), exist_ok=True)

    if version not in _read_seen_versions():
        with open(MOTD_TRACK_FILE, "a") as f:
            f.write(f"{version}\n")


def print_motd(
    console=None, force: bool = False
) -> bool:
    """Print the message of the day to the user.

    Args:
        console: Deprecated - ignored. Kept for backward compatibility.
        force: Whether to force printing even if the MOTD has been seen.

    Returns:
        True if the MOTD was printed, False otherwise.
    """
    message, version = get_motd_content()
    if force or not has_seen_motd(version):
        from rich.markdown import Markdown

        emit_info(Markdown(message))
        mark_motd_seen(version)
        return True
    return False
