"""Accessibility element listing and tree building."""

from __future__ import annotations

import sys
from typing import Any

if sys.platform != "darwin":
    ACCESSIBILITY_AVAILABLE = False
    atomacos = None
else:
    try:
        import atomacos

        ACCESSIBILITY_AVAILABLE = True
    except ImportError:
        ACCESSIBILITY_AVAILABLE = False
        atomacos = None

from code_puppy.messaging import emit_error, emit_info

from ..core.element_scoring import calculate_element_relevance
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_ATOMACOS_MISSING, ERROR_NO_FRONTMOST_APP
from ..performance_monitor import get_monitor
from ..result_types import ElementListResult
from .element_finder import get_frontmost_app


def list_accessible_elements(
    role: str | None = None, in_frontmost_app: bool = True
) -> ElementListResult:
    """
    List all accessible UI elements, optionally filtered by role.

    Args:
        role: Optional role filter (e.g., 'AXButton', 'AXTextField')
        in_frontmost_app: Search only in frontmost app (True) or system-wide (False)

    Returns:
        ElementListResult with list of elements
    """
    if not ACCESSIBILITY_AVAILABLE:
        return ElementListResult(success=False, error=ERROR_ATOMACOS_MISSING)

    group_id = generate_group_id("list_accessible_elements", str(role))
    emit_info(
        f"[bold white on blue] LIST ACCESSIBLE ELEMENTS [/bold white on blue] 📋 role={role}",
        message_group=group_id,
    )

    try:
        app = get_frontmost_app()
        if not app:
            return ElementListResult(success=False, error=ERROR_NO_FRONTMOST_APP)

        # Find elements
        if role:
            elements = app.findAllR(AXRole=role)
        else:
            elements = app.findAllR()

        # Group by role
        by_role = {}
        for elem in elements:
            try:
                elem_role = getattr(elem, "AXRole", "Unknown")
                elem_title = getattr(elem, "AXTitle", None)
                elem_description = getattr(elem, "AXDescription", None)

                if elem_role not in by_role:
                    by_role[elem_role] = []

                by_role[elem_role].append(
                    {"title": elem_title, "description": elem_description}
                )
            except Exception:
                continue

        emit_info(
            f"[green]Found {len(elements)} elements across {len(by_role)} roles[/green]",
            message_group=group_id,
        )

        for role_name, elems in sorted(by_role.items()):
            emit_info(f"  {role_name}: {len(elems)} elements", message_group=group_id)

        return ElementListResult(
            success=True,
            total_elements=len(elements),
            by_role=by_role,
            roles=list(by_role.keys()),
        )

    except Exception as e:
        emit_error(
            f"[red]Failed to list elements: {str(e)}[/red]", message_group=group_id
        )
        return ElementListResult(success=False, error=str(e))


def _build_element_tree(app_ref, max_depth: int = 5) -> list[dict[str, Any]]:
    """Traverse the accessibility tree for the frontmost app and build a list of nodes.

    OPTIMIZED: Now includes performance monitoring.

    Each node contains: type(role), title, description, depth. This mirrors Windows parity.
    """
    monitor = get_monitor()
    nodes: list[dict[str, Any]] = []

    def safe_children(elem):
        try:
            return elem.AXChildren
        except Exception:
            return []

    def traverse(elem, depth=0):
        if depth > max_depth:
            return
        try:
            role = getattr(elem, "AXRole", None) or "Unknown"
            title = getattr(elem, "AXTitle", None)
            description = getattr(elem, "AXDescription", None)
            nodes.append(
                {
                    "type": role,
                    "name": title,
                    "description": description,
                    "depth": depth,
                }
            )
            for child in safe_children(elem):
                traverse(child, depth + 1)
        except Exception:
            return

    try:
        with monitor.measure("build_element_tree"):
            root = app_ref.AXFocusedWindow or app_ref
            traverse(root, 0)
    except Exception:
        pass

    return nodes


