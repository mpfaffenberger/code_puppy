"""Accessibility element listing and tree building."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any

from code_puppy.messaging import emit_error, emit_info
from code_puppy.tools.common import generate_group_id

from ..constants import ERROR_ATOMACOS_MISSING, ERROR_NO_FRONTMOST_APP
from ..core.element_scoring import calculate_element_relevance
from ..performance_monitor import get_monitor
from ..result_types import CompactSummary, ElementListResult
from .element_finder import get_frontmost_app

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


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def _estimate_result_tokens(obj: dict | list | str) -> int:
    """Estimate tokens in a serialized object."""
    if isinstance(obj, str):
        return _estimate_tokens(obj)
    try:
        serialized = json.dumps(obj)
        return _estimate_tokens(serialized)
    except Exception:
        return 100  # Fallback estimate


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

        # Group by role AND build flat element list for compaction
        by_role = {}
        elements_list = []  # Flat list for compaction

        for elem in elements:
            try:
                elem_role = getattr(elem, "AXRole", "Unknown")
                elem_title = getattr(elem, "AXTitle", None)
                elem_description = getattr(elem, "AXDescription", None)
                elem_position = getattr(elem, "AXPosition", None)
                elem_size = getattr(elem, "AXSize", None)

                # Build element dict for flat list (needed for compaction)
                elem_dict = {
                    "role": elem_role,
                    "title": elem_title,
                    "description": elem_description,
                    # NEW: Comprehensive attributes
                    "value": getattr(elem, "AXValue", None),
                    "placeholder": getattr(elem, "AXPlaceholderValue", None),
                    "help": getattr(elem, "AXHelp", None),
                    "role_description": getattr(elem, "AXRoleDescription", None),
                    "identifier": getattr(elem, "AXIdentifier", None),
                    "subrole": getattr(elem, "AXSubrole", None),
                }

                # Add position/coordinates if available
                if elem_position and elem_size:
                    x = int(elem_position[0])
                    y = int(elem_position[1])
                    width = int(elem_size[0])
                    height = int(elem_size[1])
                    elem_dict["x"] = x
                    elem_dict["y"] = y
                    elem_dict["width"] = width
                    elem_dict["height"] = height
                    elem_dict["center_x"] = x + width // 2
                    elem_dict["center_y"] = y + height // 2

                elements_list.append(elem_dict)

                # Also group by role for by_role dict
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
            elements=elements_list,  # CRITICAL FIX: Add flat list for compaction!
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
    - Elements with meaningful text in ANY attribute
    - Common UI patterns (submit, login, search, etc.)

    Comprehensive fallback chain for text:
    title → description → placeholder → help → role_description
    """
    role = elem.get("role") or elem.get("type") or elem.get("control_type") or ""

    # Try multiple text sources in priority order
    title = (elem.get("title") or "").lower().strip()

    # CRITICAL FIX: Comprehensive fallback chain
    # Many macOS apps put labels in description, placeholder, or help text!
    if not title:
        title = (elem.get("description") or "").lower().strip()
    if not title:
        title = (elem.get("placeholder") or "").lower().strip()
    if not title:
        title = (elem.get("help") or "").lower().strip()
    if not title:
        title = (elem.get("role_description") or "").lower().strip()

    return calculate_element_relevance(role, title)


