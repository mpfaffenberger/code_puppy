"""Windows UI Automation support for desktop automation.

Provides Windows-specific automation tools using:
- pywinauto for UI element detection and interaction
- pywin32 for window management
- Windows UI Automation API
"""

from __future__ import annotations

import sys
from typing import Any

# Check if we're on Windows and libraries are available
if sys.platform == "win32":
    try:
        import win32api
        import win32con
        import win32gui
        import win32process
        from pywinauto import Application
        from pywinauto.findwindows import find_elements

        WINDOWS_AUTOMATION_AVAILABLE = True
    except ImportError:
        WINDOWS_AUTOMATION_AVAILABLE = False
        win32api = None
        win32gui = None
        win32con = None
        Application = None
else:
    WINDOWS_AUTOMATION_AVAILABLE = False
    win32gui = None
    win32con = None
    Application = None


from ..constants import ERROR_ELEMENT_NOT_FOUND, ERROR_WINDOWS_AUTOMATION_MISSING
from ..performance_monitor import get_monitor
from ..accessibility.element_list import _compact_element_list_result
from ..result_types import (
    ElementClickResult,
    ElementInfo,
    ElementListResult,
    ElementSearchResult,
)


def list_windows(include_minimized: bool = False) -> list[dict[str, Any]]:
    """
    List windows on Windows.

    Args:
        include_minimized: If True, include minimized windows with minimized=True flag

    Returns:
        List of window dictionaries with hwnd, title, class_name, pid, and minimized status
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return []

    def callback(hwnd, windows):
        # Check if minimized
        is_minimized = win32gui.IsIconic(hwnd)

        # Include window if visible OR if minimized and we want minimized windows
        if win32gui.IsWindowVisible(hwnd) or (is_minimized and include_minimized):
            title = win32gui.GetWindowText(hwnd)
            if title:  # Only include windows with titles
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    windows.append(
                        {
                            "hwnd": hwnd,
                            "title": title,
                            "class_name": win32gui.GetClassName(hwnd),
                            "pid": pid,
                            "minimized": is_minimized,
                        }
                    )
                except Exception:
                    pass

    windows = []
    win32gui.EnumWindows(callback, windows)
    return windows


def focus_window(
    window_title: str | None = None,
    class_name: str | None = None,
    hwnd: int | None = None,
) -> bool:
    """
    Focus a window on Windows.

    Args:
        window_title: Window title (exact or partial match, case-insensitive)
        class_name: Window class name
        hwnd: Window handle (direct)

    Returns:
        True if successful
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return False

    try:
        target_hwnd = None
        
        # If hwnd provided directly
        if hwnd:
            target_hwnd = hwnd
        # Find by title
        elif window_title:
            # Try exact match first (case-sensitive)
            target_hwnd = win32gui.FindWindow(None, window_title)

            # If not found, try partial case-insensitive match
            if not target_hwnd:
                windows = list_windows(include_minimized=True)
                search_term = window_title.lower()
                for window in windows:
                    if search_term in window["title"].lower():
                        target_hwnd = window["hwnd"]
                        break
        # Find by class name
        elif class_name:
            target_hwnd = win32gui.FindWindow(class_name, None)
        else:
            return False

        if not target_hwnd:
            return False
            
        # Restore if minimized
        if win32gui.IsIconic(target_hwnd):
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

        # Bring to foreground
        win32gui.SetForegroundWindow(target_hwnd)
        return True

    except Exception as e:
        # Log the error for debugging but still return False
        # This helps diagnose issues in testing
        import sys
        print(f"focus_window error: {e}", file=sys.stderr)
        return False


