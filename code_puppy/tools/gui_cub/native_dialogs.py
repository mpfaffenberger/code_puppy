"""Thread-safe native dialog implementations for macOS and Windows.

These replace pyautogui's dialog functions which use tkinter and crash
on macOS when not called from the main thread.
"""

from __future__ import annotations

import subprocess

from .platform import IS_MACOS, IS_WINDOWS


def _escape_applescript_string(text: str) -> str:
    """Escape special characters for AppleScript string literals.

    Args:
        text: Raw string to escape

    Returns:
        Escaped string safe for AppleScript
    """
    # Escape backslashes first, then quotes
    return text.replace("\\", "\\\\").replace('"', '\\"')


def native_alert(
    text: str,
    title: str = "Desktop Automation Alert",
    timeout: int = 0,
) -> str:
    """Show a native alert dialog (thread-safe).

    Args:
        text: Message to display
        title: Dialog title
        timeout: Timeout in milliseconds (0 = no timeout)

    Returns:
        Button clicked (typically "OK")

    Raises:
        RuntimeError: If dialog fails to display
    """
    if IS_MACOS:
        # Use osascript for native macOS dialog
        # AppleScript's display dialog is thread-safe!
        escaped_text = _escape_applescript_string(text)
        escaped_title = _escape_applescript_string(title)

        # Build AppleScript command
        timeout_clause = ""
        if timeout > 0:
            # Convert milliseconds to seconds
            timeout_seconds = timeout / 1000.0
            timeout_clause = f" giving up after {timeout_seconds}"

        script = f'display dialog "{escaped_text}" with title "{escaped_title}" buttons {{"OK"}} default button "OK"{timeout_clause}'

        try:
            # Calculate reasonable subprocess timeout (slightly longer than dialog timeout)
            subprocess_timeout = None
            if timeout > 0:
                subprocess_timeout = max(10, (timeout / 1000.0) + 2)

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=subprocess_timeout,
            )

            if result.returncode == 0:
                # Check if dialog timed out or user clicked
                output = result.stdout.strip()
                if "gave up:true" in output:
                    return "OK"  # Dialog timed out
                else:
                    return "OK"  # User clicked OK
            else:
                # User cancelled or error
                return "OK"  # Return OK anyway for compatibility

        except subprocess.TimeoutExpired:
            return "OK"  # Subprocess timeout (rare)
        except Exception as e:
            raise RuntimeError(f"Failed to show alert dialog: {e}")

    elif IS_WINDOWS:
        # On Windows, pyautogui's tkinter dialogs work fine
        # (Windows doesn't have the main thread restriction)
        try:
            import pyautogui

            return pyautogui.alert(text=text, title=title, timeout=timeout) or "OK"
        except Exception as e:
            raise RuntimeError(f"Failed to show alert dialog: {e}")

    else:
        raise RuntimeError("Dialogs are only supported on macOS and Windows")


def native_confirm(
    text: str,
    title: str = "Confirm",
    buttons: list[str] | None = None,
) -> str | None:
    """Show a native confirmation dialog (thread-safe).

    Args:
        text: Message to display
        title: Dialog title
        buttons: List of button labels (default: ["OK", "Cancel"])

    Returns:
        Label of clicked button, or None if cancelled

    Raises:
        RuntimeError: If dialog fails to display
    """
    if buttons is None:
        buttons = ["OK", "Cancel"]

    if IS_MACOS:
        escaped_text = _escape_applescript_string(text)
        escaped_title = _escape_applescript_string(title)

        # Build button list for AppleScript
        # Note: AppleScript buttons are in reverse order (rightmost first)
        escaped_buttons = [
            f'"{_escape_applescript_string(b)}"' for b in reversed(buttons)
        ]
        buttons_clause = "{" + ", ".join(escaped_buttons) + "}"

        # Default button is the first in our list (last in AppleScript order)
        default_button = f'"{_escape_applescript_string(buttons[0])}"'

        script = f'display dialog "{escaped_text}" with title "{escaped_title}" buttons {buttons_clause} default button {default_button}'

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60,  # Generous timeout for user interaction
            )

            if result.returncode == 0:
                # Parse the button from output like "button returned:OK, gave up:false"
                output = result.stdout.strip()
                if "button returned:" in output:
                    # Extract button text between "button returned:" and next comma (or end)
                    button_part = output.split("button returned:")[1]
                    if "," in button_part:
                        clicked_button = button_part.split(",")[0].strip()
                    else:
                        clicked_button = button_part.strip()
                    return clicked_button if clicked_button else buttons[0]
                else:
                    # Fallback - return first button
                    return buttons[0]
            else:
                # User cancelled (exit code 1)
                return None

        except subprocess.TimeoutExpired:
            # Subprocess timed out - treat as cancellation
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to show confirm dialog: {e}")

    elif IS_WINDOWS:
        try:
            import pyautogui

            if buttons:
                return pyautogui.confirm(text=text, title=title, buttons=buttons)
            else:
                return pyautogui.confirm(text=text, title=title)
        except Exception as e:
            raise RuntimeError(f"Failed to show confirm dialog: {e}")

    else:
        raise RuntimeError("Dialogs are only supported on macOS and Windows")


def native_prompt(
    text: str,
    title: str = "Input",
    default: str = "",
) -> str | None:
    """Show a native text input prompt dialog (thread-safe).

    Args:
        text: Prompt message
        title: Dialog title
        default: Default text in input field

    Returns:
        User input string, or None if cancelled

    Raises:
        RuntimeError: If dialog fails to display
    """
    if IS_MACOS:
        escaped_text = _escape_applescript_string(text)
        escaped_title = _escape_applescript_string(title)
        escaped_default = _escape_applescript_string(default)

        script = f'display dialog "{escaped_text}" with title "{escaped_title}" default answer "{escaped_default}" buttons {{"OK", "Cancel"}} default button "OK"'

        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=60,  # Generous timeout
            )

            if result.returncode == 0:
                # Parse the input from output like "button returned:OK, text returned:hello"
                output = result.stdout.strip()
                if "text returned:" in output:
                    # Extract text after "text returned:"
                    user_input = output.split("text returned:")[1].strip()
                    return user_input
                else:
                    # No text returned - return empty string
                    return ""
            else:
                # User cancelled (exit code 1)
                return None

        except subprocess.TimeoutExpired:
            # Subprocess timed out - treat as cancellation
            return None
        except Exception as e:
            raise RuntimeError(f"Failed to show prompt dialog: {e}")

    elif IS_WINDOWS:
        try:
            import pyautogui

            return pyautogui.prompt(text=text, title=title, default=default)
        except Exception as e:
            raise RuntimeError(f"Failed to show prompt dialog: {e}")

    else:
        raise RuntimeError("Dialogs are only supported on macOS and Windows")
