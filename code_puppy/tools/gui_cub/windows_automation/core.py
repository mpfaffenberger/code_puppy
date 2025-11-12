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


def _find_and_click_taskbar_button(window_title: str) -> tuple[bool, str | None]:
    """Find and click a taskbar button using Windows UI Automation.

    This is a fallback strategy when SetForegroundWindow fails due to
    focus stealing prevention.

    Args:
        window_title: Title of the window to find on taskbar

    Returns:
        Tuple of (success: bool, error_message: str | None)
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return (False, "Windows UI Automation not available")

    try:
        # Find the taskbar
        taskbar_hwnd = win32gui.FindWindow("Shell_TrayWnd", None)
        if not taskbar_hwnd:
            return (False, "Could not find taskbar")

        # Connect to taskbar using pywinauto
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        taskbar = desktop.window(handle=taskbar_hwnd)

        # Find all taskbar buttons
        # Taskbar buttons are typically in MSTaskListWClass or ReBarWindow32
        try:
            # Try to find the button by partial title match
            buttons = taskbar.descendants(control_type="Button")

            for button in buttons:
                button_name = button.element_info.name or ""
                # Match window title (taskbar buttons often have truncated titles)
                if (
                    window_title.lower() in button_name.lower()
                    or button_name.lower() in window_title.lower()
                ):
                    # Click the button
                    button.click_input()
                    import time

                    time.sleep(0.3)  # Give Windows time to process click
                    return (True, None)

            return (False, f"No taskbar button found matching '{window_title}'")

        except Exception as e:
            return (False, f"Error finding taskbar button: {type(e).__name__}: {e}")

    except Exception as e:
        return (False, f"Error accessing taskbar: {type(e).__name__}: {e}")


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
) -> tuple[bool, str | None]:
    """
    Focus a window on Windows.

    Args:
        window_title: Window title (exact or partial match, case-insensitive)
        class_name: Window class name
        hwnd: Window handle (direct)

    Returns:
        Tuple of (success: bool, error_message: str | None)
        - (True, None) if successful
        - (False, "not_found") if window not found
        - (False, "focus_failed: <reason>") if window found but focus failed
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return (False, "Windows automation not available")

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
            # IMPORTANT: Prioritize visible/non-minimized windows over minimized ones
            # This prevents focusing the wrong instance when multiple exist
            if not target_hwnd:
                windows = list_windows(include_minimized=True)
                search_term = window_title.lower()

                # Find all matching windows
                matching_windows = [
                    w for w in windows if search_term in w["title"].lower()
                ]

                # Log warning if multiple instances found
                if len(matching_windows) > 1:
                    import sys

                    pids = [w["pid"] for w in matching_windows]
                    visible_count = sum(
                        1 for w in matching_windows if not w["minimized"]
                    )
                    print(
                        f"⚠️  Multiple instances of '{window_title}' found: {len(matching_windows)} total "
                        f"({visible_count} visible, {len(matching_windows) - visible_count} minimized) "
                        f"with PIDs: {pids}. Prioritizing visible instances.",
                        file=sys.stderr,
                    )

                # First pass: look for visible, non-minimized windows
                for window in matching_windows:
                    if not window["minimized"]:
                        target_hwnd = window["hwnd"]
                        break

                # Second pass: if no visible window found, try minimized ones
                if not target_hwnd and matching_windows:
                    target_hwnd = matching_windows[0]["hwnd"]
        # Find by class name
        elif class_name:
            target_hwnd = win32gui.FindWindow(class_name, None)
        else:
            return (False, "No window identifier provided")

        if not target_hwnd:
            return (False, "not_found")

        import time

        # Verify window is actually valid and visible
        if not win32gui.IsWindow(target_hwnd):
            return (False, "not_found")

        # Restore if minimized
        was_minimized = win32gui.IsIconic(target_hwnd)
        if was_minimized:
            win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
            time.sleep(0.2)  # Give Windows time to restore

        # Verify window is now visible
        if not win32gui.IsWindowVisible(target_hwnd):
            return (False, "focus_failed: Window is not visible on screen")

        # Bring to foreground
        try:
            win32gui.SetForegroundWindow(target_hwnd)
            time.sleep(0.1)  # Give Windows time to focus

            # Verify it worked
            is_foreground = win32gui.GetForegroundWindow() == target_hwnd
            is_restored = not win32gui.IsIconic(target_hwnd)

            if is_foreground:
                return (True, None)
            elif is_restored:
                # Window restored but not foreground - this is actually OK for most use cases
                return (True, None)  # Return success since window is usable
            else:
                return (
                    False,
                    "focus_failed: Window was minimized and could not be restored",
                )

        except Exception:
            # SetForegroundWindow failed (likely Windows focus stealing prevention)
            # This is normal Windows security behavior to prevent malicious focus stealing

            # FALLBACK STRATEGY 1: Try clicking the taskbar button
            # This often works when SetForegroundWindow is blocked
            success, error = _find_and_click_taskbar_button(
                window_title or str(target_hwnd)
            )
            if success:
                # Verify the click worked
                time.sleep(0.2)
                is_foreground = win32gui.GetForegroundWindow() == target_hwnd
                if is_foreground:
                    return (True, None)
                # Even if not foreground, window may be usable
                is_restored = not win32gui.IsIconic(target_hwnd)
                if is_restored:
                    return (True, None)

            # Check if window at least got restored from original attempt
            if was_minimized:
                is_restored = not win32gui.IsIconic(target_hwnd)
                if is_restored:
                    # Partial success - window is restored and usable even if not in foreground
                    return (True, None)

            # All fallbacks failed
            return (
                False,
                f"focus_failed: Windows focus stealing prevention blocked foreground access. Taskbar click fallback: {error}",
            )

    except Exception as e:
        # Log the error for debugging
        import sys

        print(f"focus_window error: {e}", file=sys.stderr)
        return (False, f"exception: {str(e)}")


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


