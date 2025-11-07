"""Type stubs for window management operations.

Provides window focusing and bounds retrieval.
"""

from ..result_types import WindowFocusResult, WindowBoundsResult

def focus_window(
    app_name: str | None = ...,
) -> WindowFocusResult:
    """Focus (activate) a window by app name.

    Args:
        app_name: Name of application to focus (None to refocus frontmost)

    Returns:
        WindowFocusResult with success status and focused app name

    Example:
        focus_window("TextEdit")  # Focus TextEdit app
        focus_window("Safari")    # Focus Safari browser
    """
    ...

def get_active_window_bounds() -> WindowBoundsResult:
    """Get bounds of the currently active window.

    Returns:
        WindowBoundsResult with window position and size
    """
    ...

# Backwards compatibility aliases
desktop_focus_window = focus_window
desktop_get_active_window = get_active_window_bounds
