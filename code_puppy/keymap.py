"""Keymap configuration for code-puppy.

This module handles configurable keyboard shortcuts, starting with the
cancel_agent_key feature that allows users to override Ctrl+C with a
different key for cancelling agent tasks.
"""

# Character codes for Ctrl+letter combinations (Ctrl+A = 0x01, Ctrl+Z = 0x1A)
KEY_CODES: dict[str, str] = {
    "ctrl+a": "\x01",
    "ctrl+b": "\x02",
    "ctrl+c": "\x03",
    "ctrl+d": "\x04",
    "ctrl+e": "\x05",
    "ctrl+f": "\x06",
    "ctrl+g": "\x07",
    "ctrl+h": "\x08",
    "ctrl+i": "\x09",
    "ctrl+j": "\x0a",
    "ctrl+k": "\x0b",
    "ctrl+l": "\x0c",
    "ctrl+m": "\x0d",
    "ctrl+n": "\x0e",
    "ctrl+o": "\x0f",
    "ctrl+p": "\x10",
    "ctrl+q": "\x11",
    "ctrl+r": "\x12",
    "ctrl+s": "\x13",
    "ctrl+t": "\x14",
    "ctrl+u": "\x15",
    "ctrl+v": "\x16",
    "ctrl+w": "\x17",
    "ctrl+x": "\x18",
    "ctrl+y": "\x19",
    "ctrl+z": "\x1a",
    "escape": "\x1b",
}

# Valid keys for cancel_agent_key configuration
# NOTE: "escape" is excluded because it conflicts with ANSI escape sequences
# (arrow keys, F-keys, etc. all start with \x1b)
VALID_CANCEL_KEYS: set[str] = {
    "ctrl+c",
    "ctrl+k",
    "ctrl+q",
}

DEFAULT_CANCEL_AGENT_KEY: str = "ctrl+c"


class KeymapError(Exception):
    """Exception raised for keymap configuration errors."""


def get_cancel_agent_key() -> str:
    """Get the configured cancel agent key from config.

    On Windows when launched via uvx, this automatically returns "ctrl+k"
    to work around uvx capturing Ctrl+C before it reaches Python.

    Returns:
        The key name (e.g., "ctrl+c", "ctrl+k") from config,
        or the default if not configured.
    """
    from code_puppy.config import get_value
    from code_puppy.uvx_detection import should_use_alternate_cancel_key

    # On Windows + uvx, force ctrl+k to bypass uvx's SIGINT capture
    if should_use_alternate_cancel_key():
        return "ctrl+k"

    key = get_value("cancel_agent_key")
    if key is None or key.strip() == "":
        return DEFAULT_CANCEL_AGENT_KEY
    return key.strip().lower()


def validate_cancel_agent_key() -> None:
    """Validate the configured cancel agent key.

    Raises:
        KeymapError: If the configured key is invalid.
    """
    key = get_cancel_agent_key()
    if key not in VALID_CANCEL_KEYS:
        valid_keys_str = ", ".join(sorted(VALID_CANCEL_KEYS))
        raise KeymapError(
            f"Invalid cancel_agent_key '{key}' in puppy.cfg. "
            f"Valid options are: {valid_keys_str}"
        )


def cancel_agent_uses_signal() -> bool:
    """Check if the cancel agent key uses SIGINT (Ctrl+C).

    Returns:
        True if the cancel key is ctrl+c (uses SIGINT handler),
        False if it uses keyboard listener approach.
    """
    return get_cancel_agent_key() == "ctrl+c"


def get_cancel_agent_char_code() -> str:
    """Get the character code for the cancel agent key.

    Returns:
        The character code (e.g., "\x0b" for ctrl+k).

    Raises:
        KeymapError: If the key is not found in KEY_CODES.
    """
    key = get_cancel_agent_key()
    if key not in KEY_CODES:
        raise KeymapError(f"Unknown key '{key}' - no character code mapping found.")
    return KEY_CODES[key]


def get_cancel_agent_display_name() -> str:
    """Get a human-readable display name for the cancel agent key.

    Returns:
        A formatted display name like "Ctrl+K".
    """
    key = get_cancel_agent_key()
    if key.startswith("ctrl+"):
        letter = key.split("+")[1].upper()
        return f"Ctrl+{letter}"
    return key.upper()
