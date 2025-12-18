"""Wrapper utilities to reduce boilerplate in desktop automation tool definitions."""

from __future__ import annotations

import functools
from typing import Any, Callable

from rich.text import Text

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .constants import (
    ERROR_ATOMACOS_MISSING,
    ERROR_FAILSAFE_TRIGGERED,
    ERROR_PILLOW_MISSING,
    ERROR_PYAUTOGUI_MISSING,
    ERROR_WINDOWS_AUTOMATION_MISSING,
)


def check_library_available(library: str) -> tuple[bool, str | None]:
    """Check if a required library is available.

    Args:
        library: Library name to check (pyautogui, pillow, atomacos, windows)

    Returns:
        Tuple of (is_available, error_message)
    """
    if library == "pyautogui":
        try:
            import pyautogui  # noqa: F401 - testing availability

            return True, None
        except ImportError:
            return False, ERROR_PYAUTOGUI_MISSING

    elif library == "pillow":
        try:
            from PIL import Image  # noqa: F401 - testing availability

            return True, None
        except ImportError:
            return False, ERROR_PILLOW_MISSING

    elif library == "atomacos":
        try:
            import atomacos  # noqa: F401 - testing availability

            return True, None
        except ImportError:
            return False, ERROR_ATOMACOS_MISSING

    elif library == "windows":
        try:
            import win32gui  # noqa: F401 - testing availability
            from pywinauto import Application  # noqa: F401 - testing availability

            return True, None
        except ImportError:
            return False, ERROR_WINDOWS_AUTOMATION_MISSING

    return False, f"Unknown library: {library}"


# Emoji mapping for different tool types
TOOL_EMOJIS = {
    # Mouse operations
    "MOUSE MOVE": "🖱️",
    "MOUSE CLICK": "🖱️",
    "MOUSE DRAG": "🖱️",
    "MOUSE SCROLL": "🖱️",
    "MOUSE GET POSITION": "🖱️",
    # Keyboard operations
    "KEYBOARD TYPE": "⌨️",
    "KEYBOARD PRESS": "⌨️",
    "KEYBOARD HOTKEY": "⌨️",
    "KEYBOARD HOLD": "⌨️",
    "KEYBOARD RELEASE": "⌨️",
    # Keyboard shortcuts
    "COPY": "📋",
    "PASTE": "📋",
    "CUT": "✂️",
    "SELECT ALL": "🔤",
    "SAVE": "💾",
    "UNDO": "↩️",
    "REDO": "↪️",
    "FIND": "🔍",
    "NEW": "📄",
    "OPEN": "📂",
    "CLOSE": "❌",
    "QUIT": "🚪",
    # Screen/Visual
    "SCREENSHOT": "📸",
    "DESKTOP SCREENSHOT ANALYZE": "👁️",
    "OCR EXTRACT TEXT": "🔤",
    "OCR FIND TEXT": "🔍",
    "OCR VERIFY TEXT": "✅",
    # Window/Focus
    "FOCUS WINDOW": "🪟",
    "SLEEP": "💤",
    "ALERT": "⚠️",
    "CONFIRM": "❓",
    "PROMPT": "💬",
    # Accessibility
    "FIND ACCESSIBLE ELEMENT": "🔍",
    "LIST ACCESSIBLE ELEMENTS": "📋",
    "CLICK ACCESSIBLE ELEMENT": "👆",
    # Windows automation
    "WINDOWS FOCUS": "🪟",
    "WINDOWS FIND": "🔍",
    "WINDOWS CLICK": "👆",
    # Click debugging
    "HIGHLIGHT CLICK TARGET": "🎯",
    "VERIFY COORDINATES": "✅",
    "CLICK WITH VERIFICATION": "👆",
}


