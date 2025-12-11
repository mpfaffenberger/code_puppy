"""Accessibility tool registration for macOS."""

from __future__ import annotations

import sys
from typing import Any

if sys.platform != "darwin":
    ACCESSIBILITY_AVAILABLE = False
else:
    try:
        import atomacos  # noqa: F401

        ACCESSIBILITY_AVAILABLE = True
    except ImportError:
        ACCESSIBILITY_AVAILABLE = False

from pydantic_ai import RunContext

from code_puppy.messaging import emit_info
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_ATOMACOS_MISSING, ERROR_NO_FRONTMOST_APP
from ..performance_monitor import get_monitor
from ..result_types import (
    ElementClickResult,
    ElementListResult,
    ElementSearchResult,
    WindowFocusResult,
    WindowListResult,
)
from .element_finder import find_accessible_element, get_frontmost_app
from .element_list import (
    _build_element_tree,
    _compact_element_list_result,
    _list_macos_windows,
    list_accessible_elements,
)


# ============================================================================
# MODULE-LEVEL FUNCTIONS (importable for use by other modules)
# ============================================================================


def desktop_click_accessible_element(
    context: RunContext | None = None,
    role: str | None = None,
    title: str | None = None,
    identifier: str | None = None,
    in_frontmost_app: bool = True,
    fuzzy: bool = True,
    fuzzy_threshold: float = 0.25,
) -> ElementClickResult:
    """
    Find and click a UI element using Accessibility API with FUZZY MATCHING.

    This is the module-level function that can be imported directly.
    Uses fuzzy matching to handle common UI element naming variations.

    Args:
        context: Optional RunContext (not used, kept for API compatibility)
        role: Element role (e.g., 'AXButton')
        title: Element title/name to search for (supports fuzzy matching!)
        identifier: AXIdentifier for exact match (HIGHEST PRIORITY!)
        in_frontmost_app: Search only in active app
        fuzzy: Enable intelligent fuzzy matching (default: True)
        fuzzy_threshold: Minimum similarity score (0.0-1.0, default: 0.25)

    Returns:
        ElementClickResult with success status and click coordinates
    """
    # Find the element with fuzzy matching
    result = find_accessible_element(
        role=role,
        title=title,
        identifier=identifier,
        in_frontmost_app=in_frontmost_app,
        fuzzy=fuzzy,
        fuzzy_threshold=fuzzy_threshold,
    )

    if not result.success or not result.found:
        return ElementClickResult(
            success=False, error=result.error or "Element not found"
        )

    best_match = result.best_match
    if not best_match:
        return ElementClickResult(success=False, error="No element found")

    group_id = generate_group_id("desktop_click_accessible", f"{role}_{title}")

    # Try native AX Press action first
    try:
        app = get_frontmost_app()
        if app:
            search_criteria: dict[str, Any] = {}
            if role:
                search_criteria["AXRole"] = role
            if title:
                search_criteria["AXTitle"] = title

            if search_criteria:
                matches = app.findAllR(**search_criteria)
                if matches:
                    element_ref = matches[0]
                    try:
                        element_ref.Press()
                        emit_info(
                            f"[green]Pressed '{best_match.title}' using native AX Press[/green]",
                            message_group=group_id,
                        )
                        return ElementClickResult(
                            success=True,
                            clicked=True,
                            element_found=True,
                            method="ax_press",
                            element=best_match.title,
                            role=best_match.role,
                            click_x=best_match.center_x,
                            click_y=best_match.center_y,
                        )
                    except Exception:
                        pass  # Fall through to mouse click
    except Exception:
        pass  # Fall through to mouse click

    # Fallback: Click at element center using mouse (native API for multi-monitor)
    if best_match.center_x is None or best_match.center_y is None:
        return ElementClickResult(
            success=False, error="Could not determine element position"
        )

    try:
        from ..platform import click_mouse_native

        success, error = click_mouse_native(
            x=best_match.center_x, y=best_match.center_y, button="left", clicks=1
        )

        if not success:
            return ElementClickResult(
                success=False, error=f"Native click failed: {error}"
            )

        emit_info(
            f"[green]Clicked '{best_match.title}' at ({best_match.center_x}, {best_match.center_y})[/green]",
            message_group=group_id,
        )

        return ElementClickResult(
            success=True,
            clicked=True,
            element_found=True,
            method="native_click",
            element=best_match.title,
            role=best_match.role,
            click_x=best_match.center_x,
            click_y=best_match.center_y,
        )
    except Exception as e:
        return ElementClickResult(success=False, error=f"Click failed: {str(e)}")


