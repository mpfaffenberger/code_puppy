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
        import win32con
        import win32gui
        import win32process
        from pywinauto import Application
        from pywinauto.findwindows import find_elements

        WINDOWS_AUTOMATION_AVAILABLE = True
    except ImportError:
        WINDOWS_AUTOMATION_AVAILABLE = False
        win32gui = None
        win32con = None
        Application = None
else:
    WINDOWS_AUTOMATION_AVAILABLE = False
    win32gui = None
    win32con = None
    Application = None

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from .constants import ERROR_ELEMENT_NOT_FOUND, ERROR_WINDOWS_AUTOMATION_MISSING
from .result_types import (
    ElementClickResult,
    ElementInfo,
    ElementListResult,
    ElementSearchResult,
    WindowFocusResult,
    WindowListResult,
)


def list_windows() -> list[dict[str, Any]]:
    """
    List all visible windows on Windows.

    Returns:
        List of window dictionaries with hwnd, title, class_name
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return []

    def callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
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
        window_title: Window title (exact or partial match)
        class_name: Window class name
        hwnd: Window handle (direct)

    Returns:
        True if successful
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return False

    try:
        # If hwnd provided directly
        if hwnd:
            target_hwnd = hwnd
        # Find by title
        elif window_title:
            # Try exact match first
            target_hwnd = win32gui.FindWindow(None, window_title)

            # If not found, try partial match
            if not target_hwnd:
                windows = list_windows()
                for window in windows:
                    if window_title.lower() in window["title"].lower():
                        target_hwnd = window["hwnd"]
                        break
        # Find by class name
        elif class_name:
            target_hwnd = win32gui.FindWindow(class_name, None)
        else:
            return False

        if target_hwnd:
            # Restore if minimized
            if win32gui.IsIconic(target_hwnd):
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)

            # Bring to foreground
            win32gui.SetForegroundWindow(target_hwnd)
            return True

    except Exception:
        pass

    return False


def find_element(
    title: str | None = None,
    class_name: str | None = None,
    control_type: str | None = None,
    auto_id: str | None = None,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.7,
) -> ElementSearchResult:
    """
    Find UI element using Windows UI Automation.

    Args:
        title: Element title/name
        class_name: Windows class name
        control_type: Control type (Button, Edit, MenuItem, etc.)
        auto_id: Automation ID

    Returns:
        ElementSearchResult with element info including position
    """
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
            )
            return ElementSearchResult(
                success=True, found=True, count=1, matches=[info], best_match=info
            )

        # Fuzzy fallback on title if requested
        if fuzzy and title:
            import difflib

            elements = find_elements(title_re=".*")  # enumerate
            best = None
            best_score = 0.0
            for el in elements:
                name = getattr(el, "name", "") or ""
                score = difflib.SequenceMatcher(
                    None, title.lower(), name.lower()
                ).ratio()
                if score >= fuzzy_threshold and score > best_score:
                    best = el
                    best_score = score
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
                )
                return ElementSearchResult(
                    success=True, found=True, count=1, matches=[info], best_match=info
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

    Returns:
        ElementListResult with element tree
    """
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
                elem_data = {
                    "type": info.control_type,
                    "name": info.name,
                    "class": info.class_name,
                    "depth": depth,
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

        traverse(window.wrapper_object())

        return ElementListResult(
            success=True,
            total_elements=len(elements),
            elements=elements,
            by_type=by_type,
            types=list(by_type.keys()),
        )

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


def register_windows_tools(agent):
    """Register Windows automation tools."""

    @agent.tool
    def windows_focus_window(
        context: RunContext,
        window_title: str | None = None,
        class_name: str | None = None,
    ) -> WindowFocusResult:
        """
        Focus (activate) a window on Windows.

        Args:
            window_title: Window title (partial match supported)
            class_name: Window class name

        Returns:
            WindowFocusResult with success status

        Examples:
            - windows_focus_window(window_title="Notepad")
            - windows_focus_window(window_title="Untitled - Notepad")
            - windows_focus_window(class_name="Notepad")

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return WindowFocusResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id(
            "windows_focus_window", window_title or class_name or "unknown"
        )
        emit_info(
            f"[bold white on blue] WINDOWS FOCUS [/bold white on blue] 🪟 {window_title or class_name}",
            message_group=group_id,
        )

        success = focus_window(window_title=window_title, class_name=class_name)

        if success:
            emit_info(
                f"[green]Focused window: {window_title or class_name}[/green]",
                message_group=group_id,
            )
            return WindowFocusResult(success=True, window=window_title or class_name)
        else:
            emit_warning(
                f"[yellow]Could not focus window: {window_title or class_name}[/yellow]",
                message_group=group_id,
            )
            return WindowFocusResult(success=False, error="Window not found")

    @agent.tool
    def windows_find_element(
        context: RunContext,
        title: str | None = None,
        control_type: str | None = None,
        class_name: str | None = None,
        fuzzy: bool = False,
        fuzzy_threshold: float = 0.7,
    ) -> ElementSearchResult:
        """
        Find UI element using Windows UI Automation.

        Args:
            title: Element title/name
            control_type: Control type (Button, Edit, MenuItem, ComboBox, etc.)
            class_name: Windows class name

        Returns:
            ElementSearchResult with element position and info

        Examples:
            - windows_find_element(title="File", control_type="MenuItem")
            - windows_find_element(title="Save", control_type="Button")
            - windows_find_element(control_type="Edit")  # Find text field

        Common control types:
            - Button, Edit, MenuItem, ComboBox, CheckBox
            - RadioButton, ListItem, TreeItem, TabItem

        Note: Windows only. Requires pywinauto.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return ElementSearchResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id(
            "windows_find_element", title or control_type or "unknown"
        )
        emit_info(
            f"[bold white on blue] WINDOWS FIND ELEMENT [/bold white on blue] 🔍 {title or control_type}",
            message_group=group_id,
        )

        result = find_element(
            title=title,
            control_type=control_type,
            class_name=class_name,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        if result.found and result.best_match:
            emit_info(
                f"[green]Found element: {result.best_match.title} at ({result.best_match.center_x}, {result.best_match.center_y})[/green]",
                message_group=group_id,
            )
        else:
            emit_warning("[yellow]Element not found[/yellow]", message_group=group_id)

        return result

    @agent.tool
    def windows_click_element(
        context: RunContext,
        title: str | None = None,
        control_type: str | None = None,
        class_name: str | None = None,
        fuzzy: bool = False,
        fuzzy_threshold: float = 0.7,
    ) -> ElementClickResult:
        """
        Find and click UI element on Windows.

        Args:
            title: Element title/name
            control_type: Control type
            class_name: Windows class name

        Returns:
            ElementClickResult with success status

        Examples:
            - windows_click_element(title="OK", control_type="Button")
            - windows_click_element(title="File")

        Note: Windows only. Requires pywinauto.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return ElementClickResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id(
            "windows_click_element", title or control_type or "unknown"
        )
        emit_info(
            f"[bold white on blue] WINDOWS CLICK [/bold white on blue] 🖱️ {title or control_type}",
            message_group=group_id,
        )

        result = click_element(
            title=title,
            control_type=control_type,
            class_name=class_name,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        if result.success:
            emit_info(
                f"[green]Clicked element using {result.method}[/green]",
                message_group=group_id,
            )
        else:
            emit_error(
                f"[red]Click failed: {result.error}[/red]", message_group=group_id
            )

        return result

    @agent.tool
    def windows_list_elements(context: RunContext) -> ElementListResult:
        """
        List all UI elements in the active window.

        Returns:
            ElementListResult with element tree and statistics

        Examples:
            - windows_list_elements()

        Note: Windows only. Requires pywinauto.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return ElementListResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id("windows_list_elements", "all")
        emit_info(
            "[bold white on blue] WINDOWS LIST ELEMENTS [/bold white on blue] 📋",
            message_group=group_id,
        )

        result = list_elements_in_window()

        if result.success:
            emit_info(
                f"[green]Found {result.total_elements} elements across {len(result.types or [])} types[/green]",
                message_group=group_id,
            )

        return result

    @agent.tool
    def windows_list_windows(context: RunContext) -> WindowListResult:
        """
        List all visible windows on the system.

        Returns:
            WindowListResult with list of windows

        Examples:
            - windows_list_windows()

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return WindowListResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id("windows_list_windows", "all")
        emit_info(
            "[bold white on blue] WINDOWS LIST WINDOWS [/bold white on blue] 🪟",
            message_group=group_id,
        )

        windows = list_windows()

        emit_info(
            f"[green]Found {len(windows)} visible windows[/green]",
            message_group=group_id,
        )

        return WindowListResult(success=True, count=len(windows), windows=windows)

    @agent.tool
    def windows_get_focused_element(
        context: RunContext,
        pid: int,
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """
        Detect which UI element currently has keyboard focus in a Windows process.

        Args:
            pid: Process ID of the application
            window_title: Optional specific window title within the process

        Returns:
            Dictionary containing:
            - success: True if element was found
            - name: Element name
            - control_type: Control type (Edit, Button, etc.)
            - automation_id: Automation ID if available
            - class_name: Windows class name
            - value: Current text/value of the element
            - focused: True (always, when successful)
            - error: Error message if success=False

        Examples:
            - windows_get_focused_element(pid=20928)
            - windows_get_focused_element(pid=20928, window_title="Search")

        Use Cases:
            - Verify cursor is in correct field before typing
            - Detect which field is focused after Tab navigation
            - Validate tab order in forms
            - Debug field focus issues

        Note: Windows only. Requires pywinauto.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return {"success": False, "error": ERROR_WINDOWS_AUTOMATION_MISSING}

        group_id = generate_group_id("windows_get_focused_element", f"pid_{pid}")
        emit_info(
            f"[bold white on blue] WINDOWS GET FOCUSED ELEMENT [/bold white on blue] 🎯 PID {pid}",
            message_group=group_id,
        )

        result = get_focused_element_by_pid(pid=pid, window_title=window_title)

        if result.get("success"):
            emit_info(
                f"[green]Focused element: {result.get('name', 'N/A')} ({result.get('control_type', 'N/A')})[/green]",
                message_group=group_id,
            )
        else:
            emit_warning(
                f"[yellow]Could not get focused element: {result.get('error', 'Unknown error')}[/yellow]",
                message_group=group_id,
            )

        return result

    @agent.tool
    def windows_get_element_value(
        context: RunContext,
        pid: int,
        window_title: str | None = None,
        control_type: str | None = None,
        name: str | None = None,
        automation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Get the current value/text of a specific UI element in a Windows process.

        Args:
            pid: Process ID of the application
            window_title: Optional specific window title
            control_type: Optional control type filter ("Edit", "Button", etc.)
            name: Optional element name to find
            automation_id: Optional automation ID to find

        Returns:
            Dictionary containing:
            - success: True if element was found
            - value: Current text/value of the element
            - name: Element name
            - control_type: Control type
            - automation_id: Automation ID if available
            - class_name: Windows class name
            - error: Error message if success=False

        Examples:
            - windows_get_element_value(pid=20928, name="Username", control_type="Edit")
            - windows_get_element_value(pid=20928, window_title="Login", automation_id="txtUsername")

        Use Cases:
            - Verify typed text landed in correct field
            - Check field values before submission
            - Validate form data
            - Debug why text appears in wrong field

        Note: At least one search criterion (name, control_type, automation_id) must be provided.
        Note: Windows only. Requires pywinauto.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return {"success": False, "error": ERROR_WINDOWS_AUTOMATION_MISSING}

        group_id = generate_group_id(
            "windows_get_element_value",
            f"pid_{pid}_{name or automation_id or control_type or 'unknown'}",
        )
        emit_info(
            f"[bold white on blue] WINDOWS GET ELEMENT VALUE [/bold white on blue] 📝 PID {pid}",
            message_group=group_id,
        )

        result = get_element_value_by_pid(
            pid=pid,
            window_title=window_title,
            control_type=control_type,
            name=name,
            automation_id=automation_id,
        )

        if result.get("success"):
            emit_info(
                f"[green]Element value: '{result.get('value', '')}' ({result.get('name', 'N/A')})[/green]",
                message_group=group_id,
            )
        else:
            emit_warning(
                f"[yellow]Could not get element value: {result.get('error', 'Unknown error')}[/yellow]",
                message_group=group_id,
            )

        return result