def desktop_tool(
    tool_name: str,
    requires: str | list[str] | None = None,
    emit_start: bool = True,
    emit_success: bool = True,
    emit_errors: bool = True,
) -> Callable:
    """Decorator for desktop automation tools that handles common patterns.

    This decorator:
    - Checks required libraries are available
    - Generates group IDs for logging
    - Emits start/success/error messages
    - Handles FailSafeException from pyautogui
    - Provides consistent error handling

    Args:
        tool_name: Display name for the tool (e.g., "MOUSE MOVE")
        requires: Library or list of libraries required (pyautogui, pillow, atomacos, windows)
        emit_start: Whether to emit start message
        emit_success: Whether to emit success message
        emit_errors: Whether to emit error messages

    Returns:
        Decorated function with common desktop automation tool patterns

    Example:
        @desktop_tool("MOUSE MOVE", requires="pyautogui")
        def desktop_mouse_move(x: int, y: int) -> MouseActionResult:
            pyautogui.moveTo(x, y)
            return MouseActionResult(success=True, x=x, y=y)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> dict[str, Any]:
            # Check required libraries
            if requires:
                libs = [requires] if isinstance(requires, str) else requires
                for lib in libs:
                    available, error_msg = check_library_available(lib)
                    if not available:
                        if emit_errors:
                            group_id = generate_group_id(func.__name__, "error")
                            emit_error(
                                f"[red]{error_msg}[/red]", message_group=group_id
                            )
                        return {"success": False, "error": error_msg}

            # Generate group ID for this execution
            # Use first few args for context if available
            context_args = []
            for arg in args[1:3]:  # Skip 'context' first arg, take next 2
                if isinstance(arg, (str, int, float)):
                    context_args.append(str(arg)[:30])

            # Also check kwargs for common identifying parameters
            for key in ["title", "text", "question", "app_name", "window_title"]:
                if key in kwargs and kwargs[key]:
                    val = str(kwargs[key])[:30]
                    if val not in context_args:
                        context_args.append(val)

            group_id = generate_group_id(func.__name__, "_".join(context_args))

            # Emit start message
            if emit_start:
                # Build a nice display message from kwargs
                # Filter out 'context' parameter (internal pydantic-ai)
                display_params = {
                    k: v
                    for k, v in kwargs.items()
                    if k != "context" and not k.startswith("_")
                }

                if display_params:
                    # Show up to 5 most important parameters
                    param_items = list(display_params.items())[:5]
                    param_str = " ".join(f"{k}={repr(v)[:50]}" for k, v in param_items)
                else:
                    param_str = ""

                # Get appropriate emoji for this tool type
                emoji = TOOL_EMOJIS.get(
                    tool_name.upper(), "🐻"
                )  # Default to bear if not found

                if param_str:
                    emit_info(
                        f"[bold cyan]{tool_name.upper()}[/bold cyan] {emoji}  {param_str}",
                        message_group=group_id,
                    )
                else:
                    emit_info(
                        f"[bold cyan]{tool_name.upper()}[/bold cyan] {emoji}",
                        message_group=group_id,
                    )

            try:
                # Execute the actual function
                result = func(*args, **kwargs)

                # Emit success message if result indicates success
                if emit_success and isinstance(result, dict) and result.get("success"):
                    # Try to build a meaningful success message
                    success_msg = "Operation completed successfully"

                    # Customize based on result contents
                    if "x" in result and "y" in result:
                        success_msg = f"Position: ({result['x']}, {result['y']})"
                    elif "element" in result:
                        success_msg = f"Element: {result['element']}"
                    elif "focused_app" in result:
                        success_msg = f"Focused: {result['focused_app']}"
                    elif "answer" in result:
                        success_msg = f"Answer: {result['answer'][:100]}"

                    emit_info(
                        Text.from_markup(f"[green]{success_msg}[/green]"),
                        message_group=group_id,
                    )

                return result

            except Exception as e:
                # Handle FailSafeException specially
                error_class = type(e).__name__
                if error_class == "FailSafeException":
                    if emit_errors:
                        emit_warning(
                            Text.from_markup(
                                f"[yellow]{ERROR_FAILSAFE_TRIGGERED}[/yellow]"
                            ),
                            message_group=group_id,
                        )
                    return {"success": False, "error": ERROR_FAILSAFE_TRIGGERED}

                # General exception handling
                error_msg = str(e)
                if emit_errors:
                    emit_error(
                        Text.from_markup(f"[red]{tool_name} failed: {error_msg}[/red]"),
                        message_group=group_id,
                    )
                return {"success": False, "error": error_msg}

        return wrapper

    return decorator