def register_accessibility_tools(agent):
    """Register accessibility API tools for macOS."""

    @agent.tool
    def desktop_list_windows(
        context: RunContext, include_minimized: bool = False
    ) -> WindowListResult:
        """
        List application windows on macOS using Quartz APIs.

        Args:
            include_minimized: If True, include minimized/hidden windows with minimized=True flag

        Returns:
            WindowListResult with windows containing owner(name), title, bounds, and minimized status.

        Note: macOS only.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return WindowListResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_list_windows", str(include_minimized))
        emit_info(
            f"[bold white on blue] MAC LIST WINDOWS [/bold white on blue] 🪟 (minimized={include_minimized})",
            message_group=group_id,
        )
        wins = _list_macos_windows(include_minimized=include_minimized)
        minimized_count = sum(1 for w in wins if w.get("minimized", False))
        emit_info(
            f"[green]Found {len(wins)} windows ({minimized_count} minimized)[/green]",
            message_group=group_id,
        )
        return WindowListResult(success=True, count=len(wins), windows=wins)

    @agent.tool
    def desktop_un_minimize_window(
        context: RunContext, app_name: str
    ) -> WindowFocusResult:
        """
        Un-minimize (restore) a minimized window by application name.

        This brings a minimized window back from the dock/taskbar.

        Args:
            app_name: Application name (e.g., "Spotify", "Mail", "Calculator")

        Returns:
            WindowFocusResult indicating success or failure

        Note: macOS only.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return WindowFocusResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_un_minimize", app_name)
        emit_info(
            f"[bold white on blue] UN-MINIMIZE WINDOW [/bold white on blue] ↗️ {app_name}",
            message_group=group_id,
        )

        try:
            from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps

            workspace = NSWorkspace.sharedWorkspace()
            running_apps = workspace.runningApplications()

            # Find app by name (case-insensitive, matches localizedName or bundleIdentifier)
            target_app = None
            app_name_lower = app_name.lower()

            for app in running_apps:
                localized_name = app.localizedName()
                bundle_id = app.bundleIdentifier()

                # Try matching against localizedName (case-insensitive)
                if localized_name and localized_name.lower() == app_name_lower:
                    target_app = app
                    break

                # Also try matching against bundle ID suffix (e.g., "Calculator" matches "com.apple.calculator")
                if bundle_id and bundle_id.lower().endswith(f".{app_name_lower}"):
                    target_app = app
                    break

            if not target_app:
                # Provide more helpful debug info
                running_app_names = [
                    app.localizedName() for app in running_apps if app.localizedName()
                ]
                emit_info(
                    f"[yellow]App '{app_name}' not found or not running[/yellow]\n"
                    f"[dim]Running apps: {', '.join(sorted(set(running_app_names))[:20])}[/dim]",
                    message_group=group_id,
                )
                return WindowFocusResult(
                    success=False,
                    error=f"Application '{app_name}' not found or not running. Check app name spelling or verify app is installed.",
                )

            # Unhide the app (this un-minimizes it)
            target_app.unhide()

            # Activate the app to bring it to front
            target_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)

            # CRITICAL: activateWithOptions_ is asynchronous!
            # We need to wait for the window to actually become frontmost
            # before returning, otherwise subsequent OCR/screenshot calls will
            # capture the WRONG window!

            # Verification loop: wait until the app window is actually at layer 0 (topmost)
            # NOTE: We use _is_app_window_topmost() instead of NSWorkspace.frontmostApplication()
            # because NSWorkspace returns stale/incorrect data (it reports menu bar owner,
            # not actual window focus).
            import time
            from ..window_control.core import (
                _is_app_window_topmost,
                _get_active_window_bounds_impl,
            )

            max_wait_time = 3.0  # Maximum 3 seconds to wait
            poll_interval = 0.1  # Check every 100ms
            elapsed = 0.0

            actual_app_name = target_app.localizedName()

            while elapsed < max_wait_time:
                time.sleep(poll_interval)
                elapsed += poll_interval

                # Check if app has a window at layer 0 (topmost)
                if _is_app_window_topmost(actual_app_name):
                    # Success! The window is now at the topmost layer
                    # Add a tiny buffer to ensure it's fully settled
                    time.sleep(0.2)  # 200ms buffer for stability
                    emit_info(
                        f"[green]✅ Un-minimized {app_name}[/green]",
                        message_group=group_id,
                    )
                    return WindowFocusResult(
                        success=True,
                        window=app_name,
                    )

            # Timeout - the window didn't reach layer 0 in time
            # Get the actual topmost app for error message
            bounds_result = _get_active_window_bounds_impl()
            actual_topmost = (
                bounds_result.app_name if bounds_result.success else "unknown"
            )

            emit_info(
                f"[yellow]⚠️  Un-minimized {app_name} but {actual_topmost} is still topmost[/yellow]",
                message_group=group_id,
            )
            return WindowFocusResult(
                success=False,
                error=f"Un-minimized {app_name} but {actual_topmost} is still topmost after {max_wait_time}s. Window may need manual focus or could be minimized to a different space.",
            )

        except Exception as e:
            emit_info(
                f"[red]❌ Failed to un-minimize: {e}[/red]",
                message_group=group_id,
            )
            return WindowFocusResult(
                success=False,
                error=f"Failed to un-minimize {app_name}: {e}",
            )

    @agent.tool
    def desktop_list_dock_apps(context: RunContext) -> WindowListResult:
        """
        List all applications currently in the macOS Dock.

        Returns apps with their running status, hidden (minimized) state, and app name.

        Returns:
            WindowListResult with list of dock apps and their states

        Note: macOS only.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return WindowListResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_list_dock_apps")
        emit_info(
            "[bold white on blue] DOCK APPS [/bold white on blue] 📦",
            message_group=group_id,
        )

        try:
            from AppKit import NSWorkspace

            workspace = NSWorkspace.sharedWorkspace()
            running_apps = workspace.runningApplications()

            dock_apps = []
            for app in running_apps:
                app_name = app.localizedName()
                is_hidden = app.isHidden()
                is_active = app.isActive()

                dock_apps.append(
                    {
                        "app_name": app_name,
                        "running": True,  # Only running apps are in this list
                        "hidden": is_hidden,  # Minimized/hidden
                        "active": is_active,  # Currently frontmost
                        "pid": app.processIdentifier(),
                    }
                )

            emit_info(
                f"[green]Found {len(dock_apps)} running apps ({sum(1 for a in dock_apps if a['hidden'])} hidden)[/green]",
                message_group=group_id,
            )

            return WindowListResult(
                success=True,
                count=len(dock_apps),
                windows=dock_apps,  # Reusing windows field for dock apps
            )

        except Exception as e:
            emit_info(
                f"[red]❌ Failed to list dock apps: {e}[/red]",
                message_group=group_id,
            )
            return WindowListResult(
                success=False,
                error=f"Failed to list dock apps: {e}",
            )

    @agent.tool
    def desktop_click_dock_app(context: RunContext, app_name: str) -> WindowFocusResult:
        """
        Click on a dock icon to activate/un-minimize an application.

        This is useful for bringing minimized windows back to front.

        Args:
            app_name: Application name to click in dock (e.g., "Spotify", "Mail")

        Returns:
            WindowFocusResult indicating success

        Note: macOS only. This calls desktop_un_minimize_window internally.
        """
        # This is effectively the same as un-minimizing, so we delegate
        return desktop_un_minimize_window(context, app_name)

    @agent.tool
    def desktop_list_accessible_tree(
        context: RunContext, max_depth: int = 15
    ) -> ElementListResult:
        """
        List a hierarchical accessibility element tree for the frontmost app.

        Returns an ElementListResult with elements and by_type to mirror Windows parity.

        Args:
            max_depth: Maximum recursion depth (default: 15, increased from 5 for complex UIs)

        Note: macOS only. Requires atomacos.
        """
        if not ACCESSIBILITY_AVAILABLE:
            return ElementListResult(success=False, error=ERROR_ATOMACOS_MISSING)

        group_id = generate_group_id("desktop_list_accessible_tree", str(max_depth))
        emit_info(
            "[bold white on blue] ACCESSIBILITY TREE [/bold white on blue] 🌲",
            message_group=group_id,
        )

        app = get_frontmost_app()
        if not app:
            return ElementListResult(success=False, error=ERROR_NO_FRONTMOST_APP)

        elements = _build_element_tree(app, max_depth=max_depth)
        by_type: dict[str, list[dict[str, Any]]] = {}
        for node in elements:
            t = node.get("type", "Unknown")
            by_type.setdefault(t, []).append(node)

        emit_info(
            f"[green]Tree contains {len(elements)} nodes across {len(by_type)} types[/green]",
            message_group=group_id,
        )

        # Build full result
        full_result = ElementListResult(
            success=True,
            elements=elements,
            by_type=by_type,
            types=list(by_type.keys()),
            total_elements=len(elements),
        )

        # Success-conditional compaction: Return filtered actionable elements
        if len(elements) > 0:
            compact_result = _compact_element_list_result(full_result)
            emit_info(
                f"[dim]💾 Compacted tree: {len(elements)} total → {compact_result.filtered_count} actionable elements[/dim]",
                message_group=group_id,
            )
            return compact_result

        # Empty tree - return as-is
        return full_result

    @agent.tool
    def desktop_find_accessible_element(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        identifier: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.6,
    ) -> ElementSearchResult:
        """
        Find UI element using macOS Accessibility API with PIXEL-PERFECT accuracy and FUZZY MATCHING.

        This is the most accurate way to locate UI elements on macOS!
        Now with intelligent fuzzy matching for flexible element finding.

        Args:
            role: Element role - common values:
                  - 'AXButton' - Buttons
                  - 'AXTextField' - Text input fields
                  - 'AXStaticText' - Text labels
                  - 'AXMenuItem' - Menu items
                  - 'AXCheckBox' - Checkboxes
                  - 'AXRadioButton' - Radio buttons
                  - 'AXPopUpButton' - Dropdown menus
                  - 'AXWindow' - Windows
            title: Element title/name (supports fuzzy matching!)
                   Examples:
                   - "Submit" matches: "Submit", "Submit Form", "submitBtn", "btn_submit"
                   - "Save" matches: "Save", "Save As...", "saveButton", "btn-save"
            identifier: AXIdentifier for exact matching (HIGHEST PRIORITY!)
                       Use this when elements don't have titles.
                       Examples:
                       - Calculator: identifier="Seven" for "7" button
                       - Calculator: identifier="Add" for "+" button
                       - Calculator: identifier="Equals" for "=" button
                       Tip: Check element tree output for identifier values!
            in_frontmost_app: Search only in active app (faster) vs system-wide
            fuzzy: Enable intelligent fuzzy matching (default: True)
            fuzzy_threshold: Minimum similarity score (0.0-1.0, default: 0.6)
                            Higher = stricter matching, Lower = more permissive

        Returns:
            ElementSearchResult with exact element position and properties
            - If found: center_x, center_y for pixel-perfect clicking!
            - Multiple matches returned if found, sorted by match quality

        Search Priority:
            1. Identifier (exact match) - MOST RELIABLE
            2. Title (exact match)
            3. Fuzzy match on title/description/placeholder

        Examples:
            - desktop_find_accessible_element(role="AXButton", title="Save")
            - desktop_find_accessible_element(title="Submit")  # Fuzzy matches "Submit Button", "submitBtn", etc.
            - desktop_find_accessible_element(role="AXButton", identifier="Seven")  # Calculator "7" button
            - desktop_find_accessible_element(identifier="AllClear")  # Calculator AC button
            - desktop_find_accessible_element(role="AXButton", title="close", fuzzy_threshold=0.8)  # Stricter matching
            - desktop_find_accessible_element(title="login", fuzzy=False)  # Exact match only

        Troubleshooting:
            - If title search fails, check element tree for identifier attribute
            - Some apps (Calculator, custom UIs) use identifiers instead of titles
            - Use desktop_list_accessible_elements() to inspect available attributes

        Note: macOS only. Requires atomacos library.
        """
        return find_accessible_element(
            role=role,
            title=title,
            identifier=identifier,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

    @agent.tool
    def desktop_list_accessible_elements(
        context: RunContext,
        role: str | None = None,
        in_frontmost_app: bool = True,
        _internal: bool = False,  # NEW: Skip compaction for debugging
    ) -> ElementListResult:
        """
        List all accessible UI elements in the frontmost app.

        Useful for discovering what elements are available and their roles.
        By default returns top 20 most relevant elements. Use _internal=True
        to get ALL elements (useful for debugging).

        Args:
            role: Optional role filter (e.g., 'AXButton' to list only buttons)
            in_frontmost_app: Search only in active app vs system-wide
            _internal: Skip compaction, return all elements (default: False)

        Returns:
            ElementListResult with elements (compacted by default, all if _internal=True)

        Examples:
            - desktop_list_accessible_elements()  # Top 20 relevant elements
            - desktop_list_accessible_elements(role="AXButton")  # Top 20 buttons
            - desktop_list_accessible_elements(_internal=True)  # ALL elements (debug)

        Note: macOS only. Requires atomacos library.
        """
        from .element_list import _compact_element_list_result

        result = list_accessible_elements(role=role, in_frontmost_app=in_frontmost_app)

        # Skip compaction if _internal or if it failed
        if _internal or not result.success:
            return result

        # Default: Return compacted
        return _compact_element_list_result(result, max_elements=20)

    @agent.tool
    def desktop_click_accessible_element(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        identifier: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.25,
    ) -> ElementClickResult:
        """
        Find and click a UI element using Accessibility API with FUZZY MATCHING (MOST ACCURATE!).

        This combines intelligent element finding and clicking in one step.
        Uses fuzzy matching to handle common UI element naming variations.
        Now supports identifier (AXIdentifier) for exact, reliable matching!

        Args:
            role: Element role (e.g., 'AXButton')
            title: Element title/name to search for (supports fuzzy matching!)
                   Examples: "Submit" matches "Submit Button", "submitBtn", "btn_submit"
                   Also searches: description, placeholder, help text, role_description
            identifier: AXIdentifier for exact match (HIGHEST PRIORITY!)
                       Use this when elements don't have titles.
                       Examples:
                       - Calculator: identifier="Seven" for "7" button
                       - Calculator: identifier="Add" for "+" button
                       - Calculator: identifier="Equals" for "=" button
                       Tip: Check element tree output for identifier values!
            in_frontmost_app: Search only in active app
            fuzzy: Enable intelligent fuzzy matching (default: True)
            fuzzy_threshold: Minimum similarity score (0.0-1.0, default: 0.25)

        Returns:
            ElementClickResult with success status and click coordinates

        Search Priority:
            1. Identifier (exact match) - MOST RELIABLE
            2. Title (exact match)
            3. Fuzzy match on title/description/placeholder

        Examples:
            - desktop_click_accessible_element(identifier="Seven")  # Calculator "7" button
            - desktop_click_accessible_element(identifier="AllClear")  # Calculator AC button
            - desktop_click_accessible_element(role="AXButton", title="Save")
            - desktop_click_accessible_element(title="Submit")  # Fuzzy matches variations
            - desktop_click_accessible_element(title="Search")  # Matches placeholder text!

        Troubleshooting:
            - If title search fails, check element tree for identifier attribute
            - Some apps (Calculator, custom UIs) use identifiers instead of titles
            - Use desktop_list_accessible_elements() to inspect available attributes

        Note: macOS only. Uses native AX Press action or mouse click.
        """
        # Find the element with fuzzy matching
        result = find_accessible_element(
            role=role,
            title=title,
            identifier=identifier,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        if not result.success or not result.found:
            return ElementClickResult(
                success=False, error=result.error or "Element not found"
            )

        best_match = result.best_match
        if not best_match:
            return ElementClickResult(success=False, error="No element found")

        # We need to re-find the element to get the raw atomacos reference
        # (since we can't serialize it in Pydantic models)
        # This is a bit inefficient but necessary for the architecture
        group_id = generate_group_id("desktop_click_accessible", f"{role}_{title}")

        try:
            app = get_frontmost_app()
            if not app:
                return ElementClickResult(success=False, error=ERROR_NO_FRONTMOST_APP)

            search_criteria = {}
            if role:
                search_criteria["AXRole"] = role
            if title:
                search_criteria["AXTitle"] = title

            if search_criteria:
                matches = app.findAllR(**search_criteria)
            else:
                matches = []

            if matches:
                element_ref = matches[0]
                # Try native Press action first
                try:
                    element_ref.Press()
                    emit_info(
                        f"[green]Pressed '{best_match.title}' using native AX Press[/green]",
                        message_group=group_id,
                    )
                    return ElementClickResult(
                        success=True,
                        clicked=True,
                        method="ax_press",
                        element=best_match.title,
                        role=best_match.role,
                    )
                except Exception:
                    pass  # Fall through to mouse click

        except Exception:
            pass  # Fall through to mouse click

        # Fallback: Click at element center using native API (multi-monitor safe)
        if best_match.center_x is None or best_match.center_y is None:
            return ElementClickResult(
                success=False, error="Could not determine element position"
            )

        try:
            from ..platform import click_mouse_native

            success, error = click_mouse_native(
                x=best_match.center_x, y=best_match.center_y, button="left", clicks=1
            )

            if not success:
                return ElementClickResult(
                    success=False, error=f"Native click failed: {error}"
                )

            emit_info(
                f"[green]Clicked '{best_match.title}' at ({best_match.center_x}, {best_match.center_y})[/green]",
                message_group=group_id,
            )

            return ElementClickResult(
                success=True,
                clicked=True,
                method="native_click",
                element=best_match.title,
                role=best_match.role,
                x=best_match.center_x,
                y=best_match.center_y,
            )
        except Exception as e:
            return ElementClickResult(success=False, error=f"Click failed: {str(e)}")

    @agent.tool
    def desktop_get_accessible_element_value(
        context: RunContext,
        role: str | None = None,
        title: str | None = None,
        in_frontmost_app: bool = True,
        fuzzy: bool = True,
        fuzzy_threshold: float = 0.65,
    ) -> ElementSearchResult:
        """
        Get the AXValue (text/value) of an accessible element using fuzzy matching.

        Use cases:
        - Verify-before-type: confirm target is a text field (AXTextField)
        - Verify-after-type: read AXValue to confirm entered text

        Args:
            role: Element role (e.g., 'AXTextField')
            title: Element title/name (supports fuzzy matching)
            in_frontmost_app: Search only in active app vs system-wide
            fuzzy: Enable fuzzy matching on title/description/value
            fuzzy_threshold: Minimum similarity score (default 0.6)

        Returns:
            ElementSearchResult where best_match.value is populated if available
        """
        result = find_accessible_element(
            role=role,
            title=title,
            in_frontmost_app=in_frontmost_app,
            fuzzy=fuzzy,
            fuzzy_threshold=fuzzy_threshold,
        )

        # Populate value field by re-querying AXValue when possible
        try:
            if (
                result.success
                and result.found
                and result.best_match
                and ACCESSIBILITY_AVAILABLE
            ):
                app = get_frontmost_app()
                if app:
                    # Try exact match first
                    search_criteria = {}
                    if role:
                        search_criteria["AXRole"] = role
                    if title:
                        search_criteria["AXTitle"] = title
                    matches = app.findAllR(**search_criteria) if search_criteria else []
                    if matches:
                        elem = matches[0]
                        ax_value = getattr(elem, "AXValue", None)
                        if ax_value is not None:
                            result.best_match.value = str(ax_value)
            return result
        except Exception:
            return result

    @agent.tool
    def desktop_show_performance_summary(context: RunContext) -> dict[str, Any]:
        """
        Display GUI automation performance metrics.

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