def _list_macos_windows(include_minimized: bool = False) -> list[dict[str, Any]]:
    """List windows on macOS using Quartz APIs and NSWorkspace.

    Args:
        include_minimized: If True, include minimized windows with minimized=True flag

    Returns:
        List of window dicts with owner, title, bounds, and minimized status
    """
    try:
        from AppKit import NSWorkspace
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGWindowListOptionOnScreenOnly,
            kCGWindowListOptionAll,
            kCGNullWindowID,
        )  # type: ignore
    except Exception:
        return []

    # Get window list (on-screen or all based on flag)
    option = (
        kCGWindowListOptionAll if include_minimized else kCGWindowListOptionOnScreenOnly
    )
    windows = CGWindowListCopyWindowInfo(option, kCGNullWindowID) or []

    # Get running apps to check minimized state
    workspace = NSWorkspace.sharedWorkspace()
    running_apps = workspace.runningApplications()
    app_states = {}

    for app in running_apps:
        app_name = app.localizedName()
        # Check if app is hidden (minimized to dock)
        app_states[app_name] = {
            "hidden": app.isHidden(),
            "pid": app.processIdentifier(),
        }

    out: list[dict[str, Any]] = []
    for win in windows:
        try:
            layer = win.get("kCGWindowLayer", 0)
            if layer != 0:
                continue  # Skip non-app windows (status bar, etc.)

            owner = win.get("kCGWindowOwnerName")
            title = win.get("kCGWindowName")
            bounds = win.get("kCGWindowBounds", {})
            alpha = win.get("kCGWindowAlpha", 1.0)

            # Determine if window is minimized
            minimized = False
            if owner and owner in app_states:
                # Window is minimized if app is hidden OR window has 0 alpha
                minimized = app_states[owner]["hidden"] or alpha == 0

            # Skip minimized windows unless requested
            if minimized and not include_minimized:
                continue

            # Convert bounds to plain dict for JSON serialization
            bounds_dict = {
                "x": int(bounds.get("X", 0)),
                "y": int(bounds.get("Y", 0)),
                "width": int(bounds.get("Width", 0)),
                "height": int(bounds.get("Height", 0)),
            }

            out.append(
                {
                    "owner": owner,
                    "title": title,
                    "bounds": bounds_dict,
                    "minimized": minimized,
                }
            )
        except Exception:
            continue
    return out


def _calculate_element_relevance(elem: dict) -> float:
    """
    Calculate relevance score for an element (0.0 - 1.0).

    Uses extracted pure logic for element scoring.

    Prioritizes:
    - Interactive elements (buttons, fields)
    - Elements with meaningful titles
    - Common UI patterns (submit, login, search, etc.)
    """
    role = elem.get("role") or elem.get("type") or elem.get("control_type") or ""
    title = (elem.get("title") or "").lower().strip()
    return calculate_element_relevance(role, title)


def _compact_element_list_result(
    full_result: ElementListResult, max_elements: int = 20
) -> ElementListResult:
    """
    Compress element list to most relevant actionable elements.

    Strategy:
    - Filter to interactive/actionable elements (buttons, fields, menus)
    - Calculate relevance score with fuzzy matching on common actions
    - Sort by relevance (most relevant first)
    - Limit to top N most relevant elements (default: 20)
    - Generate summary

    Args:
        full_result: Full element list with all elements
        max_elements: Maximum elements to return (default: 20)

    Returns:
        Compact result with filtered, sorted actionable elements only
    """
    if not full_result.success or not full_result.elements:
        # Failure or empty - return as-is for debugging
        return full_result

    # Define actionable element types
    actionable_roles = {
        "AXButton",
        "AXTextField",
        "AXSearchField",
        "AXTextArea",
        "AXMenuItem",
        "AXCheckBox",
        "AXRadioButton",
        "AXPopUpButton",
        "AXComboBox",
        "AXIncrementor",
        "AXSlider",
        "AXLink",
        # Windows equivalents
        "Button",
        "Edit",
        "ComboBox",
        "ListItem",
        "MenuItem",
        "CheckBox",
        "RadioButton",
        "Hyperlink",
        "Document",
    }

    # Filter to actionable elements and calculate relevance
    actionable_with_scores = []
    for elem in full_result.elements:
        role = elem.get("role") or elem.get("type") or elem.get("control_type")
        if role in actionable_roles:
            # Calculate relevance score
            relevance = _calculate_element_relevance(elem)

            # Compact element structure - keep only essential fields
            compact_elem = {
                "role": role,
                "title": elem.get("title"),
                "x": elem.get("center_x") or elem.get("x"),
                "y": elem.get("center_y") or elem.get("y"),
                "relevance": round(relevance, 2),  # For debugging
            }
            # Add automation_id if available (Windows)
            if "auto_id" in elem:
                compact_elem["auto_id"] = elem["auto_id"]

            actionable_with_scores.append((relevance, compact_elem))

    # Sort by relevance (highest first) and limit to top N
    actionable_with_scores.sort(reverse=True, key=lambda x: x[0])
    actionable = [elem for _score, elem in actionable_with_scores[:max_elements]]

    # Extract unique roles
    unique_roles = list(set(elem["role"] for elem in actionable if elem["role"]))

    # Generate summary
    role_counts = {}
    for elem in actionable:
        role = elem["role"]
        role_counts[role] = role_counts.get(role, 0) + 1

    summary_parts = [
        f"{count} {role}(s)" for role, count in sorted(role_counts.items())[:5]
    ]
    summary = f"Found {len(actionable)} actionable elements: " + ", ".join(
        summary_parts
    )

    return ElementListResult(
        success=True,
        total_elements=full_result.total_elements,
        filtered_count=len(actionable),
        summary=summary,
        elements=actionable,
        roles=unique_roles,
        types=unique_roles,  # For compatibility
        # Explicitly exclude verbose fields
        by_role=None,
        by_type=None,
    )
