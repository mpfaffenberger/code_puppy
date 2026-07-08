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


def _is_windows() -> bool:
    """Check if we're running on Windows."""
    import platform

    return platform.system() == "Windows"


def get_cancel_agent_key() -> str:
    """Get the configured cancel agent key from config.

    The default is "ctrl+c" on every platform. Ctrl+C is a pure
    keybinding everywhere: the raw-mode stdin reader receives it as a
    plain ``\\x03`` byte handled by the key listener (buffer-first:
    composing input absorbs the press; an empty prompt cancels). On
    Windows, Ctrl+C-with-a-selection is additionally intercepted by the
    terminal itself as the COPY gesture, so copying agent output can't
    cancel the run.

    Returns:
        The key name (e.g., "ctrl+c", "ctrl+k") from config,
        or the default if not configured.
    """
    from code_puppy.config import get_value

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


def sigint_fallback_cancels() -> bool:
    """Should an out-of-band SIGINT cancel the running agent?

    Ctrl+C is a *pure keybinding* on every platform: whenever a raw-mode
    reader owns stdin (the key listener disables the tty's INTR char on
    POSIX; Windows strips ``ENABLE_PROCESSED_INPUT`` session-wide), ^C
    arrives as a raw ``\\x03`` byte and never becomes a signal. The key
    listener ALWAYS owns cancellation.

    SIGINT can still arrive out-of-band: ``kill -INT``, a piped stdin
    (no TTY, no listener), or the brief cooked-mode gaps between raw
    readers on POSIX. When the cancel key IS ctrl+c, that fallback
    SIGINT should cancel the run — the user pressed the cancel gesture;
    delivery mechanism is an implementation detail. When cancel is
    remapped (ctrl+k/ctrl+q), a SIGINT is NOT the cancel gesture and
    only earns a hint.

    Always False on Windows: with the console clamp active SIGINT only
    fires when the console mode has REGRESSED (something re-enabled
    processed input), and cancelling then would be wrong — the graceful
    handler instead repairs the console via reset_windows_terminal_full()
    and re-clamps, restoring pure-keybinding delivery.

    Returns:
        True if a fallback SIGINT should cancel the agent run,
        False if it should only hint at the real cancel key.
    """
    return get_cancel_agent_key() == "ctrl+c" and not _is_windows()


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