def _compact_element_list_result(
    full_result: ElementListResult,
    max_elements: int = 20,
    include_static_text: bool = True,
) -> ElementListResult:
    """
    Compress element list to most relevant elements with structured summary.

    Strategy:
    - Filter to interactive elements (buttons, fields, menus) - HIGH PRIORITY
    - Include important static elements (labels, headings, alerts) - MEDIUM PRIORITY
    - Calculate relevance score with fuzzy matching on common actions
    - Sort by relevance (most relevant first)
    - Limit to top N most relevant elements (default: 20)
    - Generate structured CompactSummary with metrics

    Args:
        full_result: Full element list with all elements
        max_elements: Maximum elements to return (default: 20)
        include_static_text: Include important static text elements (default: True)

    Returns:
        Compact result with filtered, sorted elements and structured summary
    """
    if not full_result.success or not full_result.elements:
        # Failure or empty - return as-is for debugging
        return full_result

    # PRIORITY 1: Interactive/actionable element types
    interactive_roles = {
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

    # PRIORITY 2: Important static elements (for validation/verification)
    informational_roles = {
        "AXStaticText",
        "AXHeading",
        "AXAlert",
        "AXLabel",
        "Text",
        "Heading",
        "Alert",
        "Label",  # Windows equivalents
    }

    # Filter and score all elements
    scored_elements = []
    for elem in full_result.elements:
        role = elem.get("role") or elem.get("type") or elem.get("control_type")

        relevance_multiplier = 1.0
        if role in interactive_roles:
            relevance_multiplier = 1.0  # Full weight for interactive
        elif include_static_text and role in informational_roles:
            relevance_multiplier = 0.5  # Half weight for static text
        else:
            continue  # Skip other element types

        # Calculate base relevance
        relevance = _calculate_element_relevance(elem) * relevance_multiplier

        # Compact element structure - keep only essential fields
        compact_elem = {
            "role": role,
            "title": elem.get("title")
            or elem.get("description"),  # Use description as fallback
            "x": elem.get("center_x") or elem.get("x"),
            "y": elem.get("center_x") or elem.get("y"),
            "relevance": round(relevance, 2),
        }
        # Add automation_id if available (Windows)
        if "auto_id" in elem:
            compact_elem["auto_id"] = elem["auto_id"]
        # Add description if different from title (for debugging)
        if elem.get("description") and elem.get("description") != elem.get("title"):
            compact_elem["description"] = elem.get("description")

        scored_elements.append((relevance, compact_elem))

    # Sort by relevance (highest first) and limit to top N
    scored_elements.sort(reverse=True, key=lambda x: x[0])
    actionable = [elem for _score, elem in scored_elements[:max_elements]]

    # Extract unique roles and counts
    unique_roles = list(set(elem["role"] for elem in actionable if elem["role"]))
    role_counts = {}
    for elem in actionable:
        role = elem["role"]
        role_counts[role] = role_counts.get(role, 0) + 1

    # Count element types
    interactive_count = sum(1 for e in actionable if e["role"] in interactive_roles)
    static_count = sum(1 for e in actionable if e["role"] in informational_roles)

    # Estimate token savings
    full_tokens = _estimate_result_tokens(full_result.elements)
    compact_tokens = _estimate_result_tokens(actionable)

    # Generate structured summary
    summary = CompactSummary(
        tool="accessibility_tree",
        success=True,
        timestamp=datetime.now().isoformat(),
        found_count=full_result.total_elements,
        returned_count=len(actionable),
        filtered_count=full_result.total_elements - len(actionable),
        one_line=f"Found {len(actionable)} relevant elements ({interactive_count} interactive, {static_count} informational)",
        top_items=[
            e.get("title") or "(no title)" for e in actionable[:5] if e.get("title")
        ],
        compaction_ratio=len(actionable) / full_result.total_elements
        if full_result.total_elements > 0
        else 0,
        estimated_tokens_full=full_tokens,
        estimated_tokens_compact=compact_tokens,
        tokens_saved=full_tokens - compact_tokens,
        filters_applied=[
            "interactive roles (buttons, fields, menus)",
            "informational roles (labels, headings, alerts)"
            if include_static_text
            else None,
            "relevance scored",
            f"top {max_elements} elements",
        ],
        thresholds={
            "max_elements": max_elements,
            "include_static_text": include_static_text,
        },
        element_types=dict(
            sorted(role_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        ),
        detail_hint="Use _internal=True to get all {} elements".format(
            full_result.total_elements
        ),
        full_data_available=True,
        progressive_hints=[
            "Elements include x,y coordinates for clicking",
            "Static text elements included for validation"
            if include_static_text
            else "Only interactive elements included",
            "If target element not found, try _internal=True",
        ],
        extra={"interactive_count": interactive_count, "static_count": static_count},
    )

    return ElementListResult(
        success=True,
        total_elements=full_result.total_elements,
        filtered_count=len(actionable),
        summary=summary.model_dump(),
        elements=actionable,
        roles=unique_roles,
        types=unique_roles,  # For compatibility
        # Explicitly exclude verbose fields
        by_role=None,
        by_type=None,
    )