def find_element(
    title: str | None = None,
    class_name: str | None = None,
    control_type: str | None = None,
    auto_id: str | None = None,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.65,
    early_stop_threshold: float = 0.85,
) -> ElementSearchResult:
    """
    Find UI element using Windows UI Automation.

    OPTIMIZED: Now includes performance monitoring and early-stop logic.

    Args:
        title: Element title/name
        class_name: Windows class name
        control_type: Control type (Button, Edit, MenuItem, etc.)
        auto_id: Automation ID
        fuzzy: Enable fuzzy matching (uses rapidfuzz)
        fuzzy_threshold: Minimum similarity score (default: 0.65)
        early_stop_threshold: Score threshold for early-stop optimization (default: 0.85)

    Returns:
        ElementSearchResult with element info including position
    """
    monitor = get_monitor()

    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementSearchResult(
            success=False, found=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
        )

    try:
        # Connect to active window
        app = Application(backend="uia").connect(active_only=True)
        window = app.top_window()

        # Build search criteria
        criteria = {}
        if title:
            criteria["title"] = title
        if class_name:
            criteria["class_name"] = class_name
        if control_type:
            criteria["control_type"] = control_type
        if auto_id:
            criteria["auto_id"] = auto_id

        # Find element (exact criteria first)
        element = window.child_window(**criteria)

        if element.exists():
            rect = element.rectangle()
            info = ElementInfo(
                x=rect.left,
                y=rect.top,
                width=rect.width(),
                height=rect.height(),
                center_x=rect.mid_point().x,
                center_y=rect.mid_point().y,
                title=element.element_info.name,
                control_type=element.element_info.control_type,
                class_name=element.element_info.class_name,
                auto_id=element.element_info.automation_id,
            )
            return ElementSearchResult(
                success=True, found=True, count=1, matches=[info], best_match=info
            )

        # Fuzzy fallback on title if requested
        if fuzzy and title:
            with monitor.measure("find_element_fuzzy_search"):
                from ..fuzzy_matching import similarity_score

                elements = find_elements(title_re=".*")  # enumerate
                best = None
                best_score = 0.0
                for el in elements:
                    name = getattr(el, "name", "") or ""
                    score = similarity_score(title, name)
                    if score >= fuzzy_threshold and score > best_score:
                        best = el
                        best_score = score
                        # OPTIMIZATION: Early stop on confident match
                        if score > early_stop_threshold:
                            monitor.record_early_stop()
                            break

                if best_score > 0 and best_score <= early_stop_threshold:
                    monitor.record_full_search()

                if best:
                    rect = best.rectangle
                    info = ElementInfo(
                        x=rect.left,
                        y=rect.top,
                        width=rect.width(),
                        height=rect.height(),
                        center_x=rect.mid_point().x,
                        center_y=rect.mid_point().y,
                        title=best.name,
                        control_type=best.control_type,
                        class_name=best.class_name,
                        auto_id=best.automation_id,
                    )
                    return ElementSearchResult(
                        success=True,
                        found=True,
                        count=1,
                        matches=[info],
                        best_match=info,
                    )

    except Exception:
        pass

    return ElementSearchResult(success=True, found=False)


def click_element(
    title: str | None = None,
    class_name: str | None = None,
    control_type: str | None = None,
    auto_id: str | None = None,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.7,
) -> ElementClickResult:
    """
    Find and click element on Windows.

    Args:
        title: Element title/name
        class_name: Windows class name
        control_type: Control type
        auto_id: Automation ID

    Returns:
        ElementClickResult with success status
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementClickResult(success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING)

    # Find element (support fuzzy for title)
    result = find_element(
        title=title,
        class_name=class_name,
        control_type=control_type,
        auto_id=auto_id,
        fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold,
    )

    if not result.found:
        return ElementClickResult(success=False, error=ERROR_ELEMENT_NOT_FOUND)

    # Try to click using pywinauto directly
    try:
        app = Application(backend="uia").connect(active_only=True)
        window = app.top_window()

        criteria = {}
        # Prefer resolved best_match title if fuzzy found; otherwise use provided title
        effective_title = (
            result.best_match.title
            if result.best_match and result.best_match.title
            else title
        )
        if effective_title:
            criteria["title"] = effective_title
        if class_name:
            criteria["class_name"] = class_name
        if control_type:
            criteria["control_type"] = control_type
        if auto_id:
            criteria["auto_id"] = auto_id

        element = window.child_window(**criteria)
        element.click_input()

        return ElementClickResult(
            success=True,
            clicked=True,
            method="native_click",
            element=result.best_match.title if result.best_match else None,
        )
    except Exception:
        pass

    # Fallback to coordinate click
    if result.best_match and result.best_match.center_x and result.best_match.center_y:
        try:
            import pyautogui

            pyautogui.click(result.best_match.center_x, result.best_match.center_y)
            return ElementClickResult(
                success=True,
                clicked=True,
                method="mouse_click",
                x=result.best_match.center_x,
                y=result.best_match.center_y,
            )
        except Exception as e:
            return ElementClickResult(success=False, error=str(e))

    return ElementClickResult(success=False, error="Could not click element")


def list_elements_in_window() -> ElementListResult:
    """
    List all UI elements in active window.

    OPTIMIZED: Now includes performance monitoring.

    Returns:
        ElementListResult with element tree
    """
    monitor = get_monitor()

    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementListResult(success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING)

    try:
        app = Application(backend="uia").connect(active_only=True)
        window = app.top_window()

        elements = []
        by_type = {}

        def traverse(element, depth=0):
            if depth > 5:  # Max depth to avoid recursion hell
                return

            try:
                info = element.element_info
                
                # Get coordinates
                try:
                    rect = element.rectangle()
                    x = rect.left
                    y = rect.top
                    width = rect.width()
                    height = rect.height()
                    center_x = rect.mid_point().x
                    center_y = rect.mid_point().y
                except Exception:
                    # Fallback if coordinates unavailable
                    x = y = width = height = center_x = center_y = None
                
                elem_data = {
                    "control_type": info.control_type,
                    "title": info.name,
                    "class_name": info.class_name,
                    "auto_id": info.automation_id,
                    "depth": depth,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                }

                elements.append(elem_data)

                # Group by type
                elem_type = info.control_type
                if elem_type not in by_type:
                    by_type[elem_type] = []
                by_type[elem_type].append(elem_data)

                # Traverse children
                for child in element.children():
                    traverse(child, depth + 1)

            except Exception:
                pass

        with monitor.measure("build_element_tree"):
            traverse(window.wrapper_object())

        # Build full result
        full_result = ElementListResult(
            success=True,
            total_elements=len(elements),
            elements=elements,
            by_type=by_type,
            types=list(by_type.keys()),
        )

        # Apply compaction like macOS does (return top 20 actionable elements)
        if len(elements) > 20:
            compact_result = _compact_element_list_result(full_result, max_elements=20)
            return compact_result

        return full_result

    except Exception as e:
        return ElementListResult(success=False, error=str(e))


def get_focused_element_by_pid(
    pid: int,
    window_title: str | None = None,
) -> dict[str, Any]:
    """
    Get the currently focused UI element in a process.

    Args:
        pid: Process ID of the application
        window_title: Optional specific window title within the process

    Returns:
        Dictionary with element info:
        {
            "success": bool,
            "name": str,
            "control_type": str,
            "automation_id": str,
            "class_name": str,
            "value": str,
            "focused": bool,
            "error": str (if success=False)
        }
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return {"success": False, "error": ERROR_WINDOWS_AUTOMATION_MISSING}

    try:
        # Connect to the process
        app = Application(backend="uia").connect(process=pid)

        # Get the window
        if window_title:
            window = app.window(title=window_title)
        else:
            window = app.top_window()

        # Get the focused element using UI Automation
        # The focused element is typically accessible via has_focus property
        def find_focused(element, depth=0):
            """Recursively find the focused element."""
            if depth > 10:  # Prevent infinite recursion
                return None

            try:
                # Check if this element has focus
                if (
                    hasattr(element, "has_keyboard_focus")
                    and element.has_keyboard_focus()
                ):
                    return element

                # Check children
                for child in element.children():
                    focused = find_focused(child, depth + 1)
                    if focused:
                        return focused
            except Exception:
                pass

            return None

        focused_element = find_focused(window.wrapper_object())

        if focused_element:
            info = focused_element.element_info
            value = ""
            try:
                # Try to get value pattern for Edit controls
                if hasattr(focused_element, "legacy_properties"):
                    value = focused_element.legacy_properties().get("Value", "")
                elif hasattr(focused_element, "window_text"):
                    value = focused_element.window_text()
            except Exception:
                pass

            return {
                "success": True,
                "name": info.name or "",
                "control_type": info.control_type or "",
                "automation_id": info.automation_id or "",
                "class_name": info.class_name or "",
                "value": value,
                "focused": True,
            }
        else:
            return {
                "success": False,
                "error": "No focused element found",
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get focused element: {str(e)}",
        }


