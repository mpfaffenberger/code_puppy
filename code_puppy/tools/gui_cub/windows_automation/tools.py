from __future__ import annotations

import sys
from typing import Any

if sys.platform == "win32":
    try:
        import win32api
        import win32con
        import win32gui
        import win32process

        WINDOWS_AUTOMATION_AVAILABLE = True
    except ImportError:
        WINDOWS_AUTOMATION_AVAILABLE = False
        win32api = None
        win32con = None
        win32gui = None
        win32process = None
else:
    WINDOWS_AUTOMATION_AVAILABLE = False
    win32api = None
    win32con = None
    win32gui = None
    win32process = None

from pydantic_ai import RunContext

from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_WINDOWS_AUTOMATION_MISSING
from ..performance_monitor import get_monitor
from ..result_types import (
    ElementClickResult,
    ElementListResult,
    ElementSearchResult,
    WindowFocusResult,
    WindowListResult,
)
from .core import (
    click_element,
    find_element,
    focus_window,
    get_element_value_by_pid,
    get_focused_element_by_pid,
    list_elements_in_window,
    list_windows,
)


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
    def windows_list_windows(
        context: RunContext, include_minimized: bool = False
    ) -> WindowListResult:
        """
        List windows on the system.

        Args:
            include_minimized: If True, include minimized windows with minimized=True flag

        Returns:
            WindowListResult with list of windows

        Examples:
            - windows_list_windows()
            - windows_list_windows(include_minimized=True)

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return WindowListResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id("windows_list_windows", str(include_minimized))
        emit_info(
            f"[bold white on blue] WINDOWS LIST WINDOWS [/bold white on blue] 🪟 (minimized={include_minimized})",
            message_group=group_id,
        )

        windows = list_windows(include_minimized=include_minimized)
        minimized_count = sum(1 for w in windows if w.get("minimized", False))

        emit_info(
            f"[green]Found {len(windows)} windows ({minimized_count} minimized)[/green]",
            message_group=group_id,
        )

        return WindowListResult(success=True, count=len(windows), windows=windows)

    @agent.tool
    def windows_un_minimize_window(
        context: RunContext,
        window_title: str | None = None,
        hwnd: int | None = None,
    ) -> WindowFocusResult:
        """
        Un-minimize (restore) a minimized window by title or handle.

        This brings a minimized window back from the taskbar.

        Args:
            window_title: Window title (exact or partial match)
            hwnd: Window handle (if known)

        Returns:
            WindowFocusResult indicating success or failure

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return WindowFocusResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id("windows_un_minimize", window_title or str(hwnd))
        emit_info(
            f"[bold white on blue] UN-MINIMIZE WINDOW [/bold white on blue] ↗️ {window_title or hwnd}",
            message_group=group_id,
        )

        try:
            # Find window handle
            target_hwnd = None
            if hwnd:
                target_hwnd = hwnd
            elif window_title:
                # Try exact match first
                target_hwnd = win32gui.FindWindow(None, window_title)

                # If not found, try partial match
                if not target_hwnd:
                    windows = list_windows(include_minimized=True)
                    for window in windows:
                        if window_title.lower() in window["title"].lower():
                            target_hwnd = window["hwnd"]
                            break

            if not target_hwnd:
                emit_info(
                    f"[yellow]Window '{window_title}' not found[/yellow]",
                    message_group=group_id,
                )
                return WindowFocusResult(
                    success=False,
                    error=f"Window not found: {window_title}. Check spelling or use windows_list_windows() to see available windows.",
                )

            import time

            # Restore if minimized
            was_minimized = win32gui.IsIconic(target_hwnd)
            if was_minimized:
                win32gui.ShowWindow(target_hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)  # Give Windows time to restore

            # Bring to foreground
            foreground_exception = None
            try:
                win32gui.SetForegroundWindow(target_hwnd)
                time.sleep(0.1)  # Give Windows time to focus
            except Exception as e:
                foreground_exception = e
                # Windows focus stealing prevention can block SetForegroundWindow
                # This is normal Windows security behavior, not a real error
                emit_warning(
                    f"[yellow]⚠ Could not set foreground (Windows focus stealing prevention): {type(e).__name__}[/yellow]",
                    message_group=group_id,
                )

            # ✅ VERIFY success before claiming victory
            is_restored = not win32gui.IsIconic(target_hwnd)
            try:
                is_foreground = win32gui.GetForegroundWindow() == target_hwnd
            except Exception:
                is_foreground = False

            if is_restored and is_foreground:
                emit_info(
                    "[green]✅ Un-minimized window successfully[/green]",
                    message_group=group_id,
                )
                return WindowFocusResult(
                    success=True,
                    window=window_title or str(hwnd),
                )
            elif is_restored and not is_foreground:
                # Partial success - window restored but not foreground
                # Try taskbar button click as fallback
                if foreground_exception:
                    emit_info(
                        "[cyan]🔄 Trying fallback: clicking taskbar button...[/cyan]",
                        message_group=group_id,
                    )
                    from .core import _find_and_click_taskbar_button

                    success, error = _find_and_click_taskbar_button(
                        window_title or str(target_hwnd)
                    )

                    if success:
                        time.sleep(0.2)
                        try:
                            is_foreground = (
                                win32gui.GetForegroundWindow() == target_hwnd
                            )
                            if is_foreground:
                                emit_info(
                                    "[green]✅ Taskbar button click successful![/green]",
                                    message_group=group_id,
                                )
                                return WindowFocusResult(
                                    success=True,
                                    window=window_title or str(hwnd),
                                )
                        except Exception:
                            pass
                    else:
                        emit_warning(
                            f"[yellow]⚠ Taskbar fallback failed: {error}[/yellow]",
                            message_group=group_id,
                        )

                # Window is usable even if not foreground
                emit_info(
                    "[cyan]💡 Window is restored and ready for interaction. Click inside the window to bring it to foreground if needed.[/cyan]",
                    message_group=group_id,
                )
                # Return success=True because window IS usable, just not foreground
                return WindowFocusResult(
                    success=True,
                    window=window_title or str(hwnd),
                )
            else:
                # Failed to restore - try taskbar button as last resort
                emit_warning(
                    f"[yellow]❌ Failed to restore window (restored={is_restored}, foreground={is_foreground})[/yellow]",
                    message_group=group_id,
                )

                emit_info(
                    "[cyan]🔄 Trying fallback: clicking taskbar button...[/cyan]",
                    message_group=group_id,
                )
                from .core import _find_and_click_taskbar_button

                success, error = _find_and_click_taskbar_button(
                    window_title or str(target_hwnd)
                )

                if success:
                    time.sleep(0.2)
                    is_restored = not win32gui.IsIconic(target_hwnd)
                    if is_restored:
                        emit_info(
                            "[green]✅ Taskbar button click restored window![/green]",
                            message_group=group_id,
                        )
                        return WindowFocusResult(
                            success=True,
                            window=window_title or str(hwnd),
                        )

                emit_info(
                    "[cyan]💡 NEXT STEP: Use desktop_vqa_click_two_stage() to visually find and click the taskbar button[/cyan]",
                    message_group=group_id,
                )
                return WindowFocusResult(
                    success=False,
                    error=f"Window restoration failed. Taskbar fallback: {error}. Try using desktop_vqa_click_two_stage() to click taskbar visually.",
                    window=window_title or str(hwnd),
                )

        except Exception as e:
            emit_info(
                f"[red]❌ Failed to un-minimize: {e}[/red]",
                message_group=group_id,
            )
            return WindowFocusResult(
                success=False,
                error=f"Failed to un-minimize: {e}",
            )

    @agent.tool
    def windows_list_taskbar_apps(context: RunContext) -> WindowListResult:
        """
        List applications currently in the Windows taskbar.

        Returns running applications with their window state.

        Returns:
            WindowListResult with list of taskbar apps and their states

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return WindowListResult(
                success=False, error=ERROR_WINDOWS_AUTOMATION_MISSING
            )

        group_id = generate_group_id("windows_list_taskbar_apps")
        emit_info(
            "[bold white on blue] TASKBAR APPS [/bold white on blue] 📦",
            message_group=group_id,
        )

        try:
            # Get all windows (including minimized)
            all_windows = list_windows(include_minimized=True)

            # Filter to main application windows (those that appear in taskbar)
            taskbar_apps = []
            seen_exes = set()

            for window in all_windows:
                # Skip duplicates from same executable
                hwnd = window["hwnd"]
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    handle = win32api.OpenProcess(
                        win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ,
                        False,
                        pid,
                    )
                    exe_path = win32process.GetModuleFileNameEx(handle, 0)

                    if exe_path not in seen_exes:
                        seen_exes.add(exe_path)
                        taskbar_apps.append(
                            {
                                "title": window["title"],
                                "exe": exe_path.split("\\")[-1],  # Just filename
                                "minimized": window.get("minimized", False),
                                "hwnd": hwnd,
                                "pid": pid,
                            }
                        )
                except Exception:
                    # Some processes can't be queried
                    continue

            emit_info(
                f"[green]Found {len(taskbar_apps)} taskbar apps ({sum(1 for a in taskbar_apps if a['minimized'])} minimized)[/green]",
                message_group=group_id,
            )

            return WindowListResult(
                success=True,
                count=len(taskbar_apps),
                windows=taskbar_apps,
            )

        except Exception as e:
            emit_info(
                f"[red]❌ Failed to list taskbar apps: {e}[/red]",
                message_group=group_id,
            )
            return WindowListResult(
                success=False,
                error=f"Failed to list taskbar apps: {e}",
            )

    @agent.tool
    def windows_click_taskbar_app(
        context: RunContext, window_title: str
    ) -> WindowFocusResult:
        """
        Attempt to restore and focus a window by title.

        This is an alias for windows_un_minimize_window. If the window is
        restored but not foreground due to focus stealing prevention,
        consider the window usable and proceed with your automation.
        You can click inside the window to bring it to foreground.

        Args:
            window_title: Window title to find and restore (partial match supported)

        Returns:
            WindowFocusResult indicating success

        Note: Windows only. This is equivalent to windows_un_minimize_window.
        """
        # This delegates to un-minimize which handles restoration
        return windows_un_minimize_window(context, window_title=window_title)

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

    @agent.tool
    def windows_close_window(
        context: RunContext,
        window_title: str | None = None,
        hwnd: int | None = None,
        pid: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Close a window by title, handle, or process ID.

        Useful for closing duplicate instances or cleaning up windows.
        By default, sends WM_CLOSE (graceful shutdown). Use force=True
        to terminate the process immediately.

        Args:
            window_title: Window title (exact or partial match)
            hwnd: Window handle (if known)
            pid: Process ID to close all windows from that process
            force: If True, forcefully terminate process instead of graceful close

        Returns:
            Dictionary with:
            - success: True if window(s) closed
            - closed_count: Number of windows closed
            - error: Error message if failed

        Examples:
            - windows_close_window(window_title="Calculator")  # Close Calculator gracefully
            - windows_close_window(hwnd=12345)  # Close specific window
            - windows_close_window(pid=5678, force=True)  # Force kill process

        Note: Windows only. Requires pywin32.
        """
        if not WINDOWS_AUTOMATION_AVAILABLE:
            return {"success": False, "error": ERROR_WINDOWS_AUTOMATION_MISSING}

        group_id = generate_group_id(
            "windows_close", window_title or str(hwnd) or str(pid)
        )
        emit_info(
            f"[bold white on blue] CLOSE WINDOW [/bold white on blue] ✖️ {window_title or hwnd or f'PID {pid}'} (force={force})",
            message_group=group_id,
        )

        try:
            windows_to_close = []

            # Find target window(s)
            if hwnd:
                windows_to_close.append(hwnd)
            elif window_title:
                # Find all matching windows
                all_windows = list_windows(include_minimized=True)
                search_term = window_title.lower()
                for window in all_windows:
                    if search_term in window["title"].lower():
                        windows_to_close.append(window["hwnd"])
            elif pid:
                # Find all windows from this PID
                all_windows = list_windows(include_minimized=True)
                for window in all_windows:
                    if window.get("pid") == pid:
                        windows_to_close.append(window["hwnd"])
            else:
                return {
                    "success": False,
                    "error": "Must provide window_title, hwnd, or pid",
                }

            if not windows_to_close:
                emit_warning(
                    "[yellow]No windows found to close[/yellow]",
                    message_group=group_id,
                )
                return {
                    "success": False,
                    "closed_count": 0,
                    "error": "No matching windows found",
                }

            closed_count = 0
            errors = []

            for target_hwnd in windows_to_close:
                try:
                    if force:
                        # Force kill by terminating process
                        _, pid_to_kill = win32process.GetWindowThreadProcessId(
                            target_hwnd
                        )
                        handle = win32api.OpenProcess(1, False, pid_to_kill)
                        win32api.TerminateProcess(handle, 0)
                        win32api.CloseHandle(handle)
                    else:
                        # Graceful close using WM_CLOSE
                        win32gui.PostMessage(target_hwnd, win32con.WM_CLOSE, 0, 0)

                    closed_count += 1
                except Exception as e:
                    errors.append(f"hwnd {target_hwnd}: {str(e)}")

            if closed_count > 0:
                emit_info(
                    f"[green]✅ Closed {closed_count} window(s)[/green]",
                    message_group=group_id,
                )
                return {"success": True, "closed_count": closed_count}
            else:
                emit_error(
                    f"[red]❌ Failed to close windows: {'; '.join(errors)}[/red]",
                    message_group=group_id,
                )
                return {
                    "success": False,
                    "closed_count": 0,
                    "error": f"Failed to close: {'; '.join(errors)}",
                }

        except Exception as e:
            emit_error(
                f"[red]❌ Error closing window: {e}[/red]",
                message_group=group_id,
            )
            return {"success": False, "closed_count": 0, "error": str(e)}

    @agent.tool
    def windows_show_performance_summary(context: RunContext) -> dict[str, Any]:
        """
        Display GUI automation performance metrics for Windows.

        Shows:
        - Operation timings (avg, min, max)
        - Cache hit/miss rates
        - Early-stop optimization stats

        Returns:
            Dictionary with performance summary
        """
        monitor = get_monitor()
        monitor.report(show_details=True)
        return monitor.get_summary()