def rank_element_by_query(
    element: dict,
    query: str,
    fuzzy: bool = True,
    threshold: float = 0.6,
) -> float:
    """
    Calculate relevance score for an element given a search query.

    Uses intelligent ranking that considers:
    - Text match score (70% weight) - exact/fuzzy/substring matching
    - Element type relevance (20% weight) - boost appropriate types
    - Visual prominence (10% weight) - size and position

    Args:
        element: Element dictionary with title, value, auto_id, etc.
        query: Search query string
        fuzzy: Enable fuzzy matching
        threshold: Minimum similarity score for fuzzy matches

    Returns:
        Score from 0.0 to 1.0 (higher = more relevant)
    """
    query_lower = query.lower().strip()

    # 1. TEXT MATCH SCORE (70% weight)
    text_score = 0.0

    # Check value property (highest priority for Calculator, text fields)
    value = (element.get("value") or "").lower().strip()
    if query_lower == value:  # Exact match
        text_score = 1.0
    elif query_lower in value:  # Substring match
        text_score = 0.8
    elif fuzzy and value:
        try:
            from rapidfuzz import fuzz

            text_score = max(text_score, fuzz.ratio(query_lower, value) / 100.0)
        except ImportError:
            pass

    # Check title/name
    title = (element.get("title") or "").lower().strip()
    if not text_score:  # Only check if value didn't match
        if query_lower == title:
            text_score = 1.0
        elif query_lower in title:
            text_score = 0.8
        elif fuzzy and title:
            try:
                from rapidfuzz import fuzz

                text_score = max(text_score, fuzz.ratio(query_lower, title) / 100.0)
            except ImportError:
                pass

    # Check auto_id
    auto_id = (element.get("auto_id") or "").lower().strip()
    if text_score < 0.8:  # Only check if we don't have a good match yet
        if query_lower in auto_id:
            text_score = max(text_score, 0.6)
        elif fuzzy and auto_id:
            try:
                from rapidfuzz import fuzz

                text_score = max(
                    text_score, fuzz.ratio(query_lower, auto_id) / 100.0 * 0.7
                )
            except ImportError:
                pass

    # If no match, return 0
    if text_score < threshold:
        return 0.0

    # 2. ELEMENT TYPE RELEVANCE (20% weight)
    type_score = 0.5  # Baseline
    control_type = element.get("control_type", "")

    # Boost Text/Edit for numeric/value queries
    if query.strip().replace(".", "").replace("-", "").isdigit():
        if control_type in ["Text", "Edit"]:
            type_score = 1.0
    # Boost Button for action words
    elif any(
        word in query_lower
        for word in ["submit", "ok", "cancel", "close", "save", "delete"]
    ):
        if control_type == "Button":
            type_score = 1.0

    # 3. VISUAL PROMINENCE (10% weight)
    prominence_score = 0.5  # Baseline
    area = element.get("area", 0)
    if area > 10000:  # Large element
        prominence_score = 0.8
    elif area > 5000:  # Medium element
        prominence_score = 0.6

    # Near top-left is slightly more prominent
    x = element.get("x", 1000)
    y = element.get("y", 1000)
    if x < 200 and y < 200:
        prominence_score = min(1.0, prominence_score + 0.2)

    # COMBINED SCORE
    final_score = text_score * 0.7 + type_score * 0.2 + prominence_score * 0.1

    return final_score


