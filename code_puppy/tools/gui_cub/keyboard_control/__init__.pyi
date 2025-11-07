"""Type stubs for keyboard control operations.

Provides keyboard typing, key presses, and hotkeys.
"""

from pydantic_ai import RunContext
from ..result_types import KeyboardActionResult

def desktop_keyboard_type(
    context: RunContext,
    text: str,
    interval: float = ...,
) -> KeyboardActionResult:
    """Type text using keyboard.

    Args:
        context: Agent context
        text: Text to type
        interval: Delay between keystrokes in seconds

    Returns:
        KeyboardActionResult with success status
    """
    ...

def desktop_keyboard_press(
    context: RunContext,
    key: str,
    presses: int = ...,
    interval: float = ...,
) -> KeyboardActionResult:
    """Press a key.

    Args:
        context: Agent context
        key: Key name (e.g., 'enter', 'tab', 'escape')
        presses: Number of times to press
        interval: Delay between presses

    Returns:
        KeyboardActionResult with success status
    """
    ...

def desktop_keyboard_hotkey(
    context: RunContext,
    *keys: str,
) -> KeyboardActionResult:
    """Press keyboard hotkey combination.

    Args:
        context: Agent context
        *keys: Keys to press together (e.g., 'cmd', 'c' for copy)

    Returns:
        KeyboardActionResult with success status

    Example:
        desktop_keyboard_hotkey(ctx, 'cmd', 'c')  # Copy on macOS
        desktop_keyboard_hotkey(ctx, 'ctrl', 'v')  # Paste on Windows
    """
    ...

def desktop_keyboard_hold(
    context: RunContext,
    key: str,
) -> KeyboardActionResult:
    """Hold down a key.

    Args:
        context: Agent context
        key: Key to hold

    Returns:
        KeyboardActionResult with success status

    Note:
        Must be followed by desktop_keyboard_release()
    """
    ...

def desktop_keyboard_release(
    context: RunContext,
    key: str,
) -> KeyboardActionResult:
    """Release a held key.

    Args:
        context: Agent context
        key: Key to release

    Returns:
        KeyboardActionResult with success status
    """
    ...
