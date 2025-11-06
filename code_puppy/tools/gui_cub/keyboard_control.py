"""Keyboard control for desktop automation automation."""

from __future__ import annotations

try:
    import pyautogui

    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    pyautogui = None

from pydantic_ai import RunContext

from .result_types import KeyboardActionResult
from .tool_wrapper import desktop_tool


def register_keyboard_control_tools(agent):
    """Register keyboard control tools for desktop automation."""

    @agent.tool
    @desktop_tool("KEYBOARD TYPE", requires="pyautogui")
    def desktop_keyboard_type(
        context: RunContext,
        text: str,
        interval: float = 0.0,
    ) -> KeyboardActionResult:
        """
        Type text using the keyboard.

        Args:
            text: The text to type
            interval: Time delay between each keypress in seconds (0 for fast)

        Returns:
            KeyboardActionResult with success status and typed text info

        Examples:
            - desktop_keyboard_type(text="Hello, World!") - Type text quickly
            - desktop_keyboard_type(text="username@example.com", interval=0.05) - Type slowly
        """
        pyautogui.write(text, interval=interval)
        preview = text[:50] + "..." if len(text) > 50 else text
        return KeyboardActionResult(
            success=True, text_length=len(text), preview=preview
        )

    @agent.tool
    @desktop_tool("KEYBOARD PRESS", requires="pyautogui")
    def desktop_keyboard_press(
        context: RunContext,
        key: str,
        presses: int = 1,
        interval: float = 0.0,
    ) -> KeyboardActionResult:
        """
        Press a specific key or key combination.

        Args:
            key: Key to press (e.g., 'enter', 'tab', 'esc', 'a', 'ctrl', etc.)
            presses: Number of times to press the key
            interval: Time between presses in seconds

        Returns:
            KeyboardActionResult with success status and key press details

        Common keys:
            - Navigation: 'enter', 'tab', 'esc', 'space', 'backspace', 'delete'
            - Arrows: 'up', 'down', 'left', 'right'
            - Function: 'f1' through 'f12'
            - Modifiers: 'ctrl', 'alt', 'shift', 'win' (or 'command' on Mac)
            - Letters: 'a' through 'z'
            - Numbers: '0' through '9'

        Examples:
            - desktop_keyboard_press(key="enter") - Press Enter
            - desktop_keyboard_press(key="tab", presses=3) - Press Tab 3 times
            - desktop_keyboard_press(key="backspace", presses=5) - Delete 5 characters
        """
        pyautogui.press(key, presses=presses, interval=interval)
        return KeyboardActionResult(success=True, key=key, presses=presses)

    @agent.tool
    @desktop_tool("KEYBOARD HOTKEY", requires="pyautogui")
    def desktop_keyboard_hotkey(
        context: RunContext,
        *keys: str,
    ) -> KeyboardActionResult:
        """
        Press a combination of keys simultaneously (hotkey/shortcut).

        Args:
            *keys: Keys to press together (e.g., 'ctrl', 'c' for copy)

        Returns:
            KeyboardActionResult with success status and hotkey details

        Examples:
            - desktop_keyboard_hotkey('ctrl', 'c') - Copy
            - desktop_keyboard_hotkey('ctrl', 'v') - Paste
            - desktop_keyboard_hotkey('ctrl', 'a') - Select all
            - desktop_keyboard_hotkey('ctrl', 'shift', 's') - Save As
            - desktop_keyboard_hotkey('alt', 'tab') - Switch windows
            - desktop_keyboard_hotkey('win', 'd') - Show desktop (Windows)
            - desktop_keyboard_hotkey('command', 'space') - Spotlight (Mac)
        """
        pyautogui.hotkey(*keys)
        hotkey_str = "+".join(keys)
        return KeyboardActionResult(success=True, hotkey=hotkey_str, keys=list(keys))

    @agent.tool
    @desktop_tool("KEYBOARD HOLD", requires="pyautogui", emit_success=False)
    def desktop_keyboard_hold(
        context: RunContext,
        key: str,
    ) -> KeyboardActionResult:
        """
        Hold down a key (you must release it later with desktop_keyboard_release).

        Args:
            key: Key to hold down

        Returns:
            KeyboardActionResult with success status

        WARNING: Always release held keys! Use desktop_keyboard_release.

        Examples:
            - desktop_keyboard_hold(key="shift") - Hold shift (then release it!)
            - desktop_keyboard_hold(key="ctrl") - Hold ctrl (then release it!)
        """
        pyautogui.keyDown(key)
        return KeyboardActionResult(success=True, key=key, status="held")

    @agent.tool
    @desktop_tool("KEYBOARD RELEASE", requires="pyautogui")
    def desktop_keyboard_release(
        context: RunContext,
        key: str,
    ) -> KeyboardActionResult:
        """
        Release a previously held key.

        Args:
            key: Key to release

        Returns:
            KeyboardActionResult with success status

        Examples:
            - desktop_keyboard_release(key="shift") - Release shift
            - desktop_keyboard_release(key="ctrl") - Release ctrl
        """
        pyautogui.keyUp(key)
        return KeyboardActionResult(success=True, key=key, status="released")