def search_elements_smart(
    search_query: str,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.6,
    max_results: int = 10,
    element_types: list[str] | None = None,
) -> ElementSearchResult:
    """
    Search for elements matching a query using intelligent ranking.

    Searches ALL elements (no compaction), ranks by relevance to query.

    Args:
        search_query: Text to search for
        fuzzy: Enable fuzzy matching
        fuzzy_threshold: Minimum similarity score
        max_results: Maximum matches to return
        element_types: Optional filter by control types

    Returns:
        ElementSearchResult with ranked matches
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementSearchResult(
            success=False, found=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
        )

    # Get ALL elements without compaction
    elements_result = list_elements_in_window(compact=False)
    if not elements_result.success or not elements_result.elements:
        return ElementSearchResult(
            success=False,
            found=False,
            error="Could not retrieve element tree",
        )

    # Filter by element_types if specified
    elements_to_search = elements_result.elements
    if element_types:
        elements_to_search = [
            e for e in elements_to_search if e.get("control_type") in element_types
        ]

    # Rank all elements by query relevance
    scored_elements = []
    for element in elements_to_search:
        score = rank_element_by_query(
            element, search_query, fuzzy=fuzzy, threshold=fuzzy_threshold
        )
        if score > 0:
            # Create ElementInfo with score as confidence
            elem_info = ElementInfo(
                title=element.get("title"),
                control_type=element.get("control_type"),
                class_name=element.get("class_name"),
                auto_id=element.get("auto_id"),
                center_x=element.get("center_x"),
                center_y=element.get("center_y"),
                x=element.get("x"),
                y=element.get("y"),
                width=element.get("width"),
                height=element.get("height"),
                confidence=score,
            )
            scored_elements.append(elem_info)

    if not scored_elements:
        return ElementSearchResult(
            success=True,
            found=False,
            error=f"No elements matching '{search_query}' found",
        )

    # Sort by score (highest first) and limit results
    scored_elements.sort(key=lambda x: x.confidence or 0.0, reverse=True)
    top_matches = scored_elements[:max_results]

    return ElementSearchResult(
        success=True,
        found=True,
        matches=top_matches,
        best_match=top_matches[0],
        count=len(top_matches),
    )


def list_elements_in_window(
    compact: bool = True, max_depth: int = 15
) -> ElementListResult:
    """
    List all UI elements in active window.

    OPTIMIZED: Now includes performance monitoring.

    Args:
        compact: If True and >20 elements, return top 20 actionable elements.
                 If False, return all elements unfiltered.
        max_depth: Maximum tree traversal depth (default: 15, can be increased for very deep UIs)

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
            if depth > max_depth:  # Configurable max depth (default 15, was 5)
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

                # Try to get value property for controls like Text/Edit (Calculator display, etc.)
                value = None
                try:
                    # Some controls have a Value pattern that contains their actual content
                    # This is critical for Calculator display, text fields, etc.
                    if hasattr(element, "legacy_properties"):
                        value = element.legacy_properties().get("Value")
                    elif hasattr(element, "texts"):
                        texts = element.texts()
                        if texts:
                            value = texts[0] if len(texts) > 0 else None
                except Exception:
                    # Value not available for this element type
                    pass

                # Calculate area for ranking
                area = (width * height) if (width and height) else 0

                # Check visibility and enabled state
                visible = True
                enabled = True
                try:
                    if hasattr(element, "is_visible"):
                        visible = element.is_visible()
                    if hasattr(element, "is_enabled"):
                        enabled = element.is_enabled()
                except Exception:
                    pass

                elem_data = {
                    "control_type": info.control_type,
                    "title": info.name,
                    "class_name": info.class_name,
                    "auto_id": info.automation_id,
                    "value": value,  # NEW: Capture value property for text displays
                    "depth": depth,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                    "area": area,  # For prominence ranking
                    "visible": visible,
                    "enabled": enabled,
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

        # Apply compaction if requested and >20 elements
        if compact and len(elements) > 20:
            compact_result = _compact_element_list_result(full_result, max_elements=20)
            return compact_result

        return full_result

    except Exception as e:
        return ElementListResult(success=False, error=str(e))


def list_elements_in_application(
    app_title_pattern: str | None = None,
    process_name: str | None = None,
    compact: bool = True,
    max_elements: int = 50,
    max_depth: int = 15,
) -> ElementListResult:
    """
    List all UI elements across ALL windows of an application.

    This function addresses multi-window applications like Connexus that spawn
    separate windows for dialogs/subflows. Unlike list_elements_in_window() which
    only captures the active window, this captures ALL windows belonging to the
    target application and combines their element trees.

    Args:
        app_title_pattern: Regex pattern to match window titles (e.g., ".*Connexus.*")
        process_name: Process name to filter by (e.g., "Connexus.exe")
        compact: If True, return top N actionable elements across all windows
        max_elements: Maximum elements to return when compact=True
        max_depth: Maximum tree traversal depth (default: 15, can be increased for very deep UIs)

    Returns:
        ElementListResult with combined element tree from all windows.
        Each element includes 'window_title' field to identify source window.

    Examples:
        # Get all elements from any Connexus window
        >>> list_elements_in_application(app_title_pattern=".*Connexus.*")

        # Get all elements from a specific process
        >>> list_elements_in_application(process_name="Connexus.exe")

    Use Cases:
        - Multi-window applications (Connexus, Outlook, etc.)
        - Finding elements across dialogs/popups
        - Comprehensive app automation
    """
    monitor = get_monitor()

    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementListResult(success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING)

    if not app_title_pattern and not process_name:
        return ElementListResult(
            success=False,
            error="Must provide either app_title_pattern or process_name",
        )

    try:
        from pywinauto import Desktop
        import re

        desktop = Desktop(backend="uia")
        all_elements = []
        all_by_type = {}
        window_count = 0

        # Get all top-level windows
        all_windows = desktop.windows()

        # Filter windows by criteria
        matching_windows = []
        for win in all_windows:
            try:
                window_title = win.window_text()

                if not window_title:  # Skip windows with no title
                    continue

                # Match by title pattern
                if app_title_pattern:
                    if re.search(app_title_pattern, window_title, re.IGNORECASE):
                        matching_windows.append((win, window_title))
                        continue

                # Match by process name (TODO: implement process filtering)
                # This would require getting process info from window

            except Exception:
                continue

        if not matching_windows:
            return ElementListResult(
                success=False,
                error=f"No windows found matching pattern '{app_title_pattern}'",
            )

        # Traverse each matching window
        def traverse(element, depth, window_title):
            if depth > max_depth:  # Configurable depth limit
                return []

            elements_from_node = []

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
                    x = y = width = height = center_x = center_y = None

                # Get value property
                value = None
                try:
                    if hasattr(element, "legacy_properties"):
                        value = element.legacy_properties().get("Value")
                    elif hasattr(element, "texts"):
                        texts = element.texts()
                        if texts:
                            value = texts[0] if len(texts) > 0 else None
                except Exception:
                    pass

                # Calculate area
                area = (width * height) if (width and height) else 0

                # Check visibility and enabled state
                visible = True
                enabled = True
                try:
                    if hasattr(element, "is_visible"):
                        visible = element.is_visible()
                    if hasattr(element, "is_enabled"):
                        enabled = element.is_enabled()
                except Exception:
                    pass

                elem_data = {
                    "control_type": info.control_type,
                    "title": info.name,
                    "class_name": info.class_name,
                    "auto_id": info.automation_id,
                    "value": value,
                    "depth": depth,
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "center_x": center_x,
                    "center_y": center_y,
                    "area": area,
                    "visible": visible,
                    "enabled": enabled,
                    "window_title": window_title,  # NEW: Track source window
                }

                elements_from_node.append(elem_data)

                # Group by type
                elem_type = info.control_type
                if elem_type not in all_by_type:
                    all_by_type[elem_type] = []
                all_by_type[elem_type].append(elem_data)

                # Traverse children
                for child in element.children():
                    child_elements = traverse(child, depth + 1, window_title)
                    elements_from_node.extend(child_elements)

            except Exception:
                pass

            return elements_from_node

        # Process each matching window
        with monitor.measure("build_multi_window_tree"):
            for window, window_title in matching_windows:
                try:
                    # window is already a UIAWrapper from desktop.windows()
                    # Don't call wrapper_object() on it!
                    window_elements = traverse(window, 0, window_title)
                    all_elements.extend(window_elements)
                    window_count += 1
                except Exception:
                    continue

        # Build full result with window count in summary
        summary_data = {
            "window_count": window_count,
            "total_elements": len(all_elements),
            "element_types": len(all_by_type),
        }

        full_result = ElementListResult(
            success=True,
            total_elements=len(all_elements),
            elements=all_elements,
            by_type=all_by_type,
            types=list(all_by_type.keys()),
            summary=summary_data,
        )

        # Apply compaction if requested
        if compact and len(all_elements) > max_elements:
            compact_result = _compact_element_list_result(
                full_result, max_elements=max_elements
            )
            # Preserve window count in summary
            if isinstance(compact_result.summary, dict):
                compact_result.summary["window_count"] = window_count
            return compact_result

        return full_result

    except Exception as e:
        return ElementListResult(success=False, error=str(e))


def search_text_in_elements(
    search_text: str,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.7,
) -> ElementSearchResult:
    """
    Search for text in the element tree of the active window.

    This searches through all UI elements' titles/names AND VALUE properties
    to find text matches BEFORE falling back to OCR. More efficient and reliable
    than OCR for finding text that exists in accessibility tree.

    **FIXED QUIRK:** Now searches the VALUE property in addition to title/auto_id.
    This fixes the Calculator display issue where result text (e.g., "153") is
    stored in the value property of Text/Edit controls, not in title or auto_id.
    See error.log for full details on this quirk.

    Args:
        search_text: Text to search for in element titles/names/values
        fuzzy: Enable fuzzy matching (uses rapidfuzz)
        fuzzy_threshold: Minimum similarity score (default: 0.7)

    Returns:
        ElementSearchResult with matching elements

    Example:
        # Search for "180" in Calculator result display
        # Now finds it in the value property!
        result = search_text_in_elements(search_text="180")
        if result.found:
            # Found in element tree - no OCR needed!
            click(result.best_match.center_x, result.best_match.center_y)
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementSearchResult(
            success=False, found=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
        )

    # First, get all elements in the window (NO COMPACTION - search all elements)
    elements_result = list_elements_in_window(compact=False)
    if not elements_result.success or not elements_result.elements:
        return ElementSearchResult(
            success=False,
            found=False,
            error="Could not retrieve element tree",
        )

    # Search through elements for matching text
    matches = []
    search_lower = search_text.lower().strip()

    for element in elements_result.elements:
        title = element.get("title") or ""
        auto_id = element.get("auto_id") or ""
        value = element.get("value") or ""  # NEW: Also search value property

        # Check title, auto_id, AND value for matches
        # This fixes the Calculator quirk where display text is in value, not title
        match_score = 0.0
        matched_field = None

        if fuzzy:
            # Use fuzzy matching with rapidfuzz
            try:
                from rapidfuzz import fuzz

                title_score = fuzz.ratio(search_lower, title.lower().strip()) / 100.0
                auto_id_score = (
                    fuzz.ratio(search_lower, auto_id.lower().strip()) / 100.0
                )
                value_score = fuzz.ratio(search_lower, value.lower().strip()) / 100.0

                # Prioritize value matches for text displays (Calculator, text fields)
                if value_score >= fuzzy_threshold:
                    match_score = value_score
                    matched_field = "value"
                elif title_score >= fuzzy_threshold:
                    match_score = title_score
                    matched_field = "title"
                elif auto_id_score >= fuzzy_threshold:
                    match_score = auto_id_score
                    matched_field = "auto_id"

            except ImportError:
                # Fallback to exact matching if rapidfuzz not available
                if search_lower in value.lower():
                    match_score = 1.0
                    matched_field = "value"
                elif search_lower in title.lower():
                    match_score = 1.0
                    matched_field = "title"
                elif search_lower in auto_id.lower():
                    match_score = 1.0
                    matched_field = "auto_id"
        else:
            # Exact substring matching - check value FIRST for text displays
            if search_lower in value.lower():
                match_score = 1.0
                matched_field = "value"
            elif search_lower in title.lower():
                match_score = 1.0
                matched_field = "title"
            elif search_lower in auto_id.lower():
                match_score = 1.0
                matched_field = "auto_id"

        if match_score > 0:
            # Create ElementInfo for this match
            elem_info = ElementInfo(
                title=title,
                control_type=element.get("control_type"),
                class_name=element.get("class_name"),
                auto_id=element.get("auto_id"),
                center_x=element.get("center_x"),
                center_y=element.get("center_y"),
                x=element.get("x"),
                y=element.get("y"),
                width=element.get("width"),
                height=element.get("height"),
                confidence=match_score,
                matched_field=matched_field,
            )
            matches.append(elem_info)

    if not matches:
        return ElementSearchResult(
            success=True,
            found=False,
            error=f"Text '{search_text}' not found in element tree",
        )

    # Sort by confidence (highest first)
    matches.sort(key=lambda m: m.confidence or 0.0, reverse=True)

    return ElementSearchResult(
        success=True,
        found=True,
        matches=matches,
        best_match=matches[0],
        count=len(matches),
    )


def search_element_by_value(
    value_text: str,
    fuzzy: bool = False,
    fuzzy_threshold: float = 0.7,
) -> ElementSearchResult:
    """
    Search for elements specifically by their VALUE property.

    **USE CASE:** Calculator displays, text fields, read-only text controls.
    This is a specialized version of search_text_in_elements that ONLY searches
    the value property, ignoring title and auto_id.

    **WHY THIS EXISTS:** Documents the Calculator quirk where display text
    (e.g., "153") lives in value property, not title. This function makes
    that use case explicit and clear.

    Args:
        value_text: Text to search for in element value properties
        fuzzy: Enable fuzzy matching (uses rapidfuzz)
        fuzzy_threshold: Minimum similarity score (default: 0.7)

    Returns:
        ElementSearchResult with elements matching the value

    Example:
        # Find Calculator result by value
        result = search_element_by_value(value_text="153")
        if result.found:
            print(f"Found display at ({result.best_match.center_x}, {result.best_match.center_y})")

    Note:
        For general text search, use search_text_in_elements() which searches
        title, auto_id, AND value. Use this function when you specifically
        need value-only searches.
    """
    if not WINDOWS_AUTOMATION_AVAILABLE:
        return ElementSearchResult(
            success=False, found=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
        )

    # Get all elements (NO COMPACTION - search all elements for values)
    elements_result = list_elements_in_window(compact=False)
    if not elements_result.success or not elements_result.elements:
        return ElementSearchResult(
            success=False,
            found=False,
            error="Could not retrieve element tree",
        )

    # Search ONLY value property
    matches = []
    search_lower = value_text.lower().strip()

    for element in elements_result.elements:
        value = element.get("value") or ""
        if not value:  # Skip elements without value property
            continue

        match_score = 0.0

        if fuzzy:
            try:
                from rapidfuzz import fuzz

                value_score = fuzz.ratio(search_lower, value.lower().strip()) / 100.0
                if value_score >= fuzzy_threshold:
                    match_score = value_score
            except ImportError:
                # Fallback to exact matching
                if search_lower in value.lower():
                    match_score = 1.0
        else:
            # Exact substring matching
            if search_lower in value.lower():
                match_score = 1.0

        if match_score > 0:
            elem_info = ElementInfo(
                title=element.get("title"),
                control_type=element.get("control_type"),
                class_name=element.get("class_name"),
                auto_id=element.get("auto_id"),
                center_x=element.get("center_x"),
                center_y=element.get("center_y"),
                x=element.get("x"),
                y=element.get("y"),
                width=element.get("width"),
                height=element.get("height"),
                confidence=match_score,
                matched_field="value",
            )
            matches.append(elem_info)

    if not matches:
        return ElementSearchResult(
            success=True,
            found=False,
            error=f"No elements with value='{value_text}' found in element tree",
        )

    # Sort by confidence
    matches.sort(key=lambda x: x.confidence, reverse=True)

    return ElementSearchResult(
        success=True,
        found=True,
        matches=matches,
        best_match=matches[0],
        count=len(matches),
    )


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