def get_element_value_by_pid(
    pid: int,
    window_title: str | None = None,
    control_type: str | None = None,
    name: str | None = None,
    automation_id: str | None = None,
) -> dict[str, Any]:
    """
    Get the value/text of a specific UI element in a process.

    Args:
        pid: Process ID of the application
        window_title: Optional specific window title
        control_type: Optional control type filter ("Edit", "Button", etc.)
        name: Optional element name to find
        automation_id: Optional automation ID to find

    Returns:
        Dictionary with element value:
        {
            "success": bool,
            "value": str,
            "name": str,
            "control_type": str,
            "automation_id": str,
            "class_name": str,
            "error": str (if success=False)
        }
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return {"success": False, "error": ERROR_WINDOWS_AUTOMATION_MISSING}

    # Build search criteria first
    criteria = {}
    if name:
        criteria["title"] = name
    if control_type:
        criteria["control_type"] = control_type
    if automation_id:
        criteria["auto_id"] = automation_id

    # If no criteria provided, return error before trying to connect
    if not criteria:
        return {
            "success": False,
            "error": "At least one search criterion (name, control_type, automation_id) must be provided",
        }

    try:
        # Connect to the process
        app = Application(backend="uia").connect(process=pid)

        # Get the window
        if window_title:
            window = app.window(title=window_title)
        else:
            window = app.top_window()

        # Find the element
        element = window.child_window(**criteria)

        if element.exists():
            info = element.element_info
            value = ""
            try:
                # Try multiple ways to get the value
                if hasattr(element, "legacy_properties"):
                    value = element.legacy_properties().get("Value", "")
                elif hasattr(element, "window_text"):
                    value = element.window_text()
                elif hasattr(element, "texts"):
                    texts = element.texts()
                    value = texts[0] if texts else ""
            except Exception:
                pass

            return {
                "success": True,
                "value": value,
                "name": info.name or "",
                "control_type": info.control_type or "",
                "automation_id": info.automation_id or "",
                "class_name": info.class_name or "",
            }
        else:
            return {
                "success": False,
                "error": "Element not found with the specified criteria",
            }

    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get element value: {str(e)}",
        }
